# Local MCP automation

WP-14 supplies `fcst-mcp serve --config launch.json` (equivalently
`python -m fcst_mcp serve --config launch.json`). Install `fcst[mcp]` for
JSON Schema validation and HDF5 results. No cloud provider, network endpoint,
sampling, arbitrary-code tool, or optional MCP extension is required.

The launcher supplies a trusted configuration; tools cannot create or replace
it. Create the operational database through `ProjectStore.create` or open an
existing project database. A minimal local configuration is:

```json
{
  "database": "project.db",
  "worker": "out/windows-release/Release/fcst-worker.exe",
  "policy": {
    "root": ".local/automation",
    "project_id": "00000000-0000-4000-8000-000000000001",
    "case_ids": ["00000000-0000-4000-8000-000000000022"],
    "actor": "local-analyst"
  }
}
```

Resolve launch-relative paths from the working directory. The root must exist;
the database is relative to that root. The project UUID must match the database.
Case UUIDs are authorized in advance, including cases the client will create.
The worker path is trusted launcher configuration and its exact bytes are pinned
in every job. Actor/provider identifiers are supplied by the launcher; MCP client
identity metadata is informational and never grants authority.

Defaults allow reversible project edits and deny file exports. Explicit launch
options `allow_export` and `allow_source_export` permit new local output files
and separately permit copying preserved source artifacts. Package outputs use `.fcst`; generated reports use `.json`. Existing destinations,
source overwrite, traversal, links, junctions and hardlinks are rejected. There
is no external-disclosure or privileged-execution implementation to enable.
The working root is an application I/O boundary, not an operating-system sandbox.
Launch configuration and installed code must remain trusted.

`max_wall_s`, `max_memory_mb`, `max_artifact_bytes`, `max_active_jobs` and
`max_response_bytes` bound jobs and responses. Requests may reduce compute
budgets, and cannot increase them. Windows Job Objects contain the worker tree;
wall and cancellation deadlines terminate it. Active-job admission is checked
under the durable submission write lock. Output artifacts have per-job and
resource-store bounds; audit capacity fails explicitly instead of pruning records.

## Protocol profiles

