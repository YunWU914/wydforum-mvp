"""Server-side verification for Cloudflare Turnstile and Google reCAPTCHA.

Both providers use a simple form POST to a verification endpoint, so no SDK is
required. Set CAPTCHA_PROVIDER + keys in the environment. If no keys are
configured the widget is skipped (dev only) and other anti-abuse layers
(honeypot, timing, rate limits, email activation) still apply.
"""

import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("community.captcha")

VERIFY_URLS = {
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    "recaptcha": "https://www.google.com/recaptcha/api/siteverify",
}


def is_enabled() -> bool:
    if settings.CAPTCHA_PROVIDER == "turnstile":
        return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)
    if settings.CAPTCHA_PROVIDER == "recaptcha":
        return bool(settings.RECAPTCHA_SITE_KEY and settings.RECAPTCHA_SECRET_KEY)
    return False


def site_key() -> str:
    if settings.CAPTCHA_PROVIDER == "turnstile":
        return settings.TURNSTILE_SITE_KEY
    if settings.CAPTCHA_PROVIDER == "recaptcha":
        return settings.RECAPTCHA_SITE_KEY
    return ""


def provider() -> str:
    return settings.CAPTCHA_PROVIDER if is_enabled() else "none"


def token_from_request(request) -> str:
    return (
        request.POST.get("cf-turnstile-response")
        or request.POST.get("g-recaptcha-response")
        or ""
    )


def verify(request):
    """Return (ok, reason). Fails closed on network/provider errors."""
    if not is_enabled():
        return True, "disabled"

    token = token_from_request(request)
    if not token:
        return False, "missing-token"

    if settings.CAPTCHA_PROVIDER == "turnstile":
        secret = settings.TURNSTILE_SECRET_KEY
        url = VERIFY_URLS["turnstile"]
    else:
        secret = settings.RECAPTCHA_SECRET_KEY
        url = VERIFY_URLS["recaptcha"]

    payload = urllib.parse.urlencode(
        {"secret": secret, "response": token, "remoteip": _remote_ip(request)}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # network timeout, DNS, 5xx, bad JSON...
        logger.warning("CAPTCHA verification failed: %s", exc)
        return False, "verification-unavailable"

    if not data.get("success"):
        logger.info(
            "CAPTCHA rejected: provider=%s codes=%s",
            settings.CAPTCHA_PROVIDER,
            data.get("error-codes"),
        )
        return False, "rejected"

    # reCAPTCHA v3 returns a score instead of a challenge.
    if settings.CAPTCHA_PROVIDER == "recaptcha" and "score" in data:
        if float(data.get("score", 0)) < 0.5:
            logger.info("reCAPTCHA low score: %s", data.get("score"))
            return False, "low-score"

    return True, "ok"


def _remote_ip(request) -> str:
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
