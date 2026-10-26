"""Account views.

Thin by design: authorise, call a selector or service, render. The rate
limiting lives here rather than in the service layer because it is a
property of the HTTP entry point — a management command creating an
account should not be throttled by whoever last used the web form.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts import services
from apps.accounts.forms import (
    LoginForm,
    ProfileForm,
    RegistrationForm,
    StyledPasswordChangeForm,
)
from apps.core.ratelimit import (
    LOGIN_ACCOUNT,
    LOGIN_IP,
    REGISTRATION_IP,
    check,
    client_ip,
    peek,
    record,
    reset,
)

logger = logging.getLogger(__name__)


def _retry_message(verdict) -> str:  # noqa: ANN001
    """How long to wait, rounded up to whole minutes.

    Never says "0 minutes", which reads as a bug rather than a wait.
    """
    seconds = verdict.retry_after.total_seconds() if verdict.retry_after else 60
    minutes = max(1, round(seconds / 60))
    return _("Too many attempts. Please try again in about %(minutes)d minute(s).") % {
        "minutes": minutes
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


#: What a client account is actually for. Interface copy rather than
#: marketing copy — it describes this platform's own features, so it
#: belongs with the code that would have to change if they changed, not
#: in the CMS where it could drift away from the truth.
ACCOUNT_BENEFITS = (
    "The services you have active, and what each one covers",
    "Campaigns running under them, and their progress",
    "Reports as they are published",
    "Anything waiting on your approval",
    "Messages with your account team, kept with the work",
    "Colleagues can be added, so it is not tied to one person",
)


@require_http_methods(["GET", "POST"])
def register(request: HttpRequest) -> HttpResponse:
    """Client self-registration.

    In the default configuration the account is created PENDING and the
    visitor is sent to a page explaining that. Nothing is emailed; the
    staff Inbox is where the request surfaces.
    """
    if request.user.is_authenticated:
        return redirect("/")

    ip = client_ip(request)

    if request.method == "POST":
        # Peeked before the form is validated so that a burst of invalid
        # submissions is throttled too, then recorded once we know we are
        # actually processing this one.
        verdict = peek(REGISTRATION_IP, ip)
        if not verdict.allowed:
            logger.warning("Registration rate limit hit from %s", ip)
            form = RegistrationForm(request.POST)
            form.add_error(None, _retry_message(verdict))
            return render(request, "accounts/register.html",
                          {"form": form, "throttled": True}, status=429)

        record(REGISTRATION_IP, ip)

        form = RegistrationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                result = services.register_client(
                    email=data["email"],
                    password=data["password1"],
                    full_name=data.get("full_name", ""),
                    company_name=data.get("company_name", ""),
                    phone=data.get("phone", ""),
                    job_title=data.get("job_title", ""),
                )
            except services.RegistrationError as exc:
                form.add_error("email", str(exc))
            else:
                if result.requires_approval:
                    return redirect("accounts:registration_pending")

                auth_login(request, result.user,
                           backend="apps.permissions.backends.PlatformPermissionBackend")
                messages.success(request, _("Welcome. Your account is ready."))
                return redirect("organizations:quote_create")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {
        "form": form,
        "requires_approval": services.registration_requires_approval(),
        "account_benefits": ACCOUNT_BENEFITS,
    })


def registration_pending(request: HttpRequest) -> HttpResponse:
    """Shown after registering when approval is required."""
    return render(request, "accounts/registration_pending.html")


# ---------------------------------------------------------------------------
# Sign in and out
# ---------------------------------------------------------------------------


class LoginView(auth_views.LoginView):
    """Sign in, throttled by address and by account.

    Both are needed: by address alone, a distributed attempt on one
    account slips through; by account alone, one noisy network can lock
    out an unrelated user. A successful sign-in clears the account's
    counter so a legitimate user who mistyped a few times is not left
    locked out by their own success.
    """

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return "/staff/dashboard/" if self.request.user.is_staff_member else "/organization/"

    def get_context_data(self, **kwargs) -> dict:
        """Keep the CMS site row out of Django's way.

        `auth_views.LoginView` adds its own `site` and `site_name` to the
        context, taken from the request host. Those names collide with
        the CMS settings row every other page renders its header and
        footer from, and the Django object has no `site_name` attribute —
        so on this page alone the brand silently went blank.

        Dropping them restores the one `site` the templates mean. The
        brand context processor is namespaced for the same reason, and
        a test asserts both.
        """
        context = super().get_context_data(**kwargs)
        context.pop("site", None)
        context.pop("site_name", None)
        return context

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        ip = client_ip(request)
        submitted_email = (request.POST.get("username") or "").strip().lower()

        for limit, key in ((LOGIN_IP, ip), (LOGIN_ACCOUNT, submitted_email)):
            if not key:
                continue
            verdict = check(limit, key)
            if not verdict.allowed:
                logger.warning("Sign-in rate limit hit (%s)", limit.scope)
                form = self.get_form()
                form.add_error(None, _retry_message(verdict))
                return self.render_to_response(
                    self.get_context_data(form=form), status=429
                )

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        reset(LOGIN_ACCOUNT, self.request.user.email)
        logger.info("Sign-in: %s", self.request.user.email)
        return response


class LogoutView(auth_views.LogoutView):
    next_page = "/"


# ---------------------------------------------------------------------------
# Profile and password
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def profile(request: HttpRequest) -> HttpResponse:
    """Edit your own details.

    The service enforces which fields are editable; the form only decides
    what is rendered. A crafted POST naming another field is rejected
    server-side rather than silently accepted.
    """
    if request.method == "POST":
        form = ProfileForm.for_user(request.user, data=request.POST)
        if form.is_valid():
            services.update_profile(
                user=request.user,
                actor=request.user,
                **{name: form.cleaned_data[name] for name in form.fields},
            )
            messages.success(request, _("Your profile has been updated."))
            return redirect("accounts:profile")
    else:
        form = ProfileForm.for_user(request.user)

    return render(request, "accounts/profile.html", {"form": form})


class PasswordChangeView(auth_views.PasswordChangeView):
    """Change your own password, knowing the current one."""

    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Django rotates the session hash itself; this records the change
        # so audit and the Inbox can show it, since no confirmation email
        # will.
        update_session_auth_hash(self.request, form.user)
        services.record_password_change(user=form.user, actor=self.request.user)
        messages.success(self.request, _("Your password has been changed."))
        return response


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"
