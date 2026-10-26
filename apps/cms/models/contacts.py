"""Additional public contact methods, managed alongside page content."""

import re
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from apps.cms.models.site import OrderedVisibleModel


class ContactPoint(OrderedVisibleModel):
    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        WHATSAPP = "whatsapp", "WhatsApp"
        ADDRESS = "address", "Address"
        OTHER = "other", "Other / opening hours"

    label = models.CharField(max_length=100, help_text="For example: Sales or Colombo office.")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.EMAIL)
    value = models.TextField(
        max_length=500, help_text="Email, phone number, address or other contact information.",
    )
    description = models.CharField(max_length=240, blank=True)
    link = models.URLField(
        blank=True, max_length=500,
        help_text="Optional https:// link, for example a map or booking page.",
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = "additional contact"
        verbose_name_plural = "additional contacts"

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        self.value = self.value.strip()
        if self.kind == self.Kind.EMAIL:
            try:
                validate_email(self.value)
            except ValidationError as exc:
                raise ValidationError({"value": "Enter a valid email address."}) from exc
        elif self.kind in {self.Kind.PHONE, self.Kind.WHATSAPP} and (
            not re.fullmatch(r"\+?[0-9 ()\-.]{3,40}", self.value)
            or not re.search(r"\d", self.value)
        ):
            raise ValidationError({
                "value": "Enter a phone number using digits, spaces, +, brackets or dashes.",
            })
        if self.link and not self.link.startswith(("https://", "http://")):
            raise ValidationError({"link": "Use an http:// or https:// link."})

    @property
    def href(self) -> str:
        if self.link:
            return self.link
        if self.kind == self.Kind.EMAIL:
            return f"mailto:{quote(self.value, safe='@.+')}"
        if self.kind == self.Kind.PHONE:
            return "tel:" + re.sub(r"[^0-9+]", "", self.value)
        if self.kind == self.Kind.WHATSAPP:
            return "https://wa.me/" + re.sub(r"\D", "", self.value)
        return ""
