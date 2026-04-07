import smtplib
import logging
import httpx
from email.message import EmailMessage
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def _smtp_enabled() -> bool:
        return bool(settings.smtp_host and settings.smtp_from_email)

    @staticmethod
    def _send_smtp_message(message: EmailMessage) -> None:
        logger.warning(
            '[SMTP SEND ATTEMPT] to=%s subject=%s host=%s port=%s ssl=%s tls=%s auth=%s',
            message.get('To'),
            message.get('Subject'),
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_use_ssl,
            settings.smtp_use_tls,
            bool(settings.smtp_username),
        )
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
            logger.warning('[SMTP SEND SUCCESS] to=%s subject=%s', message.get('To'), message.get('Subject'))
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        logger.warning('[SMTP SEND SUCCESS] to=%s subject=%s', message.get('To'), message.get('Subject'))

    @staticmethod
    def _mask_secret(value: str) -> str:
        clean = (value or '').strip()
        if not clean:
            return ''
        if len(clean) <= 8:
            return '***'
        return f'{clean[:4]}...{clean[-4:]}'

    @staticmethod
    def _send_via_sendgrid(
        *,
        to_emails: list[str],
        subject: str,
        text_content: str,
        html_content: str,
    ) -> None:
        api_key = (settings.sendgrid_api_key or '').strip()
        if not api_key:
            raise RuntimeError('SENDGRID_API_KEY is not configured')

        from_email = (settings.sendgrid_from_email or settings.smtp_from_email or '').strip()
        if not from_email:
            raise RuntimeError('SENDGRID_FROM_EMAIL (or SMTP_FROM_EMAIL) is required for order notifications')

        from_name = (settings.sendgrid_from_name or settings.smtp_from_name or 'SecureOffice2').strip()
        logger.warning(
            '[SENDGRID ATTEMPT] recipients_count=%d from_email=%s from_name=%s api_key_mask=%s',
            len(to_emails),
            from_email,
            from_name,
            EmailService._mask_secret(api_key),
        )
        payload = {
            'personalizations': [{'to': [{'email': email} for email in to_emails]}],
            'from': {'email': from_email, 'name': from_name},
            'subject': subject,
            'content': [
                {'type': 'text/plain', 'value': text_content},
                {'type': 'text/html', 'value': html_content},
            ],
        }
        response = httpx.post(
            'https://api.sendgrid.com/v3/mail/send',
            json=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=20,
        )
        message_id = response.headers.get('x-message-id') or response.headers.get('X-Message-Id')
        if response.status_code < 200 or response.status_code >= 300:
            excerpt = response.text[:500] if response.text else ''
            logger.error(
                '[SENDGRID ERROR] status_code=%s message_id=%s response_excerpt=%s',
                response.status_code,
                message_id,
                excerpt,
            )
            raise RuntimeError(f'SendGrid delivery failed ({response.status_code}): {excerpt}')
        logger.warning('[SENDGRID SUCCESS] status_code=%s message_id=%s', response.status_code, message_id)

    @staticmethod
    def _compose_otp_message(*, to_email: str, otp: str, purpose: str) -> EmailMessage:
        msg = EmailMessage()
        from_name = settings.smtp_from_name.strip() or 'SecureOffice2'
        msg['From'] = f'{from_name} <{settings.smtp_from_email}>'
        msg['To'] = to_email
        msg['Subject'] = f'SecureOffice2 OTP for {purpose}'
        msg.set_content(
            '\n'.join(
                [
                    'Your SecureOffice2 one-time password is:',
                    '',
                    f'  {otp}',
                    '',
                    f'It expires in {settings.otp_expire_minutes} minutes.',
                    'If you did not request this code, please ignore this email.',
                ]
            )
        )
        return msg

    @staticmethod
    def send_otp_email(*, to_email: str, otp: str, purpose: str) -> None:
        if not EmailService._smtp_enabled():
            print(f'[MOCK OTP DELIVERY] email={to_email} otp={otp} purpose={purpose}')
            return

        message = EmailService._compose_otp_message(to_email=to_email, otp=otp, purpose=purpose)
        EmailService._send_smtp_message(message)

    @staticmethod
    def _compose_design_submission_message(*, to_email: str, payload: dict) -> EmailMessage:
        lead = payload.get('lead') or {}
        msg = EmailMessage()
        from_name = settings.smtp_from_name.strip() or 'SecureOffice2'
        msg['From'] = f'{from_name} <{settings.smtp_from_email}>'
        msg['To'] = to_email
        msg['Subject'] = f"Design Submission: {payload.get('design_name') or payload.get('design_id')}"
        msg.set_content(
            '\n'.join(
                [
                    'A new SMB network design was submitted for demo handoff.',
                    '',
                    f"Design ID: {payload.get('design_id')}",
                    f"Design Name: {payload.get('design_name')}",
                    f"Status: {payload.get('status')}",
                    f"Submitted At: {payload.get('submitted_at')}",
                    '',
                    'Lead Contact:',
                    f"  Name: {lead.get('full_name') or ''}",
                    f"  Email: {lead.get('email') or ''}",
                    f"  Company: {lead.get('company_name') or ''}",
                    f"  Phone: {lead.get('phone') or ''}",
                    f"  Notes: {lead.get('notes') or ''}",
                    '',
                    'Estimate Summary:',
                    f"  Estimated CapEx: ${float(payload.get('estimated_capex') or 0):,.2f}",
                    f"  AP Count: {int(payload.get('ap_count') or 0)}",
                    f"  Switch Count: {int(payload.get('switch_count') or 0)}",
                ]
            )
        )
        return msg

    @staticmethod
    def send_design_submission_handoff(payload: dict) -> None:
        mailbox = (settings.design_handoff_email or settings.smtp_from_email or '').strip()
        if not mailbox:
            print(f'[MOCK DESIGN HANDOFF] {payload}')
            return

        if not EmailService._smtp_enabled():
            print(f'[MOCK DESIGN HANDOFF] to={mailbox} payload={payload}')
            return

        message = EmailService._compose_design_submission_message(to_email=mailbox, payload=payload)
        EmailService._send_smtp_message(message)

    @staticmethod
    def _compose_order_capture_text(payload: dict) -> str:
        customer = payload.get('customer') or {}
        pricing = payload.get('pricing') or {}
        currency = pricing.get('currency') or 'USD'
        lines = payload.get('line_items') or []

        line_blocks: list[str] = []
        for idx, line in enumerate(lines, start=1):
            line_blocks.append(
                (
                    f"{idx}. {line.get('name') or 'Line Item'} | "
                    f"Qty: {int(line.get('qty') or 0)} | "
                    f"Unit: {currency} {float(line.get('final_unit_price_snapshot') or 0):,.2f} | "
                    f"Total: {currency} {float(line.get('line_total') or 0):,.2f}"
                )
            )

        return '\n'.join(
            [
                'A new order has been captured and is ready for fulfillment.',
                '',
                f"Order ID: {payload.get('order_id')}",
                f"Quote ID: {payload.get('quote_id') or '-'}",
                f"Status: {payload.get('status')}",
                f"Created At: {payload.get('created_at') or '-'}",
                f"Estimated Delivery Date: {payload.get('estimated_delivery_date') or '-'}",
                f"Confirmed Delivery Date: {payload.get('confirmed_delivery_date') or '-'}",
                '',
                'Customer Details:',
                f"  Organization: {customer.get('organization_name') or '-'}",
                f"  Buyer Name: {customer.get('name') or '-'}",
                f"  Buyer Email: {customer.get('email') or '-'}",
                f"  Buyer Mobile: {customer.get('mobile') or '-'}",
                f"  Admin Contact: {customer.get('admin_name') or '-'} / {customer.get('admin_email') or '-'}",
                '',
                'Pricing Summary:',
                f"  One-time Total: {currency} {float(pricing.get('one_time_total') or 0):,.2f}",
                f"  Monthly Total: {currency} {float(pricing.get('monthly_total') or 0):,.2f}",
                f"  Projected 12-Month Cost: {currency} {float(pricing.get('projected_12_month_cost') or 0):,.2f}",
                '',
                'Order Lines:',
                *line_blocks,
            ]
        )

    @staticmethod
    def _compose_order_capture_html(payload: dict) -> str:
        customer = payload.get('customer') or {}
        pricing = payload.get('pricing') or {}
        currency = pricing.get('currency') or 'USD'
        rows = []
        for line in payload.get('line_items') or []:
            rows.append(
                (
                    '<tr>'
                    f"<td>{line.get('name') or 'Line Item'}</td>"
                    f"<td>{int(line.get('qty') or 0)}</td>"
                    f"<td>{currency} {float(line.get('final_unit_price_snapshot') or 0):,.2f}</td>"
                    f"<td>{currency} {float(line.get('line_total') or 0):,.2f}</td>"
                    '</tr>'
                )
            )
        rows_html = '\n'.join(rows) or '<tr><td colspan="4">No order lines available</td></tr>'

        return (
            '<html><body style="font-family:Arial, sans-serif;">'
            '<h2 style="margin-bottom:8px;">New Order Captured</h2>'
            '<p style="margin-top:0;">A new order has been captured and is ready for fulfillment.</p>'
            '<h3>Order</h3>'
            '<ul>'
            f"<li><strong>Order ID:</strong> {payload.get('order_id')}</li>"
            f"<li><strong>Quote ID:</strong> {payload.get('quote_id') or '-'}</li>"
            f"<li><strong>Status:</strong> {payload.get('status')}</li>"
            f"<li><strong>Created At:</strong> {payload.get('created_at') or '-'}</li>"
            f"<li><strong>Estimated Delivery:</strong> {payload.get('estimated_delivery_date') or '-'}</li>"
            f"<li><strong>Confirmed Delivery:</strong> {payload.get('confirmed_delivery_date') or '-'}</li>"
            '</ul>'
            '<h3>Customer</h3>'
            '<ul>'
            f"<li><strong>Organization:</strong> {customer.get('organization_name') or '-'}</li>"
            f"<li><strong>Buyer:</strong> {customer.get('name') or '-'} ({customer.get('email') or '-'})</li>"
            f"<li><strong>Mobile:</strong> {customer.get('mobile') or '-'}</li>"
            f"<li><strong>Admin Contact:</strong> {customer.get('admin_name') or '-'} / {customer.get('admin_email') or '-'}</li>"
            '</ul>'
            '<h3>Pricing</h3>'
            '<ul>'
            f"<li><strong>One-time Total:</strong> {currency} {float(pricing.get('one_time_total') or 0):,.2f}</li>"
            f"<li><strong>Monthly Total:</strong> {currency} {float(pricing.get('monthly_total') or 0):,.2f}</li>"
            f"<li><strong>Projected 12-Month Cost:</strong> {currency} {float(pricing.get('projected_12_month_cost') or 0):,.2f}</li>"
            '</ul>'
            '<h3>Order Lines</h3>'
            '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">'
            '<thead><tr><th align="left">Item</th><th align="left">Qty</th><th align="left">Unit</th><th align="left">Total</th></tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            '</table>'
            '</body></html>'
        )

    @staticmethod
    def _compose_order_capture_message(*, recipients: list[str], payload: dict) -> EmailMessage:
        msg = EmailMessage()
        from_name = settings.smtp_from_name.strip() or 'SecureOffice2'
        msg['From'] = f'{from_name} <{settings.smtp_from_email}>'
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = f"Order Captured: {payload.get('order_id')}"
        text_body = EmailService._compose_order_capture_text(payload)
        html_body = EmailService._compose_order_capture_html(payload)
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype='html')
        return msg

    @staticmethod
    def send_order_capture_handoff(*, payload: dict, recipients: list[str]) -> None:
        target_emails = [str(email).strip().lower() for email in recipients if str(email).strip()]
        order_id = payload.get('order_id')
        sendgrid_configured = bool((settings.sendgrid_api_key or '').strip())
        smtp_configured = EmailService._smtp_enabled()
        logger.warning(
            '[ORDER EMAIL START] order_id=%s recipients_count=%d sendgrid_configured=%s smtp_configured=%s sendgrid_from_email=%s smtp_from_email=%s',
            order_id,
            len(target_emails),
            sendgrid_configured,
            smtp_configured,
            (settings.sendgrid_from_email or '').strip() or None,
            (settings.smtp_from_email or '').strip() or None,
        )
        if not target_emails:
            logger.warning('[MOCK ORDER HANDOFF] order_id=%s reason=no_recipients', order_id)
            return

        subject = f"Order Captured: {payload.get('order_id')}"
        text_body = EmailService._compose_order_capture_text(payload)
        html_body = EmailService._compose_order_capture_html(payload)

        if (settings.sendgrid_api_key or '').strip():
            try:
                EmailService._send_via_sendgrid(
                    to_emails=target_emails,
                    subject=subject,
                    text_content=text_body,
                    html_content=html_body,
                )
                logger.warning('[ORDER EMAIL COMPLETED] order_id=%s channel=sendgrid recipients=%s', order_id, target_emails)
                return
            except Exception as exc:
                logger.exception('[SENDGRID ORDER HANDOFF ERROR] order_id=%s error=%s', order_id, exc)

        if not EmailService._smtp_enabled():
            logger.warning('[MOCK ORDER HANDOFF] order_id=%s reason=no_smtp_fallback recipients=%s', order_id, target_emails)
            return

        logger.warning('[ORDER EMAIL FALLBACK] order_id=%s channel=smtp reason=sendgrid_unavailable_or_failed', order_id)
        message = EmailService._compose_order_capture_message(recipients=target_emails, payload=payload)
        EmailService._send_smtp_message(message)
        logger.warning('[ORDER EMAIL COMPLETED] order_id=%s channel=smtp recipients=%s', order_id, target_emails)
