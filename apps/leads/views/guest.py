from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.core.ratelimit import RateLimit, check
from apps.leads import guest, selectors


@never_cache
@guest.require_guest_quote
@require_http_methods(["GET", "POST"])
def detail(request, token):
    quote = request.guest_quote
    if request.method == "POST":
        verdict = check(
            RateLimit("quote:guest", limit=20, window=timedelta(hours=1)), str(quote.pk)
        )
        if not verdict.allowed:
            messages.error(request, "Please wait before sending another response.")
        else:
            try:
                guest.respond(
                    token=token,
                    action=request.POST.get("action"),
                    body=request.POST.get("body", ""),
                )
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                return redirect("public:guest_quote", token=token)
    response = render(
        request,
        "public/leads/guest_quote.html",
        {
            "suppress_tracking": True,
            "quote": quote,
            "items": quote.included_items,
            "activities": selectors.client_visible_activities(quote),
        },
    )
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
