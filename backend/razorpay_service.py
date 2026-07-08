"""Razorpay Subscriptions wrapper with graceful placeholder behaviour."""
import os
import hmac
import hashlib
import logging
from typing import Optional
import razorpay

logger = logging.getLogger(__name__)

KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
PLAN_ID = os.environ.get("RAZORPAY_PLAN_ID", "")


def is_placeholder() -> bool:
    return (
        not KEY_ID
        or "placeholder" in KEY_ID.lower()
        or not KEY_SECRET
        or "placeholder" in KEY_SECRET.lower()
    )


def _client():
    return razorpay.Client(auth=(KEY_ID, KEY_SECRET))


def create_subscription(plan_id: str, total_count: int = 12, notes: Optional[dict] = None) -> dict:
    """Create a Razorpay subscription. Returns dict with subscription_id.
    Uses placeholder response if Razorpay keys are not configured."""
    if is_placeholder():
        # Mock subscription for local/dev when keys are absent
        import uuid
        sub_id = f"sub_MOCK_{uuid.uuid4().hex[:12]}"
        logger.warning(f"[Razorpay MOCK] Creating subscription: {sub_id}")
        return {"id": sub_id, "status": "created", "short_url": None, "mocked": True}
    c = _client()
    return c.subscription.create(
        {
            "plan_id": plan_id,
            "total_count": total_count,
            "quantity": 1,
            "customer_notify": 1,
            "notes": notes or {},
        }
    )


def fetch_subscription(subscription_id: str) -> dict:
    if is_placeholder() or subscription_id.startswith("sub_MOCK_"):
        return {"id": subscription_id, "status": "active", "mocked": True}
    c = _client()
    return c.subscription.fetch(subscription_id)


def cancel_subscription(subscription_id: str, cancel_at_cycle_end: int = 0) -> dict:
    if is_placeholder() or subscription_id.startswith("sub_MOCK_"):
        return {"id": subscription_id, "status": "cancelled", "mocked": True}
    c = _client()
    return c.subscription.cancel(subscription_id, {"cancel_at_cycle_end": cancel_at_cycle_end})


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET or "placeholder" in WEBHOOK_SECRET.lower():
        # In placeholder mode, accept but flag as unverified
        logger.warning("[Razorpay MOCK] Webhook secret is placeholder — accepting without verification")
        return True
    try:
        expected = hmac.new(
            WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False
