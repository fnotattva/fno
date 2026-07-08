"""Notification templates and dispatcher (Telegram DM based)."""
from typing import Optional

TEMPLATES = {
    "welcome": {
        "title": "Welcome to FnO Tattva Morning Brief",
        "body": (
            "Namaste {name},\n\n"
            "Your subscription is <b>ACTIVE</b>. Join our private Telegram channel using the link below "
            "to receive the daily Morning Market Brief at 7:00 AM IST:\n\n"
            "{invite_link}\n\n"
            "This link is single-use and expires. Do not share it.\n"
            "— Team FnO Tattva"
        ),
    },
    "payment_failed": {
        "title": "Payment Failed",
        "body": (
            "Hi {name},\n\n"
            "Your recent payment for FnO Tattva Morning Brief failed. "
            "You have a <b>2-day grace period</b> to update your payment method before access is paused.\n\n"
            "Please retry or contact support.\n"
            "— Team FnO Tattva"
        ),
    },
    "grace_reminder": {
        "title": "Grace Period Reminder",
        "body": (
            "Hi {name},\n\n"
            "Reminder: your subscription is in the grace window ending on <b>{grace_end}</b>. "
            "Please clear the pending dues to avoid losing access to the Morning Brief channel.\n"
            "— Team FnO Tattva"
        ),
    },
    "access_paused": {
        "title": "Access Paused",
        "body": (
            "Hi {name},\n\n"
            "Your access to the FnO Tattva private channel has been paused due to a failed payment. "
            "Reactivate anytime to regain access.\n"
            "— Team FnO Tattva"
        ),
    },
    "reactivation_success": {
        "title": "Welcome Back",
        "body": (
            "Hi {name},\n\n"
            "Your subscription is <b>reactivated</b>. Your new invite link:\n\n"
            "{invite_link}\n\n"
            "— Team FnO Tattva"
        ),
    },
    "daily_report_live": {
        "title": "Morning Brief is Live",
        "body": (
            "Hi {name},\n\n"
            "Today's FnO Tattva Morning Brief has been published in the private channel. "
            "Open Telegram to read it now.\n"
            "— Team FnO Tattva"
        ),
    },
}


def render(template_key: str, ctx: dict) -> Optional[dict]:
    tpl = TEMPLATES.get(template_key)
    if not tpl:
        return None
    return {
        "title": tpl["title"],
        "body": tpl["body"].format(
            name=ctx.get("name", "Subscriber"),
            invite_link=ctx.get("invite_link", "—"),
            grace_end=ctx.get("grace_end", "—"),
        ),
    }


def list_templates() -> list:
    return [{"key": k, "title": v["title"], "body": v["body"]} for k, v in TEMPLATES.items()]
