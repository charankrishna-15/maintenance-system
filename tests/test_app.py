"""End-to-end tests for the maintenance system.

Run from the project folder:
    python -m unittest discover -s tests -v
"""

import json
import os
import tempfile
import unittest

from app import create_app
from constants import SLA_HOURS
from database import connect
from ml.evaluate import evaluate
from ml.predictor import predict_urgency
from ml.train_model import METRICS_PATH
from seed import seed
from services import auth_service

PASSWORD = "Passw0rd1"


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "test.db")
        self.app = create_app({
            "TESTING": True, "DATABASE": self.db_path, "SEED_DEMO": False,
            "SECRET_KEY": "test-secret",
        })

    def tearDown(self):
        self.tmp.cleanup()

    # -- helpers --
    def add_user(self, name, email, role, **extra):
        db = connect(self.db_path)
        try:
            return auth_service.create_user_direct(db, name, email, PASSWORD, role, **extra)
        finally:
            db.close()

    def login(self, email):
        client = self.app.test_client()
        res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        return client

    def make_world(self):
        self.manager = self.add_user("Mia Manager", "mgr@test.com", "manager")
        self.plumber = self.add_user("Pete Plumber", "plumber@test.com", "staff",
                                     specialty="Plumbing")
        self.electrician = self.add_user("Ellie Electric", "elec@test.com", "staff",
                                         specialty="Electrical")
        self.tenant = self.add_user("Tina Tenant", "tina@test.com", "tenant", unit="A-1")
        self.tenant2 = self.add_user("Tom Tenant", "tom@test.com", "tenant", unit="B-2")

    def submit(self, client, title="Kitchen tap leaking", category="Plumbing",
               description="Water is dripping from the pipe under the sink all day"):
        res = client.post("/api/requests", json={
            "title": title, "category": category, "description": description})
        self.assertEqual(res.status_code, 201, res.get_data(as_text=True))
        return res.get_json()["request"]


