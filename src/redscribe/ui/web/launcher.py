"""Launch RedScribe's web frontend in a native window or the system browser.

Window mode uses :mod:`webview` (pywebview), which renders the local UI in the
platform webview (WebView2/Edge on Windows, WebKitGTK on Linux). When the
optional package is missing, RedScribe falls back to opening the same UI in
the default browser — no extra dependencies required.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from redscribe.services.demo import seed_demo
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, WebOverrides
from redscribe.ui.web.server import ApiServer

LOGGER = logging.getLogger(__name__)

WINDOW_TITLE = "RedScribe"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 600


def _open_native_window(url: str, server: ApiServer) -> bool:
    """Open ``url`` in the platform webview. Returns False when unavailable."""
    try:
        import webview  # type: ignore[import-not-found]  # optional extra
    except ImportError:
        return False
    serve_thread = threading.Thread(
        target=server.serve_forever,
        name="redscribe-http",
        daemon=True,
    )
    serve_thread.start()
    webview.create_window(
        WINDOW_TITLE,
        url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT),
    )
    webview.start()
    return True


def run(
    vault_path: Path,
    *,
    mode: str,
    theme: str | None = None,
    font_size: int | None = None,
    demo: bool = False,
    port: int = 0,
    open_browser: bool = True,
) -> int:
    """Start the local web server and open the frontend.

    ``mode`` is ``"window"`` for the native webview (falls back to a browser
    tab) or ``"browser"`` to always use the default browser.
    """
    vault_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="redscribe-vault")
    vault: Vault | None = None
    server: ApiServer | None = None
    try:
        vault = vault_executor.submit(Vault, vault_path).result()
        if demo and vault_executor.submit(vault.basic_stats).result().notes == 0:
            vault_executor.submit(seed_demo, vault).result()
        api = Api(vault, WebOverrides(theme=theme, font_size=font_size))

        def dispatch(method: str, body: dict[str, Any]) -> Any:
            future: Future[Any] = vault_executor.submit(api.handle, method, body)
            return future.result()

        server = ApiServer(("127.0.0.1", port), dispatch)
        bound_port = server.bound_port
        url = f"http://127.0.0.1:{bound_port}/"
        LOGGER.info("RedScribe web UI serving at %s (vault: %s)", url, vault.display_path)

        if mode == "window" and _open_native_window(url, server):
            return 0
        if mode == "window":
            LOGGER.warning(
                "pywebview is not installed; opening RedScribe in the default browser. "
                'Install the window extra with: python -m pip install ".[web]"'
            )
        LOGGER.info("RedScribe is running at %s — press Ctrl+C to stop.", url)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            LOGGER.debug("Ctrl+C received; stopping the web server")
        return 0
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if vault is not None:
            vault_executor.submit(vault.close).result()
        vault_executor.shutdown(wait=True)
