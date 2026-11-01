# CI execution and public download caches

Both Windows configurations retain all existing acceptance cases, fixed seeds,
sample counts, scaling sizes and numerical tolerances. This change does not create
a smaller qualification tier or move required acceptance to a scheduled workflow.

`tools/verify.py --preset windows-release --jobs 2` runs compilation and installation
before scheduling a bounded number of independent acceptance processes.
The current hosted experiment uses three workers for Debug and two for Release. Historical stage
costs prioritize long work so expensive application tests do not form a late tail;
estimates only change order and never remove new or existing work. Each stage receives
its own temporary directory. The SUNDIALS numerical checkpoint and IDA reference
preparation serialize access to shared downloads. Numerical libraries remain
single-threaded; `--tier full` serializes acceptance. Hosted timing observations
under this schedule are not frozen-hardware performance qualification.

The full Python unit suite runs once in the Foundation workflow. Its bounded JSON
receipt records candidate, coverage-manifest and actual source hashes. Debug and
Release consume that artifact from the same run and reject missing, duplicate,
failed, stale or substituted evidence. Publication checks independently retain the
privacy, gate, validation-boundary and CI/cache adversarial regressions, followed
by the complete outgoing-history scan. Local verification runs units directly
unless an explicit matching receipt is supplied.

The driver asks CTest for its complete configured inventory. Every thermal and
radiation invocation must match an acceptance-owned executable, case argument and
fixture exactly; an additional or changed CTest invocation fails verification.
The acceptance scripts execute these cases and retain their existing metrics and
binary/source bindings. CTest itself executes the two remaining native smoke
cases. No prior pass verdict is cached.

MSVC package probes retain two MSBuild projects. A separate resumed experiment
uses four compiler processes per Embree project, with two for other packages.
The compiler budget is explicit and recorded with each report. The measured Ninja experiment did not establish a gain and was not
adopted; the original package configuration, full build, install and fresh
installed-consumer checks remain. Numerical prototype build directories are stable per checkout and
configuration, while each attempt keeps its own installed runtime and evidence.
Superseded PR workflows cancel automatically. Main/release runs are retained, and
lightweight workflows no longer duplicate feature-branch push and PR events.

## Publication privacy and cache contents (TST-021)

Online caches contain only `.local/public-download-cache/wheels` and `objects`.
The cache validator admits pristine public distributions whose actual bytes match
reviewed upstream SHA-256 locks; original license notices and attribution remain
unchanged. Standalone wheel filenames must also match the locked package/version.
Public source, compiler, FreeCAD and reference-runtime archives use digest-only
object names and locked sizes where declared. These are upstream distribution
copies, not locally built packages or engineering inputs.

`tools/cache_downloads.py prepare --lock ci/requirements.lock` validates every
restored file before copying archives or resolving wheels. Installation uses the
validated wheelhouse offline with hash checking. A complete hit requires no package
index requests. A miss downloads only hash-locked wheels. `seal` checks actual
outgoing files immediately before the separate cache-save action. An unexpected
file, nested directory, link/reparse point, altered object, wrong wheel pin or
hash mismatch fails closed with category-only diagnostics.

Cache keys include all distribution locks, relevant source/runtime profiles, the
publication policy and validator implementation. There are no fallback keys and
no implicit post-job pip-cache upload. Raw build trees, locally generated native
binaries, debug paths, logs, reports, correspondence and model inputs never enter
this cache. General publication scanning still rejects uninspected binary/media
uploads. Authorized originals and existing restricted evidence remain local.

Unattended regressions in `tests/test_ci_performance.py` exercise concurrency
bounds, shared-resource serialization, native-coverage substitution, stale unit
receipts, corrupted/unlisted cache content and workflow clearance bypasses.
They belong to both the unit manifest and Publication security scope. Planning,
workflow, exact-file and outgoing-history checks remain required. Cache misses,
performance measurements and candidate receipts must never be treated as a
permission to bypass these checks.

`verification.json` records wall time, worker count, relative stage starts,
local-versus-receipt unit execution and cold/warm/unknown download-cache state.
Package reports include generator, project/compiler worker counts and configure/build/install/consumer
timings. Thermal acceptance records per-case durations so the next solver-test
bottleneck can be identified without rerunning it merely to add instrumentation.
Raw compiler output and environment values remain local.

## Continue the improvement loop

Every feature or verification PR should inspect the current timing summary and
GitHub job critical path before adding more work. Treat feedback time as an
engineering constraint throughout the project, not a one-time cleanup. The working
target is full Foundation feedback within ten minutes on a warm hosted run while
retaining all required coverage; this is an improvement target, not a product
performance qualification or a reason to relax acceptance.

