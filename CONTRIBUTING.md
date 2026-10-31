# Contributing

Thanks for helping improve RedScribe. The project values a small dependency
surface, predictable behavior, and a UI that stays out of the way.

## Development setup

```bash
git clone https://github.com/yassinalkhulaqi/Cipher-CTF-notes.git
cd Cipher-CTF-notes
python -m venv .venv
```

Activate the environment, then:

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src
```

## Running the app

```bash
python -m redscribe --demo
```

`--demo` seeds a sample vault when the vault is empty. Use `--vault PATH` to
point at a specific database.

## Guidelines

- No runtime dependencies. The core must run on a stock Python 3.10+
  installation; the optional `web` extra provides the native window.
- Keep database work on the UI thread and vault writes transactional.
- New behavior in `src/redscribe` needs tests in `tests`.
- Run `ruff format` before committing.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`,
  `test:`, `chore:`).
- UI changes should preserve dark and light themes, keyboard access, and the
  existing shortcuts.
- Do not add code that phones home, collects telemetry, or executes snippets.

## Security work

Only use RedScribe and its snippets against systems you own or are explicitly
authorized to test.
