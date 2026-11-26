"""Exercise retry boundaries against a local HTTP service and durable SQLite state.

Run: python docs/examples/safe_retries.py run --output /tmp/retry-evidence
The intentionally unsafe modes are comparison controls, not deployment examples.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import platform
import resource
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STRATEGIES = ("no_key", "new_key_per_attempt", "durable_key")
CASES = (
    "normal",
    "timeout_after_commit",
    "disconnect_after_commit",
    "server_crash_before_commit",
    "server_crash_after_commit",
    "runner_restart",
    "concurrent_delivery",
    "changed_payload",
    "distinct_actions",
    "tenant_isolation",
    "retry_budget_exhausted",
    "expired_receipt",
    "split_transaction_crash",
)
BODY = {"sku": "keyboard", "quantity": 1}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def database(path):
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def initialize(path):
    with database(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS receipts (
                tenant TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, status INTEGER NOT NULL, response TEXT NOT NULL,
                PRIMARY KEY (tenant, operation, key)
            );
            """
        )


def apply_order(connection, tenant, key, payload, event, fault="", split=False):
    """Commit the order and replay result together, except in the unsafe split control."""
    encoded = canonical(payload)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = None
        if key:
            row = connection.execute(
                "SELECT * FROM receipts WHERE tenant=? AND operation=? AND key=?",
                (tenant, "POST /orders", key),
            ).fetchone()
        if row:
            connection.rollback()
            if row["fingerprint"] != fingerprint:
                event("payload_conflict", key=key)
                return 409, {"error": "key already used with a different payload"}, True
            event("replayed", order_id=json.loads(row["response"])["order_id"], key=key)
            return row["status"], json.loads(row["response"]), True
        order_id = str(uuid.uuid4())
        response = {"order_id": order_id, "status": "created"}
        connection.execute("INSERT INTO orders VALUES (?, ?, ?)", (order_id, tenant, encoded))
        if fault == "server_crash_before_commit":
            event("exiting_before_commit", order_id=order_id)
            os._exit(71)
        if split:
            connection.commit()
            event("order_committed_without_receipt", order_id=order_id)
            if fault == "split_transaction_crash":
                os._exit(72)
            connection.execute("BEGIN IMMEDIATE")
        if key:
            connection.execute(
                "INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?)",
                (tenant, "POST /orders", key, fingerprint, 201, canonical(response)),
            )
        connection.commit()
        event("committed", order_id=order_id, key=key)
        if fault == "server_crash_after_commit":
            os._exit(73)
        return 201, response, False
    except BaseException:
        connection.rollback()
        raise


