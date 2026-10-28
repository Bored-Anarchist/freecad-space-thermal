# Development and automated verification

WP-02 supplies a C++20 worker skeleton and standalone Python application/CLI/MCP package boundaries. The worker reports build information and rejects solve requests as unimplemented. No thermal physics or legacy-file compatibility is claimed.

Create an isolated Python 3.11 environment under `.local/venv`, activate it, and run:

```text
python -m pip install --require-hashes --only-binary=:all: -r ci/requirements.lock
python tools/verify.py --tier fast --preset windows-debug
```

Use `windows-release` for the release configuration. Active development and qualification target Windows 11 x64 with Visual Studio 2022 C++ build tools and an x64 Windows SDK. macOS/Linux builds and host qualification are optional stretch goals outside the work packages; the driver rejects those platforms during this phase. The driver uses locked CMake, builds, runs CTest, installs the worker, tests it with Python and FreeCAD absent from its executable search path, and verifies that unimplemented solves fail. It installs the Python package offline with no production dependencies. Windows release disables unsafe floating-point transformations. Historical Linux presets are retained under `ci/stretch/` and are not active build targets. Set one thread for the reference profile. Exact compiler/runner builds remain Q0 qualification inputs; recorded build information reports actual versions.

If an older pip cannot use the operating system certificate store, `python tools/fetch_tooling.py` downloads wheels using verified TLS and verifies every wheel against the lock; install with `--no-index --find-links .local/wheelhouse` and the same `--require-hashes` options. No TLS-verification bypass is needed.

The fast driver compares collected case IDs with `ci/coverage.json`. Missing, duplicated, skipped, cancelled, blocked or failed required cases fail the gate. Tests prove those rejection paths. Local raw logs remain under `.local/`; CI publishes only the privacy-cleared verification/build-info JSON files. Debug symbols, source maps, raw compiler output and native binaries are not uploaded by these foundation workflows.

WP-01 adds the offline inventory checker and synthetic regression cases to that same fast driver. See [the corpus inventory](../inventory/README.md) for reproducible acquisition, local original-byte checks and the separate blocked compatibility-prerequisite command (not WP-01 completion). CI validates provenance/coverage metadata without downloading third-party models or executing imported logic. An acquired file, syntax-only corpus or retained upstream result cannot satisfy native physics or vendor qualification.

```text
python tools/verify.py --tier full --preset windows-release
python tools/check_github.py
python tools/probe_dependencies.py
python tools/host_smoke.py
python tools/build_dependencies.py --jobs 2
```

Full qualification executes the exact Windows FreeCAD host smoke and still rejects missing vendor-runner, reference-hardware and numerical-backend prerequisites at their affected gates. WP-01 is complete on its acquired baseline; those later obligations are assigned in `inventory/gaps.json`. `tools/probe_dependencies.py` is discovery only. `tools/build_dependencies.py` verifies pinned source/license hashes and builds, installs and exercises Windows SUNDIALS, HDF5, Embree and OCCT consumers. These are deployment probes; numerical correctness and production backend selection remain WP-04. PETSc's native MSVC profile is unsupported and is absent from active CI; Linux PETSc work is an uncommitted stretch goal. No candidate is adopted as a production dependency.

The active host profile pins the official Windows FreeCAD **1.1.4** bundle and embedded **cp311** Python. The smoke creates geometry, saves/reopens, edits/undoes and imports application modules using isolated preferences and a watchdog. It does not qualify the future workbench GUI. Keep standalone tooling separate from embedded FreeCAD Python. This is an add-on/workbench and separate owned engine; no FreeCAD rebuild or fork is required.

Before overlapping WP-13/WP-16 implementation, complete the [FEM reuse assessment](decisions/0003-freecad-fem-reuse.md): prefer compatible host APIs for meshes, selections/assignments and results, and record source/build/API/license evidence for reuse, adaptation or replacement. The six FEM-REUSE acceptance IDs are planned tests to implement with those features, not current smoke coverage. Add required cases to the shared local/CI coverage gate when implemented. Preserve standalone engine operation and label optional CalculiX/Elmer comparisons separately. TST-021 scans exact outgoing assessment/fixture/summary bytes; generated host files, raw decks and logs remain local until independently cleared.

