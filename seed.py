"""Demo data: 1 manager, 5 staff, 8 tenants and ~70 historical requests so the
analytics dashboard has something to show.

    python seed.py            # seeds only if the database has no users
    python seed.py --reset    # wipes the database first

Demo logins (also shown on the login page):
    manager@demo.com  / Manager@123
    plumber@demo.com  / Staff@1234      (and electrician@, hvac@, appliance@, general@)
    tenant1@demo.com  / Tenant@123      (tenant1 ... tenant8)
"""

import random
import sys
from datetime import timedelta

from constants import SLA_HOURS
from database import connect, init_db
from ml.generate_dataset import make_request
from ml.predictor import predict_urgency
from services import auth_service
from services.assignment_service import add_history
from utils import to_iso, utcnow

DEMO_ACCOUNTS = {
    "manager": ("manager@demo.com", "Manager@123"),
    "staff": ("plumber@demo.com", "Staff@1234"),
    "tenant": ("tenant1@demo.com", "Tenant@123"),
}

STAFF = [
    ("Ravi Kumar", "plumber@demo.com", "Plumbing"),
    ("Suresh Babu", "electrician@demo.com", "Electrical"),
    ("Anil Reddy", "hvac@demo.com", "HVAC"),
    ("Meena Iyer", "appliance@demo.com", "Appliance"),
    ("Farhan Sheikh", "general@demo.com", "General"),
]
TENANTS = [
    ("Priya Sharma", "A-101"), ("Rahul Verma", "A-204"), ("Sneha Nair", "B-302"),
    ("Arjun Das", "B-105"), ("Kavya Menon", "C-210"), ("Imran Khan", "C-007"),
    ("Divya Rao", "D-401"), ("Karthik S", "D-118"),
]
# Which staff member typically handles each category in the demo data.
CATEGORY_TO_STAFF = {
    "Plumbing": "plumber@demo.com", "Electrical": "electrician@demo.com",
    "HVAC": "hvac@demo.com", "Appliance": "appliance@demo.com",
    "Structural": "general@demo.com", "Pest Control": "general@demo.com",
    "Security": "general@demo.com", "General": "general@demo.com",
}
# (min, max) hours a request of that urgency typically takes to resolve.
RESOLUTION_RANGE = {"Critical": (1, 3.5), "High": (4, 20), "Medium": (12, 60), "Low": (24, 140)}


def _specialty_for(email):
    return next(s for _, e, s in STAFF if e == email)


def seed(db_path, history=70, rng_seed=7):
    init_db(db_path)
    db = connect(db_path)
    try:
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return False
        rng = random.Random(rng_seed)

        auth_service.create_user_direct(db, "Anita Desai", "manager@demo.com",
                                        "Manager@123", "manager", phone="9876500000")
        staff_ids = {}
        for name, email, specialty in STAFF:
            staff_ids[email] = auth_service.create_user_direct(
                db, name, email, "Staff@1234", "staff", phone="98765%05d" % rng.randint(0, 99999),
                specialty=specialty)
        tenants = []
        for i, (name, unit) in enumerate(TENANTS, start=1):
            uid = auth_service.create_user_direct(
                db, name, f"tenant{i}@demo.com", "Tenant@123", "tenant",
                phone="98450%05d" % rng.randint(0, 99999), unit=unit)
            tenants.append((uid, unit))

        now = utcnow()
        for i in range(history):
            category, _urg, title, body = make_request(rng, curated_only=True)
            prediction = predict_urgency(category, title, body)
            urgency = prediction["label"]
            sla = SLA_HOURS[urgency]
            tenant_id, unit = rng.choice(tenants)
            is_waiting = i >= history - 3          # last three: still waiting for assignment
            age_h = rng.uniform(0.2, 1.5) if is_waiting else rng.uniform(2, 24 * 30)
            created = now - timedelta(hours=age_h)
            assigned_to = None if is_waiting else staff_ids[CATEGORY_TO_STAFF[category]]

            status, assigned_at, started_at, resolved_at, notes = "Open", None, None, None, None
            if not is_waiting:
                assigned_at = created + timedelta(minutes=rng.randint(1, 15))
                roll = rng.random()
                lo, hi = RESOLUTION_RANGE[urgency]
                res_h = rng.uniform(lo, hi)
                # Occasionally a request overruns its SLA, so compliance is not 100 %.
                if rng.random() < 0.12:
                    res_h = sla * rng.uniform(1.1, 1.8)
                finished = created + timedelta(hours=res_h)
                keep_open = age_h < 72 and roll < 0.55
                if finished < now and not keep_open:
                    status = "Resolved"
                    started_at = assigned_at + (finished - assigned_at) * rng.uniform(0.1, 0.5)
                    resolved_at = finished
                    notes = rng.choice(["Issue fixed and tested", "Replaced faulty part",
                                        "Repaired on site, tenant confirmed",
                                        "Cleared and cleaned, working normally"])
                elif roll < 0.6:
                    status = "In Progress"
                    started_at = assigned_at + timedelta(minutes=rng.randint(10, 180))
                    if started_at > now:
                        started_at = now
                else:
                    status = "Assigned"

            created_s = to_iso(created)
            cur = db.execute(
                "INSERT INTO requests (tenant_id, title, description, category, unit, urgency,"
                " predicted_urgency, confidence, urgency_source, status, assigned_to, sla_hours,"
                " created_at, due_at, assigned_at, started_at, resolved_at, resolution_notes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tenant_id, title, body, category, unit, urgency, urgency,
                 prediction["confidence"], prediction["source"], status, assigned_to, sla,
                 created_s, to_iso(created + timedelta(hours=sla)),
                 to_iso(assigned_at) if assigned_at else None,
                 to_iso(started_at) if started_at else None,
                 to_iso(resolved_at) if resolved_at else None, notes),
            )
            rid = cur.lastrowid
            _history(db, rid, tenant_id, created, assigned_at, started_at, resolved_at,
                     status, urgency, prediction, notes, assigned_to)
        db.commit()
        return True
    finally:
        db.close()


def _history(db, rid, tenant_id, created, assigned_at, started_at, resolved_at, status,
             urgency, prediction, notes, assigned_to):
    def add(st, note, actor, when):
        db.execute(
            "INSERT INTO status_history (request_id, status, note, actor_id, created_at)"
            " VALUES (?, ?, ?, ?, ?)", (rid, st, note, actor, to_iso(when)))

    add("Open", f"Request submitted. Predicted urgency: {urgency} "
        f"({round(prediction['confidence'] * 100)}% confidence, {prediction['source']})",
        tenant_id, created)
    if assigned_at:
        name = db.execute("SELECT name FROM users WHERE id = ?", (assigned_to,)).fetchone()[0]
        add("Assigned", f"Auto-assigned to {name} (specialty match)", None, assigned_at)
    if started_at:
        add("In Progress", "Work started", assigned_to, started_at)
    if resolved_at:
        add("Resolved", notes, assigned_to, resolved_at)


if __name__ == "__main__":
    import os
    from pathlib import Path

    path = Path(__file__).resolve().parent / "instance" / "maintenance.db"
    path.parent.mkdir(exist_ok=True)
    if "--reset" in sys.argv and path.exists():
        os.remove(path)
    print("Seeded demo data." if seed(str(path)) else "Database already has users; skipped.")
