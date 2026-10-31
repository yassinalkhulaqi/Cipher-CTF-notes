"""Framework-independent domain primitives for RedScribe.

The domain layer owns immutable records, value parsing, fuzzy ranking, flag
patterns, and small text helpers. It must never import the desktop UI layer or
SQLite.
"""
