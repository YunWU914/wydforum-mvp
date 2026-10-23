from django.shortcuts import render
from django.utils import translation

from . import captcha
from .ratelimit import RateLimitExceeded


class RateLimitMiddleware:
    """Turn rate-limit exceptions into a friendly 429 page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, RateLimitExceeded):
            response = render(
                request,
                "429.html",
                {"retry_after": exception.retry_after},
                status=429,
            )
            response["Retry-After"] = str(exception.retry_after)
            return response
        return None


class SecurityHeadersMiddleware:
    """CSP and other headers. Skipped for Django admin (it uses inline JS)."""

    CSP = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' https://challenges.cloudflare.com "
        "https://www.google.com https://www.gstatic.com; "
        "frame-src https://challenges.cloudflare.com https://www.google.com; "
        "connect-src 'self' https://challenges.cloudflare.com https://www.google.com; "
        "font-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), interest-cohort=()",
        )
        return response


def current_language():
    return (translation.get_language() or "en").lower()
