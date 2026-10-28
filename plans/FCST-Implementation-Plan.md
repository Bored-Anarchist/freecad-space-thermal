# FreeCAD Space Thermal: implementation and build plan

Plan revision 1.3, 27 October 2026. Based on specification FCST-SYS-SPEC-001 revision 0.5 and the user's additional requirements for unattended testing, GitHub project delivery, removal of private/personal information before anything is put online, and explicit independence of native model creation, files and solving.

This is an implementation plan, not evidence of implemented physics or file compatibility. The workspace contains the specification, 121 registered requirements, 12 proposed compatibility profiles, three draft JSON schemas and two schema examples. WP-02 now adds a native worker/application skeleton, local/CI verification and publication-privacy preflight; it implements no thermal solving or file compatibility. [WP-02 evidence](evidence/WP-02.json) records completed foundation acceptance and remaining Q0/product obligations. The specification remains the design baseline; the automated-test requirements below add delivery obligations without relaxing its acceptance criteria.

The [delivery scope](delivery-scope.json) is Windows-only for Q0/P0/Q1/Q2. WP-01 is Complete at the acquired baseline; licensed/source/schema qualification remains with later packages. macOS and Linux configurations are optional stretch goals outside all work packages, committed milestones and release gates; see [stretch goals](stretch-goals.md). FCST remains a FreeCAD add-on/workbench with a standalone engine, not a modified FreeCAD build.

Read this plan alongside the [specification](../spec/FreeCAD-Space-Thermal-Specification.md), [requirements](../spec/requirements.csv), [compatibility profiles](../spec/compatibility-profiles.csv), and [source register](../spec/sources.md). Execution records are provided by the [work-package register](work-packages.csv), [automated-test requirements](automated-test-requirements.csv), [test-suite register](test-suites.csv), [compatibility test plan](compatibility-test-plan.csv), and [requirement traceability](requirement-traceability.csv).

## Delivery approach

Build the product around a host-independent C++20 thermal engine and a versioned Python application service. FreeCAD, the CLI, and MCP use the same operations. Vendor adapters extract and re-export source models and produce reference runs; production thermal solving belongs to FCST. Preserve the original files, stable identities, units, and model semantics from the first import implementation.

The native workflow is independently required: create a model from an empty project, assign nodes/properties/conductors/loads/cases, save an FCST `.fcst` file, reopen and edit it, run owned steady/transient solves, and inspect results without a vendor file, Thermal Desktop/SINDA/FLUINT, ESATAN, vendor licenses or vendor services. WP-01 scopes backward-compatibility coverage; native WP-02/WP-03/WP-04 slices start with public synthetic fixtures and analytic oracles while vendor access is acquired. Complete Q0 and compatibility claims still require their specified evidence; missing vendor access must not stop native core development.

Executable acceptance for ARC-001/ARC-003/ARC-009 and TST-004/TST-009/TST-014: in an isolated offline installation with vendor software and adapters absent, automatically create a geometry-free two-node model, save `.fcst`, close/reopen it, verify its canonical model hash, edit a load, solve steady and transient cases with `fcst_native`, and compare temperatures, heat flows and energy balance with independent analytic oracles. Verify result persistence and reopen. SUITE-INSTALL, SUITE-PERSIST and SUITE-PHYSICS own this scenario; a vendor-backed run cannot satisfy it. This is planned acceptance, not a completed test.

The first demonstration is a saved two-node/two-surface model with conduction, radiation, a transient solve, FreeCAD visualization, API/MCP access, and paired synthetic source fixtures. It is P0, an experimental vertical slice. Q1 is substantially larger: every Q1 requirement, both source ecosystems, required STEP-TAS content, changed-model round trips, bidirectional exchange, correlation, automation, installation, and qualification. Q2 closes the remaining required legacy inventory and advanced native behavior.

Testing is part of the product build. Engineers implement fixtures, test drivers, oracles, and runners with each feature. The user is not the test operator. Human review may approve intended physics, licensed fixture access, or proposed tolerances; creating models, launching tools, comparing outputs, collecting evidence, and deciding objective pass/fail run automatically.

GitHub is the required development and delivery platform: the authoritative source repository, Issues and Projects backlog, pull requests, GitHub Actions CI, and Releases. GitHub configuration and workflow implementation belong to WP-02; evidence-backed release publishing belongs to WP-19/WP-21. GitHub is a development dependency; installed native modeling and solving retain the specification's offline and account-free behavior.

Online publication must exclude private/personal information. This covers code and documentation as well as commit metadata, issues/PRs/comments/posts, screenshots, logs, evidence and release assets. The standing [repository instructions](../AGENTS.md) preserve this user requirement for later implementation and publication work. TST-021 makes its automated checks a required WP-02 deliverable before the first online publication.

## 1. Boundaries and decisions to establish first

| Area | Implementation direction | Decision or evidence required |
|---|---|---|
| Project development | GitHub repository, Issues/Projects, pull requests, GitHub Actions and Releases | Repository owner/URL, visibility, permissions, supported protection features and runner/evidence access established at Q0 |
| Numerical implementation | C++20, CMake, independent engine executable/library | Q0 compiler, ABI, build flags, numerical-backend prototype and platform results |
| Python integration | Application operations, FreeCAD host adapter, CLI, MCP, orchestration/reporting | Separate host and standalone Python dependency environments; no opportunistic host-Python replacement |
| Numerical libraries | Evaluate SUNDIALS and sparse solvers behind FCST interfaces; PETSc only if justified | Algebraic initialization, stiff integration, events, sparse scaling, licenses and clean Windows builds |
| Radiation | FCST estimators/optical laws with CPU intersection backend; evaluate Embree | Error/convergence evidence, deterministic seed policy and deployable dependency build |
| Geometry | Obtain mesh/geometry through a FreeCAD adapter; keep engine network-only operation possible | Supported primitives/elements, pinned FreeCAD/OCCT combination and attachment rules |
| Storage | Documented ZIP/directory `.fcst`, JSON metadata and versioned HDF5 arrays | Full model/results schemas, canonical hashing, atomic-save/recovery protocol |
| Vendor access | Separate version-matched adapters; Windows OpenTD sidecar where required | Actual licenses, runtimes, APIs, fixture rights and unattended automation paths |
| Platform qualification | Windows 11 x64 and official pinned FreeCAD 1.1.4; macOS/Linux are uncommitted stretch goals outside work packages | Qualify actual combinations; do not infer support from version names |
| MCP | Local stdio over the shared application API | Verify and pin a released protocol/SDK and named clients at Q0; separately test legacy profiles |
| Optional work | In-process pybind11, GPU acceleration, Rust comparisons, network MCP, Fluent comparisons | Add only when justified; none is necessary for the initial worker architecture |

These are implementation directions from the baseline, not a claim that the candidate dependency combination has already been built. Exact versions and vendor API calls must be established from the acquired documentation and measured prototypes. Do not choose an integration library solely because it is listed in the specification.

## 2. Proposed repository and build layout

Start in one authoritative GitHub source repository so contract changes and corresponding C++/Python/adaptor tests can land together. Preserve the current specification files. Use a separate private validation repository for privileged vendor-runner workflows and safe references to authorized local fixture stores when the source repository is public; it is test infrastructure, not a second product implementation. Private models and raw evidence remain in authorized runner-local storage unless their upload to a specific destination is explicitly permitted.

```text
spec/                           Existing design baseline
plans/                          This plan, delivery requirements and traceability
.github/
  workflows/                    GitHub Actions build, test and release workflows
  ISSUE_TEMPLATE/               Work-package and defect forms with requirement IDs
  PULL_REQUEST_TEMPLATE.md       Problem, linked issues, requirements and test evidence
  CODEOWNERS                    Actual maintainers for components and workflow changes
contracts/
  model/ operations/ worker/ results/ adapters/ migrations/
engine/
  include/fcst/                 Public host-independent interfaces
  src/model/ units/ expressions/ assembly/ numerics/
  src/radiation/ environment/ controls/ fluid/ results/
  worker/                       Standalone worker and offline engine commands
python/
  fcst_app/                      Operations, persistence, revisions, jobs, policy
  fcst_cli/                      Thin batch interface
  fcst_mcp/                      Thin stdio gateway
freecad/FCST/                    Init files, commands, objects, editors, view providers
adapters/
  common/ sinda/ esatan/ step_tas/ legacy/
sidecars/opentd/                 Separately built, version-profiled vendor bridge
tests/
  fixtures/public/               Synthetic files and generated reference cases
  fixtures/restricted-manifests/ Hashes and metadata; no unlicensed model contents
  contracts/ physics/ exchange/ integration/ gui/ security/ packaging/
  oracles/ harness/              Independent calculations, metrics and test drivers
benchmarks/                      Fixed workloads and statistical/performance policies
tools/                          Build, fixture, qualification and report commands
ci/                             Shared CI drivers, runner images and environment definitions
docs/                           Numerical methods, API, analyst and installation guides
CMakeLists.txt
CMakePresets.json
pyproject.toml
```

Proposed CMake targets are `fcst_model`, `fcst_physics`, `fcst_numerics`, `fcst_radiation`, `fcst_environment`, `fcst_results`, and `fcst-worker`. This separation must not create circular library dependencies. Numerical backends and ray-intersection libraries implement narrow interfaces; they do not own thermal identities or physics meaning. Keep required third-party licenses/provenance with their source manifests. Adopt the proposed component licenses only for newly authored code after checking actual dependency compatibility.

