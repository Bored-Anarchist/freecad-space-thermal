# FreeCAD Space Thermal: implementation and build plan

Plan revision 1.7, 29 October 2026. Based on specification FCST-SYS-SPEC-001 revision 0.9 and the user's additional requirements for unattended testing, GitHub project delivery, removal of private/personal information before anything is put online, explicit independence of native model creation, files and solving, assessment of FreeCAD FEM reuse, and an inserted WP-05.5 foundation reconciliation package.

This is an implementation plan, not evidence of implemented physics or file compatibility. The workspace contains the specification, 121 registered requirements, 12 proposed compatibility profiles, three draft JSON schemas and two schema examples. WP-02 now adds a native worker/application skeleton, local/CI verification and publication-privacy preflight; it implements no thermal solving or file compatibility. [WP-02 evidence](evidence/WP-02.json) records completed foundation acceptance and remaining Q0/product obligations. The specification remains the design baseline; the automated-test requirements below add delivery obligations without relaxing its acceptance criteria.

The [delivery scope](delivery-scope.json) is Windows-only for Q0/P0/Q1/Q2. WP-01 is Complete at the acquired baseline; licensed/source/schema qualification remains with later packages. macOS and Linux configurations are optional stretch goals outside all work packages, committed milestones and release gates; see [stretch goals](stretch-goals.md). FCST remains a FreeCAD add-on/workbench with a standalone engine, not a modified FreeCAD build.

Read this plan alongside the [specification](../spec/FreeCAD-Space-Thermal-Specification.md), [requirements](../spec/requirements.csv), [compatibility profiles](../spec/compatibility-profiles.csv), and [source register](../spec/sources.md). Execution records are provided by the [work-package register](work-packages.csv), [automated-test requirements](automated-test-requirements.csv), [test-suite register](test-suites.csv), [compatibility test plan](compatibility-test-plan.csv), and [requirement traceability](requirement-traceability.csv).

## Delivery approach

Build the product around a host-independent C++20 thermal engine and a versioned Python application service. FreeCAD, the CLI, and MCP use the same operations. Independent file adapters extract and re-export TD/SINDA and ESATAN source models; optional vendor harnesses produce external comparison evidence only. Production thermal solving belongs to FCST. Preserve the original files, stable identities, units, and model semantics from the first import implementation.

The native workflow is independently required: create a model from an empty project, assign nodes/properties/conductors/loads/cases, save an FCST `.fcst` file, reopen and edit it, run owned steady/transient solves, and inspect results without a vendor file, Thermal Desktop/SINDA/FLUINT, ESATAN, vendor licenses or vendor services. WP-01 scopes backward-compatibility coverage; native WP-02/WP-03/WP-04 slices start with public synthetic fixtures and analytic oracles while vendor access is acquired. Complete Q0 and compatibility claims still require their specified evidence; missing vendor access must not stop native core development.

Executable acceptance for ARC-001/ARC-003/ARC-009 and TST-004/TST-009/TST-014: in an isolated offline installation with vendor software and adapters absent, automatically create a geometry-free two-node model, save `.fcst`, close/reopen it, verify its canonical model hash, edit a load, solve steady and transient cases with `fcst_native`, and compare temperatures, heat flows and energy balance with independent analytic oracles. Verify result persistence and reopen. SUITE-INSTALL, SUITE-PERSIST and SUITE-PHYSICS own this scenario; a vendor-backed run cannot satisfy it. This is planned acceptance, not a completed test.

The first demonstration is a saved two-node/two-surface model with conduction, radiation, a transient solve, FreeCAD visualization, API/MCP access, and paired synthetic source fixtures. It is P0, an experimental vertical slice. Q1 is substantially larger: every Q1 requirement, both source ecosystems, required STEP-TAS content, changed-model round trips, bidirectional exchange, correlation, automation, installation, and qualification. Q2 closes the remaining required legacy inventory and advanced native behavior.

Testing is part of the product build. Engineers implement fixtures, test drivers, oracles, and runners with each feature. The user is not the test operator. Human review may approve intended physics, licensed fixture access, or proposed tolerances; creating models, launching tools, comparing outputs, collecting evidence, and deciding objective pass/fail run automatically.

GitHub is the required development and delivery platform: the authoritative source repository, Issues and Projects backlog, pull requests, GitHub Actions CI, and Releases. GitHub configuration and workflow implementation belong to WP-02; evidence-backed release publishing belongs to WP-19/WP-21. GitHub is a development dependency; installed native modeling and solving retain the specification's offline and account-free behavior.

Online publication must exclude private/personal information. This covers code and documentation as well as commit metadata, issues/PRs/comments/posts, screenshots, logs, evidence and release assets. The standing [repository instructions](../AGENTS.md) preserve this user requirement for later implementation and publication work. TST-021 makes its automated checks a required WP-02 deliverable before the first online publication.

## 1. Boundaries and decisions to establish first

The 29 October independent TD exchange correction also extends TST-021.
Execute `tests/test_independent_dwg.py` and `tools/check_td.py` in unattended
Windows verification, plus `tests/test_native_dwg.py` and `tests/test_sinda_writer.py`.
The corrected native bridge preserves ordered duplicate decoder fields and checks
complete opaque bit payloads and every unrequested logical field without echoing
private values. A separate required CI job builds the locked GPL component and
rewrites/reopens an owned fixture; candidate/source-bound bounded evidence is
required by the final handoff. Typed RcNode v22/RcConductor v22/RcHeatLoad v17 and property readers now
support guarded source-field edits and source-free constant-network DWG export.
Execute `tests/test_td_payloads.py` and `tests/test_td_properties.py`; the required
native job independently reopens all generated fields/references and compressed
scalar edits while preserving every unrequested source field. Closed canonical network import, portable source restoration and verified native
scalar exports now run without other feature packages. Add
`tests/test_td_native_model.py`, `tests/test_td_property_model.py`,
`tests/test_sinda_arrays.py` and `tests/test_td_geometry.py`; the frozen native
job exercises the real vendor-denied CLI for package import, native edits, fresh
reopen, property-library round trips, original property-document import and native
property-source edits. One-dimensional property tables are typed and guarded
without enabling unimplemented variable-property physics. Full-model semantics
remain incomplete. Scan the exact owned codecs/writers, synthetic filer fixtures,
CLI sources, preservation patch and source-hash locks alongside probe/audit sources, synthetic
tests, pinned dependency metadata, updated scope documents and bounded summaries
before publication. Policy v5 scans native headers/patches as text, retains all
sensitive patterns/budgets and rejects binary disguises. Preserve GPL attribution
and scan exact build configuration, patch pre/post hashes and provenance alongside
the source. WP-09 independent ESATAN plans/fixtures/evidence use the same TST-021
rule; documentation does not qualify an unimplemented converter.
WP-09 now applies TST-021 to exact owned codecs, CLI, acquisition/profile locks,
synthetic D-deck/TMD/XML fixtures, bounded `esatan.json` summaries and final GitHub
prose. Both Windows drivers execute the frozen unattended cases and clear the
final summary before upload. Before publication, run the standard-library security
gate plus staged, outgoing-history and approved-identity preflight. The acquired
XML was recovered from its original public GitLab mirror with exact LFS hash and
length verification; retain that payload, baseline pointer, decoded inventories,
result arrays and raw acquisition/test logs locally. Recovery adds no permission
to publish engineering data or claim full native-project/campaign qualification.
Raw drawings, companion files, decoded JSON, runtime binaries
and raw logs remain local; the original corpus remains unchanged. This adds no
permission to redistribute third-party models or proprietary libraries.

Publication history checks scan every commit's metadata and identities and every
tree's entry modes. Identical historical `(path, mode, blob)` versions share one
content scan within that invocation; new paths, modes and changed bytes are
rechecked. The TST-021 history regressions prove metadata binding and path/mode
reclassification while retaining all existing privacy patterns and budgets.

