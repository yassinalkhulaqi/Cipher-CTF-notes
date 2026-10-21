"""Persistent storage for RedScribe.

The storage layer owns the single-file SQLite vault, schema migrations, FTS5
indexing, and settings persistence. It depends on the domain layer only.
"""
