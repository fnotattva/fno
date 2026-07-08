"""Backend regression tests for FnO Tattva Subscription Access Management."""
import os
import io
import time
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@fnotattva.com"
ADMIN_PASSWORD = "FnoTattva@2026"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {token}"})
    return s


# ---------------- Health ----------------
class TestHealth:
    def test_root(self, api):
        r = api.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["razorpay_configured"] is False
        assert d["telegram_configured"] is False


# ---------------- Auth ----------------
class TestAuth:
    def test_login_success(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert "token" in r.json() and r.json()["email"] == ADMIN_EMAIL

    def test_login_bad_password(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_me_requires_token(self, api):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code in (401, 403)

    def test_me_ok(self, auth):
        r = auth.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL


# ---------------- Subscribers ----------------
class TestSubscribers:
    created_id = None
    unique_email = f"TEST_{uuid.uuid4().hex[:8]}@fnotattva.com"

    def test_subscribers_requires_auth(self, api):
        r = requests.get(f"{BASE_URL}/api/subscribers")
        assert r.status_code in (401, 403)

    def test_stats(self, auth):
        r = auth.get(f"{BASE_URL}/api/subscribers/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ("total", "by_status", "failed_payments_today", "mrr_estimate_inr"):
            assert k in d

    def test_create(self, auth):
        payload = {"name": "TEST User", "email": TestSubscribers.unique_email,
                   "mobile": "9999900000"}
        r = auth.post(f"{BASE_URL}/api/subscribers", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == payload["email"].lower()
        assert d["telegram_invite_link"], "invite link should be auto-generated (mock)"
        TestSubscribers.created_id = d["id"]

    def test_duplicate_email(self, auth):
        r = auth.post(f"{BASE_URL}/api/subscribers",
                      json={"name": "Dup", "email": TestSubscribers.unique_email,
                            "mobile": "9999900001"})
        assert r.status_code == 409

    def test_search_filter(self, auth):
        r = auth.get(f"{BASE_URL}/api/subscribers",
                     params={"q": TestSubscribers.unique_email.split("@")[0]})
        assert r.status_code == 200
        assert any(s["id"] == TestSubscribers.created_id for s in r.json())

    def test_status_filter(self, auth):
        r = auth.get(f"{BASE_URL}/api/subscribers", params={"status": "ACTIVE"})
        assert r.status_code == 200
        for s in r.json():
            assert s["subscription_status"] == "ACTIVE"
        r2 = auth.get(f"{BASE_URL}/api/subscribers", params={"status": "ALL"})
        assert r2.status_code == 200

    def test_patch(self, auth):
        r = auth.patch(f"{BASE_URL}/api/subscribers/{TestSubscribers.created_id}",
                       json={"notes": "updated by test"})
        assert r.status_code == 200
        assert r.json()["notes"] == "updated by test"

    def test_comp(self, auth):
        r = auth.post(f"{BASE_URL}/api/subscribers/{TestSubscribers.created_id}/comp",
                      json={"reason": "vip"})
        assert r.status_code == 200
        assert r.json()["subscription_status"] == "ADMIN_COMP"

    def test_reactivate(self, auth):
        r = auth.post(f"{BASE_URL}/api/subscribers/{TestSubscribers.created_id}/reactivate",
                      json={"reason": "test"})
        assert r.status_code == 200
        assert r.json()["subscription_status"] == "ACTIVE"

    def test_remove_from_channel(self, auth):
        r = auth.post(
            f"{BASE_URL}/api/subscribers/{TestSubscribers.created_id}/remove-from-channel",
            json={})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete(self, auth):
        r = auth.delete(f"{BASE_URL}/api/subscribers/{TestSubscribers.created_id}")
        assert r.status_code == 200
        # verify gone
        r2 = auth.get(f"{BASE_URL}/api/subscribers/{TestSubscribers.created_id}")
        assert r2.status_code == 404


# ---------------- Public checkout ----------------
class TestPublic:
    def test_plan(self, api):
        r = api.get(f"{BASE_URL}/api/public/plan")
        assert r.status_code == 200
        d = r.json()
        assert "plan_name" in d and "amount_inr" in d
        assert d["razorpay_configured"] is False

    def test_checkout(self, api):
        email = f"TEST_ck_{uuid.uuid4().hex[:6]}@fnotattva.com"
        r = api.post(f"{BASE_URL}/api/public/checkout",
                     json={"name": "TEST CK", "email": email, "mobile": "9111100000"})
        assert r.status_code == 200
        d = r.json()
        assert d["subscription_id"].startswith("sub_MOCK_") or d["is_placeholder"] is True
        assert d["is_placeholder"] is True


# ---------------- Webhooks ----------------
class TestWebhooks:
    sub_id_1 = f"sub_MOCK_wh_{uuid.uuid4().hex[:6]}"
    email_1 = f"TEST_wh_{uuid.uuid4().hex[:6]}@fnotattva.com"

    def _post(self, api, event, entity, kind="subscription"):
        payload = {"event": event, "payload": {kind: {"entity": entity}}}
        return api.post(f"{BASE_URL}/api/webhooks/razorpay", json=payload)

    def test_authenticated_creates_subscriber(self, api, auth):
        entity = {
            "id": TestWebhooks.sub_id_1,
            "notes": {"name": "TEST WH", "email": TestWebhooks.email_1, "mobile": "9000000000"},
        }
        r = self._post(api, "subscription.authenticated", entity)
        assert r.status_code == 200 and r.json()["processed"] is True
        # verify subscriber created ACTIVE
        subs = auth.get(f"{BASE_URL}/api/subscribers", params={"q": TestWebhooks.email_1}).json()
        assert subs and subs[0]["subscription_status"] == "ACTIVE"
        assert subs[0]["telegram_invite_link"]

    def test_charged_updates_next_billing(self, api, auth):
        entity = {
            "id": f"pay_mock_{uuid.uuid4().hex[:6]}",
            "subscription_id": TestWebhooks.sub_id_1,
            "amount": 99900,
            "method": "upi",
            "charge_at": int(time.time()) + 30 * 24 * 3600,
        }
        r = self._post(api, "subscription.charged", entity, kind="payment")
        assert r.status_code == 200
        subs = auth.get(f"{BASE_URL}/api/subscribers", params={"q": TestWebhooks.email_1}).json()
        assert subs[0]["next_billing_date"] is not None
        # payments recorded
        pays = auth.get(f"{BASE_URL}/api/payments").json()
        assert any(p.get("razorpay_subscription_id") == TestWebhooks.sub_id_1 and p["status"] == "captured"
                   for p in pays)

    def test_payment_failed_sets_grace(self, api, auth):
        entity = {
            "id": f"pay_fail_{uuid.uuid4().hex[:6]}",
            "subscription_id": TestWebhooks.sub_id_1,
            "amount": 99900,
        }
        r = self._post(api, "payment.failed", entity, kind="payment")
        assert r.status_code == 200
        subs = auth.get(f"{BASE_URL}/api/subscribers", params={"q": TestWebhooks.email_1}).json()
        assert subs[0]["subscription_status"] == "GRACE"
        assert subs[0]["grace_period_end_date"]

    def test_halted_sets_expired(self, api, auth):
        entity = {"id": TestWebhooks.sub_id_1}
        r = self._post(api, "subscription.halted", entity)
        assert r.status_code == 200
        subs = auth.get(f"{BASE_URL}/api/subscribers", params={"q": TestWebhooks.email_1}).json()
        assert subs[0]["subscription_status"] == "EXPIRED"

    def test_refund_processed(self, api, auth):
        entity = {"id": f"rfnd_{uuid.uuid4().hex[:6]}",
                  "payment_id": f"pay_{uuid.uuid4().hex[:6]}",
                  "subscription_id": TestWebhooks.sub_id_1, "amount": 99900}
        r = self._post(api, "refund.processed", entity, kind="refund")
        assert r.status_code == 200
        subs = auth.get(f"{BASE_URL}/api/subscribers", params={"q": TestWebhooks.email_1}).json()
        assert subs[0]["subscription_status"] == "REFUNDED"

    def test_webhook_logs(self, auth):
        r = auth.get(f"{BASE_URL}/api/webhook-logs")
        assert r.status_code == 200
        logs = r.json()
        assert len(logs) >= 5
        events = [l["event"] for l in logs]
        assert "subscription.authenticated" in events

    def test_payments_filter(self, auth):
        r = auth.get(f"{BASE_URL}/api/payments", params={"status": "failed"})
        assert r.status_code == 200
        for p in r.json():
            assert p["status"] == "failed"


# ---------------- Reports ----------------
class TestReports:
    report_id = None

    def test_upload_pdf(self, token):
        pdf_bytes = (b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
        files = {"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"caption": "TEST report"}
        r = requests.post(f"{BASE_URL}/api/reports/upload",
                          headers={"Authorization": f"Bearer {token}"},
                          files=files, data=data)
        assert r.status_code == 200, r.text
        TestReports.report_id = r.json()["id"]

    def test_list(self, auth):
        r = auth.get(f"{BASE_URL}/api/reports")
        assert r.status_code == 200
        assert any(x["id"] == TestReports.report_id for x in r.json())

    def test_send(self, auth):
        r = auth.post(f"{BASE_URL}/api/reports/{TestReports.report_id}/send")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and d["mocked"] is True

    def test_delete(self, auth):
        r = auth.delete(f"{BASE_URL}/api/reports/{TestReports.report_id}")
        assert r.status_code == 200


# ---------------- Notifications ----------------
class TestNotifications:
    def test_templates(self, auth):
        r = auth.get(f"{BASE_URL}/api/notifications/templates")
        assert r.status_code == 200
        tpls = r.json()
        keys = {t["key"] for t in tpls} if isinstance(tpls, list) else set(tpls.keys())
        expected = {"welcome", "payment_failed", "grace_reminder",
                    "access_paused", "reactivation_success", "daily_report_live"}
        assert expected.issubset(keys), f"Missing templates: {expected - keys}"

    def test_send_without_telegram_id(self, auth):
        # create a subscriber first
        email = f"TEST_notif_{uuid.uuid4().hex[:6]}@fnotattva.com"
        c = auth.post(f"{BASE_URL}/api/subscribers",
                      json={"name": "Notif Test", "email": email, "mobile": "9222200000"})
        sid = c.json()["id"]
        r = auth.post(f"{BASE_URL}/api/notifications/send",
                      json={"subscriber_id": sid, "template_key": "welcome"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert d["preview"] and "title" in d["preview"] and "body" in d["preview"]
        # cleanup
        auth.delete(f"{BASE_URL}/api/subscribers/{sid}")
