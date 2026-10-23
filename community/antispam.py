"""Email/domain blocklist and lightweight form-bot checks."""

import time

from django.core import signing

FORM_TS_SALT = "community.form.timestamp"


def form_timestamp() -> str:
    """Signed render time, embedded in forms to reject instant bot posts."""
    return signing.dumps(int(time.time()), salt=FORM_TS_SALT)


def form_too_fast(value: str, min_seconds: int = 2, max_age: int = 7200) -> bool:
    """True when the form was submitted impossibly fast (or is stale)."""
    try:
        rendered_at = int(signing.loads(value, salt=FORM_TS_SALT, max_age=max_age))
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return True
    return (time.time() - rendered_at) < min_seconds


DISPOSABLE_DOMAINS = {
    "10minutemail.com",
    "10minutemail.net",
    "guerrillamail.com",
    "guerrillamail.net",
    "guerrillamail.org",
    "sharklasers.com",
    "grr.la",
    "mailinator.com",
    "mailinator.net",
    "maildrop.cc",
    "yopmail.com",
    "yopmail.fr",
    "tempmail.com",
    "temp-mail.org",
    "temp-mail.io",
    "throwawaymail.com",
    "getnada.com",
    "dispostable.com",
    "trashmail.com",
    "fakeinbox.com",
    "mytemp.email",
    "emailondeck.com",
    "spamgourmet.com",
    "mailcatch.com",
    "mohmal.com",
    "burnermail.io",
}


def is_disposable(email: str) -> bool:
    domain = (email.rsplit("@", 1)[-1] if "@" in email else "").lower().strip(".")
    if not domain:
        return False
    return domain in DISPOSABLE_DOMAINS or any(
        domain.endswith("." + blocked) for blocked in DISPOSABLE_DOMAINS
    )
