# FreeCAD Space Thermal — specification package

Design baseline **0.9**, amended **29 October 2026**.

**Windows first:** develop and qualify the FreeCAD add-on/workbench and standalone engine for Windows. macOS and Linux configurations are optional [stretch goals](plans/stretch-goals.md), outside the work packages and committed delivery. No modified FreeCAD distribution is required.

Project development uses [the GitHub source repository](https://github.com/Bored-Anarchist/freecad-space-thermal), Issues/Projects, pull requests, GitHub Actions automated testing, and Releases. The [implementation plan](plans/FCST-Implementation-Plan.md) specifies required checks, scoped vendor runners, and evidence-backed release gates. The WP-02 skeleton provides C++20/CMake worker and Python package foundations with [shared local/CI verification commands](docs/development.md); solving and compatibility remain unimplemented. [WP-02 evidence](plans/evidence/WP-02.json) records completed foundation acceptance and the separate remaining Q0/product obligations. Active host and dependency packaging probes run on Windows; no production numerical backend is adopted.

Track the 22 work packages in the [FCST implementation project](https://github.com/users/Bored-Anarchist/projects/1), including the inserted WP-05.5, with requirement IDs, delivery gates, prerequisites and evidence-backed states.

[FreeCAD FEM reuse](docs/decisions/0003-freecad-fem-reuse.md) is a required assessment before overlapping WP-13 host and WP-16 mesh work. Evaluate existing mesh, selection/material/load and result tools before replacing them; retain the standalone owned engine. FEM is currently a design reference, with no implemented FEM integration or adopted FEM source. Component selection, pinned API/license checks and unattended host/mesh acceptance remain planned.

[WP-5.5 — FEM reuse and foundation reconciliation](plans/WP-05.5-Foundation-Reconciliation.md), canonical ID WP-05.5, collects the missing WP-01 through WP-05 handoff work and related issues. Its 25 implemented acceptance cases cover reuse/provenance, pinned probes, element/field/heat-flux contracts, compatibility, storage/recovery, independent spatial fixtures, representative host integration and privacy. [Completion evidence](plans/evidence/WP-05.5.json) records the completed P0 handoff before dependent feature acceptance in WP-06/WP-07/WP-13/WP-16; the completed baselines retain their original scope and evidence.

WP-07 provides the [common source exchange SDK](docs/exchange.md): byte-preserving
syntax, bounded includes, typed mapping, inert source logic, fidelity reports,
guarded exports and SI result queries. Its executable `fcst-network/1` synthetic
profile exercises shared infrastructure; vendor dialects and qualification remain
WP-08/WP-09/WP-10. Both Windows CI configurations run its frozen unattended cases.
[Completion evidence](plans/evidence/WP-07.json) records the two 165-check Windows
drivers, 33 exchange acceptance cases, security regressions and foundation handoff.

WP-08 requires [fully independent TD/SINDA import and export](docs/decisions/0004-independent-thermal-exchange.md).
The direct SINDA subset imports, edits and writes new models without vendor installations.
A corrected independent native DWG backend supports container inspection, exact
source-tree retention, typed node/conductor/heat-load payloads, direct property
databases, guarded scalar edits and source-free constant-network DWG generation.
Closed constant networks now import into native FCST projects, retain portable
originals and export canonical scalar edits. Constant property libraries and
static SINDA arrays have independent paths; rectangle geometry has a partial
envelope reader. Required complete geometry/case/manager/dynamic semantics,
additional formats and full-model DWG qualification remain open. The existing OpenTD sidecar is an optional external reference
harness. Q1 remains unqualified; public CI exercises
runtime-independent contracts without proprietary software or data.

WP-09 requires [independent ESATAN native-project, deck and result conversion](docs/decisions/0005-independent-esatan-exchange.md), with no vendor installation, API, license, prior export or conversion service. Its implementation remains Planned; the documentation change does not claim a working ESATAN converter.

[WP-03 contracts](spec/contracts/README.md) freeze native model, operation, result, HDF5 layout and worker protocol version 1.0.0. Independent C++ and Python readers validate typed entities, references, quantities, frames and expression types, and agree on normalized snapshots and semantic hashes. Both Windows configurations run the same positive/negative fixtures and bounded framing checks.

[WP-04's numerical checkpoint](docs/decisions/0001-q0-numerical.md) adds a separate C++/SUNDIALS experiment with independent analytic/nonlinear oracles, energy/event/restart checks, dense/banded and BDF/Adams comparisons, scale probes and sealed evidence. Both Windows verification configurations execute it unattended. It retains C++ as the implementation baseline; production solving, GUI workflows and vendor compatibility remain later work.

[WP-05 persistence](docs/persistence.md) supplies bounded ZIP/expanded packages, exact original-byte retention, versioned HDF5 result/mesh arrays, durable SQLite transactions with portable JSON journals, scoped retries/previews, atomic edits/undo, dependency invalidation, migration and coordinated host/package recovery. Both Windows drivers run transaction and crash regressions plus HDF5 conformance. The host adapter, live jobs and production physics remain their later work packages.

[WP-01's completed acquired inventory](inventory/README.md) records acquired Thermal Desktop/SINDA and ESATAN examples, pinned hashes, rights/dependency dispositions and feature mappings. Raw originals remain local; vendor execution is blocked by unavailable licensed runners and no compatibility profile is qualified.

**Publication privacy:** remove private/personal information before any online code, documentation, issue/PR/comment/post, log, image or release upload. The [standing repository instructions](AGENTS.md) and plan requirement TST-021 require checks before publication, sanitized outputs and separate preservation of authorized engineering originals.

This package specifies an open-source, local-first FreeCAD add-on and independently maintained **C++ numerical engine**, with **Python FreeCAD, API/MCP, automation, and test interfaces**, for spacecraft thermal engineering. Thermal Desktop/SINDA and ESATAN-TMS interoperability have equal priority. NASA/ESA compatibility means compatibility with thermal model files and workflows used by their teams. The specification covers file exchange, preserved model semantics, numerical behavior, and API/MCP automation.

**Independent native workflow:** users must be able to build a new thermal model, save it as an FCST `.fcst` project, reopen, edit and solve it with the owned engine, and inspect its results without Thermal Desktop, SINDA/FLUINT, ESATAN, their licenses or an imported vendor file. Backward compatibility is an additional required capability provided by adapters. The legacy-model inventory scopes compatibility verification; it does not define or block development of native model creation and solving.

The accepted baseline is **C++20 with CMake**, with exact compiler and dependency builds frozen at Q0. Python owns the host-facing interfaces and test orchestration; the numerical engine remains usable without FreeCAD. WP-04 tests SUNDIALS in the separate numerical checkpoint. PETSc, Embree, Open CASCADE and pybind11 remain documented candidates; a production stack requires its own qualification. Their selection and supported combinations require implementation evidence. A Q0 prototype gate compares numerical correctness, sparse scaling, deployment, and engineering effort at equivalent accuracy; language comparisons use the same numerical backend where applicable. Rust is an optional comparison prototype, not a production dependency or a parallel implementation requirement. Changing the accepted C++ baseline requires an explicit decision supported by that evidence.

**SINDA/FLUINT and Thermal Desktop are primary behavioral benchmarks and starting-point references** for thermal/fluid modeling, workflows, and interoperability. PyCanha and other open solvers may also supply licensed reusable components, comparison results, or temporary prototype backends, with provenance and dependency records. Ansys Fluent is a separate, optional CFD reference. Required production solves must ultimately run on the owned engine; wrapping another thermal solver alone does not meet that goal. Reusing suitable numerical libraries does not remove ownership of FCST's thermal assembly, physics, controls, and solve lifecycle. Product source import/export must use independent codecs. Vendor APIs may supply optional external comparison evidence only.

Start with [the specification](spec/FreeCAD-Space-Thermal-Specification.md). Supporting artifacts are:

- [Detailed implementation and build plan](plans/FCST-Implementation-Plan.md): 22 ordered work packages, including WP-05.5, component boundaries, dependencies, Windows Q0/P0/Q1/Q2 gates, and unattended test and release execution.
- [Implementation requirement traceability](plans/requirement-traceability.csv): all 121 baseline requirements plus 21 additional automated-test delivery requirements mapped to owners, work packages, suites, and planned evidence. The [test requirements](plans/automated-test-requirements.csv), [work packages](plans/work-packages.csv), [test suites](plans/test-suites.csv), and [compatibility test plan](plans/compatibility-test-plan.csv) provide the execution registers. [Validate the plan](plans/tools/validate_plan.py) with `python plans/tools/validate_plan.py`; it uses only the standard library and checks planning consistency, not implemented product behavior.

- [Requirements register](spec/requirements.csv): machine-readable requirements extracted from the specification.
- [Compatibility profiles](spec/compatibility-profiles.csv): proposed source-version, file-family, and behavior test targets and release gates.
- [Source register](spec/sources.md): primary format, tool-interface, FreeCAD, C++/Python numerical and binding candidates, optional Rust experiments, and automation references and research limitations.
- [Project manifest schema](spec/schemas/project-manifest.schema.json) and [example](spec/examples/project-manifest.json).
- [Application operation envelope schema](spec/schemas/operation-envelope.schema.json) and [example](spec/examples/create-conductor.json).
- [Representative conductor argument schema](spec/schemas/create-conductor.arguments.schema.json).
- [Package consistency validator](spec/tools/validate_spec.py): checks registers, references, schemas, and examples; requires Python and `jsonschema`.

These are design requirements and draft interface contracts, **not an implemented product or evidence of existing file compatibility**. Required compatibility and numerical testing, source-model fixtures, and unresolved inputs are explicit in the specification. JSON examples use synthetic identifiers and hashes; they are not engineering models.