def serve(args):
    initialize(args.database)
    lock = threading.Lock()

    def event(kind, **fields):
        with lock, args.events.open("a") as stream:
            stream.write(canonical({"event": kind, "time_ns": time.time_ns(), **fields}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            if self.path != "/orders":
                self.send_error(404)
                return
            tenant = self.headers.get("X-Tenant", "tenant-a")
            key = self.headers.get("Idempotency-Key")
            fault = self.headers.get("X-Test-Fault", "")
            attempt = self.headers.get("X-Attempt")
            event("received", tenant=tenant, key=key, fault=fault, attempt=attempt)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("invalid body length")
                payload = json.loads(self.rfile.read(length))
                if (
                    not isinstance(payload, dict)
                    or set(payload) != {"sku", "quantity"}
                    or not isinstance(payload["sku"], str)
                    or not payload["sku"]
                    or type(payload["quantity"]) is not int
                    or not 1 <= payload["quantity"] <= 100
                ):
                    raise ValueError("expected a sku and an integer quantity from 1 to 100")
            except (ValueError, TypeError):
                self.send_error(400)
                return
            connection = database(args.database)
            try:
                status, response, replayed = apply_order(
                    connection,
                    tenant,
                    key,
                    payload,
                    event,
                    fault,
                    split=self.headers.get("X-Test-Split") == "yes",
                )
            finally:
                connection.close()
            if fault == "timeout_after_commit":
                time.sleep(0.5)
            elif fault == "hold_response":
                time.sleep(2)
            if fault == "disconnect_after_commit":
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                event("response_dropped", attempt=attempt)
                return
            encoded = canonical(response).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("X-Replayed", str(replayed).lower())
                self.end_headers()
                self.wfile.write(encoded)
                event("response_sent", status=status, attempt=attempt)
            except (BrokenPipeError, ConnectionResetError):
                event("response_unread", attempt=attempt)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    write_json(args.ready, {"port": server.server_port, "pid": os.getpid()})
    server.serve_forever(poll_interval=0.05)


def request(port, payload, key, tenant="tenant-a", fault="", split=False, timeout=2):
    started = time.perf_counter_ns()
    record = {
        "attempt_id": str(uuid.uuid4()),
        "key": key,
        "tenant": tenant,
        "payload": payload,
        "fault": fault,
        "timeout_seconds": timeout,
    }
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {
        "Content-Type": "application/json",
        "X-Tenant": tenant,
        "X-Test-Fault": fault,
        "X-Attempt": record["attempt_id"],
    }
    if key:
        headers["Idempotency-Key"] = key
    if split:
        headers["X-Test-Split"] = "yes"
    try:
        connection.request("POST", "/orders", canonical(payload), headers)
        response = connection.getresponse()
        data = response.read().decode()
        record.update(
            status=response.status, response=data, replayed=response.getheader("X-Replayed")
        )
    except (OSError, http.client.HTTPException) as error:
        record.update(status=None, error_type=type(error).__name__, error=str(error))
    finally:
        connection.close()
    record["elapsed_ms"] = (time.perf_counter_ns() - started) / 1_000_000
    return record


def intent_key(path, strategy, action="action-1", tenant="tenant-a"):
    if strategy == "no_key":
        return None
    if strategy == "new_key_per_attempt":
        return str(uuid.uuid4())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS intents "
            "(tenant TEXT, action TEXT, key TEXT, PRIMARY KEY(tenant, action))"
        )
        connection.execute(
            "INSERT OR IGNORE INTO intents VALUES (?, ?, ?)",
            (tenant, action, str(uuid.uuid4())),
        )
        return connection.execute(
            "SELECT key FROM intents WHERE tenant=? AND action=?", (tenant, action)
        ).fetchone()[0]


class Service:
    def __init__(self, folder):
        self.folder = folder
        self.process = None
        self.port = None
        self.restarts = 0
        self.exit_codes = []

    def start(self):
        ready = self.folder / f"ready-{self.restarts}.json"
        self.restarts += 1
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "serve",
                "--database",
                str(self.folder / "server.sqlite"),
                "--events",
                str(self.folder / "server.jsonl"),
                "--ready",
                str(ready),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while not ready.exists():
            if self.process.poll() is not None or time.monotonic() > deadline:
                self.stop()
                raise RuntimeError("service failed to start")
            time.sleep(0.01)
        self.port = json.loads(ready.read_text())["port"]

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
        try:
            _, errors = self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            _, errors = self.process.communicate(timeout=5)
        self.exit_codes.append(self.process.returncode)
        if errors:
            with (self.folder / "server-stderr.txt").open("ab") as stream:
                stream.write(errors)
        self.process = None

    def restart(self):
        self.stop()
        self.start()


def run_case(folder, strategy, case):
    folder.mkdir(parents=True, exist_ok=False)
    service = Service(folder)
    attempts = []
    started = time.perf_counter()
    journal = folder / "runner.sqlite"

    def send(payload=BODY, tenant="tenant-a", action="action-1", fault="", split=False):
        record = request(
            service.port,
            payload,
            intent_key(journal, strategy, action, tenant),
            tenant,
            fault,
            split,
            timeout=0.1 if fault == "timeout_after_commit" else 2,
        )
        attempts.append(record)
        return record

    try:
        service.start()
        if case == "normal":
            send()
        elif case in ("timeout_after_commit", "disconnect_after_commit"):
            send(fault=case)
            if case == "timeout_after_commit":
                time.sleep(0.55)
            send()
        elif case.startswith("server_crash") or case == "split_transaction_crash":
            send(fault=case, split=case == "split_transaction_crash")
            service.restart()
            send()
        elif case == "runner_restart":
            client = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "client",
                    "--port",
                    str(service.port),
                    "--strategy",
                    strategy,
                    "--journal",
                    str(journal),
                    "--result",
                    str(folder / "first-client.json"),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 10
                while not (folder / "first-client.json").exists():
                    if client.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("client did not reach its crash boundary")
                    time.sleep(0.01)
                attempts.append(json.loads((folder / "first-client.json").read_text()))
                client.kill()
                client.communicate(timeout=5)
                write_json(folder / "client-exit.json", {"returncode": client.returncode})
            finally:
                if client.poll() is None:
                    client.kill()
                    client.communicate(timeout=5)
            send()
        elif case == "concurrent_delivery":
            barrier = threading.Barrier(8)

            def simultaneous(unused):
                barrier.wait(timeout=5)
                return send()

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(simultaneous, range(8)))
        elif case == "changed_payload":
            send()
            send(payload={"sku": "keyboard", "quantity": 2})
        elif case == "distinct_actions":
            send()
            send(action="action-2")
        elif case == "tenant_isolation":
            key = str(uuid.uuid4()) if strategy == "durable_key" else None
            if strategy == "durable_key":
                for tenant in ("tenant-a", "tenant-b"):
                    attempts.append(request(service.port, BODY, key, tenant))
            else:
                send()
                send(tenant="tenant-b")
        elif case == "retry_budget_exhausted":
            for unused in range(3):
                send(fault="disconnect_after_commit")
        elif case == "expired_receipt":
            send()
            with database(folder / "server.sqlite") as connection:
                connection.execute("DELETE FROM receipts")
            send()
        else:
            raise ValueError(case)
    finally:
        service.stop()
    with database(folder / "server.sqlite") as connection:
        orders = [dict(row) for row in connection.execute("SELECT * FROM orders ORDER BY rowid")]
        receipts = [
            dict(row) for row in connection.execute("SELECT * FROM receipts ORDER BY rowid")
        ]
    result = {
        "strategy": strategy,
        "case": case,
        "attempts": attempts,
        "orders": orders,
        "receipts": receipts,
        "order_count": len(orders),
        "http_attempts": len(attempts),
        "service_exit_codes": service.exit_codes,
        "elapsed_seconds": time.perf_counter() - started,
        "client_outcome": "unknown" if all(a["status"] is None for a in attempts) else "observed",
    }
    validate_result(result)
    write_json(folder / "result.json", result)
    return result


