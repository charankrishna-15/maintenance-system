"""Request Submission Service + status workflow engine."""

from constants import (
    CATEGORIES, MANAGER_TRANSITIONS, SLA_HOURS, STAFF_TRANSITIONS, STATUSES, URGENCIES,
)
from errors import ApiError
from ml.predictor import predict_urgency
from services import assignment_service
from services.assignment_service import add_history
from utils import add_hours_iso, hours_between, now_iso

BASE_SELECT = """
SELECT r.*, t.name AS tenant_name, t.phone AS tenant_phone,
       s.name AS staff_name, s.specialty AS staff_specialty
FROM requests r
JOIN users t ON t.id = r.tenant_id
LEFT JOIN users s ON s.id = r.assigned_to
"""

URGENCY_ORDER = (
    "CASE r.urgency WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 "
    "WHEN 'Medium' THEN 2 ELSE 3 END"
)


def serialize(row):
    d = dict(row)
    now = now_iso()
    resolved = d["status"] == "Resolved"
    d["overdue"] = (not resolved) and now > d["due_at"]
    d["resolved_late"] = bool(resolved and d["resolved_at"] and d["resolved_at"] > d["due_at"])
    d["resolution_hours"] = (
        round(hours_between(d["created_at"], d["resolved_at"]), 2)
        if resolved and d["resolved_at"] else None
    )
    return d


def _validate_new(data):
    def text(key, label, lo, hi):
        value = data.get(key)
        value = value.strip() if isinstance(value, str) else ""
        if len(value) < lo or len(value) > hi:
            raise ApiError(f"{label} must be {lo}-{hi} characters")
        return value

    title = text("title", "Title", 3, 100)
    description = text("description", "Description", 10, 1000)
    category = data.get("category")
    if category not in CATEGORIES:
        raise ApiError("Choose a valid category")
    return title, description, category


def preview_urgency(data):
    category = data.get("category")
    if category not in CATEGORIES:
        raise ApiError("Choose a valid category")
    title = (data.get("title") or "").strip() if isinstance(data.get("title"), str) else ""
    description = data.get("description")
    description = description.strip() if isinstance(description, str) else ""
    if len(title) + len(description) < 5:
        raise ApiError("Enter more text to predict urgency")
    result = predict_urgency(category, title, description[:1000])
    result["sla_hours"] = SLA_HOURS[result["label"]]
    return result


def create_request(db, tenant, data):
    title, description, category = _validate_new(data)
    prediction = predict_urgency(category, title, description)
    urgency = prediction["label"]
    created = now_iso()
    cur = db.execute(
        "INSERT INTO requests (tenant_id, title, description, category, unit, urgency,"
        " predicted_urgency, confidence, urgency_source, status, sla_hours, created_at,"
        " due_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?, ?)",
        (tenant["id"], title, description, category, tenant["unit"], urgency, urgency,
         prediction["confidence"], prediction["source"], SLA_HOURS[urgency], created,
         add_hours_iso(created, SLA_HOURS[urgency])),
    )
    request_id = cur.lastrowid
    add_history(db, request_id, "Open",
                f"Request submitted. Predicted urgency: {urgency} "
                f"({round(prediction['confidence'] * 100)}% confidence, "
                f"{prediction['source']})", tenant["id"])
    assignment_service.auto_assign(db, request_id)
    db.commit()
    return get_request(db, request_id)


def get_request(db, request_id):
    row = db.execute(BASE_SELECT + " WHERE r.id = ?", (request_id,)).fetchone()
    return serialize(row) if row else None


def _check_access(user, req):
    role = user["role"]
    if role == "manager":
        return
    if role == "tenant" and req["tenant_id"] == user["id"]:
        return
    if role == "staff" and req["assigned_to"] == user["id"]:
        return
    # 404 rather than 403 so ids of other people's requests are not revealed
    raise ApiError("Request not found", 404)


def get_request_detail(db, user, request_id):
    req = get_request(db, request_id)
    if req is None:
        raise ApiError("Request not found", 404)
    _check_access(user, req)
    history = db.execute(
        "SELECT h.status, h.note, h.created_at, u.name AS actor_name"
        " FROM status_history h LEFT JOIN users u ON u.id = h.actor_id"
        " WHERE h.request_id = ? ORDER BY h.id ASC",
        (request_id,),
    ).fetchall()
    req["history"] = [dict(h) for h in history]
    return req


