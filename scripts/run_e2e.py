"""Run browser E2E tests with an isolated backend and reliable cleanup."""

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PORT = 5000
READY_URL = f"http://127.0.0.1:{BACKEND_PORT}/__e2e__/health"


def _process_options():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_tree(process):
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


def _assert_port_available():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", BACKEND_PORT))
        except OSError as exc:
            raise SystemExit(
                f"Port {BACKEND_PORT} is already in use; stop the local backend before E2E."
            ) from exc


def _wait_for_backend(process, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(
                f"E2E backend exited before readiness (code {process.returncode})."
            )
        try:
            with urlopen(READY_URL, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.2)
    raise SystemExit("Timed out waiting for the E2E backend.")


def main():
    _assert_port_available()
    playwright_cli = ROOT / "node_modules" / "@playwright" / "test" / "cli.js"
    if not playwright_cli.exists():
        raise SystemExit("Playwright is not installed. Run `npm install` first.")

    environment = os.environ.copy()
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "AI_USAGE_E2E": "1",
        }
    )
    backend_process = None
    browser_process = None
    with tempfile.TemporaryDirectory(prefix="ai-usage-e2e-") as temp_dir:
        database_path = Path(temp_dir) / "sessions.sqlite3"
        backend_command = [
            sys.executable,
            "-B",
            str(ROOT / "scripts" / "e2e_backend.py"),
            "--database",
            str(database_path),
            "--port",
            str(BACKEND_PORT),
        ]
        try:
            print(f"> {' '.join(backend_command)}", flush=True)
            backend_process = subprocess.Popen(
                backend_command,
                cwd=ROOT,
                env=environment,
                **_process_options(),
            )
            _wait_for_backend(backend_process)

            browser_command = [
                os.environ.get("NODE_BINARY", "node"),
                str(playwright_cli),
                "test",
                "--config",
                "playwright.config.js",
            ]
            print(f"> {' '.join(browser_command)}", flush=True)
            browser_process = subprocess.Popen(
                browser_command,
                cwd=ROOT,
                env=environment,
                **_process_options(),
            )
            return_code = browser_process.wait()
            if return_code:
                raise SystemExit(return_code)
        finally:
            _terminate_tree(browser_process)
            _terminate_tree(backend_process)

    print("Browser E2E suite passed; temporary backend data removed.")


if __name__ == "__main__":
    main()
