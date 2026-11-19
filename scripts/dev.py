"""Start the local browser, runner, and private imaging engine."""

import argparse
from contextlib import ExitStack
from importlib import import_module
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
HOST = "127.0.0.1"
DEFAULT_DATABASE = f"postgresql://mini_nota@{HOST}:55432/mini_nota"
HTTP = build_opener(ProxyHandler({}))


class SetupError(Exception):
    """An actionable startup failure safe to print."""


def configuration():
    database = os.getenv("CATALOG_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DATABASE
    paths = {
        name: (Path.cwd() / os.getenv(name, str(ROOT / default))).resolve()
        for name, default in {
            "RAW_DIR": "data/processed/library-v1/raw",
            "MODEL_BUNDLE": "data/processed/models/cox-v1/model.json",
            "OUTCOMES_CSV": "data/processed/library-v1/outcomes.csv",
        }.items()
    }
    if not paths["RAW_DIR"].is_dir():
        raise SetupError("RAW_DIR is missing. Prepare the local Lung1 library first.")
    for name in ("MODEL_BUNDLE", "OUTCOMES_CSV"):
        if not paths[name].is_file():
            raise SetupError(f"{name} is missing. Configure the prepared library and frozen model.")
    signing_key = os.getenv("CHECKPOINT_SIGNING_KEY") or secrets.token_urlsafe(32)
    if len(signing_key) < 32:
        raise SetupError("CHECKPOINT_SIGNING_KEY must contain at least 32 characters.")
    return database, paths, signing_key


def preflight(database, paths):
    if not shutil.which("node") or not (WEB / "node_modules/next/dist/bin/next").is_file():
        raise SetupError("Install Node and run npm ci in web/.")
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from src.frozen_model import FrozenModel
        import_module("src.engine")
    except (ImportError, OSError) as exc:
        raise SetupError("Install deploy/requirements-runtime.txt in .venv and use its Python.") from exc
    try:
        connection = conninfo_to_dict(database)
    except psycopg.Error as exc:
        raise SetupError("Set CATALOG_DATABASE_URL or DATABASE_URL to a valid local PostgreSQL URL.") from exc
    host = connection.get("host")
    hostaddr = connection.get("hostaddr", HOST if host == "localhost" else host)
    if (
        not database.startswith(("postgresql://", "postgres://"))
        or host not in {HOST, "::1", "localhost"}
        or hostaddr not in {HOST, "::1"}
        or "service" in connection
    ):
        raise SetupError("Use an existing loopback PostgreSQL catalog URL for local startup.")
    try:
        model = FrozenModel(paths["MODEL_BUNDLE"])
        held_out = set(model.bundle["partition"]["held_out"])
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SetupError("MODEL_BUNDLE is unreadable or does not contain a valid frozen model.") from exc
    try:
        with psycopg.connect(database, hostaddr=hostaddr, connect_timeout=3) as conn:
            conn.read_only = True
            patients = {row[0] for row in conn.execute("SELECT patient_id FROM patient_catalog")}
            metadata = conn.execute("SELECT metadata FROM model_metadata WHERE singleton").fetchone()
            evaluation = conn.execute(
                "SELECT 1 FROM model_evaluation WHERE model_version=%s", (model.version,)
            ).fetchone()
    except psycopg.Error as exc:
        raise SetupError("Start local PostgreSQL and import the catalog, frozen model, and evaluation.") from exc
    catalog_model = metadata[0] if metadata else None
    if (
        not held_out or patients != held_out or not isinstance(catalog_model, dict)
        or catalog_model.get("model_version") != model.version or not evaluation
    ):
        raise SetupError("The local catalog and evaluation must match the frozen held-out model.")
    missing = sum(not (paths["RAW_DIR"] / patient / "ct").is_dir() for patient in patients)
    if missing:
        raise SetupError(f"RAW_DIR is missing CT directories for {missing} held-out patients.")
    return len(patients)


def available_ports(web_port):
    # Reserve all three together so an automatically chosen port cannot repeat.
    with ExitStack() as stack:
        ports = []
        for port in (web_port, 0, 0):
            listener = stack.enter_context(socket.socket())
            try:
                listener.bind((HOST, port))
            except OSError as exc:
                raise SetupError(f"Could not bind a loopback port ({port or 'automatic'}).") from exc
            ports.append(listener.getsockname()[1])
        return ports


def start(command, cwd, env, log_path, processes):
    with log_path.open("w") as log:
        processes.append(subprocess.Popen(
            command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        ))


def stop_processes(processes):
    for process in reversed(processes):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for process in reversed(processes):
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def wait_ready(request, label, processes, is_ready):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise SetupError(f"A service exited while waiting for {label}. See the logs.")
        try:
            with HTTP.open(request, timeout=3) as response:
                body = json.load(response)
                if isinstance(body, dict) and is_ready(body):
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise SetupError(f"Timed out waiting for {label}. See the logs.")


def run(database, paths, signing_key, web_port, count, hot_reload):
    web_port, runner_port, engine_port = available_ports(web_port)
    url = f"http://{HOST}:{web_port}"
    runner_url = f"http://{HOST}:{runner_port}"
    engine_url = f"http://{HOST}:{engine_port}"
    logs = Path(tempfile.mkdtemp(prefix="mini-nota-dev-"))
    print(f"Backend log: {logs / 'backend.log'}\nWeb log: {logs / 'web.log'}", flush=True)
    # Pass only local configuration to the children. A shell used for deployment
    # may also contain Modal, artifact-store, or database-writer credentials.
    shell = {name: os.environ[name] for name in ("PATH", "HOME", "TMPDIR", "LANG") if name in os.environ}
    backend = {
        **shell, **{name: str(path) for name, path in paths.items()},
        "CATALOG_DATABASE_URL": database, "CHECKPOINT_SIGNING_KEY": signing_key,
        "ENGINE_SECRET": secrets.token_urlsafe(32), "EXECUTION_BACKEND": "local",
        "RUNNER_HOST": HOST, "PORT": str(runner_port), "ENGINE_PORT": str(engine_port),
    }
    frontend = {
        **shell, "CATALOG_DATABASE_URL": database, "DATABASE_URL": database,
        "RUNNER_URL": runner_url, "NEXT_TELEMETRY_DISABLED": "1",
    }
    next_cli = ["node", "node_modules/next/dist/bin/next"]
    if not hot_reload:
        build_log = logs / "build.log"
        print(f"Building local preview. Build log: {build_log}", flush=True)
        with build_log.open("w") as log:
            build = subprocess.run(
                [*next_cli, "build"], cwd=WEB, env=frontend,
                stdout=log, stderr=subprocess.STDOUT,
            )
        if build.returncode:
            raise SetupError(f"Web build failed. See {build_log}.")

    processes = []
    try:
        start([sys.executable, "-m", "service.backend"], ROOT, backend, logs / "backend.log", processes)
        wait_ready(f"{runner_url}/health", "runner", processes, lambda body: body.get("status") == "ok")
        wait_ready(f"{engine_url}/openapi.json", "engine", processes, lambda body: "/qc" in body.get("paths", {}))
        mode = "dev" if hot_reload else "start"
        start([*next_cli, mode, "--hostname", HOST, "--port", str(web_port)],
              WEB, frontend, logs / "web.log", processes)
        catalog_request = Request(
            f"{url}/api/graphql",
            data=b'{"query":"{ patients { id } modelMetadata { model_version } }"}',
            headers={"Content-Type": "application/json"},
        )
        wait_ready(catalog_request, "web catalog", processes, lambda body: (
            not body.get("errors")
            and len((body.get("data") or {}).get("patients") or []) == count
            and bool((body.get("data") or {}).get("modelMetadata"))
        ))
        wait_ready(f"{url}/api/runs/launch-context", "web connection to the runner", processes,
                   lambda body: bool(body.get("worker_context")))
        print(f"Mini-Nota: {url}\nBrowser tests from web/: WEB_URL={url} npm run test:e2e", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise SetupError("A service stopped. See the logs.")
    finally:
        stop_processes(processes)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Configure an existing loopback catalog with CATALOG_DATABASE_URL or DATABASE_URL. "
            "Override asset locations with RAW_DIR, MODEL_BUNDLE, and OUTCOMES_CSV. "
            "Set a stable CHECKPOINT_SIGNING_KEY to verify saved approvals across restarts."
        ),
    )
    parser.add_argument("--check", action="store_true", help="Validate dependencies, assets, and catalog without starting servers.")
    parser.add_argument("--web-port", type=int, default=0, help="Choose the web port (default: a free port).")
    parser.add_argument("--hot-reload", action="store_true", help="Run Next.js in development mode with Fast Refresh.")
    args = parser.parse_args()
    if not 0 <= args.web_port <= 65535:
        parser.error("--web-port must be between 0 and 65535")
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        database, paths, signing_key = configuration()
        count = preflight(database, paths)
        print(f"Local preflight passed for {count} held-out patients.", flush=True)
        if not args.check:
            run(database, paths, signing_key, args.web_port, count, args.hot_reload)
    except SetupError as exc:
        parser.exit(1, f"mini-nota dev: {exc}\n")
    except OSError:
        parser.exit(1, "mini-nota dev: Could not start a service or open a log file. Check local permissions and dependencies.\n")
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
