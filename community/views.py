import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, F, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import emails
from .decorators import verified_required
from .forms import (
    LoginForm,
    RegisterForm,
    ReplyForm,
    ReportForm,
    ResendActivationForm,
    TopicForm,
)
from .models import Category, EmailToken, Profile, Reply, Report, Topic
from .ratelimit import client_ip, enforce

logger = logging.getLogger("community")

# (limit, window seconds) — adjust here to tune the whole site.
LIMITS = {
    "register_ip": (5, 3600),
    "login_ip": (30, 900),
    "login_user": (10, 900),
    "topic_hour": (5, 3600),
    "topic_day": (20, 86400),
    "reply_hour": (20, 3600),
    "reply_day": (100, 86400),
    "report_hour": (10, 3600),
    "resend_ip": (5, 3600),
    "resend_email": (3, 3600),
}


def _safe_next(request, fallback: str = "home"):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return reverse(fallback)


def _visible_topic_or_404(request, pk) -> Topic:
    topic = get_object_or_404(
        Topic.objects.select_related("author", "category"), pk=pk
    )
    if topic.is_hidden and not request.user.is_staff:
        raise Http404("Topic not available")
    return topic


def _topic_detail_context(request, topic, reply_form=None):
    replies = topic.replies.select_related("author", "author__profile")
    if not request.user.is_staff:
        replies = replies.filter(is_hidden=False)
    profile = None
    if request.user.is_authenticated:
        profile, _created = Profile.objects.get_or_create(user=request.user)
    return {
        "topic": topic,
        "replies": replies,
        "reply_form": reply_form or ReplyForm(request=request),
        "can_reply": (
            request.user.is_authenticated
            and (profile.email_verified or request.user.is_staff)
            and not topic.is_locked
        ),
    }


def home(request):
    category_slug = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()[:100]
    sort = request.GET.get("sort", "latest")

    topics = (
        Topic.objects.visible()
        .select_related("author", "category")
        .with_counts()
    )
    active_category = None
    if category_slug:
        active_category = get_object_or_404(
            Category, slug=category_slug, is_active=True
        )
        topics = topics.filter(category=active_category)
    if query:
        topics = topics.filter(Q(title__icontains=query) | Q(body__icontains=query))

    if sort == "popular":
        topics = topics.order_by("-is_pinned", "-views", "-last_activity_at")
    elif sort == "unanswered":
        topics = topics.filter(reply_count=0).order_by("-is_pinned", "-created_at")
    else:
        topics = topics.order_by("-is_pinned", "-last_activity_at")

    paginator = Paginator(topics, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = Category.objects.filter(is_active=True).annotate(
        topic_count=Count("topics", filter=Q(topics__is_hidden=False))
    )
    stats = {
        "members": User.objects.filter(is_active=True).count(),
        "topics": Topic.objects.visible().count(),
        "replies": Reply.objects.filter(is_hidden=False, topic__is_hidden=False).count(),
    }

    return render(
        request,
        "home.html",
        {
            "page_obj": page_obj,
            "topics": page_obj,
            "categories": categories,
            "active_category": active_category,
            "query": query,
            "sort": sort,
            "stats": stats,
            "can_post": request.user.is_authenticated,
        },
    )


def topic_detail(request, pk):
    topic = _visible_topic_or_404(request, pk)
    if request.method == "GET":
        Topic.objects.filter(pk=topic.pk).update(views=F("views") + 1)
        topic.views += 1
    return render(request, "topic_detail.html", _topic_detail_context(request, topic))


@verified_required
def topic_create(request):
    enforce(request, "topic_hour", *LIMITS["topic_hour"], ident=str(request.user.pk))
    enforce(request, "topic_day", *LIMITS["topic_day"], ident=str(request.user.pk))

    form = TopicForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        topic = form.save(commit=False)
        topic.author = request.user
        topic.save()
        messages.success(request, _("Your topic is live."))
        return redirect(topic)

    return render(
        request,
        "topic_form.html",
        {"form": form, "categories": Category.objects.filter(is_active=True)},
    )


@verified_required
def reply_create(request, pk):
    topic = _visible_topic_or_404(request, pk)
    if topic.is_locked:
        messages.error(request, _("This topic is locked."))
        return redirect(topic)

    enforce(request, "reply_hour", *LIMITS["reply_hour"], ident=str(request.user.pk))
    enforce(request, "reply_day", *LIMITS["reply_day"], ident=str(request.user.pk))

    if request.method != "POST":
        return redirect(topic)

    form = ReplyForm(request.POST, request=request)
    if form.is_valid():
        reply = form.save(commit=False)
        reply.topic = topic
        reply.author = request.user
        reply.save()
        Topic.objects.filter(pk=topic.pk).update(last_activity_at=timezone.now())
        messages.success(request, _("Reply posted."))
        return redirect(f"{topic.get_absolute_url()}#reply-{reply.pk}")

    return render(
        request,
        "topic_detail.html",
        _topic_detail_context(request, topic, reply_form=form),
        status=400,
    )


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = RegisterForm(request.POST or None, request=request)
    activation_link = ""

    if request.method == "POST":
        enforce(request, "register_ip", *LIMITS["register_ip"])
        if form.is_valid():
            user = form.save()
            raw = emails.issue_activation(user)
            request.session["pending_email"] = user.email
            if settings.DEBUG:
                activation_link = emails.activation_url(raw)
            return render(
                request,
                "activation_sent.html",
                {"email": user.email, "activation_link": activation_link},
            )

    return render(request, "register.html", {"form": form})


def activate(request, token):
    token_obj = EmailToken.find_valid(token, EmailToken.PURPOSE_ACTIVATION)
    if token_obj is None:
        return render(request, "activate.html", {"ok": False}, status=400)

    # GET only shows a confirmation page: mail scanners often prefetch links,
    # and a one-click GET would silently burn the token.
    if request.method != "POST":
        return render(
            request,
            "activate.html",
            {"confirm": True, "token": token, "email": token_obj.user.email},
        )

    # Atomic single-use: only one request can flip used_at.
    claimed = EmailToken.objects.filter(
        pk=token_obj.pk, used_at__isnull=True
    ).update(used_at=timezone.now())
    if not claimed:
        return render(request, "activate.html", {"ok": False}, status=400)

    user = token_obj.user
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    profile, _created = Profile.objects.get_or_create(user=user)
    if not profile.email_verified:
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])
    # Retire any other outstanding activation tokens.
    EmailToken.objects.filter(
        user=user,
        purpose=EmailToken.PURPOSE_ACTIVATION,
        used_at__isnull=True,
    ).update(used_at=timezone.now())

    messages.success(request, _("Email confirmed. You can sign in now."))
    return render(request, "activate.html", {"ok": True})


