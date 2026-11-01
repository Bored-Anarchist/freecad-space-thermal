# CI execution and public download caches

Both Windows configurations retain all existing acceptance cases, fixed seeds,
sample counts, scaling sizes and numerical tolerances. This change does not create
a smaller qualification tier or move required acceptance to a scheduled workflow.

`tools/verify.py --preset windows-release --jobs 2` runs compilation and installation
before scheduling at most two independent acceptance processes. Each stage receives
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

MSVC package probes use two compiler processes per project and two MSBuild
projects. Numerical prototype build directories are stable per checkout and
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

`verification.json` records wall time, worker count and local-versus-receipt unit
execution. Compare cold and warm GitHub runs separately; no hosted speedup is
claimed until those runs complete.
