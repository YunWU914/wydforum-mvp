from django.conf import settings
from django.utils import translation, timezone

from . import captcha


def site(request):
    lang = (translation.get_language() or "en").lower()
    languages = [
        {"code": code, "name": name, "active": code == lang}
        for code, name in settings.LANGUAGES
    ]
    return {
        "site_name": settings.SITE_NAME,
        "site_tagline": settings.SITE_TAGLINE,
        "site_url": settings.SITE_URL,
        "current_language": lang,
        "languages": languages,
        "captcha_provider": captcha.provider(),
        "captcha_site_key": captcha.site_key(),
        "legal_effective_date": settings.LEGAL_EFFECTIVE_DATE,
        "legal_contact_email": settings.LEGAL_CONTACT_EMAIL,
        "legal_company": settings.LEGAL_COMPANY,
        "legal_jurisdiction": settings.LEGAL_JURISDICTION,
        "email_verification_hours": settings.EMAIL_VERIFICATION_TTL_HOURS,
        "current_year": timezone.now().year,
        "debug": settings.DEBUG,
    }
