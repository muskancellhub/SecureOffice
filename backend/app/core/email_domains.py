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


def domain_has_mail_exchange(domain: str) -> bool:
    """Best-effort check that ``domain`` can actually receive email.

    Regex format + the free-provider blocklist can't catch a typo'd domain like
    ``gmali.com`` — it's syntactically valid and not on the blocklist, so signup
    accepts it, creates the tenant/user, and sends an OTP that bounces into the
    void (BUG-AUTH-010). Here we resolve the domain's DNS to confirm a mailbox
    could exist before advancing the user to the OTP screen.

    Per RFC 5321 §5.1 a domain with no MX record but an A/AAAA record still
    accepts mail (implicit MX), so we accept if *any* of MX/A/AAAA resolves.

    Returns ``False`` ONLY when the domain definitively can't receive mail —
    it doesn't exist (NXDOMAIN) or resolves but has no MX/A/AAAA. On any
    transient DNS failure (timeout, no reachable nameserver, network error) we
    **fail open** and return ``True``: a flaky resolver must never block a
    legitimate signup, and the OTP round-trip is still the real proof of inbox
    control.
    """
    if not domain:
        return False

    # Imported lazily so the module has no hard import-time DNS dependency.
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.timeout = 3.0
    resolver.lifetime = 3.0

    for rdtype in ('MX', 'A', 'AAAA'):
        try:
            if len(resolver.resolve(domain, rdtype)) > 0:
                return True
        except dns.resolver.NoAnswer:
            continue  # this record type is absent — try the next
        except dns.resolver.NXDOMAIN:
            return False  # domain does not exist at all — definitive typo/bogus
        except dns.exception.DNSException:
            return True  # transient/unknown DNS failure — fail open, don't block
    return False  # domain resolves but has no MX/A/AAAA — can't receive mail
