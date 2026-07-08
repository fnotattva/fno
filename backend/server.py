"""FnO Tattva - Subscription Access Management API."""
import os
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from models import (  # noqa: E402
    LoginRequest, LoginResponse,
    Subscriber, SubscriberCreate, SubscriberUpdate,
    PaymentRecord, WebhookLog, ReportRecord,
    CheckoutCreateRequest, CheckoutCreateResponse,
    NotificationSendRequest, ManualActionRequest,
    utcnow_iso, new_id,
)
from auth import verify_password, hash_password, create_token, require_admin  # noqa: E402
import razorpay_service as rzp  # noqa: E402
import telegram_service as tg  # noqa: E402
import notifications as notif  # noqa: E402

# ---------------- Setup ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("fno-tattva")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

UPLOAD_DIR = ROOT_DIR / "uploads" / "reports"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IST = pytz.timezone("Asia/Kolkata")
GRACE_DAYS = int(os.environ.get("GRACE_PERIOD_DAYS", "2"))
DAILY_HOUR = int(os.environ.get("DAILY_REPORT_HOUR_IST", "7"))
DAILY_MIN = int(os.environ.get("DAILY_REPORT_MINUTE_IST", "0"))

PLAN_NAME = os.environ.get("PLAN_NAME", "FnO Tattva Morning Brief - Monthly")
PLAN_AMOUNT = float(os.environ.get("PLAN_AMOUNT_INR", "999"))
PLAN_ID = os.environ.get("RAZORPAY_PLAN_ID", "")

app = FastAPI(title="FnO Tattva Subscription Access API")
api = APIRouter(prefix="/api")


# ---------------- Helpers ----------------
async def seed_admin():
    email = os.environ["ADMIN_EMAIL"]
    pwd = os.environ["ADMIN_PASSWORD"]
    existing = await db.admins.find_one({"email": email})
    if not existing:
        await db.admins.insert_one(
            {
                "id": new_id(),
                "email": email,
                "password_hash": hash_password(pwd),
                "name": "Admin",
                "created_at": utcnow_iso(),
            }
        )
        logger.info(f"Seeded admin: {email}")
    else:
        # Refresh password hash so env changes take effect
        await db.admins.update_one(
            {"email": email}, {"$set": {"password_hash": hash_password(pwd)}}
        )


