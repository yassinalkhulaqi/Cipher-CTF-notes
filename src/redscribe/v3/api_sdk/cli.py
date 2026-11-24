"""Read-only-by-default scripting CLI for the local API v3 SDK."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.router import default_router
from redscribe.v3.api_sdk.capabilities import CapabilityNegotiator
from redscribe.v3.api_sdk.client import SdkClient
from redscribe.v3.api_sdk.envelopes import render_envelope
from redscribe.v3.api_sdk.errors import ScriptError, SdkError
from redscribe.v3.api_sdk.scripting import ScriptPlan, ScriptRunner, example_script
from redscribe.v3.api_sdk.service import ExtensionService, get_service, set_service
from redscribe.v3.api_sdk.transport import InProcessTransport
from redscribe.v3.config import V3Config


def emit(value: Any) -> None:
    """Write one JSON document to stdout."""
    sys.stdout.write(json.dumps(value, sort_keys=True, indent=2, default=str) + "\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser with explicit write opt-ins."""
    parser = argparse.ArgumentParser(
        prog="redscribe-sdk-v3",
        description="Local-only API v3 SDK and scripting CLI (read-only by default)",
    )
    parser.add_argument("--config", default="", help="optional local V3 config JSON file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("capabilities", help="show negotiated capabilities")
    subparsers.add_parser("routes", help="show the route manifest")
    subparsers.add_parser("contracts", help="show SDK wire contracts")
    subparsers.add_parser("safety", help="run the static no-code-execution audit")
    subparsers.add_parser("version", help="print SDK version")

    call = subparsers.add_parser("call", help="call one API v3 route")
    call.add_argument("namespace")
    call.add_argument("action")
    call.add_argument("--body", default="{}", help="JSON request body")
    call.add_argument("--capability", default="")
    call.add_argument("--etag", default="")
    call.add_argument("--idempotency-key", default="")
    call.add_argument("--allow-write", action="store_true")
    call.add_argument("--allow-errors", action="store_true")

    pages = subparsers.add_parser("list", help="follow paginated results")
    pages.add_argument("namespace")
    pages.add_argument("action")
    pages.add_argument("--body", default="{}")
    pages.add_argument("--size", type=int, default=50)
    pages.add_argument("--offset", type=int, default=0)
    pages.add_argument("--max-pages", type=int, default=10)
    pages.add_argument("--capability", default="")

    manifest = subparsers.add_parser("manifest", help="work with data-only manifests")
    manifest_sub = manifest.add_subparsers(dest="manifest_command", required=True)
    manifest_sub.add_parser("schema", help="print the manifest schema")
    manifest_sub.add_parser("example", help="print a valid example manifest")
    manifest_sub.add_parser("script", help="print an example read-only script")
    validate = manifest_sub.add_parser("validate", help="validate a manifest file")
    validate.add_argument("path")
    install = manifest_sub.add_parser("install", help="install a validated manifest")
    install.add_argument("path")
    install.add_argument("--allow-write", action="store_true")
    install.add_argument("--idempotency-key", default="")
    install.add_argument("--etag", default="")
    remove = manifest_sub.add_parser("remove", help="remove an installed manifest")
    remove.add_argument("id")
    remove.add_argument("--allow-write", action="store_true")
    remove.add_argument("--etag", default="")

    script = subparsers.add_parser("script", help="run declarative JSON scripts")
    script_sub = script.add_subparsers(dest="script_command", required=True)
    run = script_sub.add_parser("run", help="run a read-only-by-default script")
    run.add_argument("path")
    run.add_argument("--allow-write", action="store_true")
    run.add_argument("--continue-on-error", action="store_true")

    return parser


def read_json(text: str, *, field: str = "body") -> Any:
    """Parse a JSON document from a CLI argument."""
    try:
        return json.loads(text)
    except (TypeError, ValueError) as error:
        raise SdkError(
            f"Invalid JSON in {field}: {error}",
            code="invalid_json",
            field=field,
        ) from error


def load_document(path: str) -> Any:
    """Load a JSON document from disk."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise SdkError(f"Cannot read file: {path}", code="invalid_request", field="path") from error
    return read_json(text, field="path")


def make_client(*, allow_write: bool = False) -> SdkClient:
    """Construct a client bound to the shared local router and service."""
    service = get_service()
    transport = InProcessTransport(
        router=default_router(),
        negotiator=CapabilityNegotiator(config=service.config),
        allow_write=allow_write,
    )
    return SdkClient(transport=transport)


def run_call(args: argparse.Namespace) -> int:
    """Execute the call command."""
    body = read_json(args.body)
    if not isinstance(body, dict):
        raise SdkError("Request body must be a JSON object", field="body")
    client = make_client(allow_write=args.allow_write)
    response = client.call(
        args.namespace,
        args.action,
        body,
        capability=args.capability,
        etag=args.etag,
        idempotency_key=args.idempotency_key,
        allow_errors=args.allow_errors,
    )
    emit(render_envelope(response))
    return 0 if response.ok else 1


def run_list(args: argparse.Namespace) -> int:
    """Execute the paginated list command."""
    body = read_json(args.body)
    if not isinstance(body, dict):
        raise SdkError("Request body must be a JSON object", field="body")
    client = make_client()
    pages = []
    total = 0
    for page in client.pages(
        args.namespace,
        args.action,
        body,
        size=args.size,
        max_pages=args.max_pages,
    ):
        rendered = page.as_dict()
        pages.append(rendered)
        total += len(rendered["items"])
    emit({"pages": pages, "page_count": len(pages), "item_count": total})
    return 0


def run_manifest(args: argparse.Namespace) -> int:
    """Execute one manifest subcommand."""
    service = get_service()
    command = args.manifest_command
    if command == "schema":
        emit(service.schema())
        return 0
    if command == "example":
        emit(service.example())
        return 0
    if command == "script":
        emit(example_script())
        return 0
    if command == "validate":
        document = load_document(args.path)
        client = make_client()
        response = client.call("extensions", "validate", {"manifest": document}, allow_errors=True)
        emit(render_envelope(response))
        return 0 if response.ok and response.data.get("valid") is True else 1
    if command == "install":
        document = load_document(args.path)
        body: dict[str, Any] = {
            "manifest": document,
            "allow_write": bool(args.allow_write),
        }
        client = make_client(allow_write=args.allow_write)
        response = client.call(
            "extensions",
            "install",
            body,
            etag=args.etag,
            idempotency_key=args.idempotency_key,
            allow_errors=True,
        )
        emit(render_envelope(response))
        return 0 if response.ok else 1
    if command == "remove":
        body = {"id": args.id, "allow_write": bool(args.allow_write)}
        client = make_client(allow_write=args.allow_write)
        response = client.call("extensions", "remove", body, etag=args.etag, allow_errors=True)
        emit(render_envelope(response))
        return 0 if response.ok else 1
    raise ScriptError(f"Unknown manifest command: {command}")


def run_script(args: argparse.Namespace) -> int:
    """Execute a declarative script plan."""
    document = load_document(args.path)
    plan = ScriptPlan.from_document(document)
    client = make_client(allow_write=args.allow_write)
    result = ScriptRunner(client).run(
        plan,
        allow_write=args.allow_write,
        continue_on_error=args.continue_on_error,
    )
    emit(result.as_dict())
    return 0 if result.success else 1


def dispatch(args: argparse.Namespace) -> int:
    """Dispatch parsed arguments to one command handler."""
    command = args.command
    if command == "capabilities":
        emit(get_service().negotiator.as_dict())
        return 0
    if command == "routes":
        emit(default_router().manifest())
        return 0
    if command == "contracts":
        emit(get_service().contracts())
        return 0
    if command == "safety":
        emit(get_service().safety())
        return 0
    if command == "version":
        emit({"name": "redscribe-sdk-v3", "version": "1.0.0"})
        return 0
    if command == "call":
        return run_call(args)
    if command == "list":
        return run_list(args)
    if command == "manifest":
        return run_manifest(args)
    if command == "script":
        return run_script(args)
    raise ScriptError(f"Unknown command: {command}")


def apply_config(path: str) -> None:
    """Install a local service configured from a JSON file."""
    if not path:
        return
    document = load_document(path)
    if not isinstance(document, dict):
        raise SdkError("Config must be a JSON object", field="config")
    try:
        config = V3Config(**document)
    except (TypeError, ValueError) as error:
        raise SdkError(f"Invalid V3 config: {error}", field="config") from error
    set_service(ExtensionService(config))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; write commands always require an explicit flag."""
    args = build_parser().parse_args(argv)
    try:
        apply_config(args.config)
        return dispatch(args)
    except (SdkError, V3Error) as error:
        code = error.code.value if isinstance(error, V3Error) else error.code
        message = error.message
        sys.stderr.write(
            json.dumps({"error": {"code": code, "message": message}}, sort_keys=True) + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
