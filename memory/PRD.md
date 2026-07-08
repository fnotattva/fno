# FnO Tattva — Morning Market Brief · Subscription Access Management

## Original Problem Statement
Build a production-ready subscription access management system for FnO Tattva's daily 7:00 AM Morning Market Brief. Users subscribe monthly via Razorpay Subscriptions (UPI AutoPay / Cards); only ACTIVE paid users retain access to a private Telegram channel where the daily PDF is delivered. Access is automatically revoked after failed payment + 2-day grace.

## Chosen Stack (user decision)
- Backend: **FastAPI (Python) + MongoDB** (Motor async)
- Frontend: **React + Tailwind + shadcn**
- Scheduling: APScheduler (IST)
- Auth: JWT (bcrypt hashed admin passwords)
- Integrations: Razorpay (subscriptions + webhooks), Telegram Bot API (invite links, ban/unban, sendDocument)
- WhatsApp: removed per user request

## User Personas
1. **Admin (Operator)** — logs into `/admin`, manages subscribers, uploads daily PDF, monitors webhooks/payments, sends manual notifications.
2. **Subscriber (Trader)** — visits landing page, subscribes monthly via Razorpay, joins private Telegram channel via unique invite link, consumes daily brief.

## Core Requirements (Static)
- User statuses: ACTIVE, GRACE, EXPIRED, CANCELLED, REFUNDED, ADMIN_COMP.
- Razorpay webhook events handled: subscription.authenticated/activated/charged/pending/halted/cancelled/completed, payment.failed, refund.processed.
- Telegram: single-use invite links, ban/unban via user_id, PDF sendDocument to channel.
- Scheduler: daily 07:00 IST auto-send of latest pending report; every 30 min grace-period expiry cron (auto-moves GRACE → EXPIRED after 2 days and bans from channel).
- Security: bcrypt password, JWT bearer, Razorpay webhook HMAC-SHA256 signature verification, .env-only secrets.

## What's Been Implemented (v1.0 · 2026-01-08)
- **Public Landing / Checkout** (`/`) — asymmetric hero, live pricing card, subscribe form.
- **Admin auth** — `/admin/login` + JWT bearer, protected routes.
- **Admin dashboard** (`/admin`) — integration health, KPI grid by status, MRR + failed-24h cards, recent signups.
- **Subscribers page** — search (name/email/mobile), filter by all 7 statuses, add/edit/delete, manual reactivate, manual COMP grant, remove-from-channel.
- **Payments ledger** — records from webhook events, filter by status, KPI totals.
- **Reports library** — PDF upload with caption, list, "Send now" push to channel, delivery status tracking, delete.
- **Webhook logs** — full payload viewer, signature-valid indicator.
- **Notifications** — 6 templates (welcome, payment_failed, grace_reminder, access_paused, reactivation_success, daily_report_live), preview + send to any subscriber via Telegram DM.
- **Razorpay Subscriptions** (Python SDK) with HMAC-SHA256 webhook signature verification.
- **Telegram service** — createChatInviteLink (single-use), banChatMember, unbanChatMember, sendDocument, sendMessage.
- **Scheduler** — daily 07:00 IST auto-send + 30-min grace-expiry cron.
- **Placeholder mode** — when Razorpay/Telegram env vars start with "placeholder", integrations return mocked success responses so the UI/logic can be tested end-to-end without real keys.

## Testing Status
- Backend: 31/31 pytest tests pass (auth, subscribers, webhooks, reports, notifications).
- Frontend: Playwright validated all admin flows and public checkout.

## Prioritized Backlog
### P1 (do next)
- Wire in real Razorpay/Telegram credentials — replace placeholders in `/app/backend/.env`, create actual plan in Razorpay dashboard, register webhook URL.
- Add Telegram Bot webhook listener (`/api/webhooks/telegram`) to capture `chat_join_request` / new_chat_members events → auto-populate `telegram_user_id`, `telegram_username`, `telegram_joined=true` on the matching subscriber.
- Rate-limit `/api/public/checkout` (IP + email).

### P2
- Refactor `server.py` into routers (auth, subscribers, webhooks, reports, notifications) and services.
- Retry queue for failed Telegram sends (exponential backoff).
- Email fallback (Resend/SendGrid) for notifications when subscriber never DM'd the bot.
- Export subscribers CSV.
- 2FA / TOTP for admin login.

### P3
- Multi-admin roles.
- Referral / affiliate codes with revenue-share tracking.
- Retention analytics dashboard (cohort MRR, churn).

## Next Tasks
1. Collect real Razorpay + Telegram credentials from operator and replace placeholders in `.env`.
2. Implement Telegram inbound webhook (see P1 above).
3. Add rate-limiting.
