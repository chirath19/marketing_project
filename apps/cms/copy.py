"""Public copy registry and authorized editorial changes."""

import json
from functools import lru_cache
from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError

from apps.cms.models import WebsiteCopy


@lru_cache(maxsize=1)
def defaults():
    return json.loads(Path(__file__).with_name("website_copy.json").read_text())


def overrides():
    return dict(WebsiteCopy.objects.values_list("key", "text"))


def update(*, actor, key, text, reset=False):
    if not actor.has_perm("permissions.cms_edit"):
        raise PermissionDenied
    if key not in defaults() or len(text) > 10000:
        raise ValidationError("Choose an existing text entry and keep it under 10,000 characters.")
    if reset:
        WebsiteCopy.objects.filter(key=key).delete()
    else:
        WebsiteCopy.objects.update_or_create(key=key, defaults={"text": text})
