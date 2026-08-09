"""
Notifications (spec section 13).

v1 ships a working "in_app" channel (every alert is stored in `alerts` and
surfaced on the dashboard / alerts page — this is the "simplest reliable
notification mechanism supported by the environment" the spec asks for).

email and telegram are implemented as real, working senders IF credentials
are present in the environment (SMTP_* / TELEGRAM_*), so turning them on
later is a config change, not a rewrite. WhatsApp is not implemented: the
only legitimate/legal path is the paid WhatsApp Business Cloud API, which
needs a Meta developer account + phone number registration — out of scope
for a v1 personal tool with no such account, and documented here rather
than faked.

Every send attempt (including "skipped, no channel configured") is logged
to notification_history so history is always complete and honest.
"""
import smtplib
from email.mime.text import MIMEText

import db
import config
import repository as repo


def get_recipients():
    """Recipient list, preferring the DB setting (editable from the Settings
    page, no redeploy needed) and falling back to the NOTIFY_EMAIL_TO env
    var. Always a list, e.g. ["islam@x.com", "fiancee@y.com"]."""
    stored = db.get_setting("notify_email_to", None)
    if stored:
        if isinstance(stored, str):
            return [e.strip() for e in stored.split(",") if e.strip()]
        return [e for e in stored if e]
    return list(config.NOTIFY_EMAIL_TO_LIST)


def _send_email(subject, body):
    recipients = get_recipients()
    if not (config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD and recipients):
        return False, "Email not configured (SMTP_HOST/SMTP_USER/SMTP_PASSWORD missing, or no recipient emails set in Settings)."
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = config.SMTP_USER
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, recipients, msg.as_string())
        return True, f"sent to {', '.join(recipients)}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _send_telegram(text):
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return False, "Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing)."
    try:
        import requests
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        if resp.status_code == 200:
            return True, "sent"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def format_alert_text(alert):
    lines = [
        "PRICE ALERT",
        alert.get("message", ""),
    ]
    if alert.get("recommendation"):
        lines.append(f"Recommendation: {alert['recommendation']}")
    return "\n".join(lines)


def send(alert_id):
    alert = db.query_one("SELECT * FROM alerts WHERE id=?", (alert_id,))
    if alert is None:
        return
    alert = dict(alert)
    text = format_alert_text(alert)

    channels = db.get_setting("notification_channels", config.NOTIFICATION_CHANNELS)

    # in_app: the alert row itself IS the notification; just log it.
    if "in_app" in channels:
        repo.log_notification(alert_id, "in_app", "sent", "Surfaced in dashboard/alerts page.")

    if "email" in channels:
        ok, detail = _send_email(f"Price Alert: {alert.get('message','')[:60]}", text)
        repo.log_notification(alert_id, "email", "sent" if ok else "failed", detail)

    if "telegram" in channels:
        ok, detail = _send_telegram(text)
        repo.log_notification(alert_id, "telegram", "sent" if ok else "failed", detail)

    if "whatsapp" in channels:
        repo.log_notification(alert_id, "whatsapp", "skipped",
                               "WhatsApp not implemented in v1 — requires WhatsApp Business Cloud API credentials.")
