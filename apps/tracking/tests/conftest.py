"""These existing module tests exercise the owner's enabled feature options."""
import pytest


@pytest.fixture(autouse=True)
def enabled_module_options(db):
    from apps.core.models import OperatingSettings
    OperatingSettings.objects.update_or_create(pk=1, defaults={'analytics_enabled': True})