def list_requests(db, user, status=None, urgency=None, category=None, q=None, sort=None):
    where, params = [], []
    if user["role"] == "tenant":
        where.append("r.tenant_id = ?")
        params.append(user["id"])
    elif user["role"] == "staff":
        where.append("r.assigned_to = ?")
        params.append(user["id"])

    if status:
        if status == "Active":
            where.append("r.status IN ('Assigned', 'In Progress')")
        elif status in STATUSES:
            where.append("r.status = ?")
            params.append(status)
        else:
            raise ApiError("Invalid status filter")
    if urgency:
        if urgency not in URGENCIES:
            raise ApiError("Invalid urgency filter")
        where.append("r.urgency = ?")
        params.append(urgency)
    if category:
        if category not in CATEGORIES:
            raise ApiError("Invalid category filter")
        where.append("r.category = ?")
        params.append(category)
    if q:
        like = f"%{q.strip()[:60]}%"
        where.append("(r.title LIKE ? OR r.description LIKE ? OR r.unit LIKE ?"
                     " OR t.name LIKE ? OR CAST(r.id AS TEXT) = ?)")
        params += [like, like, like, like, q.strip()[:60]]

    sql = BASE_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    if (sort or ("newest" if user["role"] == "tenant" else "priority")) == "newest":
        sql += " ORDER BY r.created_at DESC, r.id DESC"
    else:
        sql += (f" ORDER BY (r.status = 'Resolved') ASC, {URGENCY_ORDER} ASC,"
                " r.created_at ASC, r.id ASC")
    return [serialize(r) for r in db.execute(sql, params).fetchall()]


# ------------------------------------------------------------ workflow ----
def change_status(db, user, request_id, new_status, note):
    req = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if req is None:
        raise ApiError("Request not found", 404)
    _check_access(user, req)
    if new_status not in STATUSES:
        raise ApiError("Invalid status")

    allowed = MANAGER_TRANSITIONS if user["role"] == "manager" else STAFF_TRANSITIONS
    if (req["status"], new_status) not in allowed:
        raise ApiError(f"Cannot move a request from '{req['status']}' to '{new_status}'")

    note = note.strip() if isinstance(note, str) else ""
    if len(note) > 500:
        raise ApiError("Note must be 500 characters or fewer")

    now = now_iso()
    if new_status == "In Progress":
        db.execute(
            "UPDATE requests SET status = 'In Progress',"
            " started_at = COALESCE(started_at, ?), resolved_at = NULL WHERE id = ?",
            (now, request_id),
        )
        default_note = "Work started" if req["status"] == "Assigned" else "Request re-opened"
        add_history(db, request_id, new_status, note or default_note, user["id"])
    elif new_status == "Resolved":
        if len(note) < 3:
            raise ApiError("Add a short resolution note describing what was done")
        db.execute(
            "UPDATE requests SET status = 'Resolved', resolved_at = ?,"
            " resolution_notes = ? WHERE id = ?",
            (now, note, request_id),
        )
        add_history(db, request_id, new_status, note, user["id"])
    db.commit()
    return get_request(db, request_id)


def assign_request(db, manager, request_id, staff_id):
    req = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if req is None:
        raise ApiError("Request not found", 404)
    if req["status"] == "Resolved":
        raise ApiError("A resolved request cannot be reassigned. Re-open it first.")
    staff = db.execute(
        "SELECT * FROM users WHERE id = ? AND role = 'staff' AND active = 1", (staff_id,)
    ).fetchone() if isinstance(staff_id, int) else None
    if staff is None:
        raise ApiError("Choose a valid staff member")
    if req["assigned_to"] == staff["id"] and req["status"] != "Open":
        raise ApiError(f"Already assigned to {staff['name']}")

    now = now_iso()
    # Re-assigning work that was already started puts it back to 'Assigned'.
    db.execute(
        "UPDATE requests SET assigned_to = ?, status = 'Assigned', assigned_at = ?,"
        " started_at = NULL WHERE id = ?",
        (staff["id"], now, request_id),
    )
    add_history(db, request_id, "Assigned", f"Assigned to {staff['name']} by manager",
                manager["id"])
    db.commit()
    return get_request(db, request_id)


def override_urgency(db, manager, request_id, urgency):
    req = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if req is None:
        raise ApiError("Request not found", 404)
    if urgency not in URGENCIES:
        raise ApiError("Choose a valid urgency")
    if urgency == req["urgency"]:
        raise ApiError(f"Urgency is already {urgency}")
    sla = SLA_HOURS[urgency]
    db.execute(
        "UPDATE requests SET urgency = ?, urgency_source = 'manager', sla_hours = ?,"
        " due_at = ? WHERE id = ?",
        (urgency, sla, add_hours_iso(req["created_at"], sla), request_id),
    )
    add_history(db, request_id, req["status"],
                f"Urgency changed from {req['urgency']} to {urgency} by manager "
                f"(SLA now {sla}h)", manager["id"])
    db.commit()
    return get_request(db, request_id)
