# Safe-retry experiment evidence

A local HTTP order service and a scripted tool caller exercise 13 scenarios under
three retry strategies, repeated three times. These are injected failure tests,
not customer incidents or model evaluations. No model, payment service, external
API or cloud resource is involved.

- `attempts.jsonl`: all 288 client attempts, including exceptions and response bodies.
- `server-events.jsonl`: received requests, commits, replays, conflicts and response events.
- `cases.jsonl`: all 117 scenario results, final order/receipt snapshots and process exit codes.
- `run-record.json`: environment, source hash, configuration, runtime and resource measurements.
- `checksums.json`: SHA-256 checksums for the four evidence files above.

Run on Linux with Python 3.11 or newer, from the repository root:

```bash
python3 docs/examples/safe_retries.py run --output runs/safe-retries --repetitions 3
python3 -m unittest discover -s tests -p test_safe_retries.py -v
```

Use a fresh output directory on every run. The driver refuses to overwrite an
existing directory. UUIDs, process IDs, timestamps and timings will vary. A repeat
should preserve the checked order counts, response semantics and crash boundaries.
Every local run also keeps its SQLite databases and per-case process records.
The exported text files contain the observed state for public inspection without
committing hundreds of temporary database files.

The first attempt in the timeout scenario has a 100 ms client socket timeout;
the service commits, then waits 500 ms before responding. Most other requests use
a 2 s socket timeout. The concurrent scenario releases eight HTTP callers through
a barrier. The outage scenario makes three attempts, dropping each response.
This is not an end-to-end deadline or backoff benchmark. Diagnostic event writes
are synchronously flushed and affect timing.

The runner-restart scenario kills a separate client process after it receives and
records HTTP success, before a workflow completion checkpoint. Resuming starts a
new action invocation using the persisted action identity. The server crash cases
exit before commit, after commit, or between separate order/receipt commits.

Tenant headers and fault-injection headers are local test controls. They are not
an authentication scheme and must not be exposed as deployment interfaces. The
example protects a single database transaction. External payments, emails, or
other services need their own idempotency and recovery protocol. Key expiry is
modeled by deleting replay records, not by a tested wall-clock expiry policy.