1. Inspect `ci-performance.json` in the `foundation-handoff` artifact. Identify the
   longest stage and distinguish its execution time from job setup, queueing,
   cache transfer and the aggregate gate. Include runner minutes when evaluating
   extra jobs; wall-time improvements can increase compute cost.
2. State one measurable hypothesis. Prefer reducing repeated work, data movement
   and construction before adding concurrency. Preserve fixed seeds, sample
   counts, scaling repetitions, criteria, assertions and both configurations.
3. Measure equivalent workloads before/after. Record candidate/run, configuration,
   toolchain/generator, worker count, cache state and coverage. Compare cold with
   cold and warm with warm. Repeat a noisy microbenchmark or collect matched
   hosted samples when the result is borderline; use medians/ranges rather than
   selecting the fastest attempt. Do not rerun passing suites without a concrete
   measurement question.
4. Run unattended correctness and evidence-substitution checks. An improvement
   must preserve results and reduce the actual critical path, not just make one
   small test faster. Retain failed/neutral experiments and explain the decision
   to keep or revert them in sanitized PR evidence.
5. Update this evidence ledger and the plan as the bottleneck moves. Refresh
   `ci/ci-performance-baseline.json` only from an identified passing run after
   review. Never overwrite it automatically or raise a baseline to hide a
   regression. New test cases may be added; loss of a baseline case fails the
   comparison until an explicit scope decision changes the contract.

The aggregate gate runs `tools/summarize_ci_performance.py` on its current-run
passing verification and dependency reports. It verifies candidate identity, all
current cases, retention of baseline cases, dependency source identities and the
frozen radiation fixture/ensemble/scaling workload. It rejects incomplete,
substituted, nonfinite or incompatible evidence. Adding native correctness
regressions does not change the frozen statistical workload.

Timing increases over 20% and at least 60 seconds are marked `investigate` in the
scalar summary. Shared-runner timing alone does not fail physics acceptance;
coverage/workload/identity failures do fail the gate. Investigate material timing
warnings during PR work and document their disposition. Cache-state differences
are recorded so a cold/warm comparison cannot silently become a causal claim.

## Measured experiments

| Experiment | Evidence | Outcome |
|---|---|---|
| Original sequential workflow | [Main run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41252470867) | Full CI 19m 44s; Debug driver 18m 17s; Release driver 8m 04s. |
| Shared units, native deduplication, bounded acceptance | [PR baseline](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41343113138) | Cold full CI 15m 58s; Debug driver 12m 47s; Release driver 4m 19s; all checks passed. The original cold baseline remains in this ledger and Git history. This is not a controlled hardware comparison. |
| Canonical index sorting and construction-only BVH geometry | Local synthetic one-million-facet diagnostic pair | Debug construction 112.1s to 30.4s; all non-timing rows and storage accounting matched. All three independent CI scaling builds remain required. Hosted confirmation accompanies the PR. |
| Allocation-free BVH traversal stack | Local three-refinement diagnostic pairs | Trace time 1.83s to 1.13s at 99,856 facets and 1.97s to 1.35s at one million facets; all non-timing results matched. |
| Four-worker Ninja package build | Complete local pinned Embree build/install/consumer | Passed in 600s; no established gain over the hosted baseline. Incremental migration also exposed compiler-cache handling costs. Reverted the migration and retained package-phase timing instrumentation for future diagnosis. |
| Optimized BVH, timing-prioritized scheduling and continuous comparisons | [Passing warm run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41350452498), commit `ac3003d` | Full CI 12m 45s; Debug driver 9m 53s; Release driver 4m 14s; Debug radiation 5m 13s. All required checks passed, with 391 records per configuration. The prior run was cold, so total runtime differences include cache effects. |
| Three Debug acceptance workers | [Passing warm run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41355909563), commit `35cdeb5` | Full CI 11m 02s; Debug driver 407.015s versus the warm reference's 578.078s (29.6% shorter). Embree became the critical path. Aggregate job duration 2,690s. |
| Thermal residual allocation removal and four-compiler Embree | [Passing warm run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41356914583), commit `f44ab6b` | Full CI 8m 58s; Debug driver 351.812s; Release 254.500s. Embree build 321.860s versus 573.719s in the prior run; all package consumers passed. Aggregate job duration 2,331s, 13.3% less than the prior run. OCCT and the Debug tail now dominate. |
| Invariant ray cache, final checkpoint hashing and native compiler parallelism | [Passing warm run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41357834232), commit `7072a4d` | Full CI 11m 03s; Debug 413.781s; Release 203.625s; all 391 records per configuration passed. Embree's unchanged four-compiler build took 566.484s, while OCCT's unchanged two-compiler build took 228.062s. Aggregate job duration 2,420s. Retain this slower sample; resource telemetry and repetitions are needed before causal hosted-time claims. |
| Aggregate process-tree resource evidence | [Passing warm run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41359314196), commit `d94fd6f` | Full CI 10m 13s; Debug 373.407s; Release 163.484s; all 393 records per configuration passed. Embree build 503.953s / 1,974.453 CPU seconds / 2.207 GB peak job commit; OCCT build 317.015s / 728.422 CPU seconds / 1.516 GB peak job commit. All measured runners reported four logical CPUs. Aggregate job duration 2,390s. Initial accounting profile `windows-job-v1`; later comparisons isolate reusable MSBuild workers explicitly. |

