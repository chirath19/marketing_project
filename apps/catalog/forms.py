"""Catalogue editing forms. Validation only; services do the writing."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import (
    Service,
    ServiceAddon,
    ServiceCategory,
    ServiceFeature,
    ServicePackage,
)
from apps.core.forms import StyledModelForm


class PriceVisibilityMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["price_visibility"].required = False

    def clean_price_visibility(self):
        return self.cleaned_data.get("price_visibility") or "inherit"


class SlugOptionalMixin:
    """Leave the slug blank and it is derived from the name.

    Shown rather than hidden, because changing it later breaks existing
    links — a decision someone should make deliberately.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if "slug" in self.fields:
            self.fields["slug"].required = False


class ServiceCategoryForm(SlugOptionalMixin, StyledModelForm):
    class Meta:
        model = ServiceCategory
        fields = ["name", "slug", "short_description", "icon", "is_visible"]


class ServiceForm(PriceVisibilityMixin, SlugOptionalMixin, StyledModelForm):
    class Meta:
        model = Service
        fields = [
            "name", "slug", "category", "short_description", "full_description",
            "price_visibility", "price", "currency", "billing_type",
            "image", "image_alt", "icon",
            "is_featured", "can_request_quote",
            "meta_title", "meta_description",
        ]
        widgets = {
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "full_description": forms.Textarea(attrs={"rows": 8}),
        }
        help_texts = {
            "price": _("Leave empty and choose “Custom quote” if it cannot "
                       "be priced yet."),
        }


class ServiceFeatureForm(StyledModelForm):
    class Meta:
        model = ServiceFeature
        fields = ["label", "description", "is_visible"]


class ServicePackageForm(PriceVisibilityMixin, SlugOptionalMixin, StyledModelForm):
    class Meta:
        model = ServicePackage
        fields = ["name", "slug", "summary", "price_visibility", "price", "currency",
                  "billing_type", "is_recommended", "is_visible"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 2})}


class ServiceAddonForm(PriceVisibilityMixin, SlugOptionalMixin, StyledModelForm):
    class Meta:
        model = ServiceAddon
        fields = ["name", "slug", "service", "short_description", "price",
                  "price_visibility", "currency", "billing_type", "is_active", "is_visible"]
        widgets = {"short_description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["service"].empty_label = _("Applies to anything")
        self.fields["service"].required = False
