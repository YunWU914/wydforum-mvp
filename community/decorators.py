from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .models import Profile


def verified_required(view_func):
    """Require login + a verified email (staff bypass for moderation)."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        profile, _created = Profile.objects.get_or_create(user=request.user)
        if not profile.email_verified:
            return redirect("verify_email")
        return view_func(request, *args, **kwargs)

    return wrapper
