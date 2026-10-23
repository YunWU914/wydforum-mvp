import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language, gettext_lazy as _


class Category(models.Model):
    """Forum section. Names/descriptions are stored per language as JSON."""

    slug = models.SlugField(max_length=60, unique=True)
    names = models.JSONField(default=dict)
    descriptions = models.JSONField(default=dict, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "slug"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.localized("names")

    def _lang_keys(self):
        lang = (get_language() or "en").replace("-", "_")
        keys = [lang]
        if "_" in lang:
            keys.append(lang.split("_")[0])
        keys.append("en")
        return keys

    def localized(self, field: str) -> str:
        data = getattr(self, field) or {}
        for key in self._lang_keys():
            value = data.get(key)
            if value:
                return value
        return data.get("en", self.slug)

    @property
    def name(self):
        return self.localized("names")

    @property
    def description(self):
        return self.localized("descriptions")


class TopicQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_hidden=False)

    def with_counts(self):
        return self.annotate(
            reply_count=models.Count(
                "replies", filter=models.Q(replies__is_hidden=False), distinct=True
            )
        )


class Topic(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="topics"
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="topics")
    title = models.CharField(max_length=200)
    body = models.TextField(max_length=20000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)

    objects = TopicQuerySet.as_manager()

    class Meta:
        ordering = ["-is_pinned", "-last_activity_at"]
        indexes = [
            models.Index(fields=["category", "-last_activity_at"]),
            models.Index(fields=["-last_activity_at"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("topic_detail", args=[self.pk])

    @property
    def excerpt(self):
        text = " ".join(self.body.split())
        return text[:180] + ("…" if len(text) > 180 else "")


class Reply(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="replies")
    body = models.TextField(max_length=20000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["topic", "created_at"])]

    def __str__(self):
        return f"Reply #{self.pk} on {self.topic_id}"

    def get_absolute_url(self):
        return f"{self.topic.get_absolute_url()}#reply-{self.pk}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    email_verified = models.BooleanField(default=False)
    bio = models.TextField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile of {self.user.username}"

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def initials(self):
        name = self.display_name.strip()
        parts = [p for p in name.replace("_", " ").split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return name[:2].upper()


class EmailToken(models.Model):
    """Single-use, hashed email token (activation, future password resets)."""

    PURPOSE_ACTIVATION = "activation"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="email_tokens"
    )
    purpose = models.CharField(max_length=32, default=PURPOSE_ACTIVATION)
    token_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.purpose} token for {self.user_id}"

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, user, purpose: str = "activation", hours=None):
        hours = hours or settings.EMAIL_VERIFICATION_TTL_HOURS
        raw = secrets.token_urlsafe(32)
        cls.objects.create(
            user=user,
            purpose=purpose,
            token_hash=cls.hash_token(raw),
            expires_at=timezone.now() + timedelta(hours=hours),
        )
        return raw

    @classmethod
    def find_valid(cls, raw: str, purpose: str = "activation"):
        if not raw or len(raw) > 128:
            return None
        token = (
            cls.objects.select_related("user", "user__profile")
            .filter(
                token_hash=cls.hash_token(raw),
                purpose=purpose,
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            .first()
        )
        return token

    def consume(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])


class Report(models.Model):
    REASON_SPAM = "spam"
    REASON_ABUSE = "abuse"
    REASON_OFF_TOPIC = "off_topic"
    REASON_OTHER = "other"
    REASON_CHOICES = [
        (REASON_SPAM, _("Spam or advertising")),
        (REASON_ABUSE, _("Harassment or hate")),
        (REASON_OFF_TOPIC, _("Off-topic / duplicate")),
        (REASON_OTHER, _("Other")),
    ]

    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, null=True, blank=True, related_name="reports"
    )
    reply = models.ForeignKey(
        Reply, on_delete=models.CASCADE, null=True, blank=True, related_name="reports"
    )
    reporter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reports_filed"
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    note = models.TextField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_resolved",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target = self.topic or self.reply
        return f"{self.reason} report on {target}"