| Area | Implementation direction | Decision or evidence required |
|---|---|---|
| Project development | GitHub repository, Issues/Projects, pull requests, GitHub Actions and Releases | Repository owner/URL, visibility, permissions, supported protection features and runner/evidence access established at Q0 |
| Numerical implementation | C++20, CMake, independent engine executable/library | Q0 compiler, ABI, build flags, numerical-backend prototype and platform results |
| Python integration | Application operations, FreeCAD host adapter, CLI, MCP, orchestration/reporting | Separate host and standalone Python dependency environments; no opportunistic host-Python replacement |
| Numerical libraries | Evaluate SUNDIALS and sparse solvers behind FCST interfaces; PETSc only if justified | Algebraic initialization, stiff integration, events, sparse scaling, licenses and clean Windows builds |
| Radiation | FCST estimators/optical laws with CPU intersection backend; evaluate Embree | Error/convergence evidence, deterministic seed policy and deployable dependency build |
| Geometry | Obtain mesh/geometry through a FreeCAD adapter; keep engine network-only operation possible | Supported primitives/elements, pinned FreeCAD/OCCT combination and attachment rules |
| FreeCAD FEM reuse | Prefer compatible mesh, selection/assignment and result APIs behind the host adapter; retain the owned engine | WP-13/WP-16 component assessment with pinned source/API/license evidence and automated acceptance before replacement or adoption |
| Storage | Documented ZIP/directory `.fcst`, JSON metadata and versioned HDF5 arrays | Full model/results schemas, canonical hashing, atomic-save/recovery protocol |
| TD/SINDA and ESATAN exchange | Independent native-project, companion, network and result readers/writers with owned versioned semantic codecs; vendor APIs only for optional external reference work | Offline vendor-absent first import/edit/new-model export/reopen, complete semantic/dependency coverage, untouched-field preservation and deployment/license evidence |
| Platform qualification | Windows 11 x64 and official pinned FreeCAD 1.1.4; macOS/Linux are uncommitted stretch goals outside work packages | Qualify actual combinations; do not infer support from version names |
| MCP | Local stdio over the shared application API | Verify and pin a released protocol/SDK and named clients at Q0; separately test legacy profiles |
| Optional work | In-process pybind11, GPU acceleration, Rust comparisons, network MCP, Fluent comparisons | Add only when justified; none is necessary for the initial worker architecture |

These are implementation directions from the baseline, not a claim that the candidate dependency combination has already been built. Exact versions and vendor API calls must be established from the acquired documentation and measured prototypes. Do not choose an integration library solely because it is listed in the specification.

### 1.1 FreeCAD FEM reuse assessment

The [FEM reuse decision](../docs/decisions/0003-freecad-fem-reuse.md) supplies the candidate matrix, recommended dispositions, owner roles, timing and six planned automated acceptance IDs. Current implementation uses basic FreeCAD/Part APIs only; no FEM integration or adopted FEM source is claimed. Before overlapping WP-13 host implementation, assess analysis objects, mesh access/generation, selection/material/load tools, result pipelines, fixtures/test patterns and optional CalculiX/Elmer conduction references. Complete the mesh-specific selection before WP-16 implementation. Prefer compatible APIs and thin adapters; document the failed requirement, measured limitation or actual license incompatibility before replacing existing functionality. Preserve required attribution. Engine independence alone does not justify replacing host infrastructure.

Record exact upstream paths/revision/hashes, API probes on FreeCAD 1.1.4/cp311, dependency and per-file license dispositions, boundary/mapping rules, deployment cost and prototype evidence in the affected GitHub implementation issues/PRs. [WP-05.5](WP-05.5-Foundation-Reconciliation.md), displayed as WP-5.5, now owns the missing WP-01 through WP-05 foundation handoff: component inventory, representative API/mesher probes, versioned mesh/field contracts, independent fixtures and extended persistence. It completes at P0 and precedes dependent acceptance in WP-06/WP-07/WP-13/WP-16. Existing package IDs, completed baseline evidence and Windows-only scope remain intact. WP-13 retains full host workflow acceptance; WP-16 retains production spatial/mesher qualification at Q1; WP-19 checks complete evidence. FEM-REUSE-001 through FEM-REUSE-006 remain later feature cases; WP-05.5's separate planned acceptance cases cannot close them. TST-022 binds the foundation handoff; TST-008/TST-014 bind host behavior and execution identity. Missing selected external references block their comparison profile without substituting for native acceptance or stopping unrelated native development.

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
sidecars/opentd/                 Optional external reference harness only
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
9. **Continuously reduce feedback time (TST-017).** Treat CI runtime as an ongoing engineering constraint for every feature and verification change. Inspect the passing aggregate's `ci-performance.json` and GitHub critical path; target the largest measured cost, state an experiment, and verify the result unattended. Preserve all coverage, statistical/scaling workloads, numerical criteria, assertions and both Windows configurations. Compare equivalent cold/warm states and toolchains, account for setup/queue time and runner minutes, and repeat noisy comparisons when needed. Investigate increases over 20% and at least 60 seconds and record their disposition. Keep a source/run-bound baseline and sanitized experiment ledger in [the CI performance guide](../docs/ci-performance.md); refresh baselines deliberately after passing evidence, never to hide regressions. The working target is full warm Foundation feedback within ten minutes, without claiming reference-hardware product qualification.

**CI improvement checkpoint, 1 November 2026.** The implementation preserves all
required numerical/statistical/scaling, host, package and both Windows checks.
The original full CI took 19m 44s; passing warm optimized runs range from 7m 51s
to 11m 03s, with substantial shared-runner variation. The latest four-worker trial,
[run 41363285933](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41363285933)
(`25c406c`), passed all 393 records per configuration in 10m 28s. Retained changes
remove repeated unit/native execution, derivative allocations, checkpoint hashing,
BVH construction work and per-ray allocations. Bounded row scratch replaces the
intermediate per-facet cache, saving about 56 MB at one million facets with exact
ray outputs. Package/native compilation uses explicit bounded MSVC budgets.

