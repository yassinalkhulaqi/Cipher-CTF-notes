"""Portability-specific error types.

Every failure raised by the portability package maps to a stable machine code so
the API namespace can render a useful V3 error envelope without leaking bundle
contents or passphrases.
"""

from __future__ import annotations


class PortabilityError(Exception):
    """Base class for all portability failures."""

    code = "portability_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = dict(context or {})


class BundleError(PortabilityError):
    """A portable bundle is malformed, unsupported, or unreadable."""

    code = "bundle_error"


class ManifestError(BundleError):
    """A bundle manifest failed structural validation."""

    code = "manifest_error"


class VerificationError(BundleError):
    """Integrity verification failed for a bundle or one of its records."""

    code = "verification_error"


class DecryptionError(BundleError):
    """A bundle could not be opened with the supplied passphrase."""

    code = "decryption_error"


class DeviceError(PortabilityError):
    """A device identity is unknown or not trusted."""

    code = "device_error"


class MergeError(PortabilityError):
    """A merge or resolution request could not be applied."""

    code = "merge_error"


class ResolutionError(MergeError):
    """A conflict decision is invalid for the supplied conflict."""

    code = "resolution_error"


class TransferError(PortabilityError):
    """A resumable transfer is in the wrong state or has corrupt data."""

    code = "transfer_error"
