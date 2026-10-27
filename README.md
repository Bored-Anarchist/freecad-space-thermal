# FreeCAD Space Thermal — specification package

Design baseline **0.7**, amended **27 October 2026**.

**Windows first:** develop and qualify the FreeCAD add-on/workbench and standalone engine for Windows. macOS and Linux configurations are optional [stretch goals](plans/stretch-goals.md), outside the work packages and committed delivery. No modified FreeCAD distribution is required.

Project development uses [the GitHub source repository](https://github.com/Bored-Anarchist/freecad-space-thermal), Issues/Projects, pull requests, GitHub Actions automated testing, and Releases. The [implementation plan](plans/FCST-Implementation-Plan.md) specifies required checks, scoped vendor runners, and evidence-backed release gates. The WP-02 skeleton provides C++20/CMake worker and Python package foundations with [shared local/CI verification commands](docs/development.md); solving and compatibility remain unimplemented. [WP-02 evidence](plans/evidence/WP-02.json) records completed foundation acceptance and the separate remaining Q0/product obligations. Active host and dependency packaging probes run on Windows; no numerical backend is adopted.

Track the 21 work packages in the [FCST implementation project](https://github.com/users/Bored-Anarchist/projects/1), with requirement IDs, delivery gates, prerequisites and evidence-backed states.

[WP-01's completed acquired inventory](inventory/README.md) records acquired Thermal Desktop/SINDA and ESATAN examples, pinned hashes, rights/dependency dispositions and feature mappings. Raw originals remain local; vendor execution is blocked by unavailable licensed runners and no compatibility profile is qualified.

**Publication privacy:** remove private/personal information before any online code, documentation, issue/PR/comment/post, log, image or release upload. The [standing repository instructions](AGENTS.md) and plan requirement TST-021 require checks before publication, sanitized outputs and separate preservation of authorized engineering originals.

This package specifies an open-source, local-first FreeCAD add-on and independently maintained **C++ numerical engine**, with **Python FreeCAD, API/MCP, automation, and test interfaces**, for spacecraft thermal engineering. Thermal Desktop/SINDA and ESATAN-TMS interoperability have equal priority. NASA/ESA compatibility means compatibility with thermal model files and workflows used by their teams. The specification covers file exchange, preserved model semantics, numerical behavior, and API/MCP automation.

**Independent native workflow:** users must be able to build a new thermal model, save it as an FCST `.fcst` project, reopen, edit and solve it with the owned engine, and inspect its results without Thermal Desktop, SINDA/FLUINT, ESATAN, their licenses or an imported vendor file. Backward compatibility is an additional required capability provided by adapters. The legacy-model inventory scopes compatibility verification; it does not define or block development of native model creation and solving.

The accepted baseline is **C++20 with CMake**, with exact compiler and dependency builds frozen at Q0. Python owns the host-facing interfaces and test orchestration; the numerical engine remains usable without FreeCAD. SUNDIALS, PETSc, Embree, Open CASCADE, and pybind11 are documented mechanisms or candidates, not an assembled or tested FCST stack. Their selection and supported combinations require implementation evidence. A Q0 prototype gate compares numerical correctness, sparse scaling, deployment, and engineering effort at equivalent accuracy; language comparisons use the same numerical backend where applicable. Rust is an optional comparison prototype, not a production dependency or a parallel implementation requirement. Changing the accepted C++ baseline requires an explicit decision supported by that evidence.

**SINDA/FLUINT and Thermal Desktop are primary behavioral benchmarks and starting-point references** for thermal/fluid modeling, workflows, and interoperability. PyCanha and other open solvers may also supply licensed reusable components, comparison results, or temporary prototype backends, with provenance and dependency records. Ansys Fluent is a separate, optional CFD reference. Required production solves must ultimately run on the owned engine; wrapping another thermal solver alone does not meet that goal. Reusing suitable numerical libraries does not remove ownership of FCST's thermal assembly, physics, controls, and solve lifecycle. Source-format migration and source-tool comparison/re-export may still use vendor APIs where necessary.

Start with [the specification](spec/FreeCAD-Space-Thermal-Specification.md). Supporting artifacts are:

- [Detailed implementation and build plan](plans/FCST-Implementation-Plan.md): 21 ordered work packages, component boundaries, dependencies, Windows Q0/P0/Q1/Q2 gates, and unattended test and release execution.
- [Implementation requirement traceability](plans/requirement-traceability.csv): all 121 baseline requirements plus 21 additional automated-test delivery requirements mapped to owners, work packages, suites, and planned evidence. The [test requirements](plans/automated-test-requirements.csv), [work packages](plans/work-packages.csv), [test suites](plans/test-suites.csv), and [compatibility test plan](plans/compatibility-test-plan.csv) provide the execution registers. [Validate the plan](plans/tools/validate_plan.py) with `python plans/tools/validate_plan.py`; it uses only the standard library and checks planning consistency, not implemented product behavior.

- [Requirements register](spec/requirements.csv): machine-readable requirements extracted from the specification.
- [Compatibility profiles](spec/compatibility-profiles.csv): proposed source-version, file-family, and behavior test targets and release gates.
- [Source register](spec/sources.md): primary format, tool-interface, FreeCAD, C++/Python numerical and binding candidates, optional Rust experiments, and automation references and research limitations.
- [Project manifest schema](spec/schemas/project-manifest.schema.json) and [example](spec/examples/project-manifest.json).
- [Application operation envelope schema](spec/schemas/operation-envelope.schema.json) and [example](spec/examples/create-conductor.json).
- [Representative conductor argument schema](spec/schemas/create-conductor.arguments.schema.json).
- [Package consistency validator](spec/tools/validate_spec.py): checks registers, references, schemas, and examples; requires Python and `jsonschema`.

These are design requirements and draft interface contracts, **not an implemented product or evidence of existing file compatibility**. Required compatibility and numerical testing, source-model fixtures, and unresolved inputs are explicit in the specification. JSON examples use synthetic identifiers and hashes; they are not engineering models.
