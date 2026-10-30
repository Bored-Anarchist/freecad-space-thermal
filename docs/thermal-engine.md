# Owned thermal model preparation and assembly

WP-11.1 and WP-11.2 provide the C++20 preparation API in
[`fcst/thermal.hpp`](../engine/include/fcst/thermal.hpp). `thermal::load` validates
and owns an immutable SI snapshot. `Model::data()` exposes a const reference;
caller input changes cannot change the model. The existing model-v1 contract
stays unchanged. The generated
[thermal-input-v1 schema](../spec/schemas/thermal-input-v1.schema.json) wraps it:

```json
{
  "contract_version": "1.0.0",
  "model": {},
  "material_laws": [],
  "node_storage": []
}
```

Replace `model` with a complete model-v1 object. An executable synthetic example
is [material-network.json](../tests/fixtures/thermal/material-network.json).
Input is strict UTF-8 JSON, at most 1 MiB and 64 levels deep, with duplicate keys,
unknown fields, invalid units, nonfinite values and invalid references rejected.
The standalone worker accepts this envelope on stdin with `--thermal-prepare`.
Its bounded JSON output reports preparation status, hashes, equation indexes,
component diagnoses and counts. It reports `solver_available: false`.

Nodes, conductors, loads and materials use stable UUID order. Unknown-temperature
equations include capacitive and algebraic nodes; separate dense differential and
algebraic indexes retain each classification. Prescribed nodes have no unknown
index, and algebraic/prescribed capacities remain exactly zero. No artificial
storage is inserted. Every source alias retains its map UUID, source revision,
tool/version, namespace, handle, entity UUID and optional source submodel/node
number. The source lookup key is `(map UUID, namespace, handle)`; reverse lookup
retains all aliases for an entity. Errors carry safe codes and available entity
and source-map UUIDs, without echoing source text or paths.

When the model contains cases, supply `case_id` explicitly. Preparation applies
that case's temperature, power and conductance overlays to its private typed copy,
rejects repeated target/field overlays, and marks only selected loads active.
Controls must refer to a selected load. The frozen original case definitions,
frames, expressions, geometry, environments and other entities remain in the
canonical snapshot; deferred entity IDs identify features whose execution is
still pending. Preparation does not execute imported logic or evaluate load
expressions. It performs no external file reads or process/network calls.

Components are computed from strictly positive conductors; zero conductors stay
in the typed model but do not join components. Each component records prescribed
and storage anchors. `steady_conduction_singular` diagnoses the constant
conductive Laplacian when no prescribed anchor exists.
`transient_algebraic_singular` diagnoses an algebraic component with neither a
prescribed nor capacitive anchor. An isolated capacitive node is a valid transient
initial-value component and has an undetermined conductive steady temperature;
multiple independent anchored components are valid. These flags diagnose the
conductive graph, not the future full Jacobian: radiation and other residual
callbacks can change anchoring. Singular diagnoses do not discard the model.

`model_hash` equals the existing semantic model hash. `preparation_hash` also
binds case selection, material laws and storage bindings, under its own hash
domain. Entity/source/binding order and normalized equivalent units do not alter
identity; revision/audit/GUI metadata is excluded as in model-v1. Case overlays
remain ordered input. The original canonical snapshot is retained alongside the
typed case view so later assembly cannot lose unsupported physics silently.

Each `material_laws` entry names one `material_id` and overrides one or more of
`density`, `specific_heat` and `conductivity`. Each table has temperature quantities
in `temperature`, property quantities in `values`, explicit `interpolation`
(`linear` or `previous`), `extrapolation` (`error` or `clamp`) and integer
`discontinuities`. Arrays have equal lengths, 2–16,384 entries, strictly increasing
normalized temperatures and strictly positive finite values. Knots must lie in
the material's declared valid-temperature interval. With `error`, knots must
cover that entire interval; `clamp` holds the endpoint values inside that interval.
Both policies reject temperatures outside material validity. Unoverridden scalar
properties are constant over the same validity interval.

`previous` chooses the interval on the right at a knot and the final value at the
final knot. Every changed value requires its right-side knot index in
`discontinuities`; linear interpolation rejects declared jumps. Sampling reports
the value, right-hand slope at interior linear knots, left-hand slope at the final
linear knot, and a discontinuity flag for previous-value jumps. Clamped regions
have zero derivative. Jumps are retained for future event handling.

