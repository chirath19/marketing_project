"""The service-module registry.

The client dashboard is dynamic: a client sees SEO, Paid ads, Social and
Email only if their organization is entitled to them. Rather than
hard-coding that list in a template, each delivery domain registers
itself here with the predicate that decides visibility.

Navigation, routing guards and the API all read this one registry, so a
module cannot be visible in the menu but unguarded on the route — the
failure mode the brief explicitly rules out.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ServiceModule:
    key: str
    label: str
    url_name: str
    order: int = 100
    icon: str = ""
    # Resolved against an organization at request time. The default is a
    # closed door: a module must opt in to being visible.
    is_enabled: Callable[[Any], bool] = field(default=lambda organization: False)

    def enabled_for(self, organization: Any) -> bool:
        if organization is None:
            return False
        return bool(self.is_enabled(organization))


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, ServiceModule] = {}

    def register(self, module: ServiceModule) -> ServiceModule:
        if module.key in self._modules:
            raise ValueError(f"Service module {module.key!r} is already registered")
        self._modules[module.key] = module
        return module

    def get(self, key: str) -> ServiceModule | None:
        return self._modules.get(key)

    def all(self) -> list[ServiceModule]:
        return sorted(self._modules.values(), key=lambda m: (m.order, m.label))

    def enabled_for(self, organization: Any) -> list[ServiceModule]:
        return [m for m in self.all() if m.enabled_for(organization)]

    def clear(self) -> None:
        """Reset the registry. Test support only."""
        self._modules.clear()


registry = ModuleRegistry()