An isolated local OCCT four-versus-two compiler pair passed fresh full builds,
installs and consumers: 274.361s versus 339.676s (19.2% shorter), with higher CPU
and peak committed memory. Retain four with that tradeoff recorded; exclude the
earlier overlapped local pair. The opt-in single-runner calibration/ABBA workflow settled Debug's budget:
[run 41367494887](https://github.com/Bored-Anarchist/freecad-space-thermal/actions/runs/41367494887)
passed five complete attempts; four-worker median acceptance was 347.820s versus
321.125s with three, consuming about 15.9% more CPU. Return Debug to three;
Release remains two and full qualification serial. Repeat only with a new
measurement hypothesis, following
[the ongoing experiment record](../docs/ci-performance.md#paired-debug-worker-measurement).
It repeats every case five times, preserves candidate/source/unit-receipt checks,
uses bounded deadlines and publishes only individually cleared JSON. The expanded
inventory has 394 records per configuration. Benchmark summaries are explicitly
ineligible for ordinary timing baseline refreshes. After the budget decision,
refresh the baseline deliberately from a complete passing ordinary warm run.
Continue measuring the largest cost, recording keep/revert decisions and failed
or neutral experiments; the corrected local PCH prototype passed but was slower with higher memory and
is not adopted.

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

Build/verification resource evidence adds only allowlisted numeric CPU seconds,
peak process/job committed bytes, total process count and logical CPU count for
fixed command stages and the six package phases.
Unattended regressions verify inclusion of terminated descendants, timeout cleanup
of the owned process tree, nested worker containment, and rejection of identity
fields, missing phases,
nonfinite values and inconsistent peaks. Execute the complete unit suite, pinned
package build/install/consumer probes and exact-source/report/history preflights.
Profile `windows-job-v2` disables external MSBuild worker reuse in explicit and
inherited environments so accounting and per-stage temp isolation do not depend
on a pre-existing process pool. Keep V1/V2 measurements distinct. The first overlapped local OCCT pair remains inconclusive; the later isolated
pair and its CPU/memory tradeoffs are recorded in the performance guide. The bounded row-cache candidate preserves
exact ray results while replacing per-facet retained storage with accounted fixed
scratch; retain its passing hosted confirmation and every existing scaling repetition.
This extends TST-021 without uploading process identities, paths, environment or
raw logs and without relaxing build, numerical or memory acceptance. Keep the paired OCCT resource baseline when reviewing its four-compiler budget.
The cache validator rejects dangling links/reparse points using metadata even
when the destination target is missing. Paired-worker artifacts clear the five
exact verification JSON files and summary immediately before upload; raw logs
remain local. Missing clearance or unsafe resource metadata fails unattended.

Continued CI improvement adds a source/run-bound timing baseline, frozen
fixture/statistical workload digest, relative stage starts and dependency
generator/phase timings. TST-021 clears the exact scalar `ci-performance.json`
alongside the final handoff before upload. Its generator rejects stale candidates,
lost/missing/failed/duplicate cases, changed frozen workloads, substituted package
sources and invalid timings. Cost estimates affect scheduling order only. Execute
the expanded `tests/test_ci_performance.py`, native flat-scan BVH regression and
both complete acceptance configurations. Preserve original fixed ensembles,
independent scaling construction repetitions and strict Debug/Release checks.
Raw profiles, environment values, build trees and binaries remain local; this
adds no cache or general-scanner exception. Record positive and neutral
experiments in sanitized PR evidence and the ongoing performance guide.

CI acceleration preserves both Windows configurations and every existing native,
reference, radiation ensemble/scaling, host and MCP case. TST-021 now also covers
the [public download cache](../docs/ci-performance.md): cache-specific clearance
admits only byte-identical distributions from reviewed public SHA-256 locks,
with pin/name/size/path/link checks before reuse and immediately before upload.
Generated binaries/debug paths, build trees, raw logs, model inputs and pass
verdicts remain excluded. General scanner patterns and binary rejection remain
unchanged. Execute `tests/test_ci_performance.py`, the complete unit owner and
Publication security scope; reject corrupt/unlisted cache files, stale or
incomplete candidate/source-bound unit receipts, native inventory substitution,
unsafe cache paths and upload without clearance. Bounded acceptance workers
use isolated temporary directories and serialize mutable reference preparation;
full qualification remains serial. Scan exact changed sources, workflow/policy,
unit receipts, plan/register/prose and outgoing history before publication.

WP-12 extends TST-021 to exact native BVH/sampling/radiosity/coupling sources,
optical declarations, synthetic plate/steady fixtures, frozen ensemble quantities,
statistical driver, bounded `radiation.json`, scaling curves and final GitHub
prose. Both Windows drivers execute `tools/check_radiation.py`; CI preflights the
final report before upload and the handoff checks exact candidate/source hashes,
all seed/quantity/sample records and every scaling repetition. Scan staged bytes,
outgoing history and approved identities before push. Raw meshes, per-process
observations, binaries/debug files, logs and engineering originals stay local;
no new scanner exception or vendor compatibility qualification is introduced.


WP-11.1 through WP-11.10 run `tools/check_thermal.py` and the native CTest acceptance on owned
synthetic fixtures. Scan the exact C++ API/adapter/generated schema, test/driver
sources, bounded `thermal.json` reports and final GitHub prose before publication.
Both Windows jobs clear `thermal.json` before upload; the aggregate rejects stale
source hashes, incomplete cases or solver qualification claims. TST-021 retains
staged/outgoing-history and approved author/committer checks. Raw native inputs,
source identities, property observations, compiler logs, executable/debug files
and restricted engineering originals stay in authorized local storage. WP-11.3
through WP-11.5 additionally scan exact residual/Jacobian/backend sources, owned
callback/DAE/conservation fixtures, binary-hash/build-bound summaries and final PR
text. No callback source inputs, radiation geometry, native binaries or raw backend
exception text are uploaded by this implementation.

WP-11.6 also scans exact sparse-LU/Newton/steady-CLI sources, owned analytic and
manufactured steady fixtures, source/build/four-binary-bound `thermal.json` and
the revised PR text before upload. Native test/CLI failures retain bounded codes;
private source text, raw result arrays, model originals, binaries, debug files and
compiler/backend logs remain in authorized local storage. TST-021's staged and
outgoing-history/identity checks apply to every steady implementation commit.

WP-11.7 through WP-11.10 extend the same executable TST-021 boundary to exact
native transient/event/checkpoint/result/profiling sources, owned synthetic
analytic/stiff/DAE/heater/schedule/restart fixtures, the strict execution adapter,
source/build/five-binary-bound `thermal.json`, capability records and final PR
prose. Run native CTest, `tools/check_thermal.py`, both Windows verification
presets and planted privacy regressions unattended. Scan actual staged bytes,
outgoing history/approved metadata and each final generated report/text before
upload. Raw trajectories, serialized operational checkpoints, source identities,
original engineering models, native executables/debug files and compiler/backend
logs stay local; public evidence contains only bounded IDs, verdicts, counts,
timing metrics and hashes. Native execution mode cannot be substituted by an
external reference result. No privacy suppression or restricted-input upload is
introduced.

WP-11 qualification closure adds exact-byte scans of the versioned requirement
coverage/oracle register, owned SINDA/ESATAN source-literal fixtures, event-step
refinement and representative compiled-network profiling, the captured-result
comparison tool, its tamper/mode/identity regressions and report-schema-five
`thermal.json` summaries. Scan final PR prose and all outgoing history/approved
identities before push. Raw vendor decks, printed/TMD result arrays, operational
receipts, reviewer identities, license/configuration data and native binaries stay
local. A comparison receipt or synthetic reference test cannot grant licensed
vendor/Q1 qualification. TST-021 preserves that boundary in executable tests;
there is no new publication exception.

WP-11 independent-reference qualification extends TST-021 to the exact IDA and
Radau literal-equation programs, native benchmark adapter, Pycanha trial,
source/runtime/wheel pins, frozen numerical criteria and evidence-tamper tests.
Both Windows presets require `tools/check_thermal_references.py` alongside the
native suite. Clear each final `thermal-references.json`, updated plan/evidence
and final PR text before upload; scan actual staged bytes, outgoing history and
approved metadata before push. Portable reference runtimes, third-party sources
and notices, binaries, raw trajectories and compiler/backend logs remain local.
Only bounded case/verdict/error/hash receipts are public. Reference execution
cannot replace native acceptance or grant licensed vendor compatibility/Q1.

Policy v6 supports the exact public GitHub service committer generated by GitHub
merges. This is separate from approved maintainer authors/taggers, whose list is
unchanged. TST-021 executes the exact-role and real-history regression in
`tests/test_privacy.py`, the full standard-library security suite and actual
staged/outgoing-history/final-text preflight. Other service names/emails and
author/tagger use reject; prior clearances are invalidated by the policy hash.

Apply this rule to every outgoing online destination, including private repositories and restricted hosted artifacts. Access controls do not replace data minimization. Work with authorized local originals for engineering qualification and produce separate sanitized copies for material that will be published.

1. **Classify outgoing content.** Treat contact details, personal account names/paths, machine and internal-network identifiers, credentials, license material, private correspondence, customer/project identifiers and restricted models/results as private unless explicitly approved for the intended destination. Use synthetic public fixtures, relative paths and approved public maintainer identities. Preserve required third-party license notices and public attribution.
2. **Check before the first push.** WP-02 installs a local publication driver and version-controlled hook setup that checks staged files, outgoing commit history and author metadata before network transfer. Configure a privacy-preserving author email and approved public identity. A `.gitignore` file or a CI scan after upload cannot sanitize previously staged/history content; the driver must inspect the actual outgoing material.
3. **Sanitize generated outputs.** Remove personal usernames/absolute home paths from tracebacks, compiler/debug data, source maps and reports; sanitize document/image metadata, screenshot backgrounds, labels, paths and embedded content. Check packages, archives and bundled examples recursively with size/type limits. Keep exact original hashes and raw restricted evidence in authorized storage and use safe identifiers in public summaries; redaction must not fabricate engineering results.
4. **Gate prose and media publication.** Run the same preflight against rendered docs, issue/PR/comment/discussion bodies, release notes and other project posts before calling upload/post tools. Resolve screenshots and unsupported file types through a suitable inspection/sanitization path; an unchecked binary is not automatically safe. Any sensitive finding holds the affected upload until resolved or explicitly authorized for that destination.
5. **Automate checks and prove they fail correctly.** Add credential detection and project-specific privacy patterns, metadata/path inspection and an exact-output scan to local/GitHub Actions drivers. Use synthetic planted cases to prove detection of personal paths, email/contact data, credentials, commit metadata and restricted fixture references, including nested archives/generated outputs. Safe examples must also pass. Any justified public-identity/attribution exception is narrowly scoped and versioned; broad suppression of a private value is not a solution.
6. **Keep evidence sanitized.** Scanner failures identify category and safe relative location without echoing matched secrets or private values. Bind the public clearance report to the exact outgoing byte hashes and policy version. Recheck generated changes after sanitization and before upload; release publication requires both engineering qualification and privacy clearance.
7. **Handle existing exposure explicitly.** Stop further affected publication, revoke/rotate exposed credentials through the appropriate owner and remove exposed artifacts where authorized. Coordinate history rewrites and other destructive cleanup; changing the current file does not remove older copies. Preserve restricted incident evidence without reposting the sensitive contents.

WP-14 extends TST-021 to the exact typed MCP gateway, closed schemas, launcher
policy, durable native job adapter, official protocol schema/license and SDK
wheel lock, owned attack/parity fixtures, bounded `mcp.json` and final GitHub
prose. Run `tests/test_mcp.py`, `tools/check_mcp.py`, the full Windows matrix and
privacy regressions unattended. Scan actual staged bytes, outgoing history and
approved identities before push; CI clears the exact generated report before
upload. Launch configurations, operational SQLite/audit databases, imported
packages, result arrays, native binaries, screenshots and raw process/compiler
logs stay local. Original engineering bytes remain preserved. Artifact UUIDs,
client metadata and imported text cannot grant export authority or qualification.

WP-02 implements TST-021 through `tools/publication_preflight.py`, versioned policy and pre-commit/pre-push hooks. The driver inspects actual staged blobs, every reachable commit tree, complete commit objects, author/committer/tagger identities, outgoing prose and bounded nested archives. It rejects unsupported binaries/media, links, archive traversal, encrypted/unreadable inputs and inspection limits; safe reports contain opaque location IDs and categories without matched values. Clearance binds exact outgoing byte hashes and policy version/hash. Synthetic adversarial tests include deleted-history secrets, staged/worktree differences, personal paths/contact data, credentials, private identifier hashes, nested generated outputs and safe negative cases. CI repeats the same checks; direct API publication scans its exact payload before posting. See [developer commands and limitations](../docs/development.md). Restricted originals remain local; unsupported media needs an appropriate sanitization/inspection path before publication, and pattern detection does not infer every confidential engineering meaning.

WP-03 extends that executable publication boundary to the generated v1 schemas, shared types, embedded native schema table and synthetic JSON fixtures. The fast driver generates a bounded contract-conformance report with IDs and fixture hashes; both Windows jobs scan that exact report with verification/build metadata before upload. Local staged/outgoing-history and final prose scans remain mandatory. Native executables, raw compiler/reader logs, HDF5 payloads and acquired engineering originals remain local; the contract bundle does not authorize their publication. TST-021 acceptance remains `python tools/check_security.py` plus actual outgoing preflight, without new suppressions or private fixture contents.

WP-04 adds an exact pre-upload scan of each `numerical.json` summary. Its inputs are synthetic SI fixtures and independently frozen criteria; public evidence contains bounded metrics, source/backend/artifact hashes and public hardware/toolchain attributes. Raw per-attempt observations, compiler logs, executable/DLL files and restricted originals remain local. Sealed attempt manifests preserve failed/interrupted/superseded results. TST-021 acceptance executes the planted regressions plus staged/outgoing-history/identity and final prose/evidence scans before push; CI scans the final generated numerical summary before upload. No scanner suppression or authorization to publish engineering originals is added.

WP-05 adds the exact generated `persistence.json` summary to both Windows CI pre-upload scans. Synthetic package/migration fixtures, typed store/array sources, completion evidence and final PR prose are checked with the staged/outgoing-history/approved-identity preflight before publication. Generated `.fcst`, HDF5, SQLite/WAL and synthetic host files plus raw crash/array diagnostics stay local. Imported engineering originals remain unchanged in their authorized storage and are never uploaded by this workflow. TST-021 acceptance includes planted privacy regressions and exact report/prose scans; neither an inert-source role nor successful persistence validation grants publication clearance.

WP-07 extends TST-021 to the exact `exchange.json` acceptance summary, SDK sources,
fidelity schema, synthetic converter fixture and final publication prose. Both
Windows workflows clear that report before upload; it contains only case IDs,
verdicts, candidate and public input hashes. Original decks, dependency/result
bytes, packages, per-source fidelity inventories, converter logs and local failure
traces remain local until separately reviewed and cleared. `python -S
tools/check_security.py`, staged/outgoing-history and approved-identity scans, plus
exact generated-report/PR-prose preflight remain executable acceptance. Tool
authorization is recorded by hash without exposing actor identity or installed paths.

WP-08 extends TST-021 to the exact `td.json` public acceptance summary, managed
sidecar sources, SINDA/TD fixtures, bounded offline API receipts and final GitHub
prose. Policy v4 adds `.cs` to text inspection with the same sensitive patterns,
binary rejection and budgets. Both Windows jobs clear `td.json` before upload;
original projects/decks/property databases/results, private runner profiles,
compiled sidecars/vendor DLLs and raw logs stay local. Required staged-byte and
outgoing-history scans may run separately; neither scope may be skipped. Q1 holds
are recorded explicitly and are not replaced with parser or external-run success.
The independent property-law slice adds owned synthetic orthotropic, variable
table/grid, two-band optical and composite-definition fixtures. TST-021 acceptance
includes their unattended unit cases, fresh-process vendor-free CLI roundtrips,
and exact `td.json`/`dwg-backend.json` report scans. Original property laws, decoded
engineering JSON, frame companions, edited files and raw research logs stay local.
Canonical variable/composite/spectral bindings and complete DWG thermal geometry
remain WP-08 implementation work; WP-09/WP-11/WP-12 comparisons are later
qualification obligations, not prerequisites for implementing those codecs.
Complete RcRectangle v7/attribute-marker-54 and RcFdBrick v21 readers/writers now
consume data, text and handles, including subdivision, mesh, face and advection
records. TST-021 executes owned geometry mutation/stream/identity regressions and
native source-free generation, compressed parameter edits and fresh reopen. Scan
the exact codecs, bridge, synthetic fixtures and `td.json`/`dwg-backend.json`, plus
staged bytes, outgoing history/identity and final publication text. Original
geometry, decoded fields, source handles, generated containers and raw research/
build/CLI diagnostics remain local. Structural decoding cannot qualify physical
geometry or mesh regeneration; original dynamic geometry edits remain held.

FEM reuse work applies TST-021 to exact outgoing decision/assessment text, upstream attribution/license manifests, synthetic fixtures, bounded host/mesh/comparison reports and final issue/PR prose. Run `python -S tools/check_security.py` and `python tools/publication_preflight.py --staged --revision HEAD` before commit/push; scan each final generated report or post with `--file` before upload. Generated FreeCAD documents, raw solver decks, screenshots, mesh/result containers and logs stay local unless separately sanitized and cleared. Use synthetic inputs for public tests, preserve authorized originals unchanged, and do not weaken privacy policy to admit upstream examples or generated diagnostics.

The WP-04/WP-05 verification audit adds synthetic truncation, residual, authority, original-corruption, dependency/result-binding, save/host-race and growing-file regressions. Its [decision record](../docs/decisions/0002-wp04-wp05-verification.md) documents corrected behavior and executable acceptance. New sealed numerical attempts and bounded audit summaries supplement the retained original baseline. Exact source/evidence/prose and generated report scans precede upload; raw inputs, databases, binary containers and diagnostics remain local.

WP-05.5 extends TST-021 to the exact reuse/license inventory, versioned field/mesh contracts, synthetic spatial fixtures, API/mesher/host probes, bounded handoff reports and final GitHub issue/project/PR text. Run planted privacy regressions and actual staged/history/identity/file preflight before publication; CI scans each final generated report before upload. Preserve upstream notices and original engineering bytes. Raw example/host/mesh/result containers, screenshots, operational databases and logs remain local until separately sanitized and cleared. Any scanner batching/cache optimization must retain every commit's metadata and path/mode/type/policy context, including identical blobs in unsafe locations and deleted-history findings.

WP-06 extends TST-021 to the exact worker/lifecycle sources, synthetic protocol peer, CLI, acceptance register and bounded `jobs.json` report. Both Windows drivers run `tests/test_jobs.py` and `tools/check_jobs.py`; CI scans the final lifecycle report before artifact upload. Before pushing, scan all staged blobs and outgoing history/approved author metadata, then independently scan final GitHub prose and generated evidence. Public reports include only case IDs, verdicts and source/build hashes. Actor identities, snapshots, checkpoint state, operational SQLite/WAL files, native binaries, HDF5 results and raw process logs stay local. Portable result provenance omits actor identity but still requires separate exact-byte clearance before publication. See [job contract and executable acceptance](../docs/jobs.md); no privacy exceptions are introduced.

## 3. Build sequence and dependencies

Each package below specifies concrete tasks and completion evidence. Its register row identifies a lead role, prerequisites, expected outputs, and automated suites. Dependencies describe interface availability; packages can deliver a minimal slice before their complete Q1 capability. Every completion reference must point to an immutable test artifact, not a checklist marked by hand.

| Stage | Packages | Result |
|---|---|---|
| Establish Q0 | WP-01 through WP-04, plus native feasibility probes | Inventory, contracts, reference environment, criteria, automated harness and numerical decision |
| Build foundations | WP-05 through WP-10 | Durable operations/jobs and paired import/export paths |
| Reconcile foundation handoff | WP-05.5 after WP-01 through WP-05 | Evidence-backed FEM reuse subset, mesh/field contracts, storage and representative probes before dependent feature acceptance |
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

The [WP-05 implementation contract](../docs/persistence.md) documents the portable package/generation layouts, operational SQLite store and reconstructable JSON journal, explicit audit-capacity failure, supported migration/downgrade envelope, HDF5 layout enforcement and host reconciliation boundary. The required Windows driver executes the frozen persistence acceptance IDs, including fresh-process package reconstruction and hard termination at every publication boundary; standard-library cases cover SQLite crash/retry/race behavior. Job scheduling remains WP-06 and actual FreeCAD notifications/Undo integration remain WP-13; this package supplies their durable transaction/host boundary without claiming those later workflows.

[Completion evidence](evidence/WP-05.json) records both 104-check Windows configurations, 89 standard-library regressions and seven persistence integration cases. The final exact-byte prior-manifest guard is covered by the security rerun and both persistence summaries. Generated engineering containers and raw crash diagnostics remain local.

### Step 5.5 — WP-05.5: reconcile FEM reuse and the foundation handoff

Implement the detailed [WP-5.5 work package](WP-05.5-Foundation-Reconciliation.md) and its [25-case acceptance register](WP-05.5-acceptance.csv). Implementation is complete on its declared foundation subset; [candidate-linked evidence](evidence/WP-05.5.json) records both Windows configurations and all 25 required cases. The package preserves completed baselines and leaves full production FEM qualification with its later owners. It depends on WP-01 through WP-05 and completes at P0 before dependent acceptance in WP-06, WP-07, WP-13 and WP-16.

1. Inventory all six FEM candidate groups and synthetic examples with exact upstream source/API/license/dependency and reuse/adapt/replace/defer dispositions. Keep the acquired vendor inventory and publication holds separate.
2. Run representative pinned Windows FEM object/mesh/selection/result and selected mesher/import probes, with independent native startup, offline deployment, host-thread ownership, failure diagnostics and watchdogs.
3. Freeze the supported element/order/connectivity subset, explicit CAD/conduction/radiation/thermal maps, field location/rank/components/frame semantics and heat-flux W/m2 versus power W. Publish version/minimum-reader/migration decisions; preserve released v1 fixtures and hashes.
4. Implement the accepted generated contracts and independent C++/Python readers, extended HDF5/package/store validation and representative real-host transaction/result adapters. Exercise corrupt arrays/identities, stale mappings, migration/downgrade refusal, allocation budgets and crash/race recovery.
5. Prepare independent spatial expected-value generators and frozen refinement/comparison manifests. Preserve the C++/SUNDIALS network decision; optional CalculiX/Elmer references retain separate run identities and cannot close native acceptance.
6. Retain all recorded WP-04/WP-05 audit corrections/regressions; triage newly reproduced handoff issues with owner, reproducer, affected capability, blocking gate and objective closure. Measure operational resource limits and publication-scan cost without weakening qualification or privacy.
7. Implement the common local/CI expected-case gate under TST-022. Required acceptance cannot be skipped or satisfied by planned CSV rows, old reports, external runs or screenshots alone. Publish candidate-linked supplemental evidence while retaining the original baseline and failed attempts.

**Outputs:** reuse/source-license manifest; supported-subset and version ADR; contract/readers and strict extended persistence; independent spatial fixtures; pinned API/mesher and representative host probes; issue/coverage/evidence handoff. **Completion:** every applicable WP055 acceptance row and existing regression gate passes on the exact candidate in the two Windows configurations and pinned host profile, with publication clearance and linked consumer handoff. Full jobs, GUI, spatial solvers and product qualification remain WP-06/WP-13/WP-16/WP-19. A document-only planning pass cannot complete this package.

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

The [WP-06 implementation contract](../docs/jobs.md) defines the SQLite lifecycle, Windows process-tree containment, frozen v1 stream and bounded cancellation acknowledgement channel, opt-in compatible restart, atomic result publication/attachment and historical views. `python tools/check_jobs.py --worker PATH_TO_WORKER` exercises real process termination, exact restart state and synthetic successful HDF5 publication; both Windows drivers require this report. [Completion evidence](evidence/WP-06.json) records both configurations and the prerequisite handoff on the tested implementation candidate. The standalone C++ worker validates snapshots with external solver search paths absent and reports unsupported physics truthfully; production thermal engine qualification remains WP-11 and full host workflows remain WP-13. Synthetic lifecycle success is never numerical qualification.

### Step 7 — WP-07: implement common adapter infrastructure and safe logic handling

The implementation lives in `python/fcst_exchange` with its [versioned grammar and
supported limits](../docs/exchange.md), [frozen automated acceptance register](../ci/exchange-acceptance.json)
and fidelity schema. The executable synthetic reference dialect validates the common
SDK boundary; exact vendor dialects and paired source-tool qualification remain
WP-08/WP-09/WP-10. Both Windows drivers run `tools/check_exchange.py`, including real
bounded converters, pure-logic oracles, parser fuzzing, source-byte preservation,
controlled-edit reopen and result-query comparisons. Native readiness never upgrades
opaque content or grants vendor/solver qualification.

[Completion evidence](evidence/WP-07.json) records the tested implementation
candidate, both 165-check Windows configurations, all 33 exchange acceptance cases,
147 standard-library regressions, the 25-case prerequisite handoff and exact
report/prose publication clearance. WP-07 is complete on its declared common SDK
and executable synthetic reference profile; the later vendor owners retain their
full dialect and paired qualification obligations.

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

The [independent exchange decision](../docs/decisions/0004-independent-thermal-exchange.md)
requires TD/SINDA import and export without TD, OpenTD, AutoCAD/CRTechCAD,
SINDA/FLUINT, vendor licenses, prior vendor conversion or conversion servers.
The earlier OpenTD-first implementation is retained only as optional external
reference tooling. The direct SINDA subset and independent typed TD
node/conductor/heat-load/property profiles are implemented, with guarded source-field
edits and source-free constant-network DWG export. Required geometry, case, manager,
dynamic and dependency semantics and full-model reverse mapping remain incomplete.
The declared closed constant-network profile now supports canonical import, portable
`.fcst` storage and canonical scalar export/reopen. Constant original property
documents and owned property libraries have independent conversion paths; static
SINDA arrays/intrinsics have bounded readers. Complete rectangle/brick wire
profiles have owned readers/writers and guarded constant-parameter source edits;
physical geometry/mesh binding and regeneration remain unimplemented.
Unrepresented modes and additional source versions need verified format evidence,
while owned-engine and paired ESA comparisons remain later qualification dependencies. WP-08 stays in progress; historical evidence retains its scope.

1. Retain the corrected independent LibreDWG 0.14 native component, locked source,
   compiler, preservation patch and GPL notices. Its implementation fixes observed
   opaque bit-length, material/version-field and raw datastorage losses and retains
   every ordered duplicate field occurrence. Require its owned fixture build and
   fresh-process rewrite/reopen in CI. Container/source retention is implemented;
   thermal class semantics and qualified edited/new-model DWG remain open.
2. Implement owned versioned TD binary-class codecs and companion-file readers.
   Inventory submodels, nodes, geometry, GMM/TMM assignments, properties, optics,
   conductors, loads, cases, controls, expressions, handles and dependency closure.
   Container version alone does not identify the TD serialization release.
3. Map supported source fields into canonical FCST entities and implement reverse
   serializers for edited and new-model exports. Preserve every untouched field
   and required opaque bit range, reference, property database and source original;
   refuse unsupported edits. Generic geometry remains labeled geometry-only.
4. Complete required SINDA dialect parsers/writers, includes, property tables and
   reviewed source logic using owned code. Never require SINDA execution for
   import/export or execute imported Fortran as an implicit conversion step.
5. Automate offline first import, controlled edits, export and fresh-process reopen
   with all vendor software, assemblies, services and licenses absent. Attempted
   vendor process/API/remote conversion calls fail acceptance. Missing vendor
   installations cannot be a product prerequisite or a development blocker.
6. Test load, material-table, geometry/topology, property and case edits, full
   unchanged field preservation and new-model export through independent readers.
   Retained bytes, matching JSON or geometry alone cannot pass thermal conversion.
7. Compare owned-engine thermal/radiation/environment results with analytic and
   independently obtained source baselines. Optional licensed reference runners
   supply additional evidence only; never an installed-product dependency.
8. Include the required paired ESA qualification and remaining source-version/
   feature coverage in Q1/Q2 completion, with explicit unresolved fidelity holds.

**Outputs:** independent TD/SINDA codecs and writers, vendor-absent acceptance,
optional external reference harnesses and paired evidence. **Completion:** every
required Q1 TD operation passes complete semantic/dependency inventory, independent
edited/new-model round trips, offline vendor-absence and owned numerical comparisons.
Container probes and the former OpenTD delivery cannot satisfy this completion.
Q1 TD status remains held until its paired ESA qualification also passes.

### Step 9 — WP-09: implement the independent ESATAN-TMS path

The [independent ESATAN exchange decision](../docs/decisions/0005-independent-esatan-exchange.md)
requires original native-project, companion, network and result conversion without
ESATAN-TMS/ESARAD, vendor APIs, licenses, conversion services or prior vendor exports.
The earlier native-API/export prerequisite is superseded. WP-09 is In progress;
the [implemented subset](../docs/esatan.md) covers owned constant D-deck conversion,
native syntax inventories, bound TMD temperature/power queries and streaming XML
inspection. The frozen acceptance register is `ci/esatan-acceptance.json`; complete
native-project/campaign, geometry/environment/motion, runtime and paired numerical
coverage remain required. A D-deck or STEP-TAS subset cannot replace native-project
and campaign semantics. PyCanha's pinned MIT source informed format research without
becoming a runtime dependency or supplying complete preservation qualification.

The original GitLab mirror supplied the full acquired LFS XML at the exact pinned
SHA-256 and length. Preserve the original pointer and resolved payload separately.
The XML root identifies postprocessing chart/result data, not a native project
descriptor; resolving its bytes does not close the project/campaign schema gate.

1. Freeze exact native geometry/environment/kinematics/project, D-deck and result
   dialect/schema profiles from authorized fixtures. Inventory all source files,
   cases, materials/optics, GMM/TMM associations, expressions, source logic, results
   and complete dependency closure without running a vendor tool.
2. Implement bounded direct readers/writers for required native file families,
   including the acquired ERG/ERE/ERK and project/campaign formats. Retain source
   bytes, comments, syntax and every untouched field; reject unresolved required
   content. Disable XML external entities and never evaluate source commands.
3. Implement required D-deck syntax, nodes/submodels, arrays, property tables,
   couplings, includes, cases and reviewed expression/procedure semantics in owned
   code. Map to the same typed canonical entities used by TD and the owned engine;
   retained procedures and a geometry-only model cannot establish native readiness.
4. Implement independent result-file/dataset readers, including required TMD/HDF5
   schemas, with exact model/campaign/case/node identity, units/sign/time and event
   mapping. HDF5 container readability cannot qualify an undocumented schema.
5. Implement reverse serialization for supported source edits and new native
   projects/decks. Export to new complete trees and independently reopen in fresh
   processes. Preserve all unrequested fields, opaque bits and companion data;
   reject edits that cannot safely maintain full source correspondence.
6. Run offline first import, load/material/geometry/property/environment/motion/
   case edits, new-model export and reopen with all vendor installations, APIs,
   services and licenses absent. Guard against attempted vendor process/import/
   network calls. No prior ESATAN conversion or user-executed acceptance is allowed.
7. Bind STEP-TAS input/output to an independently acquired schema/dictionary under
   WP-10 when that format is actually supplied. Do not require vendor-generated
   interchange to access original native files. Preserve native campaign content
   absent from an interchange schema through declared companion formats.
8. Compare owned-engine behavior with analytic and independent source baselines;
   qualify both paired TD/ESA directions with separate semantic/loss reports.
   Optional licensed reference runners produce additional comparison evidence
   only. Missing evidence holds a compatibility claim, never mandates a vendor
   dependency in the installed product. Keep remaining Q2 semantics explicit.

**Outputs:** independent ESATAN native-project/deck/result codecs and writers,
complete campaign/dependency mapping, vendor-absent acceptance and optional external
reference harnesses. **Completion:** all required Q1 source features and directions
pass full semantic/dependency coverage, independent changed/new-model round trips,
offline vendor-absence and owned numerical comparisons. Paired ESA and TD coverage
remain separate required gates; neither can compensate for the other.

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

WP-11.1/11.2 implementation: [owned thermal preparation](../docs/thermal-engine.md)
defines the immutable typed loader, source aliases, deterministic equation indexes,
case overlays, conductive component diagnoses, versioned material-law/storage
envelope, exact specific-heat integrals and supported constant anisotropic tensors.
The [acceptance register](../ci/thermal-acceptance.json) binds executable native
and installed-worker checks in both Windows verification presets. WP-11.3 through
WP-11.5 add continuous/steady/enthalpy-step energy residuals, exact algebraic
constraints, prescribed boundary power, explicit radiation/environment/load
callbacks, canonical sparse Jacobians and guarded linear/nonlinear backend
interfaces. Independent finite differences, conservation, callback failure,
singular/algebraic, sparse-storage and backend contract cases are required in the
same native/CI driver. WP-11.6 supplies bounded equilibrated sparse LU and damped
Newton steady solves with frozen per-equation power scaling, temperature
correction criteria, material/physical bounds, independent energy acceptance and
singular/nonconvergent/fill-limit diagnostics. Owned analytic/manufactured cases
and the clean native steady CLI are required by the same acceptance register.
WP-11.7 through WP-11.10 implement adaptive, L-stable enthalpy backward Euler
with step-doubling error estimates, consistent index-one DAE initialization,
rejected-step reporting and exact requested output boundaries. Explicit schedules
and directional hysteresis events localize by re-solving, update in deterministic
batches, reinitialize algebraic constraints and preserve checkpoint/duty/energy
state. Native results include full-node temperature/power/storage/residuals,
event and step/run budgets, validity and model/settings/build provenance. Compiled
assembly/LU timing and operation counters accompany explicit backend capabilities.
Analytic single/two-node, stiff, nonlinear enthalpy, algebraic/boundary, refinement,
independent RK4, event/restart and failure cases run without a host or external
solver. All ten implementation substeps are present. Engine numerical sign-off
uses the separately executed independent reference profile below; paired vendor
compatibility and durable-job HDF5/host integration retain their owning gates.
See the API/CLI limits and event detection contract in the implementation document.

The [WP-11 qualification record](WP-11-qualification.md) and versioned
[requirement/oracle register](../ci/thermal-qualification-v1.json) bind the seven
owned requirements to actual required native case verdicts. Fixed step caps
0.2/0.1/0.05 s demonstrate heater-event/duty refinement; a 256-equation network
records compiled assembly/LU work against an exact manufactured ramp and a
localized-load conservation case. A bounded subnormal-quantization safeguard
fixes false componentwise LU failures without changing global residual or
physical energy acceptance; geometric-tail and impossible-relative-target
regressions are mandatory. Owned
constant SINDA and ESATAN decks run through the independent file adapters and
native steady/transient CLI, checked against frozen analytic temperatures,
boundary powers and enthalpy, with deliberate perturbations rejected. These are
owned source-literal comparisons, not vendor executions. Captured-result tooling
validates exact source/result/receipt hashes and identities but cannot itself
certify licensing, receipt authenticity or full Q1 qualification. No approved
reference runner is available; GAP-LICENSES/GAP-RESULTS and downstream host/MCP/
coupled-physics gates remain explicit. Planned traceability rows remain a plan
as required by its validator; actual coverage is in the executable receipts.

The user-approved alternative reference basis is
[WP-11-independent-numerical-v1](../ci/thermal-reference-v1.json): separately
formulated SUNDIALS IDA 7.3.0 full DAEs and SciPy 1.15.2 Radau reduced ODEs,
plus Pycanha core 0.23.0 cooling/closed/zero-capacity-DAE trials. Both Windows
presets require all native cases plus 46 external/native run receipts and 63
refinement, analytic and cross-solver comparison verdicts. Tolerances, requested
grids, energy/flow/event/duty and steady criteria are executable and frozen;
missing, stale, nonfinite or substituted evidence fails. The reference executables
never link/import engine assembly or solvers. This closes PHY-001 independent
solver benchmarking and WP-11 engine numerical sign-off when the candidate-bound
reports pass. The earlier licensed-runner absence is not a numerical-engine
blocker. TD/ESA compatibility, wider host/MCP/coupled physics, durable-job result
integration and full project Q1 remain independently unqualified. See
[formulations and scope](../references/thermal/README.md) and the qualification
record. A capped-step remainder regression additionally proves exact requested
output completion without skipping elapsed time or exceeding the step cap.



### Step 12 — WP-12: implement CPU radiation and thermal coupling

Implementation: [owned CPU radiation engine](../docs/radiation-engine.md), native
BVH and geometry validation, stable surface/side streams, sparse raw/corrected
exchange, separate solar/IR constant diffuse-gray optics with provenance/domain
metadata, radiosity, derivative solves and separate internal/environment thermal
callbacks. Strict installed-worker evaluation and coupled steady commands are
included. Native tests cover transient coupling and energy accounting.
`tools/check_radiation.py` requires all 16 seeds at three sample counts, 576
predeclared simultaneous intervals, analytical/independent quadrature and dense
radiosity comparisons, boundary/replay failures, correction checks and three
scaling repetitions per sample count through one million facets. Both Windows
presets and the candidate-bound foundation handoff require this acceptance.
Specular/transmissive optics, moving environments, durable solver jobs, GUI wiring
and licensed vendor compatibility retain their separately mapped gates.

[Completion evidence](evidence/WP-12.json) records both Windows verification
configurations, all 576 simultaneous intervals, independent numerical comparisons
and measured scaling through one million facets on the tested implementation.

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

The [host implementation](../docs/freecad-workbench.md) supplies the installed
workbench, schema-derived editors, canonical transactions and inverse Undo,
signed CAD capture/review links, asynchronous native steady/transient execution,
coordinated saves and linked contour/history/budget views. The supplemental
[reuse assessment](../ci/host-reuse.json) retains the foundation's pinned FEM
objects and native contour rendering; bundled Coin adds engineering overlays.
Both Windows drivers require `tools/check_host.py` and candidate/source/worker-bound
`host.json` evidence. Production spatial physics and FEM-REUSE-003/006 remain WP-16.

Before implementing overlapping objects, editors or visualization, complete the initial [FEM reuse assessment](../docs/decisions/0003-freecad-fem-reuse.md), including mesh candidates for WP-16. Record reuse/adapt/replace/defer decisions with pinned APIs, licenses and prototype evidence in the WP-13 issue/implementation PR. Route selected components through FCST adapters and the shared transaction/result contracts. The existing geometry smoke is not FEM evidence.

1. Add workbench registration, document/project links, tree objects and view providers using the pinned host APIs.
2. Implement editors for nodes, surfaces, materials/optics, conductors, loads, environments, cases and solver settings. Each editor calls the shared operation API and displays structured errors.
3. Implement selection-to-entity mappings and explicit visual overlays for nodes, mesh assignments, normals, material axes, contacts, unassigned items and invalid/ambiguous attachments.
4. Route all document changes/completion callbacks through the owning application thread. Offload expensive work to isolated jobs and keep progress/cancel controls responsive.
5. Implement canonical commit-to-host synchronization, explicit dirty/reconciliation state for direct host edits, undo through inverse transactions, and save/recovery coordination.
6. Display temperature contours and time histories, heat-flow/energy budgets, heater duty and validity/staleness. Use result IDs/units from the data layer rather than recalculating separate UI values.
7. Build host test commands and stable UI selectors/object identifiers. Automate command invocation, edits, selection, dialogs, asynchronous completion, save/reopen, undo and result inspection in an isolated FreeCAD process.
8. Use screenshots as supplementary rendering evidence; numerical/data assertions are primary. Automate visual checks for selected stable reference views with declared tolerances.

**Outputs:** usable workbench, inspectors, visualization, FEM component assessment/adapters and unattended host harness. **Completion:** a clean runner builds/saves/reopens a model through the UI, verifies canonical hashes and plotted values, exercises face changes and failure recovery, and completes without a person clicking through the test. Implement the applicable P0/Q1 FEM-REUSE-001/002/004/005 checks with their features; the coverage gate rejects missing assessment/API/license evidence, operation/units/mapping differences and stale fields. Spatial extensions remain WP-16.

### Step 14 — WP-14: implement typed MCP automation and policy enforcement

Implementation: [local MCP gateway and declared profiles](../docs/mcp.md), with
frozen `ci/mcp-acceptance.json` and candidate/input/worker-bound `mcp.json` from
`tools/check_mcp.py` in both Windows verification presets. The modern profile
uses the released 2026-07-28 metadata lifecycle and pinned upstream wire schema;
the official `mcp==1.26.0` client independently exercises the 2025-11-25 legacy
handshake. Native conduction case parity includes empty-project construction,
typed editing, durable solve/reconnect, analytic temperature/energy checks,
queued/live cancellation, interrupted-service recovery and terminal truth.
Unavailable production mesh/radiation submission, vendor conversion and viewport
capture are declared capabilities; no placeholder can report a successful solve.
Integrated two-surface parity remains WP-15, and these receipts do not grant Q1.

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

Complete WP-13's initial FEM mesh assessment before introducing a meshing stack. Evaluate FEM mesh objects/I/O and Gmsh/Netgen integration on the pinned host, select only qualified components, and record exact source/build/options/licenses plus reasons for any replacement. Explicitly map CAD references, conduction elements/thermal nodes and radiation facets; a shared geometry does not make these identities equivalent. Evaluate CalculiX/Elmer as optional separately labeled conduction references, with predeclared equivalent inputs and tolerances.

1. Freeze supported FD primitives and FE shell/solid element families from the Q1 inventory; document formulations, quadrature, lumping/reduction and validity limits.
2. Generate meshes through the geometry adapter/selected mesher with stable provenance and explicit CAD/facet/element/node mappings. Mesh refinement cannot silently change source identity associations.
3. Implement element conduction/storage assembly and rotate symmetric positive-definite material tensors from local frames. Validate interpolation and tensor/temperature ranges.
4. Implement contact mappings with physical area/gap assumptions, lumped links, convection and distributed heaters/loads. Integrated assigned power must equal the intended total.
5. Connect geometry edits to mesh/radiation/result invalidation and ambiguous attachment detection, including face split/merge/reorder/delete.
6. Implement limited MLI, insulation and reduced heat-pipe abstractions with parameter provenance, calibration/validity limits and explicit unsupported regimes.
7. Run rod/slab cases, element patch tests, rotated anisotropy, manufactured solutions, contact tests and mesh/time refinement independently of vendor comparisons.

**Outputs:** supported discretization library, qualified FEM reuse/replacement dispositions, mesh/attachment tooling, contact and reduced-component models. **Completion:** analytical/manufactured/conservation/refinement suites and mandatory imported Q1 element/property cases pass; unsupported element types are diagnosed before solving. Implement FEM-REUSE-003 and the spatial extensions of FEM-REUSE-001/004, plus FEM-REUSE-006 with WP-19. Verify mesh/element ordering, units, integrated loads, face-change/refinement invalidation and native engine independence. Selected external comparisons require their pinned profile evidence and never replace owned-engine checks.

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
2. Handle GMM, mesh, TMM, properties, campaign and results jointly where required. Use owned direct schema codecs or independently deployable open-source converters per actual profile; vendor APIs supply optional external reference evidence only for TD/ESATAN paths.
3. Qualify every required direction independently. A VIF reader does not imply a writer; current THERMICA projects are not qualified by an old SYSBAS reader.
4. Apply the same safe parse/preserve/edit/new-tree export, unchanged/controlled-edit source round trips and native-solve comparisons used for Q1.
5. Run every mandatory entity/procedure/case/operation through the coverage evaluator. Required retained-opaque, unsupported, unapproved approximation or external-only execution entries block Q2.
6. Re-run affected Q1 profiles, platform installations, security, performance and automation suites after advanced modules/adapters are added.
7. Publish the exact supported inventory, remaining non-required limitations and immutable evidence bundle. Close all five Q2 specification requirements and applicable delivery-test requirements.

**Outputs:** full required legacy adapters, advanced/native support matrix and Q2 qualification bundle. **Completion:** zero unresolved required coverage entries and all mandatory round trips/owned-engine executions pass. Compatibility claims stay bounded by the published inventory; TD/ESATAN conversion retains the independent product requirement at Q2.


## 4. Mandatory automated-test delivery requirements

The following 22 requirements implement the user's instructions for unattended testing, GitHub delivery, privacy before publication and the foundation handoff. Their full machine-readable acceptance text is in [automated-test-requirements.csv](automated-test-requirements.csv). They supplement the 121 baseline requirements; their IDs are deliberately separate. Q0 is the first required gate for test infrastructure/criteria and publication privacy; TST-022 is required at P0; Q1 requirements also apply to Q2 and changed capabilities. TST-021 applies before the first online publication even if Q0 is not yet complete.

| ID | Required behavior | First required gate |
|---|---|---|
| TST-001 | Every delivery requirement and claimed profile operation has an executable test/inspection rule, owner and evidence link | Q0 |
| TST-002 | Numerical/statistical/semantic criteria are versioned and frozen before runs; changes create reassessment runs | Q0 |
| TST-003 | Acquired fixtures have reproducible manifests, hashes, status/rights dispositions and assigned gaps; executable oracles are required at their affected qualification gate | Q0 |
| TST-004 | Owned-engine physics, energy, refinement, algebraic initialization and controls/events run automatically | Q1 |
| TST-005 | Scripted GUI/CLI/MCP sequences produce equivalent model semantics and numerical outcomes | Q1 |
| TST-006 | Persistence/job tests inject crashes, interrupted writes, retries, disconnects and cancellation races | Q1 |
| TST-007 | Licensed runners automatically perform exact-version source reopen/run, controlled edits and cross-tool comparisons | Q1 |
| TST-008 | FreeCAD tests create/edit/save/reopen/undo/solve/inspect without user clicks; FEM assessment/API/license, mapping, units and result checks accompany reused or replacement features | Q1 |
| TST-009 | Clean-machine offline install, native solve, migration, portable reopen and rollback are automated per supported profile | Q1 |
| TST-010 | Parser/archive fuzzing and non-execution, scope, injection and redaction checks run automatically | Q1 |
| TST-011 | Stochastic qualification uses predeclared fixed ensembles and convergence/coverage policy; no seed shopping | Q1 |
| TST-012 | Performance tests record actual resources/hardware and compare frozen targets at unchanged accuracy | Q1 |
| TST-013 | Test runs emit structured verdicts, diagnostics, raw data and immutable provenance/evidence manifests | Q0 |
| TST-014 | Native acceptance proves no external thermal solver was used; optional CalculiX/Elmer references have separate pinned profiles and cannot close native coverage | Q1 |
| TST-015 | Missing fixtures/licenses/runners/oracles produce blocked/incomplete required coverage, never an implicit pass | Q0 |
| TST-016 | Retries cannot erase failures; flaky tests and quarantines remain visible and cannot remove mandatory gate coverage | Q1 |
| TST-017 | GitHub is the source/work-tracking platform; GitHub Actions and local drivers run the same checks, with protected-branch required checks | Q0 |
| TST-018 | Private GitHub validation workflows isolate licensed/restricted runners, data, secrets and runtimes from public PRs and start from reproducible state | Q1 |
| TST-019 | No required acceptance step depends on the user executing a manual test procedure | Q1 |
| TST-020 | A required GitHub Actions gate checks requirements, profiles, evidence, defects and allowed claims before publishing a candidate-linked GitHub Release | Q1 |
| TST-021 | Local checks before upload and CI publication gates exclude private/personal information from code/history, metadata, docs, posts, media, logs and release assets | Q0 |
| TST-022 | WP-05.5 closes the missing foundation handoff using exact reuse/API/license evidence, versioned mesh/field contracts, strict storage, independent fixtures and unattended candidate-bound acceptance before dependent feature qualification | P0 |

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
| SUITE-GUI | Unattended FreeCAD commands/editors/selection/undo/save/reopen, FEM adapter/API probes, units/entity mappings, host-thread dispatch, canonical result/display and stale-field assertions and stable-view checks |
| SUITE-MCP | Real stdio client lifecycle, schemas/resources, bounded queries, parity, offline operation, reconnect and application job cancellation |
| SUITE-CAMPAIGN | Variant identity, sweeps, uncertainty/sensitivity replay, synthetic sensor correlation/holdout and report/table provenance |
| SUITE-SECURITY | Publication privacy, outgoing history/metadata/prose/media/artifact checks, malicious/archive/parser corpus, fuzz regressions, imported code inertness, scope/budget enforcement, isolation, secret redaction and no default listener |
| SUITE-PERF | Fixed sparse/large-query workloads, peak memory, UI/cancel latency and million-facet accuracy/scaling curves |
| SUITE-INSTALL | Clean Windows builds/packages, engine without host/Python/vendor solvers, offline host workflow, portable delivery, upgrade/rollback and licenses |
| SUITE-GATE | Traceability and criteria versions, fixture coverage, actual backend, candidate/profile hashes, blocked/flaky cases, defects and published claims |

Each suite's trigger, runner and evidence contract is recorded in [test-suites.csv](test-suites.csv). A suite is an organizational group, not one giant test: individual cases carry requirement/profile IDs so regression selection and failure triage stay specific.

For thermal cases, compare quantities with `abs(x - reference) <= atol + rtol * abs(reference)` and record maximum, RMS, relevant percentile and affected IDs. Use absolute kelvin for relative temperature normalization and declared floors near zero heat flow. Start with the specification's proposed criteria, then freeze their applicable values at Q0. Preserve the 0.1 K/1% initial cross-solver target, event-time criterion, energy criteria and separate deterministic/stochastic radiation policies in case metadata rather than embedding magic constants in scripts.

### 4.2 How unattended vendor and GUI tests work

Independent product acceptance first runs import, edit, new-model export and fresh-process reopen on offline Windows with vendor installations, APIs, assemblies, licenses and conversion endpoints absent. Attempted vendor use fails acceptance. These drivers run automatically and cannot be replaced by licensed reference jobs.

Optional external comparisons use dedicated licensed self-hosted runners for each declared vendor configuration, accessed only by controlled GitHub Actions workflows in the private validation repository described in section 2.1. The runner has a preprovisioned licensed installation and a disposable project/work directory. A supervisor checks prerequisites, creates the fixture copy, invokes documented vendor automation, waits with deadlines, retrieves results, compares them and collects artifacts. Test credentials/licenses stay outside projects and logs. Untrusted public changes cannot directly execute on restricted runners; promote reviewed source/build artifacts by verified candidate hash through a controlled job.

For each optional source-tool comparison, the reference driver verifies original hashes, runs the source baseline, independently imports and inspects fidelity, runs FCST natively, independently exports a new derivative, then reopens/runs it in the exact source tool and compares identities/topology/fields/results and unchanged content. Controlled-edit comparisons also create an equivalent source-native edit automatically. Cross-tool directions use separate manifests and target runners. Missing licensed runners hold that optional evidence, without creating a product dependency or blocking independent codec development.

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
   Complete the inserted WP-05.5 foundation reconciliation before dependent acceptance: measured FEM reuse/probes, versioned mesh/field contracts, storage, independent spatial fixtures and the TST-022 handoff gate. Scaffolding may proceed against unchanged interfaces while those decisions are resolved.
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
