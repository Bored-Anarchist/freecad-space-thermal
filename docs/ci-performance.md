# CI execution and public download caches

Both Windows configurations retain all existing acceptance cases, fixed seeds,
sample counts, scaling sizes and numerical tolerances. This change does not create
a smaller qualification tier or move required acceptance to a scheduled workflow.

`tools/verify.py --preset windows-release --jobs 2` runs compilation and installation
before scheduling at most two independent acceptance processes. Historical stage
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

MSVC package probes retain two compiler processes per project and two MSBuild
projects. The measured Ninja experiment did not establish a gain and was not
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
Package reports include generator, worker count and configure/build/install/consumer
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
| Shared units, native deduplication, bounded acceptance | [PR baseline](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41343113138) | Cold full CI 15m 58s; Debug driver 12m 47s; Release driver 4m 19s; all checks passed. This is the versioned baseline, not a controlled hardware comparison. |
| Canonical index sorting and construction-only BVH geometry | Local synthetic one-million-facet diagnostic pair | Debug construction 112.1s to 30.4s; all non-timing rows and storage accounting matched. All three independent CI scaling builds remain required. Hosted confirmation accompanies the PR. |
| Allocation-free BVH traversal stack | Local three-refinement diagnostic pairs | Trace time 1.83s to 1.13s at 99,856 facets and 1.97s to 1.35s at one million facets; all non-timing results matched. |
| Four-worker Ninja package build | Complete local pinned Embree build/install/consumer | Passed in 600s; no established gain over the hosted baseline. Incremental migration also exposed compiler-cache handling costs. Reverted the migration and retained package-phase timing instrumentation for future diagnosis. |
| Optimized BVH, timing-prioritized scheduling and continuous comparisons | [Passing warm run](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41350452498), commit `ac3003d` | Full CI 12m 45s; Debug driver 9m 53s; Release driver 4m 14s; Debug radiation 5m 13s. All required checks passed, with 391 records per configuration. The prior run was cold, so total runtime differences include cache effects. |

The BVH change sorts indices rather than large optical facet records, detects
duplicate IDs in canonical order, and computes bounds/centroids once per facet.
Scratch geometry is released after construction. Canonical order, split/tie rules,
sample streams, strict floating point and Debug checking remain intact. Flat-scan
intersection/ignore/tie regressions and the complete existing statistical campaign
verify behavior. Traversal uses a bounded stack instead of allocating for each ray;
the median tree and two-million-facet limit keep depth below 20, with a defensive
capacity check. Never report these synthetic diagnostic timings as frozen-hardware
product performance qualification.

## Next work, deliberately not started

The user ended this optimization session after the passing `ac3003d` run. Both
hosted configurations retain **two acceptance workers**; full qualification stays
serial. A proposed three-worker Debug experiment and a warm-baseline refresh were
reverted before commit or execution. Do not treat them as tested improvements.

1. **Test three Debug workers on the same hosted runner.** Use the passing warm
   run above as the reference and compare against two workers with equivalent
   cache, workload and toolchain conditions. Preserve all required cases and
   frozen samples/scaling repetitions. Check memory, CPU contention, deadlines,
   runner minutes and the end-to-end critical path, not just one stage. Retain
   three workers only if the complete unattended run shows a material gain
   without instability; otherwise retain two. Release remains at two and frozen
   qualification remains serial during the experiment.
2. **Profile the remaining Debug thermal cost.** Use per-case durations in
   `thermal.json`, especially checkpoint and heater acceptance, to locate actual
   solver/serialization overhead. Optimize implementation work while retaining
   the same integration, restart, energy and event acceptance criteria.
3. **Investigate dependency compilation once it limits the critical path.**
   Embree still took about nine minutes in the passing run. Use the new package
   phase timings and the recorded neutral Ninja result. Do not repeat a generator
   migration without a specific hypothesis, weaken package coverage, or upload
   generated binaries/build trees under the current download-cache policy.

The versioned baseline still references the earlier passing cold run. A future
experiment should deliberately record a matching warm baseline from the identified
passing run, retain the previous evidence, and explain the refresh. This session
leaves no new worker-budget experiment active.
