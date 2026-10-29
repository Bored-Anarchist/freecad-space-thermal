# Isolated workers and durable jobs (WP-06)

`fcst_app.jobs.JobStore` persists submissions, immutable model/artifact closures,
execution profile/features, actual backend build hash, dependency provenance,
settings, platform, budgets and seeds in the project's SQLite database before
returning a job ID. Actor-scoped exact retries return the original job; conflicting
payloads fail. Connections belong to their calling thread. Independent clients can
query, cancel and edit the project while a worker runs. Client timeout or disconnect
does not change job truth.

`Scheduler` holds an OS lease per project and dispatches queued jobs in submission
order, one worker at a time. Another scheduler cannot recover or steal active jobs.
On lease acquisition, previously running/cancelling attempts become `interrupted`;
queued work remains queued, and terminal states never change. `retry()` creates a
linked attempt. Neither a retry nor a service restart promotes an interruption to
success. Keep the SQLite database with its WAL while active; use SQLite's online
backup API for a consistent operational backup. Portable `.fcst` exports include
attached results, while the operational job queue remains in the database.

The trusted application supplies the backend registry and scopes. Requests, model
content, artifact references and checkpoints cannot select an executable. The native
registry probes build information and hashes the actual installed executable; the
scheduler rechecks its hash before launching. The standalone C++ worker needs no
FreeCAD, Python, vendor executable or vendor library search path. The launcher
passes only OS/runtime environment essentials and single-thread numerical settings.
The worker starts suspended and joins a Windows Job Object before it can execute.
The object bounds aggregate committed memory and the process tree (eight processes),
and kills the entire tree when the scheduler exits, including hard termination.
Workers run under the local user's account: process isolation is not an OS security
sandbox for arbitrary untrusted executable code.

The v1 bounded binary control stream carries handshake, submit, progress,
diagnostics, checkpoint acknowledgements and one terminal outcome. Frames are at
most 65,536 bytes, the pipe reader queue holds eight frames, and each job accepts at
most 1,024 serialized events. Logs never share protocol framing; worker stderr is
discarded by this launcher. Status queries page at most 64 events. A separate atomic
`cancel.frame` is a bounded cooperative request; the worker serializes its `cancel`
acknowledgement with its outgoing stream. Only that acknowledgement enters the
transcript, avoiding two-writer sequence races. A cancellation request alone does
not imply completion; success can win a cancellation race. Defaults are 60 seconds
wall time, two seconds cancellation grace, 256 MiB tree memory and 64 MiB total
checkpoint/result/query output. These limits are persisted per attempt. A missed
cancellation deadline terminates the tree and records `cancelled` with an explicit
termination reason; a wall timeout fails the attempt.

Success requires a valid terminal frame, clean EOF and zero exit status. Truncated,
oversized or trailing messages, abnormal exits, partial arrays, mismatched metadata
and out-of-root/reparse/hard-linked artifacts fail without publishing a result.
Exact output bytes, validated v1 result/HDF5 manifests and job success are committed
in one SQLite transaction. Snapshot, project, case, revision, execution mode,
backend/build, node identities and array dimensions must agree. A historical result
retains the frozen snapshot. Live attachment atomically checks both revision and
semantic hash and adds portable result artifacts and dependency invalidation; even
an engineering-equivalent later revision requires the explicit historical view.

Checkpoint restart is opt-in per trusted backend. The latest verified checkpoint
binds exact state bytes, snapshot/build hashes, case, time and sequence. Resuming
requires the same revision, settings, features, backend, dependencies and seeds;
backend state readers must additionally validate their format and preserve numerical,
time/event/control/random state. Unsupported resume reports
`resume_unsupported_use_fresh_attempt`; `retry(..., resume=False)` creates a fresh
linked attempt. The current native worker validates and hashes the snapshot and
case, then returns a failed `not_implemented` diagnostic because production thermal
assembly/solving belongs to WP-11. It advertises no solver and supports no resume.
The synthetic acceptance peer exercises successful results and restart state; these
tests never count as owned thermal physics qualification.

The Python API supports submit/query/cancel/retry/result/attach and frozen
`job.submit`, `job.cancel`, `result.query` operation dispatch with server-owned
execution configuration. Result queries produce bounded HDF5 slices held as job
artifacts. `ProjectStore.dispatch(..., jobs=jobs, execution=backend['execution'])`
routes job operations; without a configured service they remain unavailable.
Local CLI commands use the trusted `local-client` actor:

```text
fcst job-submit project.db --worker install/bin/fcst-worker.exe --case CASE_UUID --key REQUEST_UUID --expected-revision 0
fcst job-run project.db --worker install/bin/fcst-worker.exe
fcst job-status project.db --job JOB_UUID
fcst job-cancel project.db --job JOB_UUID
fcst job-retry project.db --job JOB_UUID --key NEW_REQUEST_UUID
fcst job-result project.db --job JOB_UUID --historical
```

Unattended acceptance is `python tools/check_jobs.py --worker PATH_TO_WORKER` plus
`tests/test_jobs.py`. Both Windows verification drivers run these checks. They cover
durable deduplication, scope, process exit/disconnect, cancellation/forced timeout,
service lease recovery, exact checkpoint restart, output integrity, late callbacks,
portable attachment and stale/historical guards. Real subprocess kill points cover
submission, staged publication, terminal commit and post-commit recovery. Only case
IDs, verdicts and hashes enter `jobs.json`; project databases, raw logs, snapshots,
checkpoint files, executables and HDF5 artifacts stay local. TST-021 scans the exact
public report before CI upload and staged files plus outgoing history before push.