def resend_activation(request):
    if request.user.is_authenticated and request.user.is_active:
        return redirect("home")

    form = ResendActivationForm(
        request.POST or None,
        request=request,
        initial={"email": request.GET.get("email", "")},
    )
    done = False
    activation_link = ""

    if request.method == "POST":
        enforce(request, "resend_ip", *LIMITS["resend_ip"])
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            enforce(
                request,
                "resend_email",
                *LIMITS["resend_email"],
                ident=email,
            )
            user = User.objects.filter(email__iexact=email, is_active=False).first()
            if user:
                EmailToken.objects.filter(
                    user=user,
                    purpose=EmailToken.PURPOSE_ACTIVATION,
                    used_at__isnull=True,
                ).update(used_at=timezone.now())
                raw = emails.issue_activation(user)
                if settings.DEBUG:
                    activation_link = emails.activation_url(raw)
            done = True

    return render(
        request,
        "resend_activation.html",
        {"form": form, "done": done, "email": form.data.get("email", ""), "activation_link": activation_link},
    )


@login_required
def verify_email(request):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    if profile.email_verified:
        return redirect("home")
    return render(request, "verify_email.html", {"profile": profile})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        enforce(request, "login_ip", *LIMITS["login_ip"])
        enforce(
            request,
            "login_user",
            *LIMITS["login_user"],
            ident=f"{client_ip(request)}:{request.POST.get('username', '')[:150].lower()}",
        )

    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        auth_login(request, form.get_user())
        messages.success(request, _("Welcome back."))
        return redirect(_safe_next(request))

    return render(request, "login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    auth_logout(request)
    messages.info(request, _("You have been signed out."))
    return redirect("home")


def profile(request, username):
    person = get_object_or_404(User, username=username)
    person_profile, _created = Profile.objects.get_or_create(user=person)
    topics = (
        person.topics.visible()
        .select_related("category")
        .with_counts()
        .order_by("-created_at")[:10]
    )
    replies = (
        person.replies.filter(is_hidden=False, topic__is_hidden=False)
        .select_related("topic")
        .order_by("-created_at")[:10]
    )
    return render(
        request,
        "profile.html",
        {
            "person": person,
            "person_profile": person_profile,
            "topics": topics,
            "replies": replies,
            "topic_total": person.topics.visible().count(),
            "reply_total": person.replies.filter(is_hidden=False).count(),
        },
    )


@verified_required
def report_content(request, kind, pk):
    enforce(request, "report_hour", *LIMITS["report_hour"], ident=str(request.user.pk))

    topic = None
    reply = None
    if kind == "topic":
        topic = _visible_topic_or_404(request, pk)
    elif kind == "reply":
        reply = get_object_or_404(Reply.objects.select_related("topic"), pk=pk)
        if (reply.is_hidden or reply.topic.is_hidden) and not request.user.is_staff:
            raise Http404("Reply not available")
    else:
        raise Http404("Unknown report target")

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            Report.objects.create(
                topic=topic,
                reply=reply,
                reporter=request.user,
                reason=form.cleaned_data["reason"],
                note=form.cleaned_data["note"],
            )
            messages.success(request, _("Thanks — our moderators will review this."))
            return redirect(topic.get_absolute_url() if topic else reply.topic.get_absolute_url())
    else:
        form = ReportForm()

    return render(
        request,
        "report.html",
        {"form": form, "topic": topic, "reply": reply},
    )


LEGAL_PAGES = {"terms", "privacy", "guidelines"}


def legal_index(request):
    return render(request, "legal/index.html")


def legal_page(request, page):
    if page not in LEGAL_PAGES:
        raise Http404("Legal page not found")
    return render(request, f"legal/{page}.html", {"page_key": page})


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check failed")
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})