`Material::specific_enthalpy_change(a,b)` integrates specific heat exactly by
piecewise trapezoids for linear laws and rectangles for previous-value laws,
splitting at every knot. It returns J/kg, reverses sign for reversed limits and
rejects invalid limits or arithmetic overflow. It never interpolates across a
step. Constant laws reduce to `cp * (b-a)`.

Each `node_storage` entry binds a capacitive node to a material and an explicit,
positive mass quantity. At the selected initial temperature its declared node
capacity must agree with `mass * cp(T)` to relative tolerance `1e-12`; duplicates,
algebraic/prescribed bindings and mismatches reject. Runtime capacity is
`mass * cp(T)`, and storage change is `mass * integral(cp(T), a, b)` in joules.
Without a binding, storage uses the node's explicit constant J/K capacity.
Density may vary independently, but mass stays fixed; no implicit volume or mass
creation is inferred from temperature-dependent density. Volume/mesh assignment
and spatial assembly remain WP-16.

Isotropic conductivity uses a positive scalar law. Supported anisotropy is a
constant, finite, symmetric positive-definite 3-by-3 conductivity tensor in its
explicit material frame, in W/(m K). Existing model validation and a scaled
Cholesky check reject invalid tensors. `Material::tensor(T)` returns that local
tensor, or `k(T) I` for isotropy. Supplying a scalar conductivity table with a
tensor rejects as ambiguous. Temperature-dependent tensor laws, frame transforms
for spatial assembly and general material composites remain later work.

Run unattended acceptance with:

```text
python tools/verify.py --preset windows-debug
python tools/verify.py --preset windows-release
python tools/check_thermal.py --worker WORKER_EXE --native-tests NATIVE_TEST_EXE --assembly-tests ASSEMBLY_TEST_EXE --report .local/thermal.json
python -S tools/check_security.py
```

The [acceptance register](../ci/thermal-acceptance.json) requires native analytic
constant/linear/step/clamp integrals, derivative and enthalpy checks, storage
conservation, tensor heat-flux checks, immutable/source/case loading and hostile
JSON/structure/table/binding cases, energy residuals, boundary accounting,
algebraic constraints and independent Jacobian differences. Both native acceptance executables run in
CTest and the report driver; the installed worker runs with only its own directory
on PATH and Python/host/vendor search variables removed. Both CI configurations
require `thermal.json`, validate its exact case coverage, source hashes, native
binary hashes and worker build revision in the
aggregate, and privacy-clear its actual bytes before upload. Raw compiler output,
input/output values, executable/debug files and restricted engineering models
remain local. WP-11.6 through WP-11.10, production solves, solver job integration
and full WP-11 qualification remain open.

## Energy and algebraic residuals (WP-11.3/11.4)

[`fcst/thermal_assembly.hpp`](../engine/include/fcst/thermal_assembly.hpp) exposes
`Assembly`, which owns the immutable model and callback bindings. Its unknown
temperature vector uses node equation order; the rate vector uses differential
index order only. Algebraic nodes have no rate entry. Prescribed temperatures
come from the selected model/case, or an explicit `BoundaryBinding` function of
time. They are applied before any conductive or callback evaluation, and never
enter the unknown vector. All native callback inputs and outputs use SI units.

For each conductor from node `a` to node `b`, oriented power is
`G * (T[a] - T[b])`; assembly scatters its negative to `a` and positive to `b`.
`Q[i]` is total incoming conductive, load, radiation and environment power.
The continuous residual is `F[i] = C(T[i]) * rate[i] - Q[i]` for capacitive nodes
and `F[i] = -Q[i]` for algebraic nodes, in watts. Algebraic and prescribed storage
remain exactly zero. On a prescribed node the reservoir supplies
`boundary_power[i] = -Q[i]`; positive power injects heat into the modeled node,
and negative power removes heat to maintain its prescribed temperature.

`Balance` returns effective full-node temperatures, equation-order residuals,
per-node incoming contributions by category, storage and boundary powers, and
oriented per-conductor powers. `energy_defect` is total storage power minus total
external contributions, including prescribed reservoirs. It equals the sum of
the unknown residuals, subject to floating-point summation. Internal conductive
exchange cancels; radiation and environment channels remain separately visible.

For the synthetic `material-network.json`, `State{0, {320,310}, {1}}` gives residuals
`{21.4,0}` W and prescribed boundary power `-20` W. This is an evaluation of a trial
state; a nonzero residual is reported as such.

