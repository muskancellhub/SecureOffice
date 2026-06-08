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
    def _mask_secret(value: str) -> str:
        clean = (value or '').strip()
        if not clean:
            return ''
        if len(clean) <= 8:
            return '***'
        return f'{clean[:4]}...{clean[-4:]}'

    @staticmethod
    def _send_via_resend(
        *,
        to_emails: list[str],
        subject: str,
        text_content: str,
        html_content: str,
    ) -> str | None:
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

    @staticmethod
    def _compose_otp_text(*, otp: str, purpose: str) -> str:
        return '\n'.join(
            [
                'Your Secure AI Office one-time password is:',
                '',
                f'  {otp}',
                '',
                f'It expires in {settings.otp_expire_minutes} minutes.',
                'If you did not request this code, please ignore this email.',
            ]
        )

    @staticmethod
    def _compose_otp_html(*, otp: str, purpose: str) -> str:
        return (
            '<html><body style="font-family:Arial, sans-serif; background:#f3eef4; padding:40px 0;">'
            '<div style="max-width:480px; margin:0 auto; background:#ffffff; border-radius:8px; padding:40px; text-align:center;">'
            '<h2 style="margin:0 0 8px; color:#152844;">Secure AI Office</h2>'
            f'<p style="color:#617089; margin:0 0 24px;">Your one-time password for <strong>{purpose}</strong></p>'
            f'<div style="font-size:32px; font-weight:700; letter-spacing:6px; color:#e1067d; '
            f'background:#f3dce8; border-radius:8px; padding:16px; margin:0 auto 24px; display:inline-block;">{otp}</div>'
            f'<p style="color:#617089; font-size:14px; margin:0;">Expires in {settings.otp_expire_minutes} minutes.</p>'
            '<p style="color:#617089; font-size:13px; margin:16px 0 0;">If you did not request this code, please ignore this email.</p>'
            '</div></body></html>'
        )

    @staticmethod
    def send_otp_email(*, to_email: str, otp: str, purpose: str) -> None:
        subject = f'Secure AI Office OTP for {purpose}'
        text_body = EmailService._compose_otp_text(otp=otp, purpose=purpose)
        html_body = EmailService._compose_otp_html(otp=otp, purpose=purpose)
        if not EmailService._resend_enabled():
            print(f'[MOCK OTP DELIVERY] email={to_email} otp={otp} purpose={purpose}')
            return
        EmailService._send_via_resend(
            to_emails=[to_email],
            subject=subject,
            text_content=text_body,
            html_content=html_body,
        )
        logger.warning('[OTP EMAIL COMPLETED] to=%s channel=resend purpose=%s', to_email, purpose)

    @staticmethod
    def _compose_invite_text(*, org_name: str, invited_by: str | None, login_url: str) -> str:
        lines = [
            f'You have been invited to join {org_name} on Secure AI Office.',
            '',
            f'Sign in here: {login_url}',
            'Use this email address — we will send you a one-time code to log in.',
        ]
        if invited_by:
            lines += ['', f'Invited by {invited_by}.']
        return '\n'.join(lines)

    @staticmethod
    def _compose_invite_html(*, org_name: str, invited_by: str | None, login_url: str) -> str:
        invited_line = (
            f'<p style="color:#617089; font-size:13px; margin:18px 0 0;">Invited by {invited_by}.</p>'
            if invited_by else ''
        )
        return (
            '<html><body style="font-family:Arial, sans-serif; background:#f3eef4; padding:40px 0;">'
            '<div style="max-width:480px; margin:0 auto; background:#ffffff; border-radius:8px; padding:40px; text-align:center;">'
            '<h2 style="margin:0 0 8px; color:#152844;">Secure AI Office</h2>'
            f'<p style="color:#617089; margin:0 0 24px;">You have been invited to join <strong>{org_name}</strong>.</p>'
            f'<a href="{login_url}" style="display:inline-block; background:#e1067d; color:#ffffff; '
            'text-decoration:none; font-weight:700; padding:14px 28px; border-radius:8px; margin:0 auto 24px;">Sign in</a>'
            '<p style="color:#617089; font-size:14px; margin:0;">Use this email address — we will send you a '
            'one-time code to log in.</p>'
            f'{invited_line}'
            '</div></body></html>'
        )

    @staticmethod
    def send_invite_email(*, to_email: str, org_name: str, invited_by: str | None, login_url: str) -> None:
        subject = f'You have been invited to {org_name} on Secure AI Office'
        text_body = EmailService._compose_invite_text(org_name=org_name, invited_by=invited_by, login_url=login_url)
        html_body = EmailService._compose_invite_html(org_name=org_name, invited_by=invited_by, login_url=login_url)
        if not EmailService._resend_enabled():
            print(f'[MOCK INVITE DELIVERY] email={to_email} login_url={login_url}')
            return
        EmailService._send_via_resend(
            to_emails=[to_email],
            subject=subject,
            text_content=text_body,
            html_content=html_body,
        )
        logger.warning('[INVITE EMAIL COMPLETED] to=%s channel=resend org=%s', to_email, org_name)

    @staticmethod
    def _compose_design_submission_text(payload: dict) -> str:
        lead = payload.get('lead') or {}
        return '\n'.join(
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

    @staticmethod
    def _compose_design_submission_html(payload: dict) -> str:
        lead = payload.get('lead') or {}
        return (
            '<html><body style="font-family:Arial, sans-serif;">'
            '<h2 style="margin-bottom:8px;">New SMB Network Design Submission</h2>'
            '<p style="margin-top:0;">A new SMB network design was submitted for demo handoff.</p>'
            '<h3>Design</h3>'
            '<ul>'
            f"<li><strong>Design ID:</strong> {payload.get('design_id')}</li>"
            f"<li><strong>Design Name:</strong> {payload.get('design_name')}</li>"
            f"<li><strong>Status:</strong> {payload.get('status')}</li>"
            f"<li><strong>Submitted At:</strong> {payload.get('submitted_at')}</li>"
            '</ul>'
            '<h3>Lead Contact</h3>'
            '<ul>'
            f"<li><strong>Name:</strong> {lead.get('full_name') or ''}</li>"
            f"<li><strong>Email:</strong> {lead.get('email') or ''}</li>"
            f"<li><strong>Company:</strong> {lead.get('company_name') or ''}</li>"
            f"<li><strong>Phone:</strong> {lead.get('phone') or ''}</li>"
            f"<li><strong>Notes:</strong> {lead.get('notes') or ''}</li>"
            '</ul>'
            '<h3>Estimate Summary</h3>'
            '<ul>'
            f"<li><strong>Estimated CapEx:</strong> ${float(payload.get('estimated_capex') or 0):,.2f}</li>"
            f"<li><strong>AP Count:</strong> {int(payload.get('ap_count') or 0)}</li>"
            f"<li><strong>Switch Count:</strong> {int(payload.get('switch_count') or 0)}</li>"
            '</ul>'
            '</body></html>'
        )

    @staticmethod
    def send_design_submission_handoff(payload: dict) -> None:
        mailbox = (settings.design_handoff_email or '').strip()
        if not EmailService._resend_enabled() or not mailbox:
            print(f'[MOCK DESIGN HANDOFF] to={mailbox} payload={payload}')
            return

        subject = f"Design Submission: {payload.get('design_name') or payload.get('design_id')}"
        text_body = EmailService._compose_design_submission_text(payload)
        html_body = EmailService._compose_design_submission_html(payload)
        EmailService._send_via_resend(
            to_emails=[mailbox],
            subject=subject,
            text_content=text_body,
            html_content=html_body,
        )

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
    def send_order_capture_handoff(*, payload: dict, recipients: list[str]) -> None:
        target_emails = [str(email).strip().lower() for email in recipients if str(email).strip()]
        # dedupe while preserving order
        seen: set[str] = set()
        target_emails = [e for e in target_emails if not (e in seen or seen.add(e))]
        order_id = payload.get('order_id')
        logger.warning(
            '[ORDER EMAIL START] order_id=%s recipients_count=%d resend_configured=%s resend_from_email=%s',
            order_id,
            len(target_emails),
            EmailService._resend_enabled(),
            (settings.resend_from_email or '').strip() or None,
        )
        if not target_emails or not EmailService._resend_enabled():
            logger.warning(
                '[MOCK ORDER HANDOFF] order_id=%s reason=%s',
                order_id,
                'no_recipients' if not target_emails else 'resend_not_configured',
            )
            return

        subject = f"Order Captured: {payload.get('order_id')}"
        text_body = EmailService._compose_order_capture_text(payload)
        html_body = EmailService._compose_order_capture_html(payload)
        EmailService._send_via_resend(
            to_emails=target_emails,
            subject=subject,
            text_content=text_body,
            html_content=html_body,
        )
        logger.warning('[ORDER EMAIL COMPLETED] order_id=%s channel=resend recipients=%s', order_id, target_emails)