The primary profile pins the released
[2026-07-28 protocol](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning),
its [stdio binding](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
and [discovery operation](https://modelcontextprotocol.io/specification/2026-07-28/server/discover).
Every request carries `io.modelcontextprotocol/protocolVersion` and
`io.modelcontextprotocol/clientCapabilities` in `params._meta`. It has no
initialization handshake. Results identify their type and server identity;
read results declare private caching with zero lifetime. Unknown versions return
`-32022`; missing required metadata returns `-32602`.

The independently tested legacy profile pins `2025-11-25` and official Python
SDK `mcp==1.26.0` (MIT; copyright Anthropic, PBC). It requires `initialize`, then
`notifications/initialized`. The SDK is a test dependency, not the modern
protocol implementation. Its complete wheel hash lock is
`ci/mcp-requirements.lock`. The modern wire implementation is owned code and
is tested against the exact upstream schema in `spec/mcp`, with its upstream
license preserved. Optional HTTP, Tasks and subscriptions are unsupported.

## Tools and resources

`tools/list` publishes operation-specific argument/result schemas and paginates
the discovery response. `schemas_get` retrieves an individual published contract.
Unknown fields and operations are rejected. Request IDs are limited to 128 characters or exact integers within the IEEE-754
safe range. JSON is bounded and rejects duplicate
keys, nonfinite numbers and excessive nesting. Responses never include raw
exceptions or local filesystem paths.

Inspection includes project summaries, UUID-based entities, dependencies,
compatibility discovery, validation and paged object queries. Transactions share
`ProjectStore` preview/apply/undo, revision checks and durable actor-scoped
idempotency. Typed node, conductor, material, optics, load and case tools create
their canonical entity definitions. Assignments represented by other canonical
entities use `changes_preview` / `changes_apply`; those transactions validate
the whole model atomically. Material definitions alone do not attach material
properties to a thermal node. Unsupported spatial features cannot become solves.

`solve_submit` returns a durable job UUID. `jobs_get` and `jobs_cancel` recover
and control that job across stdio processes. A separate scheduler is launched
automatically and exits after an idle interval. Stdio EOF or
`notifications/cancelled` has no application cancellation authority. A killed
scheduler leaves an interrupted attempt, and cannot manufacture success. On
reconnect, the server wakes the queue service so abandoned attempts recover
without resubmission. Client launchers that terminate process trees can interrupt
a worker; confirmed terminal outcomes remain durable.
Application cancellation has a bounded worker-termination fallback. Completed
jobs retain their outcomes, including when cancellation races completion.

The native adapter supports geometry-free conduction steady/transient cases.
The selected case supplies mode, interval and overlays; an explicit zero
environment-power vector records that a network without surfaces has no
environmental receivers. Spatial/radiation models require their corresponding
qualified callback integration and are rejected by this profile. The native
transient CLI can omit individual step records with `include_steps: false`;
sample values, events, total step count, provenance and numerical counters remain
present. Default CLI calls retain step records. The historical generic worker
handshake still reports `solver_available: false`; this adapter invokes the
separate native thermal CLI and publishes verified HDF5 through `JobStore`.

`results_query` pages samples and selected node UUIDs; historical access must be
explicit. Times use seconds, temperatures use kelvin, and power/residual values use watts. `results_compare` requires matching node identities/time grids.
`balances_get` returns a resource containing native boundary-power sums and
equation residual summaries. It does not infer a new energy acceptance verdict.
Model edits make prior results stale for live-model use.

Resources use authorized project/revision/entity or artifact UUIDs. Artifact
references bind exact byte length and SHA-256; reads return explicit base64 byte
pages, with the original bytes recoverable by concatenation. Artifact access
also checks actor and case scope. Audit pages contain actor/provider, tool
version, argument hashes, before/after revisions, change hashes and outcomes.
Canonical transaction history and frozen job inputs retain replay data locally.
Imported labels, comments, paths and logs cannot alter this policy, execution
mode, criteria or qualification status.

`snapshot_create` saves a portable project to a new authorized destination.
Import/export preview and submit currently inspect and copy portable FCST
packages into new destinations, preserving their exact source bytes and
fidelity metadata. They never replace the live database or execute a vendor
converter. Preview plans bind actor, operation, source bytes and model revision.
`reports_generate` writes a local summary explicitly labeled unqualified.
Vendor-specific conversion tools, `mesh_submit`, `radiation_submit` and
`viewport_capture` are declared unavailable. No screenshot is captured implicitly.
Integrated two-surface P0 parity remains WP-15; production spatial physics and
complete vendor/Q1 qualification remain with their owning work packages.

## Unattended verification and publication

Install both tooling locks, then run:

```text
python -m pip install --require-hashes --only-binary=:all: -r ci/requirements.lock -r ci/mcp-requirements.lock
python tools/check_mcp.py --worker out/windows-release/Release/fcst-worker.exe --report .local/mcp.json
python tools/verify.py --preset windows-debug
python tools/verify.py --preset windows-release
```

Qualification gives native Debug/Release test jobs an explicit 300-second wall
budget and bounds the client wait around that budget; numerical temperature and
energy thresholds remain fixed.

The frozen acceptance list covers in-process attacks, real modern stdio model
construction/native solve/reconnection, independent analytic temperature/energy
checks, official SDK legacy lifecycle, live/queued cancellation and interrupted
service recovery. Missing, skipped, failed or substituted evidence fails the
candidate/input/worker-bound gate. Both Windows configurations publish only
privacy-cleared `mcp.json`; raw projects, launch configuration, audit/database
files, result arrays, process/compiler logs and engineering originals remain
local. Exact staged bytes, outgoing history/approved identities and final GitHub
prose are scanned before publication as required by TST-021.
