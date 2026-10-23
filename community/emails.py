import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import EmailToken

logger = logging.getLogger("community.email")


def activation_url(raw_token: str) -> str:
    return f"{settings.SITE_URL}{reverse('activate', args=[raw_token])}"


def send_activation_email(user, raw_token: str) -> bool:
    url = activation_url(raw_token)
    subject = _("Activate your %(site)s account") % {"site": settings.SITE_NAME}
    body = "\n\n".join(
        [
            _("Hi %(username)s,") % {"username": user.username},
            _(
                "Welcome to %(site)s. Confirm your email address to finish creating your account:"
            )
            % {"site": settings.SITE_NAME},
            url,
            _(
                "This link expires in %(hours)s hours and can be used once."
            )
            % {"hours": settings.EMAIL_VERIFICATION_TTL_HOURS},
            _("If you did not create this account, you can ignore this email."),
            _("— %(site)s") % {"site": settings.SITE_NAME},
        ]
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send activation email to user %s", user.pk)
        return False


def issue_activation(user):
    """Create a fresh single-use token and email it. Returns the raw token."""
    raw = EmailToken.issue(user, EmailToken.PURPOSE_ACTIVATION)
    send_activation_email(user, raw)
    return raw
