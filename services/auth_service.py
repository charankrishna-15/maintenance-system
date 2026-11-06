"""Authentication & role management."""

import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from constants import CATEGORIES
from errors import ApiError
from utils import now_iso

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{7,20}$")


def _clean(value, field, min_len, max_len, required=True):
    value = (value or "").strip() if isinstance(value, str) else ""
    if not value:
        if required:
            raise ApiError(f"{field} is required")
        return None
    if len(value) < min_len or len(value) > max_len:
        raise ApiError(f"{field} must be {min_len}-{max_len} characters")
    return value


def _validate_account(data, password_required=True):
    name = _clean(data.get("name"), "Name", 2, 60)
    email = _clean(data.get("email"), "Email", 5, 120).lower()
    if not EMAIL_RE.match(email):
        raise ApiError("Enter a valid email address")
    password = data.get("password") or ""
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        raise ApiError("Password must be at least 8 characters")
    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        raise ApiError("Password must contain both letters and numbers")
    phone = _clean(data.get("phone"), "Phone", 7, 20, required=False)
    if phone and not PHONE_RE.match(phone):
        raise ApiError("Enter a valid phone number")
    return name, email, password, phone


def _insert_user(db, name, email, password, role, phone=None, unit=None, specialty=None):
    try:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash, role, phone, unit, specialty,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role, phone, unit, specialty,
             now_iso()),
        )
    except sqlite3.IntegrityError:
        raise ApiError("An account with this email already exists", 409)
    db.commit()
    return cur.lastrowid


def public_user(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "unit": row["unit"],
        "phone": row["phone"],
        "specialty": row["specialty"],
    }


def register_tenant(db, data):
    name, email, password, phone = _validate_account(data)
    unit = _clean(data.get("unit"), "Unit", 1, 20)
    user_id = _insert_user(db, name, email, password, "tenant", phone=phone, unit=unit)
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_staff(db, data):
    name, email, password, phone = _validate_account(data)
    specialty = data.get("specialty")
    if specialty not in CATEGORIES:
        raise ApiError("Choose a valid specialty")
    user_id = _insert_user(db, name, email, password, "staff", phone=phone,
                           specialty=specialty)
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user_direct(db, name, email, password, role, phone=None, unit=None,
                       specialty=None):
    """Used by the seeding script and tests (bypasses validation)."""
    return _insert_user(db, name, email.lower(), password, role, phone, unit, specialty)


def authenticate(db, email, password):
    email = (email or "").strip().lower() if isinstance(email, str) else ""
    if not email or not isinstance(password, str) or not password:
        raise ApiError("Email and password are required")
    row = db.execute(
        "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
    ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        raise ApiError("Invalid email or password", 401)
    return row
