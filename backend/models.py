"""Pydantic models for FnO Tattva Subscription Access Management."""
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, ConfigDict
import uuid


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------------- Auth ----------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    name: str = "Admin"


# ---------------- Subscriber ----------------
class SubscriberBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    mobile: str
    email: EmailStr
    plan_name: Optional[str] = None
    amount: Optional[float] = None
    subscription_status: str = "ACTIVE"
    notes: Optional[str] = ""


class SubscriberCreate(SubscriberBase):
    pass


class SubscriberUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[EmailStr] = None
    plan_name: Optional[str] = None
    amount: Optional[float] = None
    subscription_status: Optional[str] = None
    notes: Optional[str] = None
    telegram_user_id: Optional[str] = None
    telegram_username: Optional[str] = None


class Subscriber(SubscriberBase):
    id: str = Field(default_factory=new_id)
    razorpay_customer_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None
    telegram_user_id: Optional[str] = None
    telegram_username: Optional[str] = None
    telegram_invite_link: Optional[str] = None
    start_date: Optional[str] = None
    next_billing_date: Optional[str] = None
    grace_period_end_date: Optional[str] = None
    last_payment_status: Optional[str] = None
    telegram_joined: bool = False
    removed_from_channel: bool = False
    created_at: str = Field(default_factory=utcnow_iso)
    updated_at: str = Field(default_factory=utcnow_iso)


# ---------------- Payment ----------------
class PaymentRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    subscriber_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "INR"
    status: str  # captured, failed, pending, refunded
    method: Optional[str] = None
    description: Optional[str] = None
    created_at: str = Field(default_factory=utcnow_iso)


# ---------------- Webhook Log ----------------
class WebhookLog(BaseModel):
    id: str = Field(default_factory=new_id)
    event: str
    signature_valid: bool
    payload: dict
    processed: bool = False
    error: Optional[str] = None
    created_at: str = Field(default_factory=utcnow_iso)


# ---------------- Report ----------------
class ReportRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    filename: str
    stored_path: str
    caption: Optional[str] = None
    uploaded_at: str = Field(default_factory=utcnow_iso)
    sent_at: Optional[str] = None
    delivery_status: str = "PENDING"  # PENDING, SENT, FAILED
    delivery_error: Optional[str] = None


# ---------------- Public checkout ----------------
class CheckoutCreateRequest(BaseModel):
    name: str
    mobile: str
    email: EmailStr


class CheckoutCreateResponse(BaseModel):
    subscription_id: str
    razorpay_key_id: str
    plan_name: str
    amount: float
    customer_name: str
    customer_email: str
    customer_mobile: str
    is_placeholder: bool = False


# ---------------- Notification ----------------
class NotificationSendRequest(BaseModel):
    subscriber_id: str
    template_key: str  # welcome, payment_failed, grace_reminder, access_paused, reactivation_success, daily_report_live
    extra: Optional[dict] = None


class ManualActionRequest(BaseModel):
    reason: Optional[str] = ""