CI runs Windows debug/release, one Windows host smoke and four supported Windows packaging probes. All public workflow jobs, including planning/privacy/aggregate jobs, run on Windows runners. The required Foundation gate rejects failed or skipped active jobs. Only privacy-cleared bounded JSON reports are uploaded; bundles, third-party source, generated documents and raw logs remain local. Earlier Linux reports in `plans/evidence/foundation-profiles.json` are historical evidence, not current support or acceptance requirements. Deferred presets and the Linux host pin live under `ci/stretch/` and require a separate scope decision and requalification before use. `plans/delivery-scope.json` and regression checks enforce the active/deferred boundary.

The public GitHub repository is authoritative. Work-package issues and milestones track the version-controlled plan; `plans/github-backlog.json` maps their identities. Public CI runs only on GitHub-hosted Windows runners without vendor secrets. `tools/setup_validation.py` provisions a separate private validation repository with no privileged runners, no restricted inputs and a manual-only workflow that fails closed until exact licensed profiles and reviewed candidate promotion exist. `tools/check_github.py` reads the live private policy, exact deny-only workflow, read-only permissions and runner list; regression cases reject untrusted triggers, guard bypass, activation and write permissions. Unreviewed public pull requests cannot trigger it. Privileged vendor/performance runners still need profile-specific provisioning and isolation tests. Source-model contents and raw evidence stay in authorized runner-local stores. Workflow dependencies use immutable official Actions commits; jobs default to read permissions. Release publication is deferred until WP-19's complete evidence gate exists.

