# V3 SDK CLI Reference

Entry point:

```bash
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli [GLOBAL OPTIONS] COMMAND ...
```

The CLI is local-only. It dispatches through the in-process B00 `V3Router`; it
never opens a socket, starts a process, or evaluates a string. JSON results are
written to stdout; errors from command handlers are written as B00 error
envelopes on stdout with exit status 1, while parser/validation failures are
written as `{"error": {"code": ..., "message": ...}}` on stderr.

## Global options

| Option | Meaning |
| --- | --- |
| `--config PATH` | Load a JSON `V3Config` before running the command. This is the only way to enable extension writes in a fresh process. |

Example config:

```json
{
  "allow_extensions": true,
  "enabled_capabilities": ["extensions"],
  "offline_only": true
}
```

`--config` must appear before the subcommand.

## Commands

### Informational (always read-only)

| Command | Output |
| --- | --- |
| `version` | SDK name and version |
| `capabilities` | Negotiated capability map, granted/denied lists |
| `routes` | B00 router manifest with all registered routes |
| `contracts` | SDK wire contracts and error codes |
| `safety` | Static `ast` audit result for all SDK sources and the extensions namespace |

```bash
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli safety
```

### `call NAMESPACE ACTION [OPTIONS]`

Calls one API v3 route and prints the B00 envelope.

| Option | Default | Meaning |
| --- | --- | --- |
| `--body JSON` | `{}` | JSON object request body |
| `--capability NAME` | empty | sends `X-Capability` |
| `--etag TAG` | empty | sends `If-None-Match`; a match produces status 304 |
| `--idempotency-key KEY` | empty | sends `Idempotency-Key`; replay returns cached result |
| `--allow-write` | off | required for write routes |
| `--allow-errors` | off | print error envelopes instead of exiting with an error |

```bash
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli call system info --body '{"echo":"hi"}'
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli call extensions list --body '{"size":10}'
```

### `list NAMESPACE ACTION [OPTIONS]`

Follows B00 signed opaque cursors and prints each page.

| Option | Default |
| --- | --- |
| `--body JSON` | `{}` |
| `--size N` | `50` |
| `--offset N` | `0` |
| `--max-pages N` | `10` |
| `--capability NAME` | empty |

```bash
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli list extensions list --size 5 --max-pages 4
```

### `manifest SCHEMA|EXAMPLE|SCRIPT`

Print the schema descriptor, a valid example manifest, or a read-only example
script. These commands never mutate state.

### `manifest validate PATH`

Validate a JSON manifest file via `extensions.validate`. Exit status is 0 for a
valid declaration and 1 otherwise; the envelope's `data.issues` array lists the
exact paths and codes.

### `manifest install PATH [OPTIONS]`

| Option | Meaning |
| --- | --- |
| `--allow-write` | mandatory opt-in |
| `--idempotency-key KEY` | replay-safe installation |
| `--etag TAG` | conditional update (412 on stale ETag) |

Requires **both** `--allow-write` and a `--config` that enables extension
writes. Without the first, the transport returns `read_only_violation`; without
the second, the service returns `forbidden`.

```bash
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli \
  --config local-config.json \
  manifest install manifest.json --allow-write --idempotency-key install-1
```

### `manifest remove ID [--allow-write] [--etag TAG]`

Removes an installed manifest. Same double opt-in as `install`.

### `script run PATH [OPTIONS]`

Executes a JSON script plan (data only).

| Option | Meaning |
| --- | --- |
| `--allow-write` | permits steps marked `"write": true` |
| `--continue-on-error` | keep running after a failed step |

Without `--allow-write`, a plan containing write steps is rejected before any
call is made. The result contains `name`, `success`, `stopped_early`, and one
entry per executed step with `route`, `status`, `error_code`, and a sanitized
`data` summary.

```bash
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli script run overview.json
PYTHONPATH=src python3 -m redscribe.v3.api_sdk.cli \
  --config local-config.json \
  script run install.json --allow-write
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | command completed successfully |
| 1 | API error envelope, validation failure, or script failure |
| 2 | argparse usage error |

## Safety notes

- `--allow-write` is per invocation; there is no persistent write mode.
- A config file can only enable writes if it is passed explicitly on that same
  invocation.
- Scripts cannot reference files, URLs, modules, functions, or commands; the
  plan schema rejects those keys.
- Body values may contain sensitive data, but the SDK history records only body
  keys, and CLI output is produced only for the command being run.
