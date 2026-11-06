# MaintainIQ - Property Maintenance Request Management System

Problem #39: tenants submit maintenance requests, a machine-learning model predicts
urgency, requests are assigned to maintenance staff automatically, progress is tracked
against SLA timelines, and property managers get performance analytics.

**Stack:** Python 3 + Flask (REST API) - SQLite (database) - scikit-learn (urgency model) -
plain HTML / CSS / JavaScript (no build step, no internet needed at run time).

## 1. Run it (5 steps)

```bash
cd maintenance_system
python -m venv .venv
.venv\Scripts\activate          # Windows      (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. On first start the app trains the model (a few seconds),
creates `instance/maintenance.db` and loads demo data. To reset the demo data, stop the
server, delete `instance/maintenance.db`, and start again.

| Role    | Email                | Password     |
|---------|----------------------|--------------|
| Manager | manager@demo.com     | Manager@123  |
| Staff (plumber) | plumber@demo.com | Staff@1234 |
| Other staff | electrician@demo.com, hvac@demo.com, appliance@demo.com, general@demo.com | Staff@1234 |
| Tenant  | tenant1@demo.com ... tenant8@demo.com | Tenant@123 |

New tenants can sign up on the login page. Staff accounts are created by the manager
(Manager > Staff tab). The login page has one-click demo buttons.

## 2. Run the tests

```bash
python -m unittest discover -s tests -v      # 29 tests: auth, roles, workflow, assignment, analytics, ML, seed
python -m ml.train_model                      # retrain + print hold-out metrics
python -m ml.evaluate                         # check the model on hand-written, unseen sentences
```

## 3. Mapping to the assignment

| Module (from the flowchart)       | Where it lives                                   |
|-----------------------------------|--------------------------------------------------|
| Authentication & Role Management  | `services/auth_service.py`, `routes/api.py` (`require_role`) |
| Request Submission Service        | `services/request_service.py` (`create_request`) + tenant portal |
| Urgency Prediction Engine         | `ml/` (`predictor.py`, `train_model.py`, `generate_dataset.py`) |
| Assignment Workflow               | `services/assignment_service.py` + status workflow in `request_service.py` |
| Analytics Dashboard               | `services/analytics_service.py` + manager dashboard |

Objectives -> features: submit requests (tenant portal) - predict urgency (ML, live preview
while typing) - assign automatically (specialty match + lowest weighted workload) - track
status and timelines (Open -> Assigned -> In Progress -> Resolved, SLA due times, full
history) - manager analytics (KPIs, charts, staff performance table).

## 4. How the main parts work

**Urgency prediction (hybrid).**
1. *Safety rules*: regular expressions catch life-safety phrases (gas leak, sparks, flooding,
   exposed wires, smoke, burst pipe...) and force **Critical**.
2. *Model*: TF-IDF (word 1-2 grams) + Logistic Regression over category + title + description,
   predicting Low / Medium / High / Critical with probabilities.
3. *Low confidence*: if the top probability is below 0.45 the request defaults to **Medium**
   and the manager can correct it (corrections are tracked as "manager overrides").

SLA targets: Critical 4 h - High 24 h - Medium 72 h - Low 168 h.

**Dataset.** Synthetic, as the assignment specifies: 4,000 requests generated from curated
phrases plus "component x severity cue" combinations, with 4 % deliberate label noise
(`python -m ml.generate_dataset`, saved to `ml/maintenance_requests.csv`).

**Assignment.** Active staff only; prefer matching specialty, else a "General" technician,
else anyone. Choose the lowest weighted workload (Critical 4, High 3, Medium 2, Low 1 over
active jobs). Requests that cannot be assigned stay *Open* and are assigned automatically
when a technician is added, or via the manager's "Auto-assign" button.

**Status workflow.** Staff: Assigned -> In Progress -> Resolved (resolution note required).
Manager: same plus re-open, re-assign, urgency override. Invalid jumps are rejected by the API.

**Security.** Passwords hashed (werkzeug), server-side role checks on every endpoint,
tenants/staff can only open their own requests (404 otherwise), parameterised SQL,
output escaped in the browser (XSS-safe), JSON-only mutating requests + SameSite cookies
(CSRF), HttpOnly session cookie, security headers.

## 5. Honest notes about the ML results (be ready for this question)

* Hold-out accuracy is about **96-98 %**, but the test split comes from the *same synthetic
  generator* as the training data, so this number is optimistic.
* On 32 hand-written sentences with wording the generator never uses, the full engine
  (rules + model) scores about **81 %**, and mistakes are one level off. That is the more
  realistic figure; real tenant text would need real labelled data to improve it.
* Metrics from the last training run are in `ml/metrics.json` (confusion matrix included).

## 6. Project structure

```
app.py                 Flask app factory, page routes, error handling
database.py            SQLite schema + connection helpers (3 tables)
seed.py                Demo users and ~70 historical requests
constants.py utils.py errors.py
routes/api.py          REST endpoints (/api/...)
services/              auth, request + workflow, assignment, analytics
ml/                    dataset generator, training, predictor, evaluation
templates/ static/     HTML pages, CSS, JavaScript
tests/test_app.py      unittest suite
```

Database tables: `users` (tenant/staff/manager), `requests`, `status_history`.

## 7. API summary

| Method & path | Who | Purpose |
|---|---|---|
| POST `/api/auth/register` `/login` `/logout`, GET `/api/auth/me` | all | accounts |
| POST `/api/predict` | tenant, manager | live urgency preview |
| POST `/api/requests` | tenant | submit (auto-predict + auto-assign) |
| GET `/api/requests` (filters: status, urgency, category, q, sort) | all (scoped by role) | list |
| GET `/api/requests/<id>` | owner / assignee / manager | detail + timeline |
| PATCH `/api/requests/<id>/status` | staff, manager | move through workflow |
| POST `/api/requests/<id>/assign`, PATCH `/api/requests/<id>/urgency` | manager | reassign / override |
| POST `/api/requests/auto-assign` | manager | assign all waiting requests |
| GET/POST `/api/staff` | manager | list / add technicians |
| GET `/api/analytics` | manager | KPIs, charts, staff performance |

## 8. Known limitations (good "future work" points)

SQLite and the built-in Flask server are meant for development/demo use (use PostgreSQL +
gunicorn in production); no email/SMS notifications; no photo attachments; no login rate
limiting or password reset; the urgency model is trained on synthetic text only.