The [FCST implementation project](https://github.com/users/Bored-Anarchist/projects/1) contains all 21 work packages, with Planned, Ready, In progress, Blocked and Complete states. Fields retain completion gates, prerequisite packages, requirement IDs and owner roles. `plans/github-project.json` records the exact project/item identities and states. With authorized GitHub Projects scope, `python tools/setup_projects.py` synchronizes this initial backlog without creating duplicate projects/items or accepting unrelated existing items. WP-02 foundation acceptance is Complete; WP-01 is Complete under the user-approved acquired-inventory criteria; WP-03 native contracts are Complete with [executable evidence](../plans/evidence/WP-03.json); optional macOS/Linux work has no work package, milestone or committed delivery date. The live settings checker verifies remote project identity/visibility, repository linkage, all issue mappings and matching states; a local URL alone cannot pass.

## Publication privacy (TST-021)

WP-05 adds the [persistence service and recovery tools](persistence.md). The standard-library cases exercise package validation, scoped transactions/previews/retries, undo/invalidation, migration and synthetic host synchronization. Both Windows drivers also run `python tools/check_persistence.py`, including real process termination at save boundaries, fresh-process portable reconstruction and strict HDF5 result/mesh checks. The locked tooling includes the optional standalone `arrays` extra. CI privacy-clears the exact `persistence.json` summary alongside the existing reports before upload; generated packages, HDF5/SQLite/host files and raw crash logs remain local. Frozen operation dispatch now creates conductors and validates/hashes models; worker/job execution remains WP-06. See `docs/persistence.md` for storage limits, audit retention and the explicitly supported migration/downgrade envelope.

WP-04 adds the [numerical checkpoint and Q0 decision](decisions/0001-q0-numerical.md). Both standard Windows drivers build/install its separate C++ executable, execute independent analytic/nonlinear oracles, compare CVODE BDF/dense, BDF/band and Adams/band, exercise events/cancellation/restart and run bounded scale probes. `python tools/check_numerical.py --require-reference` also requires the frozen Release reference configuration. Every attempt has its own criteria, fixture, observations, assessment, provenance and hash seal under `.local/numerical/`; use `--replay <attempt-directory>` to verify stored evidence. Missing required cases or prerequisites fail the gate and identify missing case IDs. Full product/vendor gates remain separate.

The numerical report uploaded by CI contains bounded synthetic metrics, source/artifact hashes and public CPU/toolchain configuration. TST-021 scans that exact file along with verification/build/contract reports before upload. Raw logs, observations, binaries and DLLs stay local. The standalone production worker continues to report `solver_available=false`; this experiment does not implement live operations or durable jobs.

WP-03 adds the [frozen contract bundle](../spec/contracts/README.md), generated schemas/shared enums and independent Python/C++ readers. Regenerate with `python tools/generate_contracts.py`; CI rejects drift with `--check`. The fast driver executes Python/standard-schema regressions and runs all versioned conformance vectors against the installed native worker, including binary control framing. Use `python tools/check_contracts.py --worker out/windows-debug/Debug/fcst-worker.exe` for the focused check. Frozen expected hashes and exact fixture/frame case IDs prevent missing coverage from passing. Raw snapshots and arrays are never included in public conformance reports.

The privacy job runs `python -S tools/check_security.py` using only the standard library. Its contract regressions check the closed schema vocabulary without importing third-party validators. The independent Draft 2020-12 reader runs through `tools/generate_contracts.py --check --validate` in the locked debug/release tooling environment. Both paths are required; a privacy job must not depend on optional site packages.

The native worker accepts `--contract model`, `--contract manifest`, `--contract operation`, `--contract response`, `--contract result`, `--contract worker` or `--contract worker-frame`, with bounded input on stdin and JSON validation/hash output on stdout. This is a stateless conformance interface. It does not execute operations or start a job. Python uses `fcst_contracts.read`, `snapshot`, `canonical` and `inspect`; production validation has no third-party Python dependency. Windows SHA-256 uses the operating system BCrypt provider. There are no new bundled third-party native dependencies. HDF5 persistence and real IPC transport remain their owning work packages.

All new outgoing fixtures are synthetic JSON; generated schemas, the embedded C++ schema table and shared types are scanned as actual text bytes. The bounded `contracts.json` report contains case IDs and fixture hashes only and is included in the existing pre-upload privacy gate. Native binaries, HDF5 arrays, raw reader/compiler logs and imported model originals remain local. TST-021's existing adversarial tests, staged/outgoing-history scans and approved identity checks still apply to this complete publication copy.

The user approved the public maintainer identity recorded in `ci/publication-policy.json`. No private author email is used. The staged Git index is the sanitized publication copy; restricted originals and raw engineering evidence remain outside it. Install version-controlled hooks with:

```text
git config core.hooksPath .githooks
python tools/publication_preflight.py --staged --revision HEAD --report .local/clearance.json
python tools/publication_preflight.py --staged --revision HEAD --verify-clearance .local/clearance.json
```

Omit `--revision HEAD` only before the first commit. Pre-commit checks staged bytes; pre-push checks every reachable commit/tree and both author/committer identities. Clearance binds policy version/hash, exact bytes, locations and metadata. Recheck after any change. Native Git hooks cover ordinary pushes; direct API writes must call the same preflight explicitly. `tools/setup_github.py` scans its exact outgoing JSON payloads before posting.

For prose or generated assets, select the actual outgoing files:

```text
python tools/publication_preflight.py --file release-notes.md --file package.zip --report .local/asset-clearance.json
```

The scanner detects credential/contact/path/network patterns, hashed project-private identifiers, restricted paths, unapproved commit identities and nested archive findings. It bounds archive size/count/depth and rejects traversal, links and encrypted inputs. Unknown binaries, images, document containers and unsupported encodings fail closed until a suitable sanitization/inspection path exists; they are not cleared by their filename. Safe reports contain categories, opaque location IDs, byte counts and hashes, never sensitive matched values. Keep reports local until they themselves pass preflight. Narrow exceptions must bind exact content hashes and categories and retain required public license attribution.

Pattern scanning cannot infer all confidential engineering meaning. Use synthetic public fixtures and exclude restricted originals. Add hashes of private identifiers to the policy without publishing their raw values, and review the outgoing content classification. Do not weaken detection to force publication. If previously published content is exposed, address credentials and coordinate affected history/artifact cleanup explicitly.
