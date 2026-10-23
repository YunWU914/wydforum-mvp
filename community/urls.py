from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("t/<int:pk>/", views.topic_detail, name="topic_detail"),
    path("t/<int:pk>/reply/", views.reply_create, name="reply_create"),
    path("new/", views.topic_create, name="topic_create"),
    path("u/<str:username>/", views.profile, name="profile"),
    path("report/<str:kind>/<int:pk>/", views.report_content, name="report"),
    path("register/", views.register, name="register"),
    path("activate/resend/", views.resend_activation, name="resend_activation"),
    path("activate/<str:token>/", views.activate, name="activate"),
    path("verify-email/", views.verify_email, name="verify_email"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("legal/", views.legal_index, name="legal"),
    path("legal/<slug:page>/", views.legal_page, name="legal_page"),
    path("healthz", views.healthz, name="healthz"),
]
