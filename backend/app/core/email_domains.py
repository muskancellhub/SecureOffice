"""Email-domain helpers for company-first signup.

The company-tenant is keyed on the signup email's domain (see
docs/plans/onboarding-admin-flow/PLAN.md §1). Free/public email providers are
rejected at signup so every account maps to a real company domain.
"""
from __future__ import annotations

# Common free / public email providers. Not exhaustive — a pragmatic blocklist
# that covers the providers an individual (vs. a company) would typically use.
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset({
    'gmail.com', 'googlemail.com',
    'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
    'yahoo.com', 'yahoo.co.in', 'ymail.com', 'rocketmail.com',
    'icloud.com', 'me.com', 'mac.com',
    'aol.com', 'protonmail.com', 'proton.me', 'pm.me',
    'zoho.com', 'gmx.com', 'gmx.net', 'mail.com', 'yandex.com',
    'hey.com', 'fastmail.com', 'tutanota.com', 'tuta.io',
})


def extract_domain(email: str) -> str:
    """Lowercased domain part of an email address (``a@B.com`` -> ``b.com``).

    Returns ``''`` when there is no ``@`` or no domain part.
    """
    if not email or '@' not in email:
        return ''
    return email.rsplit('@', 1)[1].strip().lower()


def is_free_email_provider(email: str) -> bool:
    """True if the email's domain is a known free/public provider."""
    return extract_domain(email) in FREE_EMAIL_DOMAINS
