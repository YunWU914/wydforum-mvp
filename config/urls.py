from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "OpenForum moderation"
admin.site.site_title = "OpenForum"
admin.site.index_title = "Community administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("community.urls")),
]
