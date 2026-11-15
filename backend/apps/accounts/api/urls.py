from django.urls import path

from apps.accounts.api.views import CsrfView, LoginView, LogoutView, MembersView, MeView

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("members/", MembersView.as_view(), name="members"),
]
