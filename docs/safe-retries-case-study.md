# Making agent retries safe across timeouts and restarts

**Imagine an enterprise support agent ordering an approved replacement for a customer. The order goes through, but the confirmation times out. The agent retries and reports success. Two orders are now queued for fulfillment, and the support team has a duplicate to sort out.**

In the local test below, the first request timed out after about 101 ms. The order was already in the database.

Retrying created another order. Both rows had the same tenant, product and quantity. From the caller's side, the sequence looked ordinary: one timeout, then a successful `201 Created`.

There was no unusual model behavior to debug. The caller had lost the response after the service had done the work.

To examine that boundary, this experiment uses a small HTTP order service, a scripted tool caller and two SQLite databases. One database belongs to the caller; the other belongs to the service. The failures are injected locally. This is a deployment exercise, not a report from a customer environment, and it makes no model calls.

Three rounds covered **117 scenario runs and 288 HTTP requests**, retaining the failed attempts as well as the successful ones. Stable keys prevented duplicates in several failure cases. Two controls still created them: saving the receipt separately and deleting it before a late retry.

## What happens between a tool call and its result

Suppose a support agent has approval to order one replacement keyboard. Its tool sends:

```http
POST /orders
Content-Type: application/json

{"sku":"keyboard","quantity":1}
```

The service can accept that request, commit the order, and lose the connection before the caller receives the response. The order exists. The tool invocation appears to have failed.

Raising the timeout above 500 ms would let this response arrive. It would still leave the connection-drop and process-crash cases unresolved.

The test makes the timing explicit. The caller uses a 100 ms socket timeout. The service commits its writes, then holds the response for 500 ms. Here is one recorded attempt, with unrelated fields omitted:

```json
{
  "fault": "timeout_after_commit",
  "timeout_seconds": 0.1,
  "status": null,
  "error_type": "TimeoutError",
  "error": "timed out",
  "elapsed_ms": 100.892311
}
```

The exception describes the caller's wait. The server trace and final database state establish whether the write happened.

This is the same distinction AWS describes in its guidance on [timeouts and retries](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/): a failed call can still have side effects. Backoff helps control retry load. It does not undo a committed order.

## Three retry strategies, the same faults

The caller tried each scenario in three ways:

| Strategy | What the caller sends |
| --- | --- |
| No key | The same payload again, without an operation identifier |
| New key per attempt | A new UUID for every HTTP request |
| Durable action key | One UUID saved for the intended action before the first request, then reused |

The service supports keys in all three runs. The first strategy does not send one. The second sends a different one each time, which makes each retry look like new work.

The table counts **orders created in one scenario run**, not successful responses. All three repetitions produced these counts.

| Injected condition | No key | New key per attempt | Durable action key |
| --- | ---: | ---: | ---: |
| Response arrives normally | 1 | 1 | 1 |
| Caller times out after commit | 2 | 2 | 1 |
| Connection closes after commit | 2 | 2 | 1 |
| Service exits before commit, then restarts | 1 | 1 | 1 |
| Service exits after commit, then restarts | 2 | 2 | 1 |
| Caller process dies before its completion checkpoint | 2 | 2 | 1 |
| Eight concurrent deliveries of one intended action | 8 | 8 | 1 |
| All three responses are dropped | 3 | 3 | 1 |

The before-commit case is an important control. An interrupted transaction leaves no committed order, so the next attempt should create one. After commit, the correct behavior is to return the saved result.

There is no success percentage here. The faults were chosen deliberately, not sampled from production traffic. The counts establish behavior under those faults; they do not estimate how often customers will encounter them.

## Keep the identity outside the model conversation

The durable key belongs to a particular approved action. It is saved before sending the request.

In the example, the caller stores a mapping from `(tenant, action)` to a random UUID. A fresh invocation looks up the same action and gets the same key. That mapping survives a caller restart because it is in SQLite rather than a Python variable.

![The caller saves an action key before sending. The service saves an order and its replay receipt together in one database transaction.](images/safe-retries/durable-boundaries.png)

The workflow must preserve the action identifier too. After a restart, this test resumes `action-1`; it does not ask a model to invent a replacement identity. Generating a new action ID on every restart would lose the protection before the HTTP request was even sent.

Nor should the model decide that every new tool invocation deserves a new key. An SDK retry, a workflow retry and a resumed invocation can all be attempts to complete the same approved action.

Two genuinely separate orders can have identical payloads. If a customer intentionally orders two keyboards in two transactions, hashing the payload as the operation key would incorrectly collapse the second order into the first. The distinct-action control sends the same payload with two action identities and correctly creates two orders.

The payload hash has a different job: detecting a changed request under an existing key.

## The service has to make a promise it can keep

The service stores a replay receipt containing the key, request fingerprint, response status and response body. A repeated request with the same key and payload returns that saved result, including the original order ID.

The relevant sequence is:

```text
BEGIN IMMEDIATE
  look up (tenant, operation, key)
  if a receipt exists:
    reject a different payload, or return the saved response
  otherwise:
    insert the order
    insert its replay receipt
COMMIT
```

Both inserts occur in one transaction. If storing the receipt fails, the order insert rolls back too. One regression test forces exactly that failure with a SQLite trigger, then verifies that a later valid request can still create the order.