`steady_residual` omits storage. `step_residual(time, T, previous_T, seconds)` uses
the exact enthalpy storage change divided by the supplied positive interval.
This assembles an implicit step equation; it does not select timesteps or run an
integrator. The previous vector has the same unknown ordering; algebraic entries
carry no storage. Reversed temperature changes retain their physical sign.

`PowerBinding` associates a unique entity UUID with a load, radiation or environment
callback. It declares affected full-node indexes and every temperature derivative
dependency. A callback receives time, the complete effective temperature vector
and a derivative-request flag. It returns one incoming power per affected node;
when derivatives are requested it returns one value per declared dependency,
including zeros, otherwise an empty derivative vector. Bindings execute in UUID
order. Duplicate, out-of-range or inconsistent declarations, changed result shapes,
nonfinite outputs and exceptions fail with bounded codes and source-aware UUIDs.
Native callbacks must be pure, deterministic functions of their immutable context
and arguments; the engine does not interpret imported source code.

A bound load replaces that load's scalar contribution; it is never added a second
time. Only active loads can be bound, and their affected node must match the model.
An active expression load requires a binding. Every radiation entity and every
environment selected by the case or referenced by radiation requires its own
binding. An environment binding must cover the nodes of each radiation binding
that references it. Radiation bindings supply internal modeled exchange;
environment bindings supply external exchange. Geometry-to-node mapping and the
actual radiation/environment physics remain their owners' responsibility in
WP-12/WP-17, with separately qualified energy/geometry checks.

The loader retains typed environment/radiation records and active requirement IDs.
Assembly rejects active controls until explicit control state/event handling is
implemented, and rejects unassembled conduction elements until spatial assembly
exists. Unreferenced definitions remain inert. Singular conductive components
remain inspectable/evaluable; assembly does not invent constraints or capacities
to produce a solution. Invalid states, property domains and arithmetic overflow
fail explicitly. At material jumps a residual can use the declared right-side
value, while a storage Jacobian rejects as `nondifferentiable`.

## Jacobians and backend boundary (WP-11.5)

`linearize` returns `d_temperature` and `d_rate`. The capacitive diagonal includes
`C'(T) * rate`; the rate Jacobian contains `C(T)` only on capacitive equations.
Conductive and declared callback derivatives complete the temperature Jacobian.
`combined(alpha)` returns `d_temperature + alpha * d_rate` for an implicit backend.
For an enthalpy-step equation, the storage temperature derivative is `C(T)/seconds`
and the rate Jacobian is zero. Algebraic rows always contain the derivatives of
their heat-balance constraint. Prescribed temperatures contribute to powers and
residuals but introduce no unknown columns.

`Sparsity` constructs canonical square CSR from unknown diagonals, positive
conductors and callback dependencies. Duplicate entries are merged in sorted
order; numerical additions outside the pattern reject. Zero algebraic diagonal
entries are structural entries, not storage. Storage is proportional to declared
nonzeros, with bounded dimensions and entry counts; no dense all-pairs allocation
is required. The synthetic 100,000-node tridiagonal check verifies 299,998 entries
and a manufactured matrix-vector product, without making a solver throughput claim.

`LinearBackend` and `NonlinearBackend` define synchronous backend-independent
interfaces with `converged`, `singular`, `nonconverged` and `unsupported` outcomes.
They borrow inputs only for the call. `steady_problem` and `step_problem` factories
own their assembly snapshot and fixed parameters. Guarded problem evaluations
check shape, finite values and the exact declared Jacobian pattern.

`solve_linear` and `solve_nonlinear` validate options and backend results, then
recompute the infinity-norm residual independently of the backend's reported norm.
Convergence must satisfy `atol + rtol * reference`, with `reference = norm(rhs)` for
linear systems and `norm(F(initial))` for nonlinear problems. Invalid convergence
claims reject; failed outcomes remain failed outcomes. This is the interface
contract, not the production scaling/stopping strategy required by WP-11.6.
Backend exceptions are sanitized; a backend cannot swallow a malformed guarded
problem evaluation and subsequently claim success.

Acceptance compares all temperature and rate Jacobian entries, the combined
implicit Jacobian, and steady/enthalpy-step Jacobians against independently
perturbed residual evaluations on smooth fixtures. Nonlinear radiation, cross-node
load dependence, environment exchange and variable capacity are exercised together.
Analytic-answer test adapters verify both backend interfaces and false-convergence
rejection. Production linear/nonlinear steady algorithms, stiff time integration,
event handling and solver job/result publication remain WP-11.6 through WP-11.10;
`solver_available` stays false.
