"""Assignment Workflow: automatic, workload-aware staff assignment.

Rules
  1. Only active staff are considered.
  2. Prefer staff whose specialty equals the request category; if none exist
     fall back to "General" staff, then to any staff member.
  3. Among candidates choose the lowest *weighted* workload
     (Critical=4, High=3, Medium=2, Low=1 summed over Assigned/In-Progress
     requests), then fewest active requests, then lowest id.
"""

from utils import now_iso

WORKLOAD_SQL = """
SELECT u.id, u.name, u.specialty,
       COUNT(r.id) AS active_count,
       COALESCE(SUM(CASE r.urgency
                      WHEN 'Critical' THEN 4 WHEN 'High' THEN 3
                      WHEN 'Medium' THEN 2 WHEN 'Low' THEN 1 END), 0) AS load
FROM users u
LEFT JOIN requests r
       ON r.assigned_to = u.id AND r.status IN ('Assigned', 'In Progress')
WHERE u.role = 'staff' AND u.active = 1
GROUP BY u.id
"""


def staff_workloads(db):
    return [dict(r) for r in db.execute(WORKLOAD_SQL)]


def pick_staff(db, category, exclude_id=None):
    staff = [s for s in staff_workloads(db) if s["id"] != exclude_id]
    if not staff:
        return None
    pool = (
        [s for s in staff if s["specialty"] == category]
        or [s for s in staff if s["specialty"] == "General"]
        or staff
    )
    return min(pool, key=lambda s: (s["load"], s["active_count"], s["id"]))


def add_history(db, request_id, status, note, actor_id):
    db.execute(
        "INSERT INTO status_history (request_id, status, note, actor_id, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (request_id, status, note, actor_id, now_iso()),
    )


def auto_assign(db, request_id):
    """Assign an Open request to the best staff member. Returns the staff dict
    or None when the request is not open or nobody is available."""
    req = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if req is None or req["status"] != "Open":
        return None
    staff = pick_staff(db, req["category"])
    if staff is None:
        return None
    now = now_iso()
    db.execute(
        "UPDATE requests SET assigned_to = ?, status = 'Assigned', assigned_at = ?"
        " WHERE id = ?",
        (staff["id"], now, request_id),
    )
    match = "specialty match" if staff["specialty"] == req["category"] else "best available"
    add_history(db, request_id, "Assigned",
                f"Auto-assigned to {staff['name']} ({match}, workload {staff['load']})",
                None)
    return staff


def auto_assign_all_open(db):
    """Assign every Open request, most urgent first. Returns number assigned."""
    rows = db.execute(
        "SELECT id FROM requests WHERE status = 'Open' ORDER BY CASE urgency"
        " WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,"
        " created_at ASC"
    ).fetchall()
    count = 0
    for row in rows:
        if auto_assign(db, row["id"]):
            count += 1
    db.commit()
    return count
