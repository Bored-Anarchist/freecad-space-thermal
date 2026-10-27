# Development and automated verification

WP-02 supplies a C++20 worker skeleton and standalone Python application/CLI/MCP package boundaries. The worker reports build information and rejects solve requests as unimplemented. No thermal physics or legacy-file compatibility is claimed.

Create an isolated Python 3.11 environment under `.local/venv`, activate it, and run:

```text
python -m pip install --require-hashes --only-binary=:all: -r ci/requirements.lock
python tools/verify.py --tier fast --preset windows-debug
```

Use `windows-release` for the release configuration. Active development and qualification target Windows 11 x64 with Visual Studio 2022 C++ build tools and an x64 Windows SDK. macOS/Linux builds and host qualification are deferred to WP-22 after Windows WP-21/Q2; the driver rejects those platforms during this phase. The driver uses locked CMake, builds, runs CTest, installs the worker, tests it with Python and FreeCAD absent from its executable search path, and verifies that unimplemented solves fail. It installs the Python package offline with no production dependencies. Windows release disables unsafe floating-point transformations. Historical Linux presets are retained under `ci/deferred/` and are not active build targets. Set one thread for the reference profile. Exact compiler/runner builds remain Q0 qualification inputs; recorded build information reports actual versions.

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

Full qualification executes the exact Windows FreeCAD host smoke and still rejects missing vendor-runner, reference-hardware and numerical-backend prerequisites at their affected gates. WP-01 is complete on its acquired baseline; those later obligations are assigned in `inventory/gaps.json`. `tools/probe_dependencies.py` is discovery only. `tools/build_dependencies.py` verifies pinned source/license hashes and builds, installs and exercises Windows SUNDIALS, HDF5, Embree and OCCT consumers. These are deployment probes; numerical correctness and production backend selection remain WP-04. PETSc's native MSVC profile is unsupported and is absent from active CI; Linux PETSc work is deferred with WP-22. No candidate is adopted as a production dependency.

The active host profile pins the official Windows FreeCAD **1.1.4** bundle and embedded **cp311** Python. The smoke creates geometry, saves/reopens, edits/undoes and imports application modules using isolated preferences and a watchdog. It does not qualify the future workbench GUI. Keep standalone tooling separate from embedded FreeCAD Python. This is an add-on/workbench and separate owned engine; no FreeCAD rebuild or fork is required.

CI runs Windows debug/release, one Windows host smoke and four supported Windows packaging probes. All public workflow jobs, including planning/privacy/aggregate jobs, run on Windows runners. The required Foundation gate rejects failed or skipped active jobs. Only privacy-cleared bounded JSON reports are uploaded; bundles, third-party source, generated documents and raw logs remain local. Earlier Linux reports in `plans/evidence/foundation-profiles.json` are historical evidence, not current support or acceptance requirements. Deferred presets and the Linux host pin live under `ci/deferred/` and must be requalified during WP-22. `plans/delivery-scope.json` and regression checks enforce the active/deferred boundary.

The public GitHub repository is authoritative. Work-package issues and milestones track the version-controlled plan; `plans/github-backlog.json` maps their identities. Public CI runs only on GitHub-hosted Windows runners without vendor secrets. `tools/setup_validation.py` provisions a separate private validation repository with no privileged runners, no restricted inputs and a manual-only workflow that fails closed until exact licensed profiles and reviewed candidate promotion exist. `tools/check_github.py` reads the live private policy, exact deny-only workflow, read-only permissions and runner list; regression cases reject untrusted triggers, guard bypass, activation and write permissions. Unreviewed public pull requests cannot trigger it. Privileged vendor/performance runners still need profile-specific provisioning and isolation tests. Source-model contents and raw evidence stay in authorized runner-local stores. Workflow dependencies use immutable official Actions commits; jobs default to read permissions. Release publication is deferred until WP-19's complete evidence gate exists.

The [FCST implementation project](https://github.com/users/Bored-Anarchist/projects/1) contains all 22 work packages, with Planned, Ready, In progress, Blocked and Complete states. Fields retain completion gates, prerequisite packages, requirement IDs and owner roles. `plans/github-project.json` records the exact project/item identities and states. With authorized GitHub Projects scope, `python tools/setup_projects.py` synchronizes this initial backlog without creating duplicate projects/items or accepting unrelated existing items. WP-02 foundation acceptance is Complete; WP-01 is Complete under the user-approved acquired-inventory criteria; WP-03 native contracts are Ready; WP-22 macOS/Linux work is Planned at POST-Q2 after WP-21. The live settings checker verifies remote project identity/visibility, repository linkage, all issue mappings and matching states; a local URL alone cannot pass.

## Publication privacy (TST-021)

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
