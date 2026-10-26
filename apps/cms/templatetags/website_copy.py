"""Editable plain text; one override query per request."""

from django import template

from apps.cms.copy import defaults, overrides

register = template.Library()


@register.simple_tag(takes_context=True)
def website_copy(context, key):
    request = context.get("request")
    if request is not None:
        if not hasattr(request, "_website_copy"):
            request._website_copy = overrides()
        values = request._website_copy
    else:
        values = overrides()
    return values.get(key, defaults().get(key, ""))


@register.simple_tag(takes_context=True)
def editable_public_form(context, form):
    """Apply editorial labels without changing field names or validation."""
    scope = "quote" if "objective" in form.fields else "contact"
    registry = defaults()
    for name, field in form.fields.items():
        key = f"public.forms.{scope}.{name}"
        if f"{key}.label" in registry:
            field.label = website_copy(context, f"{key}.label")
        if f"{key}.help" in registry:
            field.help_text = website_copy(context, f"{key}.help")
        if hasattr(field, "choices"):
            field.choices = [(value, website_copy(context, f"{key}.choice.{value or 'blank'}"))
                             for value, label in field.choices]
    form._bound_fields_cache.clear()
    return ""
