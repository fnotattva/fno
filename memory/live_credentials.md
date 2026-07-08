# FnO Tattva — Production (LIVE) credentials backup

Purpose: Stashed here before switching to Razorpay TEST mode for end-to-end testing.
After testing is done, restore these to /app/backend/.env.

## Razorpay LIVE (as of switch-over)
- RAZORPAY_KEY_ID = rzp_live_TAwbdxpgxtxj41
- RAZORPAY_KEY_SECRET = tKKHoTFJysKbDMzQ7WPz54B4
- RAZORPAY_WEBHOOK_SECRET = HMQT9Tm_XFzeWn5
- RAZORPAY_PLAN_ID = plan_TAwigLhJZf3D4W
- PLAN_NAME = FnO Tattva Morning Brief
- PLAN_AMOUNT_INR = 149

## Telegram (unchanged — same for test + live)
- TELEGRAM_BOT_TOKEN = 8969330587:AAHeNY_S29gBDJ5IDIeLyBpGf2PrW4RQgVw
- TELEGRAM_CHANNEL_ID = -1002781197002
- TELEGRAM_WEBHOOK_SECRET = fnotattva-tg-hook-2026

## Admin (unchanged)
- ADMIN_EMAIL = admin@fnotattva.com
- ADMIN_PASSWORD = FnoTattva@2026

## Webhook URLs currently registered on Razorpay
- Production URL: (whatever the user has configured, using webhook secret HMQT9Tm_XFzeWn5)
- Preview URL: https://fno-access-hub.preview.emergentagent.com/api/webhooks/razorpay
