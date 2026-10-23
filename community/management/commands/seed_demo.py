import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from community.models import Category, Profile, Reply, Topic

CATEGORIES = [
    {
        "slug": "announcements",
        "position": 10,
        "names": {
            "en": "Announcements",
            "zh_hans": "站务公告",
            "ja": "お知らせ",
            "es": "Anuncios",
        },
        "descriptions": {
            "en": "Product updates, rules and community news.",
            "zh_hans": "产品更新、社区规则与官方消息。",
            "ja": "アップデート、ルール、コミュニティのニュース。",
            "es": "Novedades del producto, normas y noticias.",
        },
    },
    {
        "slug": "general",
        "position": 20,
        "names": {
            "en": "General discussion",
            "zh_hans": "综合讨论",
            "ja": "雑談・一般",
            "es": "Charla general",
        },
        "descriptions": {
            "en": "Open-ended conversation about anything on-topic.",
            "zh_hans": "任何符合社区主题的开放讨论。",
            "ja": "テーマに沿った自由な話題。",
            "es": "Conversación abierta sobre cualquier tema.",
        },
    },
    {
        "slug": "help",
        "position": 30,
        "names": {
            "en": "Help & feedback",
            "zh_hans": "求助与反馈",
            "ja": "ヘルプとフィードバック",
            "es": "Ayuda y comentarios",
        },
        "descriptions": {
            "en": "Ask questions, report bugs, suggest improvements.",
            "zh_hans": "提问、反馈问题、提出改进建议。",
            "ja": "質問、不具合報告、改善提案。",
            "es": "Preguntas, errores y sugerencias.",
        },
    },
    {
        "slug": "showcase",
        "position": 40,
        "names": {
            "en": "Showcase",
            "zh_hans": "作品展示",
            "ja": "作品紹介",
            "es": "Proyectos",
        },
        "descriptions": {
            "en": "Share what you are building, writing or learning.",
            "zh_hans": "分享你在做、在写、在学的东西。",
            "ja": "作っているもの、書いているもの、学んでいることを共有。",
            "es": "Comparte lo que estás creando o aprendiendo.",
        },
    },
]

DEMO_TOPICS = [
    {
        "username": "ada",
        "category": "announcements",
        "title": "Welcome to OpenForum — start here",
        "body": (
            "This is the MVP test build of our community. Accounts are open to everyone, "
            "but email confirmation is required before posting.\n\n"
            "A few ground rules: be kind, stay on topic, and report spam instead of replying to it. "
            "We are testing rate limits and moderation tools, so some actions may feel strict."
        ),
        "pinned": True,
        "replies": [
            ("lin", "Glad to be here. The language switcher works nicely — testing from Shanghai."),
            ("kenji", "読みやすくて良いですね。テスト参加します。"),
        ],
    },
    {
        "username": "lin",
        "category": "help",
        "title": "How do I change the interface language?",
        "body": (
            "I see a language selector in the header. Does it also change the emails I receive?\n\n"
            "Would be useful to know whether the choice is stored on my account or only in this browser."
        ),
        "replies": [
            (
                "ada",
                "For the MVP the choice is stored in a cookie and a session, so it follows this browser. "
                "Per-account language preferences are on the roadmap.",
            )
        ],
    },
    {
        "username": "kenji",
        "category": "showcase",
        "title": "Showcase: a tiny CLI for tracking reading habits",
        "body": (
            "I built a small command-line tool that logs what I read each day and prints a weekly summary. "
            "It is intentionally boring: one SQLite file, no sync, no accounts.\n\n"
            "Happy to share the design if anyone is interested in building something similar."
        ),
        "replies": [
            ("lin", "Please do. I would especially like to see how you handle time zones."),
            ("ada", "Nice. A short write-up in Showcase would be very welcome."),
        ],
    },
    {
        "username": "ada",
        "category": "general",
        "title": "What does a good community onboarding look like?",
        "body": (
            "We are redesigning the first ten minutes of the experience. What made you stay in a forum "
            "the first time you joined one?\n\n"
            "For me it was a single well-written welcome post and a reply from a real person within a day."
        ),
        "replies": [],
    },
]


class Command(BaseCommand):
    help = "Create the default categories, and optionally demo users/topics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Also create demo users, topics and replies (development only).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow demo content even when DEBUG=0.",
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("DEMO_PASSWORD", "DemoPass!2026"),
            help="Password for demo accounts.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for spec in CATEGORIES:
            _obj, created = Category.objects.update_or_create(
                slug=spec["slug"],
                defaults={
                    "names": spec["names"],
                    "descriptions": spec["descriptions"],
                    "position": spec["position"],
                    "is_active": True,
                },
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Categories ready ({created_count} created, {len(CATEGORIES)} total)."
            )
        )

        if not options["demo"]:
            return
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to create demo accounts with known passwords when DEBUG=0. "
                "Pass --force if this is a disposable test environment."
            )
        if Topic.objects.exists():
            self.stdout.write("Topics already exist — demo content skipped.")
            return

        users = {}
        for username, email in (
            ("ada", "ada@example.com"),
            ("lin", "lin@example.com"),
            ("kenji", "kenji@example.com"),
        ):
            user, created = User.objects.get_or_create(
                username=username, defaults={"email": email, "is_active": True}
            )
            if created:
                user.set_password(options["password"])
                user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            if not profile.email_verified:
                profile.email_verified = True
                profile.save(update_fields=["email_verified"])
            users[username] = user

        topics = 0
        replies = 0
        for item in DEMO_TOPICS:
            topic = Topic.objects.create(
                category=Category.objects.get(slug=item["category"]),
                author=users[item["username"]],
                title=item["title"],
                body=item["body"],
                is_pinned=item["pinned"] if "pinned" in item else False,
                views=12 + topics * 7,
            )
            topics += 1
            for username, body in item["replies"]:
                Reply.objects.create(topic=topic, author=users[username], body=body)
                replies += 1
            if item["replies"]:
                topic.last_activity_at = topic.replies.order_by("-created_at").first().created_at
                topic.save(update_fields=["last_activity_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo content ready: {topics} topics, {replies} replies. "
                f"Sign in as ada / {options['password']}"
            )
        )
