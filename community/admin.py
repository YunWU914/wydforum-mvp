from django.contrib import admin
from django.utils import timezone

from .models import Category, EmailToken, Profile, Reply, Report, Topic


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "position", "is_active")
    list_editable = ("position", "is_active")
    search_fields = ("slug", "names")


@admin.action(description="Hide selected")
def hide_items(modeladmin, request, queryset):
    queryset.update(is_hidden=True)


@admin.action(description="Unhide selected")
def unhide_items(modeladmin, request, queryset):
    queryset.update(is_hidden=False)


@admin.action(description="Pin selected")
def pin_items(modeladmin, request, queryset):
    queryset.update(is_pinned=True)


@admin.action(description="Unpin selected")
def unpin_items(modeladmin, request, queryset):
    queryset.update(is_pinned=False)


@admin.action(description="Lock selected")
def lock_items(modeladmin, request, queryset):
    queryset.update(is_locked=True)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "author",
        "created_at",
        "last_activity_at",
        "views",
        "is_pinned",
        "is_locked",
        "is_hidden",
    )
    list_filter = ("category", "is_pinned", "is_locked", "is_hidden")
    search_fields = ("title", "body", "author__username")
    autocomplete_fields = ("author",)
    date_hierarchy = "created_at"
    actions = [hide_items, unhide_items, pin_items, unpin_items, lock_items]
    readonly_fields = ("views", "created_at", "updated_at", "last_activity_at")


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "author", "created_at", "is_hidden")
    list_filter = ("is_hidden",)
    search_fields = ("body", "author__username", "topic__title")
    autocomplete_fields = ("author", "topic")
    actions = [hide_items, unhide_items]


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "email_verified", "created_at")
    list_filter = ("email_verified",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)


@admin.register(EmailToken)
class EmailTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "created_at", "expires_at", "used_at")
    list_filter = ("purpose",)
    search_fields = ("user__username", "user__email")
    readonly_fields = (
        "user",
        "purpose",
        "token_hash",
        "created_at",
        "expires_at",
        "used_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "reason", "topic", "reply", "reporter", "created_at", "resolved_at")
    list_filter = ("reason", "resolved_at")
    search_fields = ("note", "reporter__username", "topic__title", "reply__body")
    readonly_fields = ("created_at",)

    @admin.action(description="Mark selected reports as resolved")
    def resolve_reports(self, request, queryset):
        queryset.filter(resolved_at__isnull=True).update(
            resolved_at=timezone.now(), resolved_by=request.user
        )

    actions = [resolve_reports]
