from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Let people sign in with either their username or their email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None

        user = (
            User.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
            .order_by("id")
            .first()
        )
        if user is None:
            User().set_password(password)  # equalize timing
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