class AuthTests(BaseCase):
    def test_register_and_login_flow(self):
        c = self.app.test_client()
        res = c.post("/api/auth/register", json={
            "name": "New Tenant", "email": "New@Test.com", "unit": "C-3", "password": "abc12345"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["redirect"], "/tenant")
        me = c.get("/api/auth/me").get_json()["user"]
        self.assertEqual(me["role"], "tenant")
        self.assertEqual(me["email"], "new@test.com")
        self.assertNotIn("password_hash", json.dumps(me))
        c.post("/api/auth/logout", json={})
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        res = c.post("/api/auth/login", json={"email": "new@test.com", "password": "abc12345"})
        self.assertEqual(res.status_code, 200)

    def test_registration_validation(self):
        c = self.app.test_client()
        base = {"name": "Val", "email": "val@test.com", "unit": "A-1", "password": "abc12345"}
        cases = [
            ({"password": "short1"}, "Password"),
            ({"password": "onlyletters"}, "letters and numbers"),
            ({"email": "not-an-email"}, "valid email"),
            ({"name": ""}, "Name"),
            ({"unit": ""}, "Unit"),
            ({"phone": "abc"}, "phone"),
        ]
        for override, fragment in cases:
            res = c.post("/api/auth/register", json={**base, **override})
            self.assertEqual(res.status_code, 400, override)
            self.assertIn(fragment.lower(), res.get_json()["error"].lower())

    def test_duplicate_email_rejected(self):
        c = self.app.test_client()
        payload = {"name": "Dup", "email": "dup@test.com", "unit": "A-1", "password": "abc12345"}
        self.assertEqual(c.post("/api/auth/register", json=payload).status_code, 201)
        res = self.app.test_client().post("/api/auth/register", json=payload)
        self.assertEqual(res.status_code, 409)

    def test_bad_login(self):
        self.make_world()
        c = self.app.test_client()
        res = c.post("/api/auth/login", json={"email": "tina@test.com", "password": "wrong"})
        self.assertEqual(res.status_code, 401)
        res = c.post("/api/auth/login", json={"email": "nobody@test.com", "password": "x"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(c.post("/api/auth/login", json={}).status_code, 400)

    def test_passwords_are_hashed(self):
        self.make_world()
        db = connect(self.db_path)
        row = db.execute("SELECT password_hash FROM users WHERE email='tina@test.com'").fetchone()
        db.close()
        self.assertNotEqual(row[0], PASSWORD)
        self.assertTrue(row[0].startswith(("scrypt:", "pbkdf2:")))

    def test_json_content_type_required_for_mutations(self):
        self.make_world()
        c = self.login("mgr@test.com")
        res = c.post("/api/requests/auto-assign", data="x=1",
                     content_type="application/x-www-form-urlencoded")
        self.assertEqual(res.status_code, 415)


class PermissionTests(BaseCase):
    def test_role_restrictions(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        staff = self.login("plumber@test.com")
        anon = self.app.test_client()

        self.assertEqual(anon.get("/api/requests").status_code, 401)
        self.assertEqual(tenant.get("/api/analytics").status_code, 403)
        self.assertEqual(tenant.get("/api/staff").status_code, 403)
        self.assertEqual(tenant.post("/api/requests/auto-assign", json={}).status_code, 403)
        self.assertEqual(staff.post("/api/requests", json={}).status_code, 403)
        self.assertEqual(staff.get("/api/analytics").status_code, 403)
        self.assertEqual(
            staff.post("/api/staff", json={"name": "x"}).status_code, 403)

    def test_tenants_only_see_their_own_requests(self):
        self.make_world()
        t1, t2 = self.login("tina@test.com"), self.login("tom@test.com")
        r1 = self.submit(t1)
        self.assertEqual(t2.get("/api/requests").get_json()["count"], 0)
        self.assertEqual(t2.get(f"/api/requests/{r1['id']}").status_code, 404)
        self.assertEqual(t1.get(f"/api/requests/{r1['id']}").status_code, 200)

    def test_staff_cannot_touch_other_staffs_requests(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        req = self.submit(tenant)                      # goes to the plumber
        electrician = self.login("elec@test.com")
        self.assertEqual(electrician.get(f"/api/requests/{req['id']}").status_code, 404)
        res = electrician.patch(f"/api/requests/{req['id']}/status",
                                json={"status": "In Progress"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(electrician.get("/api/requests").get_json()["count"], 0)

    def test_pages_and_redirects(self):
        self.make_world()
        anon = self.app.test_client()
        self.assertEqual(anon.get("/").status_code, 200)
        for path in ("/tenant", "/staff", "/manager"):
            res = anon.get(path)
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers["Location"], "/")
        tenant = self.login("tina@test.com")
        self.assertEqual(tenant.get("/tenant").status_code, 200)
        self.assertEqual(tenant.get("/manager").headers["Location"], "/tenant")
        self.assertEqual(tenant.get("/").headers["Location"], "/tenant")
        self.assertEqual(self.login("plumber@test.com").get("/staff").status_code, 200)
        self.assertEqual(self.login("mgr@test.com").get("/manager").status_code, 200)
        self.assertEqual(anon.get("/nope").status_code, 404)
        self.assertEqual(anon.get("/api/nope").get_json()["error"], "Not found")
        self.assertEqual(anon.get("/static/js/common.js").status_code, 200)


class RequestAndAssignmentTests(BaseCase):
    def test_submission_predicts_urgency_and_auto_assigns_by_specialty(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        plumbing = self.submit(tenant)
        self.assertEqual(plumbing["assigned_to"], self.plumber)
        self.assertEqual(plumbing["status"], "Assigned")
        self.assertIn(plumbing["urgency"], SLA_HOURS)
        self.assertEqual(plumbing["sla_hours"], SLA_HOURS[plumbing["urgency"]])
        self.assertEqual(plumbing["unit"], "A-1")

        electrical = self.submit(tenant, title="Socket dead", category="Electrical",
                                 description="The kitchen outlets have stopped working completely")
        self.assertEqual(electrical["assigned_to"], self.electrician)

    def test_emergency_is_critical(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        req = self.submit(tenant, title="Gas smell", category="Appliance",
                          description="I can smell gas coming from the stove in the kitchen")
        self.assertEqual(req["urgency"], "Critical")
        self.assertEqual(req["sla_hours"], 4)
        detail = tenant.get(f"/api/requests/{req['id']}").get_json()["request"]
        self.assertTrue(detail["history"][0]["note"].startswith("Request submitted"))

    def test_validation_errors(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        good = {"title": "Valid title", "category": "Plumbing",
                "description": "A sufficiently long description"}
        for override in ({"title": "ab"}, {"description": "short"}, {"category": "Nope"},
                         {"title": "x" * 101}, {"description": "x" * 1001}, {"title": 5}):
            res = tenant.post("/api/requests", json={**good, **override})
            self.assertEqual(res.status_code, 400, override)

    def test_load_is_spread_across_matching_staff(self):
        self.make_world()
        second = self.add_user("Quinn Plumber", "plumber2@test.com", "staff", specialty="Plumbing")
        tenant = self.login("tina@test.com")
        assigned = [self.submit(tenant)["assigned_to"] for _ in range(4)]
        self.assertEqual(set(assigned), {self.plumber, second})
        self.assertNotEqual(assigned[0], assigned[1])

    def test_falls_back_to_general_staff_then_waits_for_staff(self):
        self.make_world()
        general = self.add_user("Gina General", "gen@test.com", "staff", specialty="General")
        tenant = self.login("tina@test.com")
        pest = self.submit(tenant, title="Ants in kitchen", category="Pest Control",
                           description="A few ants are trailing along the counter daily")
        self.assertEqual(pest["assigned_to"], general)

    def test_request_waits_when_no_staff_then_auto_assigns_when_staff_added(self):
        self.add_user("Mia Manager", "mgr@test.com", "manager")
        self.add_user("Tina Tenant", "tina@test.com", "tenant", unit="A-1")
        tenant = self.login("tina@test.com")
        req = self.submit(tenant)
        self.assertEqual(req["status"], "Open")
        self.assertIsNone(req["assigned_to"])

        manager = self.login("mgr@test.com")
        res = manager.post("/api/staff", json={
            "name": "Late Plumber", "email": "late@test.com", "password": "abc12345",
            "specialty": "Plumbing"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["auto_assigned"], 1)
        detail = tenant.get(f"/api/requests/{req['id']}").get_json()["request"]
        self.assertEqual(detail["status"], "Assigned")

    def test_add_staff_validation(self):
        self.make_world()
        manager = self.login("mgr@test.com")
        res = manager.post("/api/staff", json={
            "name": "Bad", "email": "bad@test.com", "password": "abc12345", "specialty": "Cooking"})
        self.assertEqual(res.status_code, 400)
        res = manager.post("/api/staff", json={
            "name": "Dup", "email": "plumber@test.com", "password": "abc12345",
            "specialty": "Plumbing"})
        self.assertEqual(res.status_code, 409)

    def test_filters_and_search(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        self.submit(tenant, title="Leaky tap", category="Plumbing")
        self.submit(tenant, title="Dead socket", category="Electrical",
                    description="The study socket is not working at all now")
        manager = self.login("mgr@test.com")
        self.assertEqual(manager.get("/api/requests").get_json()["count"], 2)
        self.assertEqual(manager.get("/api/requests?category=Electrical").get_json()["count"], 1)
        self.assertEqual(manager.get("/api/requests?q=leaky").get_json()["count"], 1)
        self.assertEqual(manager.get("/api/requests?status=Resolved").get_json()["count"], 0)
        self.assertEqual(manager.get("/api/requests?status=Bogus").status_code, 400)
        self.assertEqual(manager.get("/api/requests?urgency=Bogus").status_code, 400)
        # sql-injection style input is treated as plain text
        res = manager.get("/api/requests?q=' OR 1=1 --")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["count"], 0)


class WorkflowTests(BaseCase):
    def test_full_lifecycle(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        staff = self.login("plumber@test.com")
        req = self.submit(tenant)
        rid = req["id"]

        # cannot jump straight to resolved
        res = staff.patch(f"/api/requests/{rid}/status", json={"status": "Resolved", "note": "done"})
        self.assertEqual(res.status_code, 400)

        res = staff.patch(f"/api/requests/{rid}/status", json={"status": "In Progress"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["request"]["status"], "In Progress")
        self.assertIsNotNone(res.get_json()["request"]["started_at"])

        # resolution note required
        res = staff.patch(f"/api/requests/{rid}/status", json={"status": "Resolved"})
        self.assertEqual(res.status_code, 400)

        res = staff.patch(f"/api/requests/{rid}/status",
                          json={"status": "Resolved", "note": "Replaced the washer"})
        done = res.get_json()["request"]
        self.assertEqual(done["status"], "Resolved")
        self.assertFalse(done["resolved_late"])
        self.assertIsNotNone(done["resolution_hours"])

        # staff cannot reopen, manager can
        res = staff.patch(f"/api/requests/{rid}/status", json={"status": "In Progress"})
        self.assertEqual(res.status_code, 400)
        manager = self.login("mgr@test.com")
        res = manager.patch(f"/api/requests/{rid}/status", json={"status": "In Progress"})
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.get_json()["request"]["resolved_at"])

        history = tenant.get(f"/api/requests/{rid}").get_json()["request"]["history"]
        self.assertEqual([h["status"] for h in history],
                         ["Open", "Assigned", "In Progress", "Resolved", "In Progress"])

    def test_invalid_status_values(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        staff = self.login("plumber@test.com")
        rid = self.submit(tenant)["id"]
        self.assertEqual(staff.patch(f"/api/requests/{rid}/status",
                                     json={"status": "Bogus"}).status_code, 400)
        self.assertEqual(staff.patch(f"/api/requests/{rid}/status",
                                     json={"status": "Open"}).status_code, 400)
        self.assertEqual(tenant.patch(f"/api/requests/{rid}/status",
                                      json={"status": "Resolved"}).status_code, 403)
        self.assertEqual(staff.patch("/api/requests/9999/status",
                                     json={"status": "In Progress"}).status_code, 404)

    def test_manager_reassign_and_override_urgency(self):
        self.make_world()
        second = self.add_user("Quinn Plumber", "plumber2@test.com", "staff", specialty="Plumbing")
        tenant = self.login("tina@test.com")
        manager = self.login("mgr@test.com")
        req = self.submit(tenant)
        rid = req["id"]

        target = second if req["assigned_to"] == self.plumber else self.plumber
        res = manager.post(f"/api/requests/{rid}/assign", json={"staff_id": target})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["request"]["assigned_to"], target)
        self.assertEqual(manager.post(f"/api/requests/{rid}/assign",
                                      json={"staff_id": target}).status_code, 400)
        self.assertEqual(manager.post(f"/api/requests/{rid}/assign",
                                      json={"staff_id": 9999}).status_code, 400)
        self.assertEqual(manager.post(f"/api/requests/{rid}/assign",
                                      json={"staff_id": "1"}).status_code, 400)

        new_level = "Low" if req["urgency"] != "Low" else "High"
        res = manager.patch(f"/api/requests/{rid}/urgency", json={"urgency": new_level})
        updated = res.get_json()["request"]
        self.assertEqual(updated["urgency"], new_level)
        self.assertEqual(updated["sla_hours"], SLA_HOURS[new_level])
        self.assertEqual(updated["urgency_source"], "manager")
        self.assertNotEqual(updated["due_at"], req["due_at"])
        self.assertEqual(manager.patch(f"/api/requests/{rid}/urgency",
                                       json={"urgency": new_level}).status_code, 400)
        self.assertEqual(manager.patch(f"/api/requests/{rid}/urgency",
                                       json={"urgency": "Extreme"}).status_code, 400)

    def test_cannot_reassign_resolved_request(self):
        self.make_world()
        tenant, staff = self.login("tina@test.com"), self.login("plumber@test.com")
        manager = self.login("mgr@test.com")
        rid = self.submit(tenant)["id"]
        staff.patch(f"/api/requests/{rid}/status", json={"status": "In Progress"})
        staff.patch(f"/api/requests/{rid}/status", json={"status": "Resolved", "note": "Fixed it"})
        res = manager.post(f"/api/requests/{rid}/assign", json={"staff_id": self.electrician})
        self.assertEqual(res.status_code, 400)

    def test_overdue_flag(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        manager = self.login("mgr@test.com")
        rid = self.submit(tenant)["id"]
        db = connect(self.db_path)
        db.execute("UPDATE requests SET due_at = '2000-01-01T00:00:00Z' WHERE id = ?", (rid,))
        db.commit()
        db.close()
        self.assertTrue(manager.get(f"/api/requests/{rid}").get_json()["request"]["overdue"])
        self.assertEqual(manager.get("/api/analytics").get_json()["summary"]["overdue"], 1)


class AnalyticsTests(BaseCase):
    def test_numbers_add_up(self):
        self.make_world()
        tenant = self.login("tina@test.com")
        staff = self.login("plumber@test.com")
        manager = self.login("mgr@test.com")

        empty = manager.get("/api/analytics").get_json()
        self.assertEqual(empty["summary"]["total"], 0)
        self.assertIsNone(empty["summary"]["sla_compliance_pct"])
        self.assertIsNone(empty["summary"]["avg_resolution_hours"])

        a = self.submit(tenant)
        self.submit(tenant, title="Socket dead", category="Electrical",
                    description="The study socket is not working at all now")
        staff.patch(f"/api/requests/{a['id']}/status", json={"status": "In Progress"})
        staff.patch(f"/api/requests/{a['id']}/status", json={"status": "Resolved", "note": "Fixed"})

        data = manager.get("/api/analytics").get_json()
        s = data["summary"]
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["resolved"], 1)
        self.assertEqual(s["assigned"], 1)
        self.assertEqual(sum(data["by_status"].values()), 2)
        self.assertEqual(sum(data["by_urgency"].values()), 2)
        self.assertEqual(sum(data["by_category"].values()), 2)
        self.assertEqual(s["sla_compliance_pct"], 100.0)
        self.assertEqual(len(data["daily"]), 14)
        self.assertEqual(sum(d["created"] for d in data["daily"]), 2)
        self.assertEqual(sum(d["resolved"] for d in data["daily"]), 1)
        pete = next(m for m in data["staff"] if m["name"] == "Pete Plumber")
        self.assertEqual(pete["resolved"], 1)
        self.assertEqual(pete["sla_compliance_pct"], 100.0)
        self.assertEqual(pete["active_requests"], 0)


class MachineLearningTests(unittest.TestCase):
    def test_safety_rules(self):
        for text in ("There is a gas leak in my kitchen", "sparks from the socket",
                     "the bathroom is flooding", "smoke coming from the heater"):
            result = predict_urgency("General", "Problem", text)
            self.assertEqual(result["label"], "Critical", text)
            self.assertEqual(result["source"], "safety-rule")

    def test_prediction_shape(self):
        result = predict_urgency("Plumbing", "Tap", "The tap is dripping slowly")
        self.assertIn(result["label"], SLA_HOURS)
        self.assertTrue(0 <= result["confidence"] <= 1)
        self.assertAlmostEqual(sum(result["probabilities"].values()), 1.0, places=1)

    def test_holdout_accuracy(self):
        with open(METRICS_PATH) as fh:
            metrics = json.load(fh)
        self.assertGreaterEqual(metrics["accuracy"], 0.90)

    def test_generalises_to_unseen_wording(self):
        # Hand-written sentences that are not in the training generator.
        self.assertGreaterEqual(evaluate(), 0.75)


class SeedTests(unittest.TestCase):
    def test_seed_data_is_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "seed.db")
            self.assertTrue(seed(path))
            self.assertFalse(seed(path))   # idempotent
            db = connect(path)
            count = lambda sql: db.execute(sql).fetchone()[0]
            self.assertEqual(count("SELECT COUNT(*) FROM users WHERE role='manager'"), 1)
            self.assertEqual(count("SELECT COUNT(*) FROM users WHERE role='staff'"), 5)
            self.assertEqual(count("SELECT COUNT(*) FROM users WHERE role='tenant'"), 8)
            self.assertEqual(count("SELECT COUNT(*) FROM requests"), 70)
            self.assertEqual(count(
                "SELECT COUNT(*) FROM requests WHERE resolved_at IS NOT NULL"
                " AND resolved_at < created_at"), 0)
            self.assertEqual(count(
                "SELECT COUNT(*) FROM requests WHERE status='Resolved' AND resolved_at IS NULL"), 0)
            self.assertEqual(count(
                "SELECT COUNT(*) FROM requests WHERE status='Open' AND assigned_to IS NOT NULL"), 0)
            self.assertEqual(count(
                "SELECT COUNT(*) FROM requests r WHERE NOT EXISTS"
                " (SELECT 1 FROM status_history h WHERE h.request_id = r.id)"), 0)
            db.close()


if __name__ == "__main__":
    unittest.main()
