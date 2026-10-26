"""The module registry decides what a client can see. Its default must be
a closed door, not an open one."""

import pytest

from apps.core.registry import ModuleRegistry, ServiceModule


@pytest.fixture
def registry():
    registry = ModuleRegistry()
    yield registry
    registry.clear()


class FakeOrganization:
    def __init__(self, modules):
        self.modules = set(modules)


def module(key, *, order=100, enabled_keys=()):
    return ServiceModule(
        key=key,
        label=key.title(),
        url_name=f"{key}:index",
        order=order,
        is_enabled=lambda org: key in getattr(org, "modules", set()) and key in enabled_keys,
    )


def test_a_module_is_invisible_by_default(registry):
    """A module registered without a predicate must not be visible."""
    registry.register(ServiceModule(key="seo", label="SEO", url_name="seo:index"))

    assert registry.enabled_for(FakeOrganization({"seo"})) == []


def test_enabled_for_filters_by_entitlement(registry):
    registry.register(module("seo", order=1, enabled_keys=("seo",)))
    registry.register(module("social", order=2, enabled_keys=("social",)))

    org = FakeOrganization({"seo"})

    assert [m.key for m in registry.enabled_for(org)] == ["seo"]


def test_nothing_is_enabled_without_an_organization(registry):
    registry.register(module("seo", enabled_keys=("seo",)))

    assert registry.enabled_for(None) == []


def test_modules_are_ordered(registry):
    registry.register(module("email", order=40, enabled_keys=("email",)))
    registry.register(module("seo", order=10, enabled_keys=("seo",)))
    registry.register(module("paid_ads", order=20, enabled_keys=("paid_ads",)))

    assert [m.key for m in registry.all()] == ["seo", "paid_ads", "email"]


def test_duplicate_registration_is_rejected(registry):
    registry.register(module("seo"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(module("seo"))