For concurrent deliveries, this example acquires the write transaction before reading the receipt. SQLite allows only [one writer at a time](https://www.sqlite.org/lang_transaction.html). That makes the eight-request result straightforward: one request creates the order, and the other seven replay its result.

This choice also serializes unrelated writes. It is convenient for a small reproduction, but the test says nothing about its throughput at customer scale. A different database needs its own tested locking and conflict-handling path.

The key is scoped to the tenant and operation. The same UUID in another tenant must not return the first tenant's order. The local test uses a header to supply tenant identity; a deployed service would have to obtain and authorize that identity from authenticated context. Possessing a key is not permission to see its result.

Reusing a key with a changed quantity returns `409` and creates no second order. Reordering the JSON fields remains a replay, because the fingerprint is computed from canonicalized input. Invalid quantities are rejected before the key is consumed.

These are explicit service semantics. Providers may make different choices about saved errors and retention. For example, [Stripe documents its own replay and parameter-matching rules](https://docs.stripe.com/api/idempotent_requests); copying a header name does not copy that contract.

## A key did not fix the split transaction

One comparison mode deliberately commits the order first and saves the receipt in a second transaction.

The service exits in between. On restart, it has an order but no receipt. The retry uses the original durable key, finds nothing to replay, and creates a second order.

The saved server events show the gap:

```text
order_committed_without_receipt  order A
process exits
request received with same key
committed                        order B
response_sent                    201
```

This excerpt shortens the UUIDs for readability. The complete events retain both IDs and timestamps.

![Separate commits leave an order without a receipt if the process exits between them. A single transaction commits both records or neither.](images/safe-retries/commit-gap.png)

All three repetitions produced **two orders**, despite the stable key. The missing guarantee was atomic storage of the effect and its replay record.

AWS's article on [idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) makes the same requirement explicit: recording the request token and performing the mutations need to be an atomic operation.

That boundary becomes harder when the effect belongs to another system. A local database transaction cannot roll back a payment that an external provider has already accepted. The provider needs to recognize the same operation identity, or the integration needs a way to query and reconcile the outcome. Queuing the work through an outbox can make the local handoff durable, but the receiver still has to tolerate repeated delivery.

This experiment does not implement a payment provider, an outbox or cross-service recovery. Its guarantee ends at the order service's database.

## Stopping retries does not establish failure

Another scenario drops every response and stops after three attempts.

With a durable key, the final database contains one order. The caller has three connection failures and no successful response. Its outcome remains `unknown`.

Reporting that operation as failed would be misleading. Automatically starting a new action with a fresh key could create another order. A workflow needs a distinct path for an unresolved outcome: retain the original identity, reconcile through an authorized lookup or repeat request when safe, and escalate if it cannot establish what happened.

That is also an evaluation requirement. A checker that sees only tool exceptions might mark this as three failed operations. A checker that sees only the database might mark it successful. The full result is that the order was created, duplicates were prevented, and the caller did not receive confirmation.

Retry limits, backoff and a total deadline still matter. The example uses fixed attempt counts to expose correctness; it does not test a production backoff policy or retry storms. Its socket timeout is not a complete workflow deadline.

## How long does the protection last?

A final test deletes the replay receipt after a successful request, then sends the same key again. It creates a second order.

Deleting the receipt models loss of replay history. It is not a wall-clock expiry test. The result is enough to show why a retention window must cover the period in which a workflow can resume, not just the few seconds an HTTP library spends retrying.

For a long-running deployment, I would want a documented answer to this before enabling automatic recovery: what happens if an approved action resumes after the server has forgotten its key?

A durable business identifier with a uniqueness rule may provide longer protection than a temporary response cache. Where that is unavailable, a late resume may need reconciliation rather than another create request.

## Run it and inspect the records

The experiment runs on Linux with Python 3.11 or newer and uses only the standard library. It starts local processes and listens on `127.0.0.1`.

```bash
git clone https://github.com/deavgprime/iac-eval-bench.git
cd iac-eval-bench
git switch --detach 5de3e73a495878377f57324e9947f2e90ca89554
python3 docs/examples/safe_retries.py run \
  --output runs/safe-retries \
  --repetitions 3
python3 -m unittest discover -s tests -p test_safe_retries.py -v
```

Use a fresh output directory each time. The driver refuses to overwrite an existing run.

The [saved evidence](examples/safe-retries-results/README.md) includes every client attempt, the server events and final order/receipt snapshots. The [source](examples/safe_retries.py) includes the unsafe comparison modes, so the duplicate behavior can be reproduced as well as the protected path.

The recorded run used Python 3.12.3 and SQLite 3.45.1. It completed in 29.26 seconds, with 18.53 CPU seconds across child processes. The driver and largest child each reached a reported peak RSS of about 29.4 MiB. Those are per-process peaks, not total concurrent memory. Event logging flushes to disk and affects timing, so these measurements describe the test workload rather than service performance.

The crash tests terminate processes; they do not test a host outage, disk failure or regional failover. The fault headers are test controls, not an interface to expose in a deployment.

Before giving an agent write access, this is a useful small evaluation to run against each tool: lose the response after the write, then retry through the real workflow. Check the external state, the saved operation identity and what the caller reports. A successful retry response alone does not establish that the intended action happened once.
