"""Provider registry with the built-in venues registered."""
from __future__ import annotations

from .base import BookingProvider, ProviderRegistry, Slot, wait_for, pfill
from .vatican import VaticanProvider

__all__ = [
    "BookingProvider", "ProviderRegistry", "Slot", "wait_for", "pfill",
    "VaticanProvider", "default_registry",
]


def default_registry() -> ProviderRegistry:
    """A registry with all built-in providers registered."""
    reg = ProviderRegistry()
    reg.register(VaticanProvider())
    return reg
