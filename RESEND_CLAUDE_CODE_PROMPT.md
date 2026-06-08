# Resend Email Migration — Claude Code Handoff

## Objective
Migrate all transactional email (OTP + order notifications + design handoff) in the FastAPI backend from the current SendGrid/SMTP provider chain to **Resend only**, using the official `resend` Python SDK. Rip out SendGrid and SMTP send paths entirely. Keep the mock path for local dev/tests.

## Context / decisions (already made — do not re-litigate)
- **Provider strategy:** Resend ONLY. Remove SendGrid + SMTP send code. No fallback chain.
- **Implementation:** Official `resend` Python SDK (not raw httpx).
- **Domain:** `cellhubms.com` is verified in Resend. Sending confirmed working via curl (returns a message `id`).
- **From identity (already in `backend/.env`):**
  - `RESEND_API_KEY` — present
  - `RESEND_FROM_EMAIL=no-reply@cellhubms.com`  ← add if missing
  - `RESEND_FROM_NAME=CellHub`  ← add if missing
- All email currently funnels through `app/services/email_service.py`. No route/service callers change — only this service + config + deps + tests.

## Scope — files to change
1. `backend/requirements.txt`
2. `backend/app/core/config.py`
3. `backend/app/services/email_service.py`
4. `backend/.env` and `backend/.env.example`
5. `backend/tests/` (any test asserting SendGrid/SMTP behavior)

---

## 1. `backend/requirements.txt`
Add:
```
resend>=2.0.0
```
Then install into the backend venv: `pip install -r requirements.txt` (venv at `backend/.venv`).

## 2. `backend/app/core/config.py`
Add these fields to the `Settings` class:
```python
resend_api_key: str = Field(default='', alias='RESEND_API_KEY')
resend_from_email: str = Field(default='', alias='RESEND_FROM_EMAIL')
resend_from_name: str = Field(default='SecureOffice2', alias='RESEND_FROM_NAME')
```
Remove the now-unused SendGrid + SMTP fields (`smtp_*`, `sendgrid_*`). Keep `design_handoff_email`. Grep the codebase for any other readers of those removed settings before deleting (`smtp_`, `sendgrid_`) and clean them up.

## 3. `backend/app/services/email_service.py` — rewrite
This is the core change. Current file has: `_smtp_enabled`, `_send_smtp_message`, `_mask_secret`, `_send_via_sendgrid`, OTP composers, `send_otp_email`, design-submission composer + `send_design_submission_handoff`, order composers + `send_order_capture_handoff`.

**Keep:** all HTML/text composer methods unchanged —
`_compose_otp_text`, `_compose_otp_html`, `_compose_order_capture_text`, `_compose_order_capture_html`, and the design submission body builder (extract its text/html out of the `EmailMessage` builder into plain strings).

**Delete:** `_smtp_enabled`, `_send_smtp_message`, `_send_via_sendgrid`, and the `EmailMessage`-returning builders (`_compose_otp_message`, `_compose_order_capture_message`, `_compose_design_submission_message`). Keep `_mask_secret` (still useful for logging).

**Add** a single send helper:
```python
import logging
import resend
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
resend.api_key = (settings.resend_api_key or '').strip()


class EmailService:
    @staticmethod
    def _resend_enabled() -> bool:
        return bool((settings.resend_api_key or '').strip())

    @staticmethod
    def _send_via_resend(*, to_emails: list[str], subject: str,
                         text_content: str, html_content: str) -> str | None:
        if not EmailService._resend_enabled():
            raise RuntimeError('RESEND_API_KEY is not configured')
        from_email = (settings.resend_from_email or '').strip()
        if not from_email:
            raise RuntimeError('RESEND_FROM_EMAIL is required')
        from_name = (settings.resend_from_name or 'SecureOffice2').strip()
        logger.warning(
            '[RESEND ATTEMPT] recipients_count=%d from=%s <%s> subject=%s',
            len(to_emails), from_name, from_email, subject,
        )
        resp = resend.Emails.send({
            'from': f'{from_name} <{from_email}>',
            'to': to_emails,
            'subject': subject,
            'html': html_content,
            'text': text_content,
        })
        # SDK returns a dict-like with 'id'
        msg_id = resp.get('id') if isinstance(resp, dict) else getattr(resp, 'id', None)
        logger.warning('[RESEND SUCCESS] message_id=%s recipients_count=%d', msg_id, len(to_emails))
        return msg_id
```

**Rewrite the three public methods** to call `_send_via_resend()` directly, preserving the mock path when the key is absent:

```python
    @staticmethod
    def send_otp_email(*, to_email: str, otp: str, purpose: str) -> None:
        subject = f'SecureOffice2 OTP for {purpose}'
        text_body = EmailService._compose_otp_text(otp=otp, purpose=purpose)
        html_body = EmailService._compose_otp_html(otp=otp, purpose=purpose)
        if not EmailService._resend_enabled():
            print(f'[MOCK OTP DELIVERY] email={to_email} otp={otp} purpose={purpose}')
            return
        EmailService._send_via_resend(
            to_emails=[to_email], subject=subject,
            text_content=text_body, html_content=html_body,
        )
        logger.warning('[OTP EMAIL COMPLETED] to=%s channel=resend purpose=%s', to_email, purpose)
```
Apply the same shape to:
- `send_order_capture_handoff(*, payload, recipients)` — normalize/dedupe recipients as it does today, mock when empty or key absent, else `_send_via_resend(to_emails=target_emails, ...)` with the existing order composers. Subject: `f"Order Captured: {payload.get('order_id')}"`.
- `send_design_submission_handoff(payload)` — resolve mailbox (`settings.design_handoff_email`), mock when key absent or no mailbox, else send via Resend using the extracted design body strings. **Do not leave this on SMTP** — it will break once SMTP config is removed.

## 4. Env files
`backend/.env` — ensure present (do not commit real key):
```
RESEND_API_KEY=<real key, keep only here>
RESEND_FROM_EMAIL=no-reply@cellhubms.com
RESEND_FROM_NAME=CellHub
```
`backend/.env.example` — add the same keys with placeholder values; remove the `SMTP_*` and `SENDGRID_*` entries.

## 5. Tests
- Update anything in `backend/tests/` that patches/asserts SendGrid (`_send_via_sendgrid`, `api.sendgrid.com`) or SMTP (`smtplib`).
- New approach: monkeypatch `resend.Emails.send` to return `{'id': 'test_...'}` and assert it was called with the expected `from`/`to`/`subject`/`html`/`text`.
- Add a test asserting the mock path runs (no exception, no send) when `RESEND_API_KEY` is empty.

---

## Verification (must pass before done)
1. `cd backend && source .venv/bin/activate && pip install -r requirements.txt`
2. Import check: `python -c "from app.services.email_service import EmailService; from app.core.config import get_settings; print('ok')"`
3. App boots: `python -c "from app.main import app; print('app ok')"` (or start uvicorn briefly).
4. `pytest` green.
5. Grep confirms removal: `grep -rin "sendgrid\|smtplib\|_send_smtp\|api.sendgrid" app/` returns nothing in source (excluding venv).
6. Live smoke (optional, real key): trigger one OTP send to your own address and one order-capture; confirm a Resend `message_id` appears in logs.

## Watch-outs
- `send_design_submission_handoff` is the easy-to-miss third sender — migrate it too.
- Don't delete the OTP/order **composer** methods, only the `EmailMessage` builders and provider methods.
- `resend.api_key` is set at module import from settings — confirm it's read after env load (it is, via `get_settings()`).
- Keep all existing throttle/rate-limit/OTP-attempt logic in callers untouched; this change is provider-only.
