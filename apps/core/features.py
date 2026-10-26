"""Central feature registry. Disabling a feature never deletes its records."""

from django.core.exceptions import PermissionDenied

# key: (label, default, parent). Existing master switches remain authoritative.
FEATURES = {
    "integrations": ("External integrations", False, ""),
    "api": ("Application API", False, ""),
    "analytics": ("Website analytics", False, ""),
    "meta_ads": ("Meta Ads API", True, "integrations"),
    "google_ads": ("Google Ads API", True, "integrations"),
    "google_analytics": ("Google Analytics reporting API", True, "integrations"),
    "google_search_console": ("Google Search Console", True, "integrations"),
    "linkedin_ads": ("LinkedIn Ads API", True, "integrations"),
    "tiktok_ads": ("TikTok Ads API", True, "integrations"),
    "gtm": ("Google Tag Manager", True, "analytics"),
    "ga4": ("Google Analytics browser tag", True, "analytics"),
    "meta_pixel": ("Meta Pixel", True, "analytics"),
    "rudderstack": ("RudderStack", True, "analytics"),
    "campaigns": ("Campaign workspace", True, ""),
    "seo": ("SEO workspace", True, ""),
    "paid_ads": ("Paid Ads workspace", True, ""),
    "social": ("Social Media workspace", True, ""),
    "email_marketing": ("Email Marketing workspace", True, ""),
    "approvals": ("Deliverable approvals", True, ""),
    "messages": ("Client conversations", True, ""),
    "reports": ("Client progress reports", True, ""),
    "payments": ("Invoices and payment receipts", True, ""),
    "service_requests": ("Service renewals, extensions and extras", True, ""),
}
MASTER_FIELDS = {"integrations": "integrations_enabled", "api": "api_enabled",
                 "analytics": "analytics_enabled"}


def settings_for(actor=None):
    from apps.core.operations import current

    operating = getattr(actor, "_operating_settings", None) if actor else None
    if operating is None:
        operating = current()
        if actor is not None and getattr(actor, "is_authenticated", False):
            actor._operating_settings = operating
    return operating


def enabled(key, *, operating=None, actor=None):
    if key not in FEATURES:
        return False
    operating = operating if operating is not None else settings_for(actor)
    if key in MASTER_FIELDS:
        return bool(getattr(operating, MASTER_FIELDS[key]))
    _, default, parent = FEATURES[key]
    return bool(operating.feature_flags.get(key, default)) and (
        not parent or enabled(parent, operating=operating)
    )


def visible(key, actor, *, operating=None):
    if key == "client_workspace":
        return any(visible(item, actor, operating=operating)
                   for item in ("messages", "reports", "payments"))
    return bool(getattr(actor, "is_super_admin", False)) or enabled(
        key, actor=actor, operating=operating
    )


def require(key, actor):
    if not visible(key, actor):
        raise PermissionDenied("This feature is not currently available.")


def permission_available(actor, codename):
    module = codename.rsplit("_", 1)[0]
    if module == "settings":
        return actor.is_super_admin
    # analytics_* also governs manual progress reports, so it cannot be gated
    # by website tracking. Tracking routes have their own feature guard.
    key = {"messaging": "messages"}.get(module, module)
    if key in FEATURES and key != "analytics":
        return visible(key, actor)
    return True


def route_feature(request, kwargs):
    """Map server entry points to the same switches used by navigation."""
    path = request.path
    if path.startswith("/staff/messages/"):
        return "client_workspace"
    if path.startswith("/staff/integrations/"):
        return kwargs.get("provider", "integrations")
    if path.startswith(("/staff/analytics/", "/staff/tracking/")):
        return "analytics"
    for key, segment in [("seo", "seo"), ("paid_ads", "paid-ads"),
                         ("social", "social"), ("email_marketing", "email-marketing"),
                         ("campaigns", "campaigns"), ("approvals", "approvals")]:
        if path.startswith((f"/staff/{segment}/", f"/organization/{segment}/")):
            return key
    if path.startswith("/organization/area/"):
        return kwargs.get("key")
    for key, segment in [("messages", "messages"), ("reports", "reports"),
                         ("payments", "receipts"), ("payments", "invoices"),
                         ("service_requests", "service-requests")]:
        if path.startswith((f"/organization/{segment}/", f"/staff/{segment}/")):
            return key
    return None
