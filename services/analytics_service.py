"""Analytics Dashboard: property-manager performance metrics."""

from datetime import timedelta

from constants import CATEGORIES, STATUSES, URGENCIES
from services.assignment_service import staff_workloads
from utils import hours_between, now_iso, utcnow


def _avg(values):
    values = list(values)
    return round(sum(values) / len(values), 1) if values else None


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


def _resolution_hours(r):
    return hours_between(r["created_at"], r["resolved_at"])


def _on_time(r):
    return r["resolved_at"] <= r["due_at"]


def build_analytics(db):
    now = now_iso()
    rows = [dict(r) for r in db.execute("SELECT * FROM requests")]
    resolved = [r for r in rows if r["status"] == "Resolved" and r["resolved_at"]]

    by_status = {s: 0 for s in STATUSES}
    by_urgency = {u: 0 for u in URGENCIES}
    by_category = {c: 0 for c in CATEGORIES}
    for r in rows:
        by_status[r["status"]] += 1
        by_urgency[r["urgency"]] += 1
        by_category[r["category"]] = by_category.get(r["category"], 0) + 1

    unresolved = [r for r in rows if r["status"] != "Resolved"]
    overdue = [r for r in unresolved if now > r["due_at"]]
    overridden = [r for r in rows if r["urgency_source"] == "manager"]

    summary = {
        "total": len(rows),
        "open": by_status["Open"],
        "assigned": by_status["Assigned"],
        "in_progress": by_status["In Progress"],
        "resolved": by_status["Resolved"],
        "overdue": len(overdue),
        "critical_active": sum(1 for r in unresolved if r["urgency"] == "Critical"),
        "avg_resolution_hours": _avg(_resolution_hours(r) for r in resolved),
        "sla_compliance_pct": _pct(sum(1 for r in resolved if _on_time(r)), len(resolved)),
        "override_rate_pct": _pct(len(overridden), len(rows)),
    }

    avg_by_urgency = {
        u: _avg(_resolution_hours(r) for r in resolved if r["urgency"] == u)
        for u in URGENCIES
    }

    # Created vs resolved per day for the last 14 days (UTC dates).
    today = utcnow().date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    daily = []
    for d in days:
        key = d.isoformat()
        daily.append({
            "date": key,
            "created": sum(1 for r in rows if r["created_at"][:10] == key),
            "resolved": sum(1 for r in resolved if r["resolved_at"][:10] == key),
        })

    # Per-staff performance.
    loads = {s["id"]: s for s in staff_workloads(db)}
    staff_rows = db.execute(
        "SELECT id, name, specialty, active FROM users WHERE role = 'staff' ORDER BY name"
    ).fetchall()
    staff = []
    for s in staff_rows:
        mine = [r for r in rows if r["assigned_to"] == s["id"]]
        mine_resolved = [r for r in mine if r["status"] == "Resolved" and r["resolved_at"]]
        mine_active = [r for r in mine if r["status"] in ("Assigned", "In Progress")]
        staff.append({
            "id": s["id"],
            "name": s["name"],
            "specialty": s["specialty"],
            "active": bool(s["active"]),
            "active_requests": len(mine_active),
            "workload_score": loads.get(s["id"], {}).get("load", 0),
            "total_assigned": len(mine),
            "resolved": len(mine_resolved),
            "avg_resolution_hours": _avg(_resolution_hours(r) for r in mine_resolved),
            "sla_compliance_pct": _pct(sum(1 for r in mine_resolved if _on_time(r)),
                                       len(mine_resolved)),
            "overdue": sum(1 for r in mine_active if now > r["due_at"]),
        })

    return {
        "summary": summary,
        "by_status": by_status,
        "by_urgency": by_urgency,
        "by_category": by_category,
        "avg_resolution_by_urgency": avg_by_urgency,
        "daily": daily,
        "staff": staff,
    }
