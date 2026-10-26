"""Authentication routes.

Password *reset* is deliberately absent. It would need to deliver a token
to the account holder, and this version sends nothing outbound. A
staff-issued reset — recorded, time-limited and surfaced in the Inbox —
is a later phase; adding a route here that cannot work would be worse
than not having one.
"""

from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/pending/", views.registration_pending, name="registration_pending"),

    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),

    path("profile/", views.profile, name="profile"),
    path("password/", views.PasswordChangeView.as_view(), name="password_change"),
    path("password/done/", views.PasswordChangeDoneView.as_view(),
         name="password_change_done"),
]
