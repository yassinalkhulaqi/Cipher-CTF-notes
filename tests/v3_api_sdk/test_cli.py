"""Subprocess tests for the read-only-by-default scripting CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from redscribe.v3.api_sdk.manifest import example_manifest

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
CONFIG = {
    "allow_extensions": True,
    "enabled_capabilities": ["extensions"],
    "offline_only": True,
}


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "redscribe.v3.api_sdk.cli", *args],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
        check=False,
    )


def stdout_json(result: subprocess.CompletedProcess[str]) -> Any:
    return json.loads(result.stdout)


def write_json(path: Path, document: Any) -> str:
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def test_cli_version_and_info_commands() -> None:
    result = run_cli("version")
    assert result.returncode == 0
    assert stdout_json(result)["version"] == "1.0.0"

    capabilities = run_cli("capabilities")
    assert capabilities.returncode == 0
    assert stdout_json(capabilities)["advertised"]["extensions"] is True

    routes = run_cli("routes")
    assert routes.returncode == 0
    manifest = stdout_json(routes)
    assert manifest["version"] == "3.0"
    assert "extensions" in manifest["namespaces"]

    contracts = run_cli("contracts")
    assert stdout_json(contracts)["execution"] == "none"

    safety = run_cli("safety")
    assert stdout_json(safety)["clean"] is True


def test_cli_manifest_documentation_commands() -> None:
    schema = run_cli("manifest", "schema")
    assert schema.returncode == 0
    assert stdout_json(schema)["data_only"] is True

    example = run_cli("manifest", "example")
    assert stdout_json(example)["schema"] == "redscribe-extension/1"

    script = run_cli("manifest", "script")
    assert stdout_json(script)["name"] == "local-overview"


def test_cli_validates_manifest_files(tmp_path: Path) -> None:
    valid = write_json(tmp_path / "valid.json", example_manifest())
    result = run_cli("manifest", "validate", valid)
    assert result.returncode == 0
    payload = stdout_json(result)
    assert payload["data"]["valid"] is True
    assert payload["meta"]["api_version"] == "3.0"

    invalid = write_json(tmp_path / "invalid.json", {"id": "x", "code": "eval()"})
    bad = run_cli("manifest", "validate", invalid)
    assert bad.returncode == 1
    assert stdout_json(bad)["data"]["valid"] is False


def test_cli_call_and_list_commands() -> None:
    called = run_cli("call", "system", "info", "--body", '{"echo":"hi"}')
    assert called.returncode == 0
    assert stdout_json(called)["data"]["api_version"] == "3.0"

    listed = run_cli("list", "extensions", "list", "--size", "2", "--max-pages", "3")
    assert listed.returncode == 0
    payload = stdout_json(listed)
    assert payload["page_count"] >= 1
    assert payload["item_count"] >= 0

    missing = run_cli("call", "extensions", "not_a_route")
    assert missing.returncode == 1
    assert "Unknown route" in missing.stderr


def test_cli_rejects_bad_json_and_config(tmp_path: Path) -> None:
    bad_body = run_cli("call", "system", "info", "--body", "{not json}")
    assert bad_body.returncode == 1
    assert "invalid_json" in bad_body.stderr

    missing_file = run_cli("manifest", "validate", str(tmp_path / "nope.json"))
    assert missing_file.returncode == 1
    assert "invalid_request" in missing_file.stderr

    config = write_json(tmp_path / "bad-config.json", {"page_size": 999})
    bad_config = run_cli("--config", config, "version")
    assert bad_config.returncode == 1
    assert "config" in bad_config.stderr


def test_cli_write_requires_double_opt_in(tmp_path: Path) -> None:
    manifest = write_json(tmp_path / "manifest.json", example_manifest())
    config = write_json(tmp_path / "config.json", CONFIG)

    blocked = run_cli("manifest", "install", manifest)
    assert blocked.returncode == 1
    assert stdout_json(blocked)["error"]["code"] == "read_only_violation"

    disabled = run_cli("manifest", "install", manifest, "--allow-write")
    assert disabled.returncode == 1
    denied = stdout_json(disabled)["error"]
    assert denied["code"] == "forbidden"
    assert "disabled by local configuration" in denied["message"]

    installed = run_cli("--config", config, "manifest", "install", manifest, "--allow-write")
    assert installed.returncode == 0
    payload = stdout_json(installed)
    assert payload["data"]["extension"]["id"] == "example.panel"

    blocked_remove = run_cli("manifest", "remove", "example.panel")
    assert blocked_remove.returncode == 1
    assert stdout_json(blocked_remove)["error"]["code"] == "read_only_violation"


def test_cli_idempotent_install(tmp_path: Path) -> None:
    manifest = write_json(tmp_path / "manifest.json", example_manifest())
    config = write_json(tmp_path / "config.json", CONFIG)
    args = (
        "--config",
        config,
        "manifest",
        "install",
        manifest,
        "--allow-write",
        "--idempotency-key",
        "cli-key-1",
    )
    first = run_cli(*args)
    second = run_cli(*args)
    assert first.returncode == 0
    assert second.returncode == 0
    assert stdout_json(first)["data"]["extension"] == stdout_json(second)["data"]["extension"]


def test_cli_script_runner_read_only_by_default(tmp_path: Path) -> None:
    read_only = write_json(
        tmp_path / "read.json",
        {
            "name": "overview",
            "steps": [
                {"namespace": "system", "action": "info", "label": "info"},
                {"namespace": "extensions", "action": "schema", "label": "schema"},
            ],
        },
    )
    result = run_cli("script", "run", read_only)
    assert result.returncode == 0
    payload = stdout_json(result)
    assert payload["success"] is True
    assert [item["label"] for item in payload["steps"]] == ["info", "schema"]


def test_cli_script_write_opt_in(tmp_path: Path) -> None:
    config = write_json(tmp_path / "config.json", CONFIG)
    write_plan = write_json(
        tmp_path / "write.json",
        {
            "name": "install-one",
            "steps": [
                {
                    "label": "install",
                    "namespace": "extensions",
                    "action": "install",
                    "body": {
                        "manifest": example_manifest(),
                        "allow_write": True,
                    },
                    "write": True,
                },
                {
                    "label": "read-back",
                    "namespace": "extensions",
                    "action": "get",
                    "body": {"id": "example.panel"},
                    "write": False,
                },
                {
                    "label": "remove",
                    "namespace": "extensions",
                    "action": "remove",
                    "body": {"id": "example.panel", "allow_write": True},
                    "write": True,
                },
            ],
        },
    )
    blocked = run_cli("script", "run", write_plan)
    assert blocked.returncode == 1
    assert "read_only_violation" in blocked.stderr

    allowed = run_cli("--config", config, "script", "run", write_plan, "--allow-write")
    assert allowed.returncode == 0
    payload = stdout_json(allowed)
    assert payload["success"] is True
    assert payload["steps"][1]["data"]["extension"]["version"] == "1.0.0"
    assert payload["steps"][2]["data"]["removed"] is True


def test_cli_script_validation_errors(tmp_path: Path) -> None:
    bad = write_json(
        tmp_path / "bad.json",
        {"name": "bad", "steps": [{"namespace": "system", "action": "info", "eval": "1"}]},
    )
    result = run_cli("script", "run", bad)
    assert result.returncode == 1
    assert "invalid_script" in result.stderr


@pytest.mark.parametrize("command", ["capabilities", "routes", "contracts", "safety"])
def test_cli_information_commands_are_read_only(command: str) -> None:
    result = run_cli(command)
    assert result.returncode == 0
    assert result.stdout.strip().startswith("{")
