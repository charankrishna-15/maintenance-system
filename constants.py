"""Shared constants used across the application."""

ROLES = ("tenant", "staff", "manager")

CATEGORIES = (
    "Plumbing",
    "Electrical",
    "HVAC",
    "Appliance",
    "Structural",
    "Pest Control",
    "Security",
    "General",
)

URGENCIES = ("Low", "Medium", "High", "Critical")

# Target resolution time (hours) for each urgency level (SLA).
SLA_HOURS = {"Critical": 4, "High": 24, "Medium": 72, "Low": 168}

STATUSES = ("Open", "Assigned", "In Progress", "Resolved")

# Weight used by the assignment workflow to measure staff workload.
LOAD_WEIGHT = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

# Allowed (from_status, to_status) transitions.
STAFF_TRANSITIONS = {
    ("Assigned", "In Progress"),
    ("In Progress", "Resolved"),
}
MANAGER_TRANSITIONS = STAFF_TRANSITIONS | {
    ("Resolved", "In Progress"),  # re-open
}

HOME_BY_ROLE = {"tenant": "/tenant", "staff": "/staff", "manager": "/manager"}
