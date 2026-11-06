"""JSON REST API (blueprint mounted at /api)."""

from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from constants import (
    CATEGORIES, HOME_BY_ROLE, SLA_HOURS, STATUSES, URGENCIES,
)
from database import get_db
from errors import ApiError
from services import analytics_service, assignment_service, auth_service, request_service

api = Blueprint("api", __name__, url_prefix="/api")


def require_role(*roles):
    """Require a logged-in user (optionally with one of the given roles)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.user is None:
                raise ApiError("Please log in to continue", 401)
            if roles and g.user["role"] not in roles:
                raise ApiError("You do not have permission to do this", 403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object")
    return data


# ------------------------------------------------------------------ auth ----
def _login(user):
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True


@api.post("/auth/register")
def register():
    user = auth_service.register_tenant(get_db(), body())
    _login(user)
    return jsonify(user=auth_service.public_user(user),
                   redirect=HOME_BY_ROLE[user["role"]]), 201


@api.post("/auth/login")
def login():
    data = body()
    user = auth_service.authenticate(get_db(), data.get("email"), data.get("password"))
    _login(user)
    return jsonify(user=auth_service.public_user(user), redirect=HOME_BY_ROLE[user["role"]])


@api.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@api.get("/auth/me")
@require_role()
def me():
    return jsonify(user=auth_service.public_user(g.user))


@api.get("/meta")
def meta():
    return jsonify(categories=CATEGORIES, urgencies=URGENCIES, statuses=STATUSES,
                   sla_hours=SLA_HOURS)


# -------------------------------------------------------------- requests ----
@api.post("/predict")
@require_role("tenant", "manager")
def predict():
    return jsonify(request_service.preview_urgency(body()))


@api.post("/requests")
@require_role("tenant")
def create_request():
    created = request_service.create_request(get_db(), g.user, body())
    return jsonify(request=created), 201


@api.get("/requests")
@require_role()
def list_requests():
    args = request.args
    items = request_service.list_requests(
        get_db(), g.user,
        status=args.get("status"), urgency=args.get("urgency"),
        category=args.get("category"), q=args.get("q"), sort=args.get("sort"),
    )
    return jsonify(requests=items, count=len(items))


@api.post("/requests/auto-assign")
@require_role("manager")
def auto_assign_all():
    count = assignment_service.auto_assign_all_open(get_db())
    return jsonify(assigned=count)


@api.get("/requests/<int:request_id>")
@require_role()
def request_detail(request_id):
    return jsonify(request=request_service.get_request_detail(get_db(), g.user, request_id))


@api.patch("/requests/<int:request_id>/status")
@require_role("staff", "manager")
def update_status(request_id):
    data = body()
    updated = request_service.change_status(
        get_db(), g.user, request_id, data.get("status"), data.get("note"))
    return jsonify(request=updated)


@api.post("/requests/<int:request_id>/assign")
@require_role("manager")
def assign(request_id):
    updated = request_service.assign_request(
        get_db(), g.user, request_id, body().get("staff_id"))
    return jsonify(request=updated)


@api.patch("/requests/<int:request_id>/urgency")
@require_role("manager")
def set_urgency(request_id):
    updated = request_service.override_urgency(
        get_db(), g.user, request_id, body().get("urgency"))
    return jsonify(request=updated)


# ----------------------------------------------------------------- staff ----
@api.get("/staff")
@require_role("manager")
def list_staff():
    loads = {s["id"]: s for s in assignment_service.staff_workloads(get_db())}
    rows = get_db().execute(
        "SELECT id, name, email, phone, specialty, active FROM users"
        " WHERE role = 'staff' ORDER BY name").fetchall()
    staff = []
    for r in rows:
        item = dict(r)
        item["workload_score"] = loads.get(r["id"], {}).get("load", 0)
        item["active_requests"] = loads.get(r["id"], {}).get("active_count", 0)
        staff.append(item)
    return jsonify(staff=staff)


@api.post("/staff")
@require_role("manager")
def add_staff():
    db = get_db()
    user = auth_service.create_staff(db, body())
    # New capacity: place any waiting requests.
    assigned = assignment_service.auto_assign_all_open(db)
    return jsonify(staff=auth_service.public_user(user), auto_assigned=assigned), 201


# ------------------------------------------------------------- analytics ----
@api.get("/analytics")
@require_role("manager")
def analytics():
    return jsonify(analytics_service.build_analytics(get_db()))
