import re

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from . import captcha
from .antispam import form_timestamp, form_too_fast, is_disposable
from .models import Category, Profile, Reply, Report, Topic

RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "moderator",
    "mod",
    "support",
    "staff",
    "system",
    "openforum",
    "official",
    "help",
}


class AntiBotFormMixin(forms.Form):
    """Honeypot + signed render timestamp + CAPTCHA (when configured)."""

    hp_field = forms.CharField(
        required=False,
        label="",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "tabindex": "-1",
                "class": "hp-field",
                "aria-hidden": "true",
            }
        ),
    )
    ts = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        if not self.is_bound and "ts" in self.fields:
            self.fields["ts"].initial = form_timestamp()

    def clean_hp_field(self):
        if self.cleaned_data.get("hp_field"):
            raise ValidationError(_("Something went wrong. Please reload and try again."))
        return ""

    def clean(self):
        cleaned = super().clean()
        if "ts" in self.fields and form_too_fast(
            cleaned.get("ts", ""), settings.FORM_MIN_FILL_SECONDS
        ):
            raise ValidationError(
                _("That was too quick. Please take a moment and submit again.")
            )
        if self.request is not None:
            ok, _reason = captcha.verify(self.request)
            if not ok:
                raise ValidationError(
                    _("Human verification failed. Please try again.")
                )
        return cleaned


class RegisterForm(AntiBotFormMixin, forms.Form):
    username = forms.RegexField(
        regex=re.compile(r"^[A-Za-z0-9_]{3,30}$"),
        label=_("Username"),
        help_text=_("3–30 characters: letters, numbers and underscore."),
        error_messages={
            "invalid": _("Use 3–30 characters: letters, numbers and underscore only.")
        },
        widget=forms.TextInput(
            attrs={"autocomplete": "username", "autofocus": True, "placeholder": "ada_lovelace"}
        ),
    )
    email = forms.EmailField(
        label=_("Email"),
        help_text=_("We send a one-time activation link. Use a permanent address."),
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
    )
    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("At least 10 characters. Avoid common or numeric-only passwords."),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    agree = forms.BooleanField(
        label=_("I agree to the Terms of Service and Privacy Policy."),
        error_messages={"required": _("You must accept the Terms and Privacy Policy.")},
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if username.lower() in RESERVED_USERNAMES:
            raise ValidationError(_("That username is reserved."))
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(_("That username is already taken."))
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if is_disposable(email):
            raise ValidationError(_("Please use a permanent email address."))
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("An account with this email already exists."))
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError(_("The two passwords do not match."))
        return password2

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        username = cleaned.get("username")
        email = cleaned.get("email")
        if password and username and email:
            candidate = User(username=username, email=email)
            try:
                validate_password(password, candidate)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            is_active=False,
        )
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.email_verified = False
        profile.save(update_fields=["email_verified"])
        return user


class LoginForm(AntiBotFormMixin, AuthenticationForm):
    username = forms.CharField(
        label=_("Username or email"),
        widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class TopicForm(AntiBotFormMixin, forms.ModelForm):
    class Meta:
        model = Topic
        fields = ["category", "title", "body"]
        labels = {
            "category": _("Category"),
            "title": _("Title"),
            "body": _("Post"),
        }
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": _("A clear, specific question or title"), "maxlength": 200}
            ),
            "body": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": _("Add context, what you tried, and what you need."),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = _("Choose a category")
        self.fields["body"].help_text = _("Plain text. Line breaks are preserved.")

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if len(title) < 5:
            raise ValidationError(_("Please write a slightly longer title."))
        return title

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if len(body) < 10:
            raise ValidationError(_("Please add a little more detail."))
        return body


class ReplyForm(AntiBotFormMixin, forms.ModelForm):
    class Meta:
        model = Reply
        fields = ["body"]
        labels = {"body": _("Reply")}
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 5, "placeholder": _("Write a helpful reply…")}
            )
        }

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if len(body) < 2:
            raise ValidationError(_("Please write a reply."))
        return body


class ReportForm(forms.Form):
    reason = forms.ChoiceField(label=_("Reason"), choices=Report.REASON_CHOICES)
    note = forms.CharField(
        label=_("Details (optional)"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class ResendActivationForm(AntiBotFormMixin, forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )
