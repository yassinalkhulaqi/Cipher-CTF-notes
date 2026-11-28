"""Accessibility and internationalization polish for the v4 workspace.

The package is layered: :mod:`types` holds validated, data-only contracts;
:mod:`service` runs audits, translations, formatting, motion resolution, and
tours; :mod:`storage` persists preference snapshots and catalog metadata; and
:mod:`api` exposes the whole slice through v4 envelopes. ``register(api)`` wires
the routes into dynamic namespace discovery without editing shared registries.
"""

from __future__ import annotations

from redscribe.v4.a11y_i18n.api import register

__all__ = ["register"]