def validate_result(result):
    case, strategy = result["case"], result["strategy"]
    keyed = strategy == "durable_key"
    counts = {
        "normal": 1,
        "server_crash_before_commit": 1,
        "distinct_actions": 2,
        "tenant_isolation": 2,
        "expired_receipt": 2,
        "split_transaction_crash": 2,
        "concurrent_delivery": 1 if keyed else 8,
        "retry_budget_exhausted": 1 if keyed else 3,
        "changed_payload": 1 if keyed else 2,
    }
    expected = counts.get(case, 1 if keyed else 2)
    assert result["order_count"] == expected, result
    attempts = result["attempts"]
    if case in (
        "timeout_after_commit",
        "disconnect_after_commit",
        "server_crash_before_commit",
        "server_crash_after_commit",
        "split_transaction_crash",
    ):
        assert attempts[0]["status"] is None, result
        assert attempts[-1]["status"] == 201, result
    if case == "retry_budget_exhausted":
        assert result["client_outcome"] == "unknown", result
    elif case == "changed_payload" and keyed:
        assert [a["status"] for a in attempts] == [201, 409], result
    else:
        assert attempts[-1]["status"] == 201, result
    if case == "timeout_after_commit":
        assert attempts[0]["error_type"] in ("TimeoutError", "timeout"), result
    if case == "server_crash_before_commit":
        assert result["service_exit_codes"][0] == 71, result
    if case in ("server_crash_after_commit", "split_transaction_crash"):
        assert result["service_exit_codes"][0] == (73 if case.startswith("server") else 72)
    if keyed and case in (
        "timeout_after_commit",
        "disconnect_after_commit",
        "server_crash_after_commit",
        "runner_restart",
    ):
        assert attempts[-1]["replayed"] == "true", result
    if keyed and case == "concurrent_delivery":
        assert len({json.loads(a["response"])["order_id"] for a in attempts}) == 1
        assert sum(a["replayed"] == "false" for a in attempts) == 1


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    results = []
    try:
        for repetition in range(args.repetitions):
            for case in CASES:
                for strategy in STRATEGIES:
                    folder = args.output / f"round-{repetition + 1}" / case / strategy
                    result = run_case(folder, strategy, case)
                    results.append(
                        {
                            "round": repetition + 1,
                            "case": case,
                            "strategy": strategy,
                            "orders": result["order_count"],
                            "http_attempts": result["http_attempts"],
                            "elapsed_seconds": result["elapsed_seconds"],
                        }
                    )
            print(
                f"Round {repetition + 1}: {len(CASES) * len(STRATEGIES)} cases verified", flush=True
            )
    finally:
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        write_json(
            args.output / "run-record.json",
            {
                "python": sys.version,
                "platform": platform.platform(),
                "sqlite": sqlite3.sqlite_version,
                "model_calls": 0,
                "network": "HTTP on 127.0.0.1 only",
                "results": results,
                "elapsed_seconds": time.perf_counter() - started,
                "child_cpu_seconds": after.ru_utime
                + after.ru_stime
                - before.ru_utime
                - before.ru_stime,
                "max_child_rss_kib": after.ru_maxrss,
                "driver_max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "complete": len(results) == args.repetitions * len(CASES) * len(STRATEGIES),
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve")
    for name in ("database", "events", "ready"):
        server.add_argument("--" + name, type=Path, required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--repetitions", type=int, default=3)
    client = sub.add_parser("client")
    client.add_argument("--port", type=int, required=True)
    client.add_argument("--strategy", choices=STRATEGIES, required=True)
    client.add_argument("--journal", type=Path, required=True)
    client.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "serve":
        serve(args)
    elif args.command == "client":
        key = intent_key(args.journal, args.strategy)
        result = request(args.port, BODY, key)
        write_json(args.result, result)
        # The parent kills this client before a workflow completion checkpoint exists.
        time.sleep(30)
    else:
        if not 1 <= args.repetitions <= 10:
            parser.error("repetitions must be between 1 and 10")
        run(args)


if __name__ == "__main__":
    main()