The BVH change sorts indices rather than large optical facet records, detects
duplicate IDs in canonical order, and computes bounds/centroids once per facet.
Scratch geometry is released after construction. Canonical order, split/tie rules,
sample streams, strict floating point and Debug checking remain intact. Flat-scan
intersection/ignore/tie regressions and the complete existing statistical campaign
verify behavior. Traversal uses a bounded stack instead of allocating for each ray;
the median tree and two-million-facet limit keep depth below 20, with a defensive
capacity check. Never report these synthetic diagnostic timings as frozen-hardware
product performance qualification.

## Resumed experiments and next work

Optimization resumed after the passing documentation checkpoint `1156dff` in
[run 41352210980](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41352210980):
full CI 12m 13s, Debug 578.078s and Release 206.406s, both warm with two workers.
The versioned baseline now deliberately references that passing run with unchanged
workload and case retention. The original cold run remains recorded above.

The first resumed experiment sets Debug to three acceptance workers and leaves
Release at two. Debug passed in 407.015s versus 578.078s (29.6% shorter), retaining
all 391 records. [The complete run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41355909563)
passed in 11m 02s, with Embree now limiting the critical path. Stage durations
stayed comparable while long stages overlapped.
The full qualification tier remains serial. Before retaining it, compare complete
warm hosted runs, correctness, contention and runner cost against the identified
two-worker reference.

The next experiment removes unused derivative-matrix allocations from thermal
residual probes and transient line-search callbacks. A local sequential Debug
pair passed the same two-node, heater and checkpoint tests in 12.64/27.28/53.71s
versus 14.59/31.50/64.10s before (13-16% shorter). Exact residual/linearization
balance parity is checked for all three storage modes. Integration tolerances,
step/event algorithms, callback invocation order, energy checks and Debug runtime
checking remain unchanged. A separate complete heater-output pair matched every sample, event, all 26,688
step records, energy budgets and checkpoint bytes exactly, with identical solver
evaluation counters. The complete hosted run passed as recorded in the ledger.

Embree's warm build phase alone took 579.797s in the reference. Its largest
MSBuild project is capped at two compiler processes. Test a four-compiler budget
for Embree with the same full source/options/generator and installed consumer;
leave other packages at two. This avoids repeating the neutral Ninja migration.
The full hosted run passed and its substantial build-time/runner-time reduction
supports retaining four Embree compiler workers. Package peak-memory telemetry is
not yet collected; record it before increasing budgets further. Never infer a gain
from an incremental local rebuild.

The geometry/checkpoint/native-build candidates passed complete hosted verification
as recorded above. Local controlled pairs support their execution-time changes;
the slower aggregate sample is retained rather than discarded:

- Cache invariant triangle edge vectors and the exact scale-relative determinant
  cutoff used by intersection. Paired Debug traces at 65,536 samples shortened
  from 0.462/3.248/2.883s to 0.379/2.313/1.895s for plates/cube/spheres, with all
  non-timing hit rows identical. The cache adds 56 bytes per facet plus fixed
  container overhead, explicitly included in `storage_bytes`; the unchanged
  2,048-byte-per-facet limit and peak-working-set evidence still apply. Preserve
  near-parallel rejection and nearest/ignore/tie behavior.
- Keep each last-committed checkpoint snapshot but serialize/hash it once before
  synchronous return. Both successful and partial-failure results retain sealed,
  resumable checkpoints. The heater acceptance shortened from 27.31s to 23.58s
  after the allocation change. Resource-failure restart/tamper regressions cover
  checkpoints returned after accepted steps; existing energy/event failures remain.
- Compile native MSVC targets with two compiler processes per project alongside
  the existing two-project limit. A matched clean Debug core build shortened from
  15.15s to 9.10s. Strict floating point, assertions and Debug runtime checks remain.
  Judge the full clean hosted build, rather than incremental build time.

