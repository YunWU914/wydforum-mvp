import re

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from .models import Category, EmailToken, Profile, Topic
from .middleware import RateLimitMiddleware
from .ratelimit import RateLimitExceeded, enforce

# Tests render templates without a collected manifest.
PLAIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}


def plain_static(cls):
    return override_settings(STORAGES=PLAIN_STORAGES)(cls)


def fill_times(form_html: str) -> dict:
    """Pull the signed timestamp out of a rendered form."""
    match = re.search(r'name="ts" value="([^"]+)"', form_html)
    return {"ts": match.group(1)} if match else {}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FORM_MIN_FILL_SECONDS=0,
    CAPTCHA_PROVIDER="none",
)
@plain_static
class RegistrationFlowTests(TestCase):
    def _register(self, **overrides):
        html = self.client.get(reverse("register")).content.decode()
        data = {
            "username": "ada_lovelace",
            "email": "ada@example.com",
            "password1": "correct-horse-battery",
            "password2": "correct-horse-battery",
            "agree": "on",
            **fill_times(html),
            **overrides,
        }
        return self.client.post(reverse("register"), data)

    def test_register_sends_activation_and_keeps_account_inactive(self):
        response = self._register()
        self.assertContains(response, "Check your inbox", status_code=200)
        user = User.objects.get(username="ada_lovelace")
        self.assertFalse(user.is_active)
        self.assertFalse(user.profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("activate", mail.outbox[0].body)

    def test_honeypot_rejects_bots(self):
        self._register(hp_field="spammy-bot")
        self.assertFalse(User.objects.filter(username="ada_lovelace").exists())

    def test_disposable_email_rejected(self):
        self._register(email="throwaway@mailinator.com")
        self.assertFalse(User.objects.filter(username="ada_lovelace").exists())

    def test_activation_requires_confirmation_then_enables_login(self):
        self._register()
        token_match = re.search(
            r"/activate/([A-Za-z0-9_\-]+)", mail.outbox[0].body
        )
        token = token_match.group(1)

        confirm = self.client.get(reverse("activate", args=[token]))
        self.assertContains(confirm, "Confirm your email", status_code=200)
        # A GET alone must not consume the token (mail scanners prefetch).
        self.assertFalse(User.objects.get(username="ada_lovelace").is_active)

        self.client.post(reverse("activate", args=[token]))
        user = User.objects.get(username="ada_lovelace")
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.email_verified)
        self.assertTrue(
            EmailToken.objects.get(user=user).used_at, "token should be single-use"
        )

        html = self.client.get(reverse("login")).content.decode()
        response = self.client.post(
            reverse("login"),
            {"username": "ada_lovelace", "password": "correct-horse-battery", **fill_times(html)},
        )
        self.assertRedirects(response, reverse("home"))

    def test_resend_activation_is_generic(self):
        response = self.client.post(
            reverse("resend_activation"),
            {"email": "nobody@example.com", **fill_times(self.client.get(reverse("resend_activation")).content.decode())},
        )
        self.assertContains(response, "Request received")
        self.assertEqual(len(mail.outbox), 0)


@plain_static
class ForumContentTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            slug="general",
            names={"en": "General", "zh_hans": "综合讨论"},
        )
        self.user = User.objects.create_user("lin", password="StrongPass!2026")
        profile, _created = Profile.objects.get_or_create(user=self.user)
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])
        self.topic = Topic.objects.create(
            category=self.category, author=self.user, title="Hello world", body="First post body."
        )

    def test_home_lists_topics(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Hello world")
        self.assertContains(response, "General")

    def test_search_and_category_filter(self):
        self.assertContains(self.client.get(reverse("home") + "?q=hello"), "Hello world")
        self.assertNotContains(self.client.get(reverse("home") + "?q=nothing"), "Hello world")
        self.assertContains(
            self.client.get(reverse("home") + "?category=general"), "Hello world"
        )

    def test_category_names_localized(self):
        with translation.override("zh-hans"):
            self.assertEqual(str(self.category), "综合讨论")

    @override_settings(FORM_MIN_FILL_SECONDS=0, CAPTCHA_PROVIDER="none")
    def test_verified_user_can_post_topic_and_reply(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("topic_create")).content.decode()
        response = self.client.post(
            reverse("topic_create"),
            {"category": self.category.pk, "title": "A brand new topic", "body": "Somebody help me test this.", **fill_times(html)},
        )
        topic = Topic.objects.get(title="A brand new topic")
        self.assertRedirects(response, topic.get_absolute_url())

        html = self.client.get(topic.get_absolute_url()).content.decode()
        response = self.client.post(
            reverse("reply_create", args=[topic.pk]),
            {"body": "A thoughtful reply.", **fill_times(html)},
        )
        self.assertRedirects(response, f"{topic.get_absolute_url()}#reply-1", fetch_redirect_response=False)

    def test_unverified_user_redirected_to_verify(self):
        Profile.objects.filter(user=self.user).update(email_verified=False)
        self.client.force_login(self.user)
        response = self.client.get(reverse("topic_create"))
        self.assertRedirects(response, reverse("verify_email"))

    def test_legal_pages_render(self):
        self.assertEqual(self.client.get(reverse("legal")).status_code, 200)
        for page in ("terms", "privacy", "guidelines"):
            self.assertEqual(self.client.get(reverse("legal_page", args=[page])).status_code, 200)
        self.assertEqual(self.client.get(reverse("legal_page", args=["bogus"])).status_code, 404)

    def test_language_cookie_switches_ui(self):
        self.client.cookies["forum_language"] = "zh-hans"
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'lang="zh-hans"')
        self.assertContains(response, "最新讨论")

    def test_set_language_sets_cookie(self):
        response = self.client.post(reverse("set_language"), {"language": "ja"})
        self.assertIn("forum_language", response.cookies)
        self.assertEqual(response.cookies["forum_language"].value, "ja")


@plain_static
class RateLimitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_enforce_raises_after_limit(self):
        request = self.factory.get("/", REMOTE_ADDR="10.0.0.1")
        with self.assertRaises(RateLimitExceeded):
            for _ in range(3):
                enforce(request, "test-bucket", limit=2, window=60)

    def test_rate_limit_response_page(self):
        from django.http import HttpResponse

        request = self.factory.get("/", REMOTE_ADDR="10.0.0.2")
        middleware = RateLimitMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(middleware(request).status_code, 200)
        try:
            for _ in range(2):
                enforce(request, "test-view", limit=1, window=60)
            raised = False
        except RateLimitExceeded as exc:
            raised = True
            response = middleware.process_exception(request, exc)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response["Retry-After"], str(exc.retry_after))
        self.assertTrue(raised)