def clean(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc


async def _get_subscriber(sub_id: str) -> Optional[dict]:
    doc = await db.subscribers.find_one({"id": sub_id}, {"_id": 0})
    return doc


async def _log_webhook(event: str, sig_valid: bool, payload: dict, processed: bool, err: Optional[str] = None):
    log = WebhookLog(event=event, signature_valid=sig_valid, payload=payload, processed=processed, error=err)
    await db.webhook_logs.insert_one(log.model_dump())


async def _record_payment(subscriber_id: Optional[str], sub_id: Optional[str], pay_id: Optional[str],
                          amount: Optional[float], status: str, method: Optional[str] = None,
                          description: Optional[str] = None):
    p = PaymentRecord(
        subscriber_id=subscriber_id, razorpay_subscription_id=sub_id,
        razorpay_payment_id=pay_id, amount=amount, status=status,
        method=method, description=description,
    )
    await db.payments.insert_one(p.model_dump())


# ---------------- Health ----------------
@api.get("/")
async def root():
    return {
        "service": "FnO Tattva Subscription Access API",
        "status": "ok",
        "razorpay_configured": not rzp.is_placeholder(),
        "telegram_configured": not tg._placeholder(),
    }


# ---------------- Auth ----------------
@api.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    admin = await db.admins.find_one({"email": req.email.lower()})
    if not admin or not verify_password(req.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(admin["email"])
    return LoginResponse(token=token, email=admin["email"], name=admin.get("name", "Admin"))


@api.get("/auth/me")
async def me(admin_email: str = Depends(require_admin)):
    return {"email": admin_email, "name": "Admin"}


# ---------------- Subscribers ----------------
@api.get("/subscribers")
async def list_subscribers(
    q: Optional[str] = Query(None, description="search by name/email/mobile"),
    status: Optional[str] = None,
    _: str = Depends(require_admin),
):
    query: dict = {}
    if status and status != "ALL":
        query["subscription_status"] = status
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"mobile": {"$regex": q, "$options": "i"}},
        ]
    cursor = db.subscribers.find(query, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(2000)


@api.get("/subscribers/stats")
async def subscriber_stats(_: str = Depends(require_admin)):
    pipeline = [{"$group": {"_id": "$subscription_status", "count": {"$sum": 1}}}]
    agg = await db.subscribers.aggregate(pipeline).to_list(100)
    by_status = {a["_id"]: a["count"] for a in agg}
    total = sum(by_status.values())
    # Failed payments today
    today = datetime.now(timezone.utc).date().isoformat()
    failed_today = await db.payments.count_documents({"status": "failed", "created_at": {"$gte": today}})
    # MRR estimate
    active = list(await db.subscribers.find(
        {"subscription_status": {"$in": ["ACTIVE", "GRACE"]}}, {"_id": 0, "amount": 1}
    ).to_list(5000))
    mrr = sum(float(s.get("amount") or 0) for s in active)
    return {
        "total": total,
        "by_status": by_status,
        "failed_payments_today": failed_today,
        "mrr_estimate_inr": mrr,
    }


@api.post("/subscribers", response_model=Subscriber)
async def add_subscriber(req: SubscriberCreate, _: str = Depends(require_admin)):
    existing = await db.subscribers.find_one({"email": req.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Subscriber with this email already exists")
    sub = Subscriber(**req.model_dump())
    sub.email = sub.email.lower()
    sub.plan_name = sub.plan_name or PLAN_NAME
    sub.amount = sub.amount if sub.amount is not None else PLAN_AMOUNT
    sub.start_date = utcnow_iso()
    # Generate invite link if channel configured
    invite = await tg.create_invite_link(sub.name)
    sub.telegram_invite_link = invite
    await db.subscribers.insert_one(sub.model_dump())
    return sub


@api.get("/subscribers/{sub_id}", response_model=Subscriber)
async def get_subscriber(sub_id: str, _: str = Depends(require_admin)):
    doc = await _get_subscriber(sub_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    return doc


@api.patch("/subscribers/{sub_id}", response_model=Subscriber)
async def update_subscriber(sub_id: str, req: SubscriberUpdate, _: str = Depends(require_admin)):
    doc = await _get_subscriber(sub_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    updates = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    updates["updated_at"] = utcnow_iso()
    await db.subscribers.update_one({"id": sub_id}, {"$set": updates})
    return await _get_subscriber(sub_id)


@api.delete("/subscribers/{sub_id}")
async def delete_subscriber(sub_id: str, _: str = Depends(require_admin)):
    doc = await _get_subscriber(sub_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    # Attempt to remove from Telegram channel
    if doc.get("telegram_user_id"):
        await tg.ban_user(doc["telegram_user_id"])
    await db.subscribers.delete_one({"id": sub_id})
    return {"ok": True}


@api.post("/subscribers/{sub_id}/remove-from-channel")
async def remove_from_channel(sub_id: str, _: str = Depends(require_admin)):
    doc = await _get_subscriber(sub_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    ok = False
    if doc.get("telegram_user_id"):
        ok = await tg.ban_user(doc["telegram_user_id"])
    await db.subscribers.update_one(
        {"id": sub_id},
        {"$set": {"removed_from_channel": True, "updated_at": utcnow_iso()}},
    )
    return {"ok": True, "telegram_call_ok": ok}


@api.post("/subscribers/{sub_id}/reactivate")
async def reactivate(sub_id: str, req: ManualActionRequest, _: str = Depends(require_admin)):
    doc = await _get_subscriber(sub_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    if doc.get("telegram_user_id"):
        await tg.unban_user(doc["telegram_user_id"])
    invite = await tg.create_invite_link(doc.get("name", "member"))
    await db.subscribers.update_one(
        {"id": sub_id},
        {
            "$set": {
                "subscription_status": "ACTIVE",
                "removed_from_channel": False,
                "telegram_invite_link": invite,
                "grace_period_end_date": None,
                "updated_at": utcnow_iso(),
                "notes": (doc.get("notes") or "") + f"\n[Reactivated {utcnow_iso()}] {req.reason or ''}",
            }
        },
    )
    return await _get_subscriber(sub_id)


@api.post("/subscribers/{sub_id}/comp")
async def grant_comp(sub_id: str, req: ManualActionRequest, _: str = Depends(require_admin)):
    doc = await _get_subscriber(sub_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    invite = doc.get("telegram_invite_link") or await tg.create_invite_link(doc.get("name", "member"))
    await db.subscribers.update_one(
        {"id": sub_id},
        {
            "$set": {
                "subscription_status": "ADMIN_COMP",
                "telegram_invite_link": invite,
                "updated_at": utcnow_iso(),
                "notes": (doc.get("notes") or "") + f"\n[COMP granted {utcnow_iso()}] {req.reason or ''}",
            }
        },
    )
    return await _get_subscriber(sub_id)


# ---------------- Public checkout ----------------
@api.get("/public/plan")
async def public_plan():
    return {
        "plan_name": PLAN_NAME,
        "amount_inr": PLAN_AMOUNT,
        "razorpay_key_id": os.environ.get("RAZORPAY_KEY_ID", ""),
        "razorpay_configured": not rzp.is_placeholder(),
        "channel_name": os.environ.get("TELEGRAM_CHANNEL_NAME", "FnO Tattva Morning Brief"),
    }


@api.post("/public/checkout", response_model=CheckoutCreateResponse)
async def public_checkout(req: CheckoutCreateRequest):
    """Create a Razorpay subscription for a new/existing customer and return details for
    the frontend Razorpay checkout modal."""
    email = req.email.lower()
    existing = await db.subscribers.find_one({"email": email}, {"_id": 0})
    plan_id = PLAN_ID or "plan_placeholder"
    sub_resp = rzp.create_subscription(
        plan_id=plan_id,
        total_count=12,
        notes={"name": req.name, "email": email, "mobile": req.mobile},
    )
    sub_id = sub_resp["id"]
    is_mock = sub_resp.get("mocked", False)

    if existing:
        await db.subscribers.update_one(
            {"email": email},
            {
                "$set": {
                    "razorpay_subscription_id": sub_id,
                    "name": req.name,
                    "mobile": req.mobile,
                    "updated_at": utcnow_iso(),
                }
            },
        )
    else:
        s = Subscriber(
            name=req.name, mobile=req.mobile, email=email,
            plan_name=PLAN_NAME, amount=PLAN_AMOUNT,
            subscription_status="ACTIVE" if is_mock else "GRACE",
            razorpay_subscription_id=sub_id,
            start_date=utcnow_iso(),
        )
        await db.subscribers.insert_one(s.model_dump())

    return CheckoutCreateResponse(
        subscription_id=sub_id,
        razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID", ""),
        plan_name=PLAN_NAME,
        amount=PLAN_AMOUNT,
        customer_name=req.name,
        customer_email=email,
        customer_mobile=req.mobile,
        is_placeholder=is_mock,
    )


# ---------------- Razorpay Webhook ----------------
@api.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    valid = rzp.verify_webhook_signature(body, signature)
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": body.decode(errors="ignore")}

    if not valid:
        await _log_webhook(payload.get("event", "unknown"), False, payload, False, "invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = payload.get("event", "")
    err: Optional[str] = None
    try:
        await _handle_event(event, payload)
    except Exception as e:
        err = str(e)
        logger.exception("webhook handler failed")

    await _log_webhook(event, valid, payload, err is None, err)
    return {"ok": True, "event": event, "processed": err is None}


async def _find_subscriber_by_sub(sub_id: Optional[str], email: Optional[str] = None) -> Optional[dict]:
    if sub_id:
        doc = await db.subscribers.find_one({"razorpay_subscription_id": sub_id}, {"_id": 0})
        if doc:
            return doc
    if email:
        return await db.subscribers.find_one({"email": email.lower()}, {"_id": 0})
    return None


async def _handle_event(event: str, payload: dict):
    entity = (
        payload.get("payload", {}).get("subscription", {}).get("entity")
        or payload.get("payload", {}).get("payment", {}).get("entity")
        or payload.get("payload", {}).get("refund", {}).get("entity")
        or {}
    )
    sub_id = entity.get("subscription_id") or entity.get("id") if event.startswith("subscription.") else entity.get("subscription_id")
    payment_id = entity.get("id") if event.startswith("payment.") else entity.get("payment_id")
    amount_paise = entity.get("amount")
    amount = float(amount_paise) / 100 if isinstance(amount_paise, (int, float)) else None
    email_hint = (entity.get("notes") or {}).get("email") if isinstance(entity.get("notes"), dict) else None

    doc = await _find_subscriber_by_sub(sub_id, email_hint)

    async def upsert(fields: dict):
        fields["updated_at"] = utcnow_iso()
        if doc:
            await db.subscribers.update_one({"id": doc["id"]}, {"$set": fields})

    if event == "subscription.authenticated":
        # Create subscriber if not present
        if not doc:
            notes = entity.get("notes") or {}
            s = Subscriber(
                name=notes.get("name", "Unknown"),
                mobile=notes.get("mobile", ""),
                email=(notes.get("email") or f"unknown-{sub_id}@fnotattva.local").lower(),
                plan_name=PLAN_NAME, amount=PLAN_AMOUNT,
                subscription_status="ACTIVE",
                razorpay_subscription_id=sub_id,
                start_date=utcnow_iso(),
            )
            invite = await tg.create_invite_link(s.name)
            s.telegram_invite_link = invite
            await db.subscribers.insert_one(s.model_dump())
        else:
            invite = doc.get("telegram_invite_link") or await tg.create_invite_link(doc.get("name", "member"))
            await upsert({
                "subscription_status": "ACTIVE",
                "telegram_invite_link": invite,
                "last_payment_status": "authenticated",
            })

    elif event == "subscription.activated":
        await upsert({"subscription_status": "ACTIVE", "last_payment_status": "activated"})

    elif event == "subscription.charged":
        next_charge_at = entity.get("charge_at") or entity.get("current_end")
        upd = {"subscription_status": "ACTIVE", "last_payment_status": "charged"}
        if next_charge_at:
            upd["next_billing_date"] = datetime.fromtimestamp(int(next_charge_at), tz=timezone.utc).isoformat()
        await upsert(upd)
        await _record_payment(doc["id"] if doc else None, sub_id, payment_id, amount, "captured", entity.get("method"), "subscription.charged")

    elif event in ("subscription.pending", "payment.failed"):
        grace_end = datetime.now(timezone.utc) + timedelta(days=GRACE_DAYS)
        await upsert({
            "subscription_status": "GRACE",
            "last_payment_status": "failed" if event == "payment.failed" else "pending",
            "grace_period_end_date": grace_end.isoformat(),
        })
        await _record_payment(doc["id"] if doc else None, sub_id, payment_id, amount, "failed", entity.get("method"), event)

    elif event == "subscription.halted":
        await upsert({"subscription_status": "EXPIRED", "last_payment_status": "halted"})
        if doc and doc.get("telegram_user_id"):
            await tg.ban_user(doc["telegram_user_id"])
            await upsert({"removed_from_channel": True})

    elif event == "subscription.cancelled":
        await upsert({"subscription_status": "CANCELLED", "last_payment_status": "cancelled"})

    elif event == "subscription.completed":
        await upsert({"subscription_status": "EXPIRED", "last_payment_status": "completed"})
        if doc and doc.get("telegram_user_id"):
            await tg.ban_user(doc["telegram_user_id"])
            await upsert({"removed_from_channel": True})

    elif event == "refund.processed":
        await upsert({"subscription_status": "REFUNDED", "last_payment_status": "refunded"})
        await _record_payment(doc["id"] if doc else None, sub_id, payment_id, amount, "refunded", None, "refund.processed")


# ---------------- Webhook logs ----------------
@api.get("/webhook-logs")
async def webhook_logs(limit: int = 100, _: str = Depends(require_admin)):
    docs = await db.webhook_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return docs


# ---------------- Telegram inbound webhook ----------------
TG_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")


@api.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    """Inbound Telegram Bot API webhook. Handles chat_member updates so we can capture
    a subscriber's telegram_user_id + username when they join the private channel via
    their unique invite link."""
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    valid_sig = bool(TG_WEBHOOK_SECRET) and provided == TG_WEBHOOK_SECRET
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        pass

    if not valid_sig:
        await _log_webhook("telegram.unauthorized", False, payload, False, "bad secret token")
        raise HTTPException(status_code=401, detail="Invalid secret token")

    err: Optional[str] = None
    event_name = "telegram." + next(
        (k for k in ("chat_member", "my_chat_member", "message", "chat_join_request") if k in payload),
        "unknown",
    )
    try:
        await _handle_telegram_update(payload)
    except Exception as e:
        err = str(e)
        logger.exception("telegram webhook handler failed")

    await _log_webhook(event_name, True, payload, err is None, err)
    return {"ok": True}


async def _handle_telegram_update(update: dict):
    """Extract user join events and match them back to a subscriber via invite link."""
    cm = update.get("chat_member") or update.get("my_chat_member")
    if not cm:
        # Also handle when a user DMs the bot for the first time — capture their id
        msg = update.get("message")
        if msg:
            frm = msg.get("from") or {}
            if frm.get("id"):
                # try to bind DM sender to subscriber by matching bot start payload (email)
                text = msg.get("text", "")
                if text.startswith("/start"):
                    parts = text.split(maxsplit=1)
                    if len(parts) == 2:
                        payload_arg = parts[1].strip().lower()
                        # payload could be an email or a subscriber id
                        target = await db.subscribers.find_one(
                            {"$or": [{"email": payload_arg}, {"id": payload_arg}]},
                            {"_id": 0},
                        )
                        if target:
                            await db.subscribers.update_one(
                                {"id": target["id"]},
                                {"$set": {
                                    "telegram_user_id": str(frm["id"]),
                                    "telegram_username": frm.get("username"),
                                    "updated_at": utcnow_iso(),
                                }},
                            )
        return

    new_status = (cm.get("new_chat_member") or {}).get("status")
    old_status = (cm.get("old_chat_member") or {}).get("status")
    user = (cm.get("new_chat_member") or {}).get("user") or (cm.get("from") or {})
    user_id = user.get("id")
    username = user.get("username")
    chat_id = str((cm.get("chat") or {}).get("id") or "")
    invite = cm.get("invite_link") or {}
    invite_url = invite.get("invite_link")

    # Only care about our configured channel
    if chat_id and os.environ.get("TELEGRAM_CHANNEL_ID") and chat_id != os.environ["TELEGRAM_CHANNEL_ID"]:
        return

    joined_now = new_status in ("member", "administrator", "creator") and old_status in ("left", "kicked", None, "restricted")
    left_now = new_status in ("left", "kicked") and old_status in ("member", "administrator", "creator", "restricted")

    if joined_now and user_id:
        # Match to subscriber by invite_link URL
        doc = None
        if invite_url:
            doc = await db.subscribers.find_one({"telegram_invite_link": invite_url}, {"_id": 0})
        if not doc and username:
            doc = await db.subscribers.find_one({"telegram_username": username}, {"_id": 0})

        if doc:
            await db.subscribers.update_one(
                {"id": doc["id"]},
                {"$set": {
                    "telegram_user_id": str(user_id),
                    "telegram_username": username,
                    "telegram_joined": True,
                    "removed_from_channel": False,
                    "updated_at": utcnow_iso(),
                }},
            )
            logger.info(f"Bound telegram user {user_id}(@{username}) to subscriber {doc.get('email')}")
        else:
            logger.warning(f"Telegram user {user_id}(@{username}) joined but no matching subscriber found (invite={invite_url})")

    if left_now and user_id:
        await db.subscribers.update_one(
            {"telegram_user_id": str(user_id)},
            {"$set": {"telegram_joined": False, "removed_from_channel": True, "updated_at": utcnow_iso()}},
        )



# ---------------- Payments ----------------
@api.get("/payments")
async def payments(subscriber_id: Optional[str] = None, status: Optional[str] = None, limit: int = 200, _: str = Depends(require_admin)):
    q: dict = {}
    if subscriber_id:
        q["subscriber_id"] = subscriber_id
    if status:
        q["status"] = status
    docs = await db.payments.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return docs


# ---------------- Reports ----------------
@api.get("/reports")
async def list_reports(_: str = Depends(require_admin)):
    docs = await db.reports.find({}, {"_id": 0}).sort("uploaded_at", -1).to_list(200)
    return docs


@api.post("/reports/upload")
async def upload_report(
    file: UploadFile = File(...),
    caption: str = Form(""),
    _: str = Depends(require_admin),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    rid = new_id()
    safe_name = f"{rid}_{Path(file.filename).name}"
    dest = UPLOAD_DIR / safe_name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    rec = ReportRecord(id=rid, filename=file.filename, stored_path=str(dest), caption=caption)
    await db.reports.insert_one(rec.model_dump())
    return rec


@api.post("/reports/{report_id}/send")
async def send_report_now(report_id: str, _: str = Depends(require_admin)):
    rec = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    result = await tg.send_channel_document(rec["stored_path"], rec.get("caption") or f"📈 FnO Tattva Morning Brief — {datetime.now(IST).strftime('%d %b %Y')}")
    status = "SENT" if result.get("ok") else "FAILED"
    err = None if result.get("ok") else str(result)
    await db.reports.update_one(
        {"id": report_id},
        {"$set": {"delivery_status": status, "sent_at": utcnow_iso(), "delivery_error": err}},
    )
    return {"ok": result.get("ok", False), "mocked": result.get("mocked", False)}


@api.delete("/reports/{report_id}")
async def delete_report(report_id: str, _: str = Depends(require_admin)):
    rec = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        Path(rec["stored_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    await db.reports.delete_one({"id": report_id})
    return {"ok": True}


# ---------------- Notifications ----------------
@api.get("/notifications/templates")
async def get_templates(_: str = Depends(require_admin)):
    return notif.list_templates()


@api.post("/notifications/send")
async def send_notification(req: NotificationSendRequest, _: str = Depends(require_admin)):
    doc = await _get_subscriber(req.subscriber_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    ctx = {
        "name": doc.get("name", "Subscriber"),
        "invite_link": doc.get("telegram_invite_link") or "—",
        "grace_end": doc.get("grace_period_end_date") or "—",
    }
    if req.extra:
        ctx.update(req.extra)
    rendered = notif.render(req.template_key, ctx)
    if not rendered:
        raise HTTPException(status_code=400, detail="Unknown template")
    ok = False
    if doc.get("telegram_user_id"):
        ok = await tg.send_direct_message(doc["telegram_user_id"], f"<b>{rendered['title']}</b>\n\n{rendered['body']}")
    return {"ok": ok, "preview": rendered, "delivered_via_telegram_dm": ok}


# ---------------- Scheduler jobs ----------------
async def job_daily_report():
    """At 7 AM IST, send the most recently uploaded pending report."""
    logger.info("Running daily report job")
    rec = await db.reports.find_one({"delivery_status": "PENDING"}, sort=[("uploaded_at", -1)])
    if not rec:
        logger.info("No pending report to send")
        return
    result = await tg.send_channel_document(
        rec["stored_path"],
        rec.get("caption") or f"📈 FnO Tattva Morning Brief — {datetime.now(IST).strftime('%d %b %Y')}",
    )
    status = "SENT" if result.get("ok") else "FAILED"
    await db.reports.update_one(
        {"id": rec["id"]},
        {"$set": {"delivery_status": status, "sent_at": utcnow_iso(), "delivery_error": None if result.get("ok") else str(result)}},
    )


async def job_grace_expiry():
    """Move GRACE users to EXPIRED after grace_period_end_date, remove from channel."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = db.subscribers.find(
        {"subscription_status": "GRACE", "grace_period_end_date": {"$lte": now}},
        {"_id": 0},
    )
    async for doc in cursor:
        logger.info(f"Grace expired for {doc.get('email')}")
        if doc.get("telegram_user_id"):
            await tg.ban_user(doc["telegram_user_id"])
        await db.subscribers.update_one(
            {"id": doc["id"]},
            {"$set": {
                "subscription_status": "EXPIRED",
                "removed_from_channel": True,
                "updated_at": utcnow_iso(),
            }},
        )


scheduler: Optional[AsyncIOScheduler] = None


# ---------------- Startup ----------------
@app.on_event("startup")
async def on_start():
    await seed_admin()
    global scheduler
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(job_daily_report, CronTrigger(hour=DAILY_HOUR, minute=DAILY_MIN), id="daily_report")
    scheduler.add_job(job_grace_expiry, IntervalTrigger(minutes=30), id="grace_expiry")
    scheduler.start()
    logger.info(f"Scheduler started. Daily report at {DAILY_HOUR:02d}:{DAILY_MIN:02d} IST")

    # Register Telegram webhook (best effort)
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if base and TG_WEBHOOK_SECRET:
        try:
            result = await tg.set_webhook(f"{base}/api/webhooks/telegram", TG_WEBHOOK_SECRET)
            logger.info(f"Telegram setWebhook: {result}")
        except Exception as e:
            logger.warning(f"Telegram setWebhook failed: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    if scheduler:
        scheduler.shutdown(wait=False)
    client.close()


# ---------------- Wire up ----------------
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