The Python application service owns the committed project/revision and operation lifecycle. The shared C++ model library is authoritative for engineering quantity types, physics invariants, typed snapshots, and engine-side validation. Generate wire/storage type definitions where practical from versioned contracts, and use common conformance fixtures for the Python and C++ implementations. The worker revalidates snapshots; the Python layer does not implement a second thermal solver.

Inside FreeCAD, application dispatch runs on the host's owning thread for document mutations. Standalone dispatch can run without FreeCAD. Both dispatch paths use the same operation handlers and validation contract. No worker or vendor bridge receives a live FreeCAD object or mutates a document.

### 2.1 GitHub repository and delivery setup

1. **Establish the repository.** Identify the GitHub owner and intended existing/new repository, visibility and collaborator roles at Q0. Record the canonical URL in project metadata, build manifests and contributor documentation. Retain required restricted fixtures outside a public source repository and publish only material with recorded rights. The repository, Issues/Projects backlog, protections and remote configuration are implemented and checked under WP-02.
2. **Create the executable backlog.** Represent each work package as a GitHub Issue with linked implementation/test tasks, requirement IDs, prerequisites, owner and Q0/P0/Q1/Q2 milestone. Track them in GitHub Projects with explicit planned, ready, in-progress, blocked and complete states. Link defects to affected profiles/builds, automated reproductions and release disposition. The CSV registers remain version-controlled baselines; issue/project links must identify the same work rather than introduce a competing requirement list.
3. **Use pull requests for changes.** Each PR links its issue/work package, affected requirement/profile IDs, intended behavior and automated verification. Add real maintainer/team handles to CODEOWNERS after repository ownership is known. Protect the default and release branches against unchecked changes and destructive history updates; configure required checks and appropriate review ownership. Verify the selected repository visibility and account plan support the required protections at Q0. [GitHub ruleset documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
4. **Make automated checks decisive.** GitHub Actions runs the same local test drivers and publishes uniquely named checks. A required aggregate check compares collected cases with the expected coverage manifest and fails on missing, failed, blocked, cancelled or unexpectedly skipped required work. Configure checks after their first run establishes their identities. Changes to tests, criteria and workflows are reviewed and tested like numerical changes; the PR author cannot replace failed numerical evidence with a green documentation-only check.
5. **Separate public and privileged runners.** Public PR checks use GitHub-hosted Windows runners and public synthetic fixtures without vendor credentials. Exact-version vendor, restricted-data and dedicated-performance workflows run from a controlled private validation repository with explicitly scoped runner access and a reviewed candidate SHA/build manifest. Keep private fixture data in authorized runner-local storage; online transfer needs explicit destination-specific permission. Never execute unreviewed PR code in a privileged context. Recreate or reset execution state and verify candidate/artifact hashes before each run; return only approved sanitized verdict summaries and safe evidence references to the source repository. This design follows GitHub's guidance on self-hosted runner access. [Runner access documentation](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access)
6. **Version and scope workflow dependencies.** Pin external actions to reviewed full commit SHAs, lock build/test dependencies and grant the minimum job permissions. PR test jobs need read access; release publication receives write permissions only in its release job. Do not execute candidate code through privileged `pull_request_target` workflows. Record workflow revisions, Actions run/attempt/job IDs, commit SHA and runner image with evidence. [GitHub Actions secure-use reference](https://docs.github.com/en/actions/reference/security/secure-use)
7. **Publish qualified releases.** Run the gate evaluator for the exact candidate, then produce GitHub Releases tied to that tested commit/tag with binaries, source/build/dependency/license manifests, checksums, profile matrix and approved qualification summaries. Preserve immutable evidence in durable, access-appropriate storage; expiring workflow artifacts alone cannot satisfy the retention contract. Restricted model contents and license material stay in controlled storage with hash references in public summaries.
8. **Verify repository settings automatically.** Add a settings checker for remote identity, required branch checks, workflow permissions, supported protection settings, runner restrictions and release-to-commit evidence links. Unavailable permissions, protection features or licensed runners are reported as setup blockers, not silently relaxed. Review of repository access or a release decision does not make the user responsible for executing tests.

The planned GitHub workflow deliverables are:

| Workflow | Scope and trigger | Runner/evidence |
|---|---|---|
| `planning-checks.yml` | Pull requests and pushes validate this plan, registers and specification package | Hosted Windows; planning consistency only |
| `ci.yml` | Pull requests and pushes build and run fast/affected contract, unit, analytic, API and public exchange/security suites | Hosted Windows; named required checks |
| `integration.yml` | Integration-branch changes and scheduled full deterministic/statistical campaigns | Hosted or controlled qualified profiles; all collected verdicts |
| `gui.yml` | Host changes and integration/release qualification | Qualified FreeCAD desktop/display runners through the appropriate trusted boundary |
| `vendor-validation.yml` | Reviewed candidates and source/adapter profile changes, dispatched in the private validation repository | Restricted exact-version licensed runners; paired source round-trip evidence |
| `performance.yml` | Relevant reviewed changes, reference schedules and release candidates | Controlled fixed hardware; accuracy, timing and peak-memory artifacts |
| `release.yml` | Candidate/tag qualification and publishing under established release authorization | Gate aggregation, clean installs, checksums and GitHub Release assets |

The foundation, planning, publication, exact host smoke and candidate packaging workflows are implemented under WP-02; run links and deployment evidence are tracked in the [WP-02 evidence record](evidence/WP-02.json) and [durable profile summaries](evidence/foundation-profiles.json). Product integration, GUI, licensed vendor, numerical performance and release workflows remain future outputs until their runnable profiles exist. Workflow schedules are GitHub Actions configuration, not app automations.

### 2.2 Privacy and sanitization before publication

Apply this rule to every outgoing online destination, including private repositories and restricted hosted artifacts. Access controls do not replace data minimization. Work with authorized local originals for engineering qualification and produce separate sanitized copies for material that will be published.

1. **Classify outgoing content.** Treat contact details, personal account names/paths, machine and internal-network identifiers, credentials, license material, private correspondence, customer/project identifiers and restricted models/results as private unless explicitly approved for the intended destination. Use synthetic public fixtures, relative paths and approved public maintainer identities. Preserve required third-party license notices and public attribution.
2. **Check before the first push.** WP-02 installs a local publication driver and version-controlled hook setup that checks staged files, outgoing commit history and author metadata before network transfer. Configure a privacy-preserving author email and approved public identity. A `.gitignore` file or a CI scan after upload cannot sanitize previously staged/history content; the driver must inspect the actual outgoing material.
3. **Sanitize generated outputs.** Remove personal usernames/absolute home paths from tracebacks, compiler/debug data, source maps and reports; sanitize document/image metadata, screenshot backgrounds, labels, paths and embedded content. Check packages, archives and bundled examples recursively with size/type limits. Keep exact original hashes and raw restricted evidence in authorized storage and use safe identifiers in public summaries; redaction must not fabricate engineering results.
4. **Gate prose and media publication.** Run the same preflight against rendered docs, issue/PR/comment/discussion bodies, release notes and other project posts before calling upload/post tools. Resolve screenshots and unsupported file types through a suitable inspection/sanitization path; an unchecked binary is not automatically safe. Any sensitive finding holds the affected upload until resolved or explicitly authorized for that destination.
5. **Automate checks and prove they fail correctly.** Add credential detection and project-specific privacy patterns, metadata/path inspection and an exact-output scan to local/GitHub Actions drivers. Use synthetic planted cases to prove detection of personal paths, email/contact data, credentials, commit metadata and restricted fixture references, including nested archives/generated outputs. Safe examples must also pass. Any justified public-identity/attribution exception is narrowly scoped and versioned; broad suppression of a private value is not a solution.
6. **Keep evidence sanitized.** Scanner failures identify category and safe relative location without echoing matched secrets or private values. Bind the public clearance report to the exact outgoing byte hashes and policy version. Recheck generated changes after sanitization and before upload; release publication requires both engineering qualification and privacy clearance.
7. **Handle existing exposure explicitly.** Stop further affected publication, revoke/rotate exposed credentials through the appropriate owner and remove exposed artifacts where authorized. Coordinate history rewrites and other destructive cleanup; changing the current file does not remove older copies. Preserve restricted incident evidence without reposting the sensitive contents.

WP-02 implements TST-021 through `tools/publication_preflight.py`, versioned policy and pre-commit/pre-push hooks. The driver inspects actual staged blobs, every reachable commit tree, complete commit objects, author/committer/tagger identities, outgoing prose and bounded nested archives. It rejects unsupported binaries/media, links, archive traversal, encrypted/unreadable inputs and inspection limits; safe reports contain opaque location IDs and categories without matched values. Clearance binds exact outgoing byte hashes and policy version/hash. Synthetic adversarial tests include deleted-history secrets, staged/worktree differences, personal paths/contact data, credentials, private identifier hashes, nested generated outputs and safe negative cases. CI repeats the same checks; direct API publication scans its exact payload before posting. See [developer commands and limitations](../docs/development.md). Restricted originals remain local; unsupported media needs an appropriate sanitization/inspection path before publication, and pattern detection does not infer every confidential engineering meaning.

WP-03 extends that executable publication boundary to the generated v1 schemas, shared types, embedded native schema table and synthetic JSON fixtures. The fast driver generates a bounded contract-conformance report with IDs and fixture hashes; both Windows jobs scan that exact report with verification/build metadata before upload. Local staged/outgoing-history and final prose scans remain mandatory. Native executables, raw compiler/reader logs, HDF5 payloads and acquired engineering originals remain local; the contract bundle does not authorize their publication. TST-021 acceptance remains `python tools/check_security.py` plus actual outgoing preflight, without new suppressions or private fixture contents.

WP-04 adds an exact pre-upload scan of each `numerical.json` summary. Its inputs are synthetic SI fixtures and independently frozen criteria; public evidence contains bounded metrics, source/backend/artifact hashes and public hardware/toolchain attributes. Raw per-attempt observations, compiler logs, executable/DLL files and restricted originals remain local. Sealed attempt manifests preserve failed/interrupted/superseded results. TST-021 acceptance executes the planted regressions plus staged/outgoing-history/identity and final prose/evidence scans before push; CI scans the final generated numerical summary before upload. No scanner suppression or authorization to publish engineering originals is added.

## 3. Build sequence and dependencies

Each package below specifies concrete tasks and completion evidence. Its register row identifies a lead role, prerequisites, expected outputs, and automated suites. Dependencies describe interface availability; packages can deliver a minimal slice before their complete Q1 capability. Every completion reference must point to an immutable test artifact, not a checklist marked by hand.

| Stage | Packages | Result |
|---|---|---|
| Establish Q0 | WP-01 through WP-04, plus native feasibility probes | Inventory, contracts, reference environment, criteria, automated harness and numerical decision |
| Build foundations | WP-05 through WP-10 | Durable operations/jobs and paired import/export paths |
| Build P0 | Minimal WP-11 through WP-14, integrated by WP-15 | Automated end-to-end two-node/two-surface demonstration |
| Complete Q1 | Finish prior packages plus WP-16 through WP-19 | Qualified owned core, both ecosystems and unattended release evidence |
| Complete Windows Q2 | WP-20 and WP-21 | Required advanced physics, user logic and all mandatory legacy profiles |

Do acquisition and feasibility work early for both ecosystems. After contracts stabilize, TD and ESATAN adapter implementation may proceed concurrently with core numerical work. This describes engineering staffing, not a request to run implementation agents during this planning task.

The dependency register allows native contract and analytic-prototype slices without WP-01. WP-01 findings must still be reconciled into the complete contracts and explicit compatibility dispositions before Q0 closes; paired source qualification belongs to Q1; adapters retain their inventory dependency. Native create/save/reopen/solve checks run as soon as their components exist, before the full P0 integration demonstration.

### Step 1 — WP-01: freeze the acquired inventory and explicit dispositions

The user narrowed WP-01 to the delivered baseline: 55 immutable files from four public sources, six model/example cases, 21 feature groups, all 12 profile dispositions and the independent public analytic seed. Original bytes, notices and restricted metadata remain local.

1. Lock provenance and hashes against pinned upstream Git trees and verify every acquired original locally.
2. Record source-version observations, dependency/result/rights status and every required operation; unknowns require explicit owned gaps.
3. Map all acquired cases and feature/profile rows to requirements, components and later-package owners. TD and ESATAN retain equal compatibility priority.
4. Preserve publication holds and inert source logic. Keep all acquired profiles unqualified.

**Outputs:** acquired inventory, source/hash manifests, feature/operation map, rights/dependency dispositions and assigned qualification gaps. **Completion:** offline metadata checks and all 55 local original-byte checks pass; no acquired row lacks provenance, ownership or a required disposition. This criterion is met and WP-01 is Complete.

**Explicit later obligations:** licensed reference runtimes, exact source/dependency closure and source reopen/export/run are WP-08/WP-09; normative STEP-TAS schema/dictionary/validation is WP-10; redistribution and paired numerical-reference closure is WP-19; advanced and legacy coverage remain WP-12/WP-20/WP-21 as mapped in [inventory/gaps.json](../inventory/gaps.json). These still block the affected compatibility or publication claim. They do not reopen WP-01 or block native Q0 work. `python tools/check_inventory.py --local --qualify` remains the separate blocked compatibility-prerequisite check, not the WP-01 completion command.

See [WP-01 evidence](evidence/WP-01.json) and [inventory](../inventory/README.md). Closing this inventory is not a compatibility, source-run or physics qualification claim.

### Step 2 — WP-02: create the source/build/test foundation

1. Establish the authoritative GitHub repository, Issues/Projects backlog, milestone/requirement links, PR/issue templates, component ownership, proposed licenses for new code, contribution rules and a dependency/provenance manifest. Configure and automatically verify default/release-branch protections and required checks.
2. Add CMake build/install presets for a debug/sanitizer configuration where supported and a release reference configuration. Add a Python package layout and isolated lockfiles for standalone tooling and host-compatible dependencies.
3. Implement empty engine/worker entry points, structured diagnostic types and build-info output. The native executable must launch with FreeCAD and Python absent.
4. Add GitHub Actions Windows CI that builds, runs a trivial executable test, imports standalone Python modules, validates contracts, and stores machine-readable results. Add the planning/specification checks first, before product code exists. Host smoke jobs use the exact selected FreeCAD build. Establish the separate private validation repository and scoped vendor/performance runner access as required.
5. Create platform installation/build probes for the numerical, HDF5, intersection and geometry candidates. Measure packaging burden and record licenses rather than adding every candidate to production.
6. Define supported compiler/runtime/ABI profiles, dependency source hashes, thread settings and floating-point flags. Avoid unsafe optimization flags in the deterministic numerical reference profile.
7. Provide one documented developer command for the fast suite and one for full qualification. GitHub Actions uses the same drivers and publishes a required aggregate coverage check; workflow jobs cannot silently skip required cases.
8. Implement TST-021's local publication driver, staged/outgoing-history and author-metadata checks, generated-output/prose/media scanning, sanitized reports and exact-byte publication clearance. Verify the check using planted synthetic private data before the first push or post. GitHub Actions repeats the checks, and the release workflow requires privacy clearance for its final assets.

**Outputs:** GitHub repository/backlog/protection setup, reproducible skeleton builds, Actions workflows, scoped runner infrastructure, tested publication-privacy preflight, dependency records, developer setup guide. **Completion:** clean Windows runners build/install the skeleton; engine-only smoke tests pass without host/Python; CI rejects a deliberately broken fixture in an isolated harness self-check; the repository-settings checker confirms the agreed GitHub configuration; publication preflight rejects planted private data and clears the exact outgoing artifacts.

**Foundation acceptance boundary:** the exact FreeCAD 1.1.4/cp311 bundle smoke and pinned candidate source build/install/consumer probes are part of WP-02. The controlled private validation infrastructure is deliberately disabled until WP-08/WP-09 supply authorized reference profiles; its fail-closed policy, workflow, permissions and absence of privileged runners are checked live. Activating licensed source execution remains with WP-08/WP-09; it does not block completed WP-01. Numerical backend selection and reference hardware/compiler freeze remain WP-04's existing Q0 decision, and the full qualification driver continues to reject their absence. Completing the foundation cannot close Q0, qualify a compatibility profile or qualify the future WP-13 workbench.

### Step 3 — WP-03: freeze model, operation, result and worker contracts

1. Define typed UUID entities for projects/submodels, geometry, meshes, nodes, materials/optics, conductors, loads, radiation, environments, cases, controls and results. Keep source handles/node numbers in separate versioned maps.
2. Specify quantity dimensions, SI normalization, absolute/relative temperature conversions, frames, tensor orientations, epochs/time scales and property valid ranges. Reject nonfinite values and invalid physical ranges with entity/source diagnostics.
3. Keep CAD faces, radiation facets, conduction elements and thermal nodes distinct. Define many-to-many mappings, weights/areas and provenance; include geometry-free networks.
4. Define stable attachment records using source revision, persistent references and geometry signatures. Ambiguous face changes require explicit reassignment; a signature match alone is not proof of correctness.
5. Specify a typed expression AST, operators/functions, evaluation order, table interpolation/extrapolation policy, symbol resolution and cycle handling. Dimension/type errors must be testable without a solve.
6. Publish full JSON model/operation/result schemas and HDF5 paths/dtypes/shapes/chunking/units/index conventions. Use an explicit UUID-to-array-index map. Draft manifest/envelope schemas are inputs to this work, not a complete product model.
7. Specify semantic canonicalization: preserved required IDs, deterministic field/array order, floating-point encoding, signed zero, byte order, normalized quantities and exclusion of timestamps/GUI state. Distinguish semantic, artifact and build hashes.
8. Specify per-operation arguments/results, errors, capability negotiation and major-version rejection. Write contract fixtures independently readable in C++ and Python.
9. Define worker messages: handshake, submit/snapshot/artifact references, progress, diagnostics, cancellation, terminal outcome and checkpoint metadata. Frame bounded control messages; keep large arrays in verified local artifacts.
10. Version all contracts together with migration/read-compatibility policies and minimum supported readers.

**Outputs:** complete schemas, canonicalization and IPC documents, positive/negative fixtures, generated/shared types. **Completion:** C++ and independent Python readers agree on normalized snapshots/hashes; collision, mixed-unit, anisotropic-frame, unknown-field, version-mismatch and invalid-reference cases behave identically.

WP-03 implementation is documented in the [v1 contract bundle](../spec/contracts/README.md), with executable evidence in [WP-03.json](evidence/WP-03.json). The shared local/CI fast driver checks generated-byte drift, frozen positive hashes, exact required case IDs, independent C++/Python normalized bytes/diagnostics/hashes, standard schema conformance and bounded native control frames. The acquired WP-01 feature reconciliation is included in the contract document; all vendor qualification gaps retain their owners. This freezes the native interface baseline; persistence, operation execution, actual worker jobs, thermal solving and complete Q0 closure remain subsequent work packages.

The WP-03 verification follow-up adds frozen 64/65-record graph boundaries in both serialization and dependency-ID directions, valid and over-limit nested ASTs, checkpoint time-unit/frame cases and decoded Unicode-key cases. Both readers use complete-graph longest paths rather than cached traversal depth. TST-021 preflight scans the new synthetic JSON inputs and updated evidence as actual outgoing bytes; no raw engineering models, binary frames or local audit logs enter publication.

### Step 4 — WP-04: build numerical oracles and pass the Q0 prototype checkpoint

1. Create fixture manifests with analytical equations or independently derived expected values, declared discretization, comparison quantities, tolerances, units, normalization floors and expected failure categories.
2. Establish criterion versions separately from result files. Freeze criteria before execution and preserve failed results when criteria later change.
3. Build a small C++ prototype with nonlinear conductance/capacity, capacitive/algebraic/prescribed nodes, consistent initialization, radiation feedback and heater switching. Exercise the independently authored native seed without a vendor runtime; paired TD/ESA source cases remain required under their Q1 adapter qualification.
4. Compare candidate integration/sparse backends on the same equations, accuracy settings, hardware and inputs. Check Jacobian/residual consistency, energy, events, failure diagnostics and restart before timing.
5. Run sparse scale probes and clean install probes. Record implementation effort, debug/deployment issues, memory and runtime; freeze reference hardware and toolchain settings.
6. If a Rust comparison is explicitly selected, keep it a bounded prototype using the same numerical backend where applicable. Otherwise record that C++ met or failed the checkpoint; a Rust implementation is not a dependency.
7. Predeclare Monte Carlo seed ensembles, sample/replicate counts, interval estimator/coverage, multiplicity treatment, convergence and practical error policy.
8. Record the Q0 decision, selected libraries/interfaces and unresolved limitations. An unsatisfactory backend triggers another measured candidate, not weakened criteria.

**Outputs:** executable oracle harness, baseline numerical/statistical/performance policies, prototype results and architecture decision. **Completion:** repeatable automated runs establish acceptable C++ suitability and required deployment behavior; Q0 acquired-inventory/contracts/native prototype items are also complete; affected compatibility access remains required before Q1 claims. Prototype success permits implementation, not compatibility claims.

The [Q0 numerical decision](../docs/decisions/0001-q0-numerical.md) implements this checkpoint using the independent analytic seed, a stiff nonlinear capacitive/algebraic/prescribed network, radiation feedback and heater switches. The standard debug/release driver builds and installs the separate C++ experiment and requires exact coverage of native/oracle comparisons, analytic Jacobians, energy/events, cooperative cancellation/restart, steady balance, failure diagnostics and sparse fixed-bandwidth scale probes. Criteria, Monte Carlo policy and reference hardware/toolchain are frozen separately from per-attempt results. Each attempt retains raw observations and sealed provenance locally; hosted summaries are privacy-scanned. SUNDIALS BDF/dense, BDF/band and Adams/band are measured at the same accuracy; C++ remains the baseline. [Completion evidence](evidence/WP-04.json) records both 84-check Windows runs, 23 frozen-reference cases and 70 standard-library regressions, with the [bounded numerical baseline](evidence/numerical-baseline.json). Full production physics, general DAE/sparse graphs and every vendor compatibility qualification remain with their mapped later work packages.

### Step 5 — WP-05: implement persistence, revisions and transactional operations

1. Implement expanded-directory and ZIP package readers/writers, artifact hashing, dependency closure checks and versioned JSON/HDF5 storage. Immutable original imports remain byte-for-byte retained.
2. Validate archive limits, normalized paths, duplicate paths, dot segments, reserved names, links/escapes and checksums before publishing a project. Never deserialize executable objects.
3. Implement a durable per-project transaction journal/store. A small embedded database is a proposed operational store; portable project semantics must remain reconstructable from documented package data.
4. Implement operation dispatch, actor/project-scoped idempotency and optimistic revision checks. Atomically store changes, revision and deduplication outcome; same-key/different-payload retries fail.
5. Implement separate preview-plan IDs/hashes with payload, base revision, policy scope and expiry. Apply rechecks every condition and does not acquire authority from preview.
6. Implement multi-entity atomic edits, inverse change sets and undo as a new committed revision. Readers see a committed snapshot, never a partly edited model.
7. Build dependency invalidation for mesh, geometry, optics, environment, solves, comparisons and acceptance checks. Distinguish stale-for-live-model from historically valid results.
8. Stage saves on the target filesystem, verify contents, atomically replace the committed package and retain a recoverable prior revision. Coordinate `.FCStd` via revision/hash journal states rather than assuming a two-file atomic operation.
9. Implement schema migration, read compatibility, recoverable backups and explicit downgrade export where supported.

**Outputs:** package store, operation engine, revision/invalidation graph, migration/recovery tools. **Completion:** fault injection at write/flush/replace/journal/sync boundaries yields the previous valid revision or a clearly recoverable committed state. Restarted retries cannot duplicate entities/jobs. No failure reports a false clean save.

### Step 6 — WP-06: implement isolated workers and durable jobs

1. Implement protocol negotiation and artifact-root authorization; verify snapshot schema, byte hashes and semantic hash before starting numerical work.
2. Persist job submission with immutable snapshot, profile/feature selection, actual backend/build/settings, execution mode, resource budget and random seeds before returning a job ID.
3. Implement `queued`, `running`, `cancelling`, `succeeded`, `failed`, `cancelled`, `interrupted` transitions with linked attempts for retries/resumes. A service restart never turns an interrupted run into success.
4. Stream bounded progress/diagnostics on a control channel. Keep logs separate from protocol framing and apply response backpressure/size limits.
5. Implement idempotent cancellation, acknowledgement, configurable deadline and worker-termination fallback. Check cancellation in long kernels, including ray tracing and sparse solve boundaries.
6. Write temporary result artifacts, validate the completed result manifest, and publish atomically. Partial/checkpoint outputs remain labeled; terminal jobs cannot be overwritten by late callbacks.
7. Implement checkpoint/restart only for explicitly supported states, preserving time/event/control/backend/seed state and verifying compatibility. Unsupported resume offers a fresh linked attempt rather than a false continuation.
8. Reject stale result attachment to live cases; provide an explicit historical snapshot/view path.

**Outputs:** scheduler/job store, worker protocol, lifecycle/recovery manager. **Completion:** automated kill, disconnect, cancellation race, timeout, duplicate-submission, stale-result and restart tests preserve both job truth and project recovery. Native qualification runs prove external thermal solvers were unavailable.

### Step 7 — WP-07: implement common adapter infrastructure and safe logic handling

1. Define adapter discovery/capabilities, runtime probing, import preview/staging, conversion plans, semantic mapping, diagnostics and export interfaces.
2. Build a source dependency resolver that safely reads permitted data includes, reports missing files and never executes include commands or imported logic. Record include graphs and original source locations.
3. Implement syntax-preserving parsed trees for declared network dialects, with original byte ranges/comments and opaque unknown regions. Unknown syntax is reported, not interpreted by filename extension.
4. Produce per-entity/dependency/procedure/case and per-operation fidelity records with source/target IDs, status, evidence and limitations. Preserve `native-reconstructed`, `bridged-executable`, `retained-opaque`, `approximated`, `unsupported` separately.
5. Map reviewed source expressions/procedures into the typed FCST IR with explicit source-language evaluation rules. Retain untranslatable originals inertly and block required native execution.
6. Export to a new tree. Patch preserved source content only where supported and reject unsafe changes affecting opaque content; an unsupported preservation case must not silently drop fields.
7. Implement source-result import with quantity, units, sign, identity and time-grid mappings. Declare interpolation rules and avoid interpolating across discontinuities without an explicit policy.
8. Add size/depth/recursion/entity limits, parser fuzzing and future-syntax fixtures. Run vendor/third-party conversion tools under bounded roots/resources and recorded authorization.

**Outputs:** adapter SDK, syntax/semantic IR, fidelity schema, safe resolver and result readers. **Completion:** positive, partial, malformed and malicious fixtures yield complete reports; comments/code/logs cannot execute or alter authorization. Required unknown semantics block a runnable/qualified status.

### Step 8 — WP-08: implement the Thermal Desktop/SINDA path

1. Create a version-profiled Windows bridge with a discovery-only runtime probe. Select its .NET/compiler/runtime from the actual OpenTD release requirements; do not assume one binary covers every target.
2. On a copied source project, inventory custom thermal entities, submodels, node IDs/classes, GMM/TMM assignments, properties, optics, conductors, cases, controls, references and dependencies. Include external property databases such as those actually referenced by the fixture.
3. Extract required geometry and thermal data through the declared API into adapter IR, then canonical entities. Generic DWG/DXF geometry import remains labeled geometry-only.
4. Implement declared SINDA deck dialect parsers/writers, includes, property tables, expressions and required reviewed source logic. Map each construct to owned-engine capability or an explicit unsupported status.
5. Implement supported canonical-to-TD edits against the copied source tree and source identity map. Validate supported changes before calling the vendor API.
6. Automate unchanged and controlled-edit reopen/run/result extraction on the licensed runner. Independently make equivalent source-native edits and compare their results with FCST-edited derivatives.
7. Exercise loads, material tables, geometry/topology, properties and cases, plus unchanged opaque-content preservation. A parser-only test cannot qualify editing/export.
8. Compare owned-engine thermal/radiation/environment runs with the matching SINDA and TD/RadCAD references, preserving separate execution-mode labels.

**Outputs:** TD/OpenTD profile implementations, SINDA adapters, reference runner and paired evidence. **Completion:** every required Q1 TD feature/operation passes semantic inventory, edited round trips and numerical comparisons on exact runtimes. Q1 TD status remains blocked until its paired ESA qualification also passes.

### Step 9 — WP-09: implement the ESATAN-TMS path

1. Build version-specific prerequisite probes and unattended export/import/reopen/result drivers for the selected ESATAN versions.
2. Inventory project/campaign files, cases, geometry, properties, GMM/TMM mappings, includes, expressions, user logic and results. Do not reconstruct campaigns from geometry alone.
3. Implement the required `.d` dialects with preserved syntax, source locations, tables, units, submodels/node identities and reviewed expression semantics.
4. Use native API/export and STEP-TAS paths where available, together with required companion files; map to the same canonical entities used by TD.
5. Implement supported edits and export to a copied project tree. Preserve untouched content or fail explicitly when the adapter cannot safely write it.
6. Automate unchanged and controlled-edit source reopen/run, equivalent source-native edits and source-result comparison using the same categories required for TD.
7. Compare FCST native execution with ESATAN reference cases, and retain diagnostics for required semantics scheduled for Q2.

**Outputs:** ESATAN profile adapters, result readers and unattended reference runner. **Completion:** the paired Q1 ESA profile passes the same semantic, edit/re-export and numerical criteria as TD. Extra work in either ecosystem cannot compensate for missing coverage in the other.

### Step 10 — WP-10: implement STEP-TAS and bidirectional exchange

1. Bind parsing and validation to the acquired schema/dictionary version. Inventory needed entities, relationships, dataset types and direction requirements from both source corpora.
2. Implement data types, references, units/frames, geometry/network associations and required metadata. Reject malformed relationships with source locations.
3. Implement writers from canonical entities and validate output with an independent schema checker and actual target-tool reopening.
4. Retain source/campaign content absent from STEP-TAS through explicit companion artifacts and fidelity records; do not label retention as execution/edit support.
5. Define a named TD/ESA common semantic profile. Export TD→FCST→ESA and ESA→FCST→TD as separate tests with independently declared supported feature sets.
6. Compare discrete identity/topology, mapped numeric fields, case settings and equivalent numerical results in each direction. Record every approximation/loss.
7. Generate capability statements from actual tested schema entities/datasets/versions/directions. Do not advertise a whole conformance class unless the entire class is tested.

**Outputs:** schema-backed reader/writer/validator, common-profile converters and evidence. **Completion:** all mandatory Q1 datasets and both cross-tool directions pass; unrelated format-class work is not required. Required unsupported content blocks the affected profile.

### Step 11 — WP-11: implement the owned thermal network engine

1. Implement typed immutable model loading, structural validation, node classification, source identity maps and equation indexing. Diagnose unanchored/singular components without declaring every disconnected-but-well-posed component invalid.
2. Implement constant and temperature-dependent material tables with explicit interpolation/range rules, enthalpy/storage and valid density/capacity/conductivity. Validate positivity and supported anisotropic tensors.
3. Assemble the owned energy residual from storage, conductive exchange, loads, radiation/environment callbacks and boundaries. Use consistent signs and explicit boundary heat-flow accounting.
4. For algebraic nodes, assemble algebraic constraints. Apply prescribed temperatures consistently and compute boundary power. Do not insert arbitrary tiny capacities to avoid DAE support.
5. Implement residual/Jacobian evaluation, sparsity construction and a backend-independent linear/nonlinear solve interface. Check Jacobians against independent differences on small smooth fixtures.
6. Implement linear and nonlinear steady solves with meaningful residual scaling, stopping criteria, diagnostics and singular/nonconvergent termination.
7. Implement stiff transient solves with consistent initialization, tolerance control, rejected-step reporting, agreed output sampling and energy accounting based on enthalpy.
8. Implement heater hysteresis and schedules as explicit state/event logic: event localization, simultaneous-event ordering, state update/reinitialization, and checkpoint state. Define chattering/error behavior.
9. Return temperature, conductive/boundary power, storage change, residuals, events, duty cycles and step/run energy balances with validity/provenance.
10. Add compiled-kernel profiling and backend capability records. Optional external reference solvers use separate execution modes and cannot satisfy these tests.

**Outputs:** owned network assembly and steady/transient/event solvers. **Completion:** single/two-node analytic cases, nonlinear properties, algebraic/prescribed nodes, singular cases, conservation, refinement and independent source comparisons pass without FreeCAD, Python, or external thermal solvers installed.

### Step 12 — WP-12: implement CPU radiation and thermal coupling

1. Build radiation meshes with facet/surface/node identity maps, orientation, front/back activation, groups/exclusions and optical assignments. Detect invalid geometry and mapping areas before tracing.
2. Implement a CPU intersection abstraction and BVH/intersection backend. Test geometric intersections independently from radiative estimators.
3. Implement seeded sampling, ray distributions, occlusion, escape and a documented view-factor estimator. Assign reproducible streams to stable work identities; thread scheduling must not silently change the reference experiment.
4. Implement diffuse-gray radiosity/exchange with separate solar absorptance and IR emittance, two-sided optics and open-environment terms. State assumptions under which fixed fourth-power couplings are valid.
5. Couple radiative powers and derivatives to the owned thermal residual. Keep environment exchange bookkeeping explicit to prevent double counting.
6. Measure bounds, reciprocity, closure and escape. Preserve raw estimator evidence; any correction/normalization algorithm must report its effect and pass independent checks.
7. Design sparse, hierarchical or streamed exchange storage and bounded result queries. Test approximation error instead of constructing a mandatory dense all-pairs matrix.
8. Run fixed Monte Carlo ensembles and sample-count refinement. Assess coverage/convergence and practical error jointly; a single favorable seed is insufficient.

**Outputs:** CPU radiation engine, exchange artifacts and uncertainty diagnostics. **Completion:** analytic enclosure/plate/sphere cases, black/gray/two-sided surfaces, occlusion/groups/escape, source comparisons and coupled energy checks pass. Million-facet scaling publishes build/throughput/memory/error curves before a throughput promise is made.

### Step 13 — WP-13: build the FreeCAD host and model-review interface

1. Add workbench registration, document/project links, tree objects and view providers using the pinned host APIs.
2. Implement editors for nodes, surfaces, materials/optics, conductors, loads, environments, cases and solver settings. Each editor calls the shared operation API and displays structured errors.
3. Implement selection-to-entity mappings and explicit visual overlays for nodes, mesh assignments, normals, material axes, contacts, unassigned items and invalid/ambiguous attachments.
4. Route all document changes/completion callbacks through the owning application thread. Offload expensive work to isolated jobs and keep progress/cancel controls responsive.
5. Implement canonical commit-to-host synchronization, explicit dirty/reconciliation state for direct host edits, undo through inverse transactions, and save/recovery coordination.
6. Display temperature contours and time histories, heat-flow/energy budgets, heater duty and validity/staleness. Use result IDs/units from the data layer rather than recalculating separate UI values.
7. Build host test commands and stable UI selectors/object identifiers. Automate command invocation, edits, selection, dialogs, asynchronous completion, save/reopen, undo and result inspection in an isolated FreeCAD process.
8. Use screenshots as supplementary rendering evidence; numerical/data assertions are primary. Automate visual checks for selected stable reference views with declared tolerances.

**Outputs:** usable workbench, inspectors, visualization and unattended host harness. **Completion:** a clean runner builds/saves/reopens a model through the UI, verifies canonical hashes and plotted values, exercises face changes and failure recovery, and completes without a person clicking through the test.

### Step 14 — WP-14: implement typed MCP automation and policy enforcement

1. Add a local stdio server over the shared application operations. Verify the chosen released protocol lifecycle/SDK instead of inferring compatibility from an API method name.
2. Publish operation-specific tool argument/result schemas, capability discovery, project inspection, typed edits/transactions, job controls, results and import/export/report tools from the specification.
3. Implement versioned resources with authorized UUID/revision/artifact access, pagination and response bounds. View captures are explicit and include camera/case/time/revision metadata.
4. Enforce server-issued project/case scope, filesystem roots and compute budgets. Standing authorization covers ordinary reversible edits; source overwrite, external disclosure and privileged code execution require the corresponding authority.
5. Keep imported comments/paths/code/logs untrusted. They cannot change policy, criteria, profile status or execution-mode labels.
6. Implement redacted audit events containing actor/provider where known, tool/version, argument hashes, revisions, changes and outcomes. Avoid credentials or hidden reasoning in project packages.
7. Separate application job cancellation from transport cancellation. Reconnecting clients recover durable job outcomes and cannot duplicate submissions.
8. Run in-process and real-client protocol tests offline. Default installs open no network listener; if network MCP is later shipped, give it separate opt-in/auth/origin/transport tests.

**Outputs:** stdio MCP gateway, policy layer and protocol/client profiles. **Completion:** a scripted MCP client builds and solves the same fixture as GUI/CLI with the same normalized IDs/hashes and acceptance results. Scope, injection, pagination, disconnect and cancellation cases pass. No cloud provider or arbitrary-code tool is needed.

### Step 15 — WP-15: integrate and automatically demonstrate P0

1. Generate a two-node/two-surface project with explicit material, capacity, conductor, optical, environment/boundary and initial-condition values.
2. Build/save/reopen it through CLI/API, FreeCAD and MCP operation sequences. Use fixed UUIDs or a declared identity map for parity.
3. Compute a native conduction/radiation transient and compare against the corresponding analytic/reduced-model oracle under predeclared criteria.
4. Verify FreeCAD contour/history values against result queries, then change one load and prove invalidation/stale-result guards work.
5. Exercise one public synthetic fixture from each ecosystem through the declared limited adapter paths and inspect fidelity reports. A declared deck subset does not qualify a native vendor project.
6. Cancel a solve, terminate a worker and reopen the saved project. Check that no partial solution is published as complete.
7. Produce a single machine-readable P0 report with input/build/criteria hashes and all evidence links.

**Outputs:** repeatable demonstration project and `qualify --gate P0` report. **Completion:** the full scripted demonstration passes on the selected Windows native/host profiles and named MCP client profile. P0 claims remain experimental even when every demo step passes.

### Step 16 — WP-16: complete FD/FE discretization, contacts and property coverage

1. Freeze supported FD primitives and FE shell/solid element families from the Q1 inventory; document formulations, quadrature, lumping/reduction and validity limits.
2. Generate meshes through the geometry adapter/selected mesher with stable provenance and explicit CAD/facet/element/node mappings. Mesh refinement cannot silently change source identity associations.
3. Implement element conduction/storage assembly and rotate symmetric positive-definite material tensors from local frames. Validate interpolation and tensor/temperature ranges.
4. Implement contact mappings with physical area/gap assumptions, lumped links, convection and distributed heaters/loads. Integrated assigned power must equal the intended total.
5. Connect geometry edits to mesh/radiation/result invalidation and ambiguous attachment detection, including face split/merge/reorder/delete.
6. Implement limited MLI, insulation and reduced heat-pipe abstractions with parameter provenance, calibration/validity limits and explicit unsupported regimes.
7. Run rod/slab cases, element patch tests, rotated anisotropy, manufactured solutions, contact tests and mesh/time refinement independently of vendor comparisons.

**Outputs:** supported discretization library, mesh/attachment tooling, contact and reduced-component models. **Completion:** analytical/manufactured/conservation/refinement suites and mandatory imported Q1 element/property cases pass; unsupported element types are diagnosed before solving.

### Step 17 — WP-17: implement environments, motion and campaign events

1. Define supported body constants, epoch/time scale, orbit/trajectory, attitude and articulation representations. Choose/pin any time/orbit dependency through Q0 evidence and record reduction assumptions.
2. Implement frame transforms, sun/body directions and eclipse/occultation with independently derived simple configurations and timing references.
3. Implement solar, albedo, planetary IR, deep-space and chamber boundary models with separate optical bands, explicit assumptions and integrated incident-power checks.
4. Build a common event schedule for heater controls, orbit/eclipse transitions and moving geometry. Define interpolation, discontinuity and event-order behavior.
5. Cache/recompute radiation exchange only when dependency hashes and error policy permit it; quantify geometric and temporal interpolation error for articulated models.
6. Support case overlays for hot/cold, operating/nonoperating, BOL/EOL and test/flight. Preserve shared entity/source identity across variants.
7. Compare heating histories and temperatures with TD/RadCAD and ESATAN cases, while retaining independent geometry/flux/refinement checks.

**Outputs:** environment/kinematics engine, loading histories and case definitions. **Completion:** orbit/eclipse/chamber/moving-panel fixtures meet timing, power and refinement criteria without double-counted energy; changing motion/optics invalidates affected exchange and solve artifacts.

### Step 18 — WP-18: implement campaigns, correlation and reporting

1. Add bounded batch sweeps with immutable per-case snapshots, parameter bounds, distributions/correlations, seeds, sampled inputs and linked results. Enforce job/memory/compute budgets.
2. Implement declared sensitivity methods and compare selected derivatives with independent finite differences/refinement. Record perturbation sizes and failed samples.
3. Import sensor/time data with units, uncertainty and mappings. Preserve original observations, time-grid/interpolation provenance and the uncorrelated baseline.
4. Implement bounded correlation/parameter fitting with objective metrics, parameter bounds/change rationale and separate training/holdout comparisons. Do not fit and score exclusively on the same observations.
5. Add user-configured temperature allowables/margins as versioned inputs. Limit changes invalidate affected checks without silently modifying historical run data.
6. Generate reports from run/artifact IDs: assumptions, configuration, provenance, fidelity losses, numerical convergence, uncertainty, balances, limits, defects and limitations. Include machine-readable tables alongside human-readable plots/reports.
7. Reproduce a fully synthetic test/correlation campaign automatically; measured data can extend validation but is not required for every compatibility test.

**Outputs:** case manager, sweep/sensitivity/correlation tools and report generator. **Completion:** deterministic campaign replay and synthetic holdout checks pass; every plot/table matches queried result data and the correct immutable revision.

### Step 19 — WP-19: qualify, scale, package and release Q1

1. Run all Q1 suites on frozen configuration profiles and all mandatory fixture/profile rows. Include changed source models and both cross-tool directions.
2. Run a native-only environment without vendor solvers/FreeCAD/Python for the engine suite, and separate host/API/MCP parity environments. Record actual loaded backend/build dependencies.
3. Profile large models. Test 100,000-node inspection within 5 s after load, UI/cancellation acknowledgement within 1 s, and the 100,000-node/1,000,000-link steady sparse benchmark within 60 s/16 GiB on the frozen reference hardware. Record raw timings/memory and any explicit performance disposition separately from physics correctness.
4. Publish million-facet radiation scaling/error curves; do not invent a throughput threshold before measurement. Verify query paging, streaming and bounded memory.
5. Automate clean offline installation and model open/build/solve/report/uninstall/rollback on Windows. Test portable dependency closure and `.FCStd` coordinated recovery on clean machines.
6. Add sanitizers where supported, parser/security fuzz regression, malformed packages, injection/scope checks, secret redaction, dependency/license inventories and source/build reproducibility checks.
7. Generate analyst/developer/API/MCP documentation and runnable examples from tested interfaces. Publish supported versions/directions/features/backends from evidence, not a manually embellished support list. Produce GitHub Release assets tied to the tested candidate commit/tag, checksums, license/dependency manifests and qualification summary; retain raw evidence durably under its access policy. Run privacy preflight on final assets, rendered documentation, metadata, logs and release prose, and publish only outputs bound to a valid sanitization/clearance report.
8. Run the gate evaluator over all 114 Q1 specification requirements and applicable automated-test requirements, considering defects and explicitly accepted dispositions. Missing/failed required tests block the gate.

**Outputs:** Q1 binaries/source bundle, dependency/license hashes, support matrix, methods/API guides, examples and immutable qualification report. **Completion:** both ecosystems and every Q1 obligation pass on claimed profiles. There is no user-run manual acceptance script and no general full-suite parity claim.

### Step 20 — WP-20: implement required Q2 advanced owned physics and logic

Plan and prototype this work from WP-01 findings; do not wait for Q1 to discover its architecture. Production tasks can proceed after their interfaces are ready. Q2 acceptance follows Q1.

1. Turn each required advanced corpus feature into an explicit equation/semantics contract and automated oracle/reference case. Unknown scope remains visible rather than being estimated as a small generic add-on.
2. For required fluid networks, define pressure/flow/enthalpy states, mass/momentum/energy equations, fluid-property ranges and component laws; model pumps/valves/heat exchangers only as required by the corpus.
3. Implement coupled thermal-fluid residual/Jacobian assembly, consistent initialization, event handling and conservation. Qualify strong/partitioned coupling choices against refinement/stability evidence rather than assuming either is sufficient.
4. Implement required two-phase/detailed heat-pipe/other advanced behavior or a specifically accepted native equivalent. Verify regime transitions, properties and validity limits against analytical/independent cases and FLUINT/FloCAD reference runs.
5. Implement required specular/transmissive/spectral optical laws with independent ray/energy tests and declared estimator changes; diffuse-gray success does not close these features.
6. Translate required remaining source procedures to maintained native semantics with regression evidence. Any privileged executable extension uses a narrow versioned ABI and isolated, explicitly authorized execution; opaque storage or vendor execution alone cannot close required native support.
7. Extend public model/results/worker contracts through versioned migrations and requalify affected Q1 cases.

**Outputs:** required advanced engine modules, source-logic implementations and method documents. **Completion:** every mapped advanced feature passes independent correctness/conservation/refinement tests and source comparisons on the owned engine, including flow/pressure/temperature/energy quantities where applicable.

### Step 21 — WP-21: close Q2 legacy profiles and full inventory qualification

1. Implement exact required SYSTEMA/THERMICA, THERMISOL, ESARAD, SYSBAS/VIF, TRASYS and additional customer dialect/version paths identified by the inventory.
2. Handle GMM, mesh, TMM, properties, campaign and results jointly where required. Choose native APIs/schema paths or approved converter invocations per actual profile.
3. Qualify every required direction independently. A VIF reader does not imply a writer; current THERMICA projects are not qualified by an old SYSBAS reader.
4. Apply the same safe parse/preserve/edit/new-tree export, unchanged/controlled-edit source round trips and native-solve comparisons used for Q1.
5. Run every mandatory entity/procedure/case/operation through the coverage evaluator. Required retained-opaque, unsupported, unapproved approximation or external-only execution entries block Q2.
6. Re-run affected Q1 profiles, platform installations, security, performance and automation suites after advanced modules/adapters are added.
7. Publish the exact supported inventory, remaining non-required limitations and immutable evidence bundle. Close all five Q2 specification requirements and applicable delivery-test requirements.

**Outputs:** full required legacy adapters, advanced/native support matrix and Q2 qualification bundle. **Completion:** zero unresolved required coverage entries and all mandatory round trips/owned-engine executions pass. Compatibility claims stay bounded by the published inventory; proprietary source conversion may still require declared vendor tools.


## 4. Mandatory automated-test delivery requirements

The following 21 requirements implement the user's instructions for unattended testing, GitHub delivery and privacy before publication. Their full machine-readable acceptance text is in [automated-test-requirements.csv](automated-test-requirements.csv). They supplement the 121 baseline requirements; their IDs are deliberately separate. Q0 is the first required gate for test infrastructure/criteria and publication privacy, while Q1 requirements also apply to Q2 and any changed capability. TST-021 applies before the first online publication even if Q0 is not yet complete.

| ID | Required behavior | First required gate |
|---|---|---|
| TST-001 | Every delivery requirement and claimed profile operation has an executable test/inspection rule, owner and evidence link | Q0 |
| TST-002 | Numerical/statistical/semantic criteria are versioned and frozen before runs; changes create reassessment runs | Q0 |
| TST-003 | Acquired fixtures have reproducible manifests, hashes, status/rights dispositions and assigned gaps; executable oracles are required at their affected qualification gate | Q0 |
| TST-004 | Owned-engine physics, energy, refinement, algebraic initialization and controls/events run automatically | Q1 |
| TST-005 | Scripted GUI/CLI/MCP sequences produce equivalent model semantics and numerical outcomes | Q1 |
| TST-006 | Persistence/job tests inject crashes, interrupted writes, retries, disconnects and cancellation races | Q1 |
| TST-007 | Licensed runners automatically perform exact-version source reopen/run, controlled edits and cross-tool comparisons | Q1 |
| TST-008 | FreeCAD tests create/edit/save/reopen/undo/solve/inspect without user clicks; screenshots supplement data assertions | Q1 |
| TST-009 | Clean-machine offline install, native solve, migration, portable reopen and rollback are automated per supported profile | Q1 |
| TST-010 | Parser/archive fuzzing and non-execution, scope, injection and redaction checks run automatically | Q1 |
| TST-011 | Stochastic qualification uses predeclared fixed ensembles and convergence/coverage policy; no seed shopping | Q1 |
| TST-012 | Performance tests record actual resources/hardware and compare frozen targets at unchanged accuracy | Q1 |
| TST-013 | Test runs emit structured verdicts, diagnostics, raw data and immutable provenance/evidence manifests | Q0 |
| TST-014 | Native acceptance runs prove no external thermal solver was used and preserve actual execution modes | Q1 |
| TST-015 | Missing fixtures/licenses/runners/oracles produce blocked/incomplete required coverage, never an implicit pass | Q0 |
| TST-016 | Retries cannot erase failures; flaky tests and quarantines remain visible and cannot remove mandatory gate coverage | Q1 |
| TST-017 | GitHub is the source/work-tracking platform; GitHub Actions and local drivers run the same checks, with protected-branch required checks | Q0 |
| TST-018 | Private GitHub validation workflows isolate licensed/restricted runners, data, secrets and runtimes from public PRs and start from reproducible state | Q1 |
| TST-019 | No required acceptance step depends on the user executing a manual test procedure | Q1 |
| TST-020 | A required GitHub Actions gate checks requirements, profiles, evidence, defects and allowed claims before publishing a candidate-linked GitHub Release | Q1 |
| TST-021 | Local checks before upload and CI publication gates exclude private/personal information from code/history, metadata, docs, posts, media, logs and release assets | Q0 |

For Q0, a traceability entry may identify a planned executable test for a future capability, but Q0's own inventory/contract/prototype checks must already execute. At Q1/Q2 a planned test is insufficient: required test evidence must exist for the exact candidate and configuration. A specialist's review of assumptions or a documented scope decision is distinct from asking the user to run tests.

### 4.1 Test layers, drivers and independent oracles

Use CTest for compiled unit/physics tests and a pinned Python test runner for application/adaptor/integration orchestration. Select the exact frameworks at Q0. Tests that compare identical implementation paths are insufficient for physics acceptance: analytical calculations, manufactured solutions, mesh/time refinement, conservation and independent source-tool results provide different evidence.

| Suite | Required automated checks |
|---|---|
| SUITE-CONTRACT | JSON/HDF5 schemas, units/frames, identity maps, deterministic hashes, versions, expression type/cycle errors and independent readers |
| SUITE-PERSIST | Package round trips, archive safety, original bytes, atomic saves, host journals, migrations, backups and dependency invalidation |
| SUITE-PHYSICS | Network/FD/FE residuals, steady/transient references, anisotropy, contacts, nonlinear properties, energy and refinement |
| SUITE-EVENT | Algebraic initialization, prescribed nodes, hysteresis, schedules, event localization/order, checkpoint/restart and failure diagnostics |
| SUITE-RADIATION | Geometry intersections, optical laws, enclosure/escape/reciprocity, fixed statistical ensembles, coupled energy and approximation error |
| SUITE-ENV | Frames, orbit/attitude/articulation, eclipses, solar/albedo/IR/chamber power and temporal/geometric refinement |
| SUITE-EXCHANGE | Syntax/semantic preservation, native IR mappings, source IDs, fidelity reports, STEP-TAS validation and public round-trip cases |
| SUITE-VENDOR | Exact-version TD/SINDA/RadCAD and ESATAN reference runs, changed-model reopen/run, source-native equivalent edits, cross-tool exchange; Q2 FLUINT/legacy additions |
| SUITE-API | Transactions, preview/apply, actor/project idempotency, revisions, concurrency, jobs, cancellation and stale-result guards |
| SUITE-GUI | Unattended FreeCAD commands/editors/selection/undo/save/reopen, visible mappings, host-thread dispatch, result/display assertions and stable-view checks |
| SUITE-MCP | Real stdio client lifecycle, schemas/resources, bounded queries, parity, offline operation, reconnect and application job cancellation |
| SUITE-CAMPAIGN | Variant identity, sweeps, uncertainty/sensitivity replay, synthetic sensor correlation/holdout and report/table provenance |
| SUITE-SECURITY | Publication privacy, outgoing history/metadata/prose/media/artifact checks, malicious/archive/parser corpus, fuzz regressions, imported code inertness, scope/budget enforcement, isolation, secret redaction and no default listener |
| SUITE-PERF | Fixed sparse/large-query workloads, peak memory, UI/cancel latency and million-facet accuracy/scaling curves |
| SUITE-INSTALL | Clean Windows builds/packages, engine without host/Python/vendor solvers, offline host workflow, portable delivery, upgrade/rollback and licenses |
| SUITE-GATE | Traceability and criteria versions, fixture coverage, actual backend, candidate/profile hashes, blocked/flaky cases, defects and published claims |

Each suite's trigger, runner and evidence contract is recorded in [test-suites.csv](test-suites.csv). A suite is an organizational group, not one giant test: individual cases carry requirement/profile IDs so regression selection and failure triage stay specific.

For thermal cases, compare quantities with `abs(x - reference) <= atol + rtol * abs(reference)` and record maximum, RMS, relevant percentile and affected IDs. Use absolute kelvin for relative temperature normalization and declared floors near zero heat flow. Start with the specification's proposed criteria, then freeze their applicable values at Q0. Preserve the 0.1 K/1% initial cross-solver target, event-time criterion, energy criteria and separate deterministic/stochastic radiation policies in case metadata rather than embedding magic constants in scripts.

### 4.2 How unattended vendor and GUI tests work

Create dedicated licensed self-hosted runners for each declared vendor configuration, accessed only by controlled GitHub Actions workflows in the private validation repository described in section 2.1. The runner has a preprovisioned licensed installation and a disposable project/work directory. A supervisor checks prerequisites, creates the fixture copy, invokes documented vendor automation, waits with deadlines, retrieves results, compares them and collects artifacts. Test credentials/licenses stay outside projects and logs. Untrusted public changes cannot directly execute on restricted runners; promote reviewed source/build artifacts by verified candidate hash through a controlled job.

For each round trip, the driver runs this complete chain: verify original hashes → run source baseline → import and inspect fidelity → run FCST natively → export a new derivative → reopen/run derivative in the exact source tool → compare identities/topology/fields/results and unchanged content. Controlled-edit cases also create an equivalent source-native edit automatically. Cross-tool directions use separate manifests and target runners.

If a vendor interface needs an interactive desktop, use a dedicated signed-in automation session with a test supervisor, timeouts and stable selectors. Prefer supported vendor APIs/commands wherever possible. Automating a supported UI does not remove license constraints. If no reliable unattended route exists, record a blocked profile and build the missing driver/path; do not replace it with a request for the user to click through tests or accept a screenshot as numerical evidence.

FreeCAD test jobs launch an isolated instance on the pinned build and use host-side test hooks on the application thread. Command-level tests assert canonical state; UI tests exercise editor widgets, selection/view providers and event-loop responsiveness. A watchdog handles dialogs/hangs and captures crash logs. Run the supported Windows desktop profile; macOS/Linux host work is an optional stretch goal outside the work packages; a headless engine test alone cannot qualify the GUI.

### 4.3 Continuous integration and execution cadence

| Trigger | Automatically executed work | Merge/release effect |
|---|---|---|
| Developer command | Contract/unit tests plus directly affected physics/API cases | Fast feedback using the same fixtures/drivers as CI |
| Each proposed change | Windows build, schema/unit tests, affected integration/analytic cases, public exchange and security regressions | Required checks must pass before merge |
| Integration branch / scheduled run | Full deterministic suites, GUI/CLI/MCP parity, fixed stochastic ensembles, fuzz budgets and relevant vendor profiles | Failure/blocked status is visible and assigned; required coverage remains outstanding |
| Adapter/source-version change | All affected original and controlled-edit round trips plus both applicable cross-tool directions | Requalify exact affected profiles; do not inherit stale evidence |
| Numerical/dependency/compiler change | Analytic/conservation/refinement, source comparisons, stochastic and resource suites affected by the change | New build evidence; changed library identity cannot reuse old pass results silently |
| Release candidate | All gate-required suites, exact profile matrix, clean install/offline/rollback and performance qualification | Gate evaluator blocks incomplete or failing candidates |

GitHub Actions is the selected CI provider. Establish its event triggers, schedules, scoped runner access, required check identities and retention settings during WP-02; this plan does not create a recurring automation in the user's app. Avoid hardware-sensitive performance checks on noisy shared workers: run frozen targets on dedicated reference hardware through controlled workflows and publish variance/raw measurements. Required-check aggregation must validate actual coverage rather than accepting skipped jobs as test evidence.

Retries may collect diagnostic evidence but do not overwrite the original verdict. Any allowed infrastructure-only retry policy is declared in advance and records each attempt/reason. A flaky mandatory test must be repaired or explicitly dispositioned through the defect process; quarantine alone never supplies a passing requirement.

### 4.4 Machine-readable evidence and release evaluation

Each run manifest includes GitHub repository/commit and Actions workflow/run/attempt/job IDs, requirement and test IDs, profile/operation/direction, source/target/backend versions, actual execution mode, source/build hashes, dependency manifest, fixture/snapshot hashes, criteria version, hardware/OS/thread configuration, settings/seeds, start/end state, raw observations, metrics, diagnostics and artifact byte hashes. Local runs record their local driver identity before any later CI association. Use bounded public summaries and controlled restricted artifacts. Preserve failed runs and superseded criteria in authorized storage; any uploaded form also requires TST-021 privacy clearance. Public summaries must not expose private actor identities, local paths, hardware hostnames or raw restricted observations.

The gate evaluator rejects a candidate when any required coverage entry is missing, failed, blocked, stale, based on the wrong configuration, or satisfied only by an external solver where native execution is required. An absent license/runner becomes `blocked`, with a cause and affected profiles. An explicitly non-applicable optional case is recorded with a reason and cannot remove an actual requirement. Objective output states are `passed`, `failed`, `blocked`, `interrupted`, or explicitly `not_applicable`; they are separate from model fidelity statuses.

Evidence for cached unchanged tests can be reused only if the declared test-input dependency closure, candidate build/configuration and criteria match and the gate records the reuse. Release-level clean install, paired compatibility and required performance runs execute against the actual release candidate. Tolerance changes create new assessments and never rewrite historical outcomes. Test collection is itself checked against the expected manifest so zero tests cannot look successful.

## 5. Release checklists executed by the gate driver

| Gate | Automated completion evidence | Additional prerequisites |
|---|---|---|
| Q0 | Acquired-inventory and explicit-disposition completeness, contracts/independent readers, numerical prototype, criteria/hardware records and harness self-checks | Acquired fixture/disposition baseline and native architecture/physics decisions; source runtime/schema closure remains with affected compatibility gates |
| P0 | Complete WP-15 scripted demo across native/host/API/MCP paths and paired synthetic fixtures, with crash/cancel/invalidation checks | Q0 baseline; demo clearly labeled experimental |
| Q1 | Every Q1 requirement and applicable TST requirement, paired TD/ESA profiles, STEP-TAS datasets, changed-model source round trips, both cross-tool directions, native-only solve and clean offline installs | No unaccepted critical qualification-impacting defect; exact tested support matrix and performance dispositions |
| Q2 | All Q1 regression plus every required legacy/advanced/entity/case/operation entry and Q2 native fluid/optical/logic comparisons | No unresolved required native behavior or required source editing/re-export path |

Before a release is declared, the driver generates a coverage table for every claimed configuration and privacy clearance for the exact outgoing release contents/prose. The product owner and engineering leads may review the evidence and any scope/disposition decisions; they do not supply manual test execution in place of it. Product claims are generated from passing coverage and cannot be broadened by editing report prose.

## 6. Staffing, critical paths and estimation

Staff by responsibility: numerical/physics, geometry/radiation, host/API/MCP, TD interoperability, ESA interoperability, and automation/release. These are workstreams, not an assumed headcount. People can cover several roles, but named ownership and equal TD/ESA capacity remain necessary. The test/release owner builds shared runners/gate reporting; feature engineers own their fixtures and tests so testing does not become a final handoff.

Two paths determine Q1 readiness:

1. Fixtures/schema/vendor access → canonical contracts → paired source extraction/re-export → changed-model round trips and both exchange directions.
2. Contracts/oracles/backend decision → durable snapshots/jobs → owned network/radiation → FD/FE/environments/campaigns → unattended platform qualification.

FreeCAD and MCP implementations join both paths at P0 and Q1. A short numerical demo does not reduce vendor compatibility work. Advanced Q2 design starts with the inventory, and unknown user logic or two-phase behavior may dominate the later schedule.

Produce calendar estimates after WP-01 through WP-04 establish corpus size, access and measured implementation effort. Estimate each work package as: concrete feature/element/dialect count + fixture/automation work + integration/diagnostics + requalification/packaging. Record optimistic/likely/pessimistic engineering effort, available owners and external-access lead times. Recompute the dependency graph's critical path when scope changes. Do not turn this sequence into unsupported fixed delivery dates or treat automation as optional contingency work.

### 6.1 Main risks and planned resolution

| Risk | Resolve early through | What blocks completion |
|---|---|---|
| Missing proprietary semantics/dependencies | Completed WP-01 gap map and WP-08/WP-09 paired extraction probes | Required unknown fields/procedures/cases remain unassigned |
| No unattended vendor route/license | Version-specific runner feasibility probe | Required source reopen/run cannot execute automatically |
| Geometry attachment drift | Stable mapping contract and split/merge tests | Silent material/heater reassignment or ambiguous mappings accepted as valid |
| Numerical backend insufficient | Q0 DAE/events/sparse/deployment prototype | Wrong initialization/events, failed conservation or unusable supported builds |
| Radiation memory/statistical errors | Sparse/streamed design and predeclared ensemble tests | Dense-only scaling or selective reruns used to claim success |
| Host/document recovery faults | Journaled commits and kill-point tests | False clean state, mismatched revisions or partial results shown as final |
| Advanced native-feature uncertainty | Feature/equation mapping and Q2 prototypes during Q0/Q1 | Required fluid/optical/logic feature remains external-only |
| Misleading release evidence | Automated gate/provenance checks | Stale, substituted, missing, blocked or manually asserted test outcomes |

## 7. First implementation backlog and developer commands

The first tickets should produce reviewable, automatically checked artifacts in the order below. Begin native foundation work immediately; compatibility acquisition proceeds alongside it and does not hold native implementation:

1. Implement the publication-privacy preflight before any push/post, then establish the GitHub repository/backlog/protection settings and create the CMake/Python skeleton, GitHub Actions planning and Windows build jobs, engine-only smoke test and build-info manifests.
2. Publish identity/units, minimal native thermal snapshot, `.fcst` storage, result and operation/worker contracts; add C++/Python conformance/hash fixtures using synthetic models authored from scratch.
3. Start the compatibility inventory and acquire one runnable TD and one ESA source fixture with dependencies/results; implement an inventory checker. Continue native work while access is pending; record missing compatibility prerequisites explicitly.
4. Create analytic one/two-node oracles and an immutable criteria register; add structured test/evidence output and missing-test detection.
5. Run the C++ nonlinear/algebraic/event/sparse deployment prototype and record the numerical decision.
6. Implement atomic packages/revisions and model-authoring operations with durable retry/conflict tests.
7. Implement worker submit/progress/cancel/publication and crash/restart/stale-result tests.
8. As soon as native kernels are available, execute create→save→close/reopen→edit→steady/transient solve→persist/reopen results with vendor software and adapters absent. In the compatibility work, prove paired source extraction→canonical→new-source export/reopen on the limited acquired fixtures; keep profile status unqualified until full coverage passes.
9. Add native thermal/radiation minimal kernels and scripted FreeCAD/MCP construction/visualization, then execute P0.
10. Expand according to WP-16 through WP-21, always landing executable fixtures/oracles and evidence collection with each feature.

The following is the proposed command contract to implement; these product commands do **not** exist yet:

```text
cmake --preset <pinned-platform-debug-or-release>
cmake --build --preset <pinned-platform-debug-or-release>
ctest --preset <pinned-platform-test-profile> --output-on-failure
python -m fcst_tests run --tier fast --profile <configuration>
python -m fcst_tests run --suite vendor --profile <exact-vendor-configuration>
python -m fcst_tests qualify --gate P0 --candidate <build-manifest>
python -m fcst_tests qualify --gate Q1 --candidate <build-manifest>
python -m fcst_tests qualify --gate Q2 --candidate <build-manifest>
```

Today, the planning package itself can be checked without extra dependencies:

```text
python plans/tools/validate_plan.py
```

That validator checks requirement/test traceability, work-package dependencies, suites and planning-file links. It does not test a thermal product. The existing specification validator additionally needs `jsonschema`; product qualification will require the actual implementation, fixtures and licensed runner environments described above.