The next candidate replaces the eager per-facet ray cache with bounded per-row
scratch. A row preloads geometry when the mesh fits its 512 slots; larger meshes
cache only visited facets and evict by slot. Rows own their scratch, so concurrent
rows never mutate the mesh. Native cached/uncached comparisons force eviction and
retain every integer result. At one million facets the new cache replaces
56,000,032 extra retained bytes with 32,768 bytes of fixed scratch, which remains
included in `storage_bytes`. Both-order diagnostic pairs retained exact raw rows;
construction stayed about 28-30s and peak working set fell by about 56 MB. Dense
trace timings remain close to the eager cache. Judge final timings after hosted
confirmation; do not claim the small construction differences as a controlled win.

The first local OCCT budget pair passed both full builds/consumers but is
**inconclusive**: CPU/process totals differed unexpectedly and another local build
overlapped part of the experiment. Do not use that pair to justify a gain. Repeat
fresh builds with four-CPU affinity and an isolated MSBuild worker pool, in reversed
order, with no concurrent local compiler work.

1. **Measure the next worker budget against the current three-worker result.**
   Keep Release at two and full qualification serial. Compare four versus three
   Debug workers only with equivalent warm workloads and toolchains. Preserve all
   cases, samples, scaling repetitions and deadlines. Retain four only after a
   complete unattended run reduces the critical path without instability or a
   material compute/memory penalty; otherwise retain three.
2. **Measure OCCT compilation using resource evidence.** Its pinned package took
   426.203s in the latest passing run. Collect the two-compiler baseline's CPU and
   peak committed memory before testing four per project. Keep the same full
   source/features, two MSBuild projects, install and independent consumer. Check
   the aggregate critical path and runner cost; do not retain a neutral change.
3. **Profile the new Debug thermal/radiation balance.** Inspect per-case and
   ensemble timings after the geometry/checkpoint changes. Prefer removing
   repeated invariant work before adding complexity. Keep exact-output tests,
   energy/event/restart criteria, memory limits and strict Debug behavior.
4. **Refresh the warm baseline deliberately after the final passing run.** Retain
   prior cold/warm evidence and identify the run/candidate/workload and worker
   budgets. Repeat borderline measurements; never choose the fastest seed or
   automatically raise a baseline to conceal a regression.

Verification command stages, package phases and the aggregate `ci-performance.json`
now add CPU seconds, peak per-process and aggregate job
committed-memory bytes, and total process count. These are kernel-maintained job
counters, including already exited descendants; they are not sampled process
lists. See Microsoft's [job accounting](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)
and [memory counters](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).
Committed memory differs from the radiation subject's peak working set; do not
present either as reference-hardware qualification or conflate them. CPU seconds
divided by phase wall time indicates average CPU parallelism, not elapsed time.

Each phase runs in a fresh Windows job, assigned before resuming the tool so its
children cannot escape accounting. Profile `windows-job-v2` also forces
`MSBUILDDISABLENODEREUSE=1`: an existing MSBuild worker can otherwise execute work
outside the new process tree or retain another stage's temporary directory.
See the [MSBuild guidance](https://github.com/dotnet/msbuild/blob/main/documentation/wiki/MSBuild-Tips-%26-Tricks.md)
and [upstream reuse issue](https://github.com/dotnet/msbuild/issues/13594).
The setting applies to explicit and inherited environments and is tested
unattended. Extra process startup is included in the measured wall time. V1 and V2
resource profiles remain distinct; do not mix their CPU totals as a causal pair.
External pre-existing system services are outside owned-tree accounting. No CPU/memory/process-count limit is added.
Closing the job terminates its remaining descendants, including timeout cleanup;
command outcomes and every installed consumer still determine acceptance.
Regression tests prove exited-child accounting, nested worker containment, owned-tree timeout cleanup, and
numeric-only allowlists. The aggregate requires all six valid phase records,
reviewed generator and bounded project/compiler counts. Missing metadata, private
identity fields, nonfinite or impossible values fail the summary. Earlier baseline
scalar totals remain compatible.
Only fixed stage/phase names, numeric totals and logical CPU counts enter these
new public fields. The small direct engine-identity probe keeps its existing
bounded evidence. Process
identities, executable/command paths, environment and raw logs remain local.

Radiation reports now retain native-case and ensemble build/trace scalar timings
to locate the next dominant cost without repeating the fixed campaign just to
add instrumentation. Required seeds, repetitions and assertions remain intact.

Raw diagnostics and usage-account metadata remain local. Only existing sanitized
scalar reports and reviewed source/documentation are published under TST-021.
