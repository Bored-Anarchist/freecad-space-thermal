# Owned thermal preparation, assembly and steady solving

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
python tools/check_thermal.py --worker WORKER_EXE --native-tests NATIVE_TEST_EXE --assembly-tests ASSEMBLY_TEST_EXE --steady-tests STEADY_TEST_EXE --report .local/thermal.json
python -S tools/check_security.py
```

The [acceptance register](../ci/thermal-acceptance.json) requires native analytic
constant/linear/step/clamp integrals, derivative and enthalpy checks, storage
conservation, tensor heat-flux checks, immutable/source/case loading and hostile
JSON/structure/table/binding cases, energy residuals, boundary accounting,
algebraic constraints, independent Jacobian differences and steady solves. All native acceptance executables run in
CTest and the report driver; the installed worker runs with only its own directory
on PATH and Python/host/vendor search variables removed. Both CI configurations
require `thermal.json`, validate its exact case coverage, source hashes, native
binary hashes and worker build revision in the
aggregate, and privacy-clear its actual bytes before upload. Raw compiler output,
input/output values, executable/debug files and restricted engineering models
remain local. The later sections describe the implemented WP-11.7 through
WP-11.10 transient/event APIs and numerical qualification; durable-job integration
retains its separate follow-on gate.

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
external load/environment contributions, including prescribed reservoirs.
`internal_exchange_defect` records net conductive and internal radiation power,
which should be zero. Energy defect equals the sum of unknown residuals plus
this internal defect, subject to floating-point summation. A nonconservative
radiation callback remains visible as an energy defect; it is never reclassified
as an external source or silently normalized. Radiation and environment channels
remain separately visible.

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
contract. The steady scaling/stopping strategy is defined below under WP-11.6.
Backend exceptions are sanitized; a backend cannot swallow a malformed guarded
problem evaluation and subsequently claim success. `EvaluationDomainError`
identifies a recoverable physical trial domain, allowing a native algorithm to
backtrack. Shape, nonfinite protocol arguments and ordinary callback failures
remain fatal. Assembly steady-problem factories classify physical range failures
this way; they do not execute imported logic.

Acceptance compares all temperature and rate Jacobian entries, the combined
implicit Jacobian, and steady/enthalpy-step Jacobians against independently
perturbed residual evaluations on smooth fixtures. Nonlinear radiation, cross-node
load dependence, environment exchange and variable capacity are exercised together.
Analytic-answer test adapters verify both backend interfaces and false-convergence
rejection. Native steady algorithms are implemented under WP-11.6 below. The later
WP-11.7 through WP-11.10 sections implement stiff integration and events.
Durable-job/result integration remains separate; the frozen job protocol's
`solver_available` stays false.

## Native steady solves (WP-11.6)

[`fcst/thermal_steady.hpp`](../engine/include/fcst/thermal_steady.hpp) supplies
`SparseLuBackend`, `DampedNewtonBackend` and `solve_steady`. This is an owned
steady numerical implementation. The Q0 CVODE/BDF transient decision remains
unchanged; no new external dependency or thermal application is required.

Sparse LU uses row/column equilibration, deterministic partial row pivoting and
sparse row/column indexes. It retains lower and upper factors for iterative
refinement. It checks both the requested residual criterion and a row-wise
backward error, protecting small equations from an unrelated large RHS. Defaults
bound dimension at 100,000 and factor storage at 1,000,000 entries, with a scaled
pivot threshold of `64 * machine_epsilon`, backward error tolerance `1e-12` and
at most three refinement corrections. Fill exhaustion returns `unsupported` with
`fill_limit`; a zero/numerically deficient pivot returns `singular`. No tiny
pivot, capacity, anchor or dense fallback is inserted. These bounds describe the
supported kernel, not a throughput or arbitrary-graph conditioning guarantee.

Newton obtains an analytic sparse Jacobian and an independently checked LU
direction at each accepted state. Backtracking requires sufficient decrease in
the scaled infinity-norm residual (Armijo coefficient `1e-4`, factor `0.5`, at
most 32 backtracks), or satisfaction of the residual tolerance. Bounds restrict
every trial. A recoverable physical-domain failure rejects the trial and permits
a smaller step. Ordinary model/callback errors stop the solve. A step that rounds
to the unchanged temperature vector is diagnosed as stagnation, not convergence.

`solve_steady` selects direct linear corrections for constant conductors and
temperature-independent power bindings. Temperature-dependent power dependencies
select damped Newton. The explicit direct-linear method rejects temperature
dependencies whose affinity is not established; such models can use Newton.
Both paths use the same residual, prescribed temperatures and zero-storage
algebraic equations. Multiple independent anchored components are supported.
An unanchored conductive component is diagnosed from its actual Jacobian, rather
than the conductive graph alone: a nonlinear environment callback can supply a
valid anchor. Even an initially zero residual must pass the Jacobian rank check.
All-prescribed models legitimately have no unknowns.

Per-equation power scales are frozen at the initial state. By default each is the
maximum of the initial residual magnitude, its incoming contribution magnitudes,
and `abs(J[i,j]) * temperature_scale[j]`. Temperature scales default to
`max(1 K, abs(initial_temperature))`. Explicit positive per-equation power scales
and per-variable temperature scales are supported. An identically zero row uses
a placeholder scale only for arithmetic; it still fails the rank check.

The physical row limit is `absolute_power_tolerance + relative_power_tolerance *
power_scale[i]`, with defaults `0 W` and `1e-10`. These limits remain fixed during
the solve. The scaled infinity residual must be at most one. The newly computed
Newton correction must also be at most one when normalized by
`absolute_temperature_tolerance + relative_temperature_tolerance *
temperature_scale[i]`, defaulting to `1e-8 K` and `1e-10`. A small correction
alone cannot indicate success. Default iteration limit is 50 accepted updates;
iteration exhaustion and line-search/bounds/stagnation failures retain failed
status and the last valid temperature state. Limits below representable numerical
range fail explicitly. Initial values must satisfy physical/material bounds;
additional user temperature bounds can narrow them.

After numerical convergence, the engine independently recomputes residuals and
the physical heat budget. Both global energy defect and internal exchange defect
must satisfy `absolute_energy_tolerance + relative_energy_tolerance * reference`,
default `0 W` and `1e-10`. The reference contains actual exchanged powers, not
large Jacobian coefficients or `G*T`: a rounded-away temperature gradient cannot
hide an unbalanced load. Each radiation callback's own net power is checked
relative to its own absolute power, preventing opposite defects or large unrelated
networks from hiding a nonconservative callback. No callback is normalized to
force a pass. An energy failure changes the outcome to `nonconverged`.

`SteadyResult` includes the selected method, temperatures, physical balance,
frozen power scales/row limits, normalized residuals, iteration/evaluation/rejected
trial counts, correction norm and bounded reason codes. Singular/fill failures
carry available equation/entity/source-map context. `converged`, `singular`,
`nonconverged` and `unsupported` are distinct outcomes. Invalid configuration is a
bounded input error; a failed numerical run is never marked successful.

The standalone worker accepts a thermal-input-v1 envelope on stdin with
`--thermal-steady`. Its default settings solve supported constant networks and
return full-node temperatures, boundary power, residuals, limits, provenance
hashes and diagnostics as JSON. Exit status zero requires convergence and energy
acceptance. The native API additionally supports registered native nonlinear
callbacks and configurable solver options. Models needing callback physics or
control/spatial execution cannot silently gain support through the CLI.

Build information declares `steady_available: true`. The existing
`solver_available: false` refers to the frozen durable-job protocol, whose steady
result/checkpoint publication is still pending; `--solve` and durable job/result integration are not enabled by the steady substep.
The following transient API supplies the later WP-11.7 through WP-11.10 work.

Acceptance includes hand-authored analytic steady values, a nonlinear quartic
radiation/environment network, later-stage row pivots, a manufactured 10,000-row
tridiagonal solve checked at every entry, components spanning 200 orders of
conductance, domain/merit backtracking, zero-residual singular systems,
temperature bounds, fill/iteration limits, false small-step convergence, energy
defect cancellation and unrepresentable temperature gradients. The standalone
CLI runs with Python/host/vendor search paths absent. Existing Q0 dense/band
comparisons still run as their own numerical checkpoint; this does not replace
their evidence or assert a new performance ranking. Paired vendor qualification and durable-job/host integration remain separate.
The owned implementation acceptance below adds independent transient comparisons.


## Adaptive transient execution (WP-11.7)

`thermal_transient.hpp` exposes `solve_transient(Assembly, TransientOptions,
optional<TransientCheckpoint>)`. The engine is compiled C++20 and requires no
FreeCAD, Python, SUNDIALS or external thermal solver to execute. The owned
backward Euler step is L-stable and solves
`[H(T_new)-H(T_old)]/dt - Q(t_new,T_new) = 0` on differential rows and `-Q=0`
on algebraic rows. Prescribed nodes stay outside the unknown vector. Initial
consistency fixes differential temperatures exactly and solves algebraic rows;
differential rates then follow from `Q/C(T)`. A singular algebraic block fails
initialization. Higher-index/underdetermined systems are not regularized.

Every candidate interval solves one full step and two half steps. The accepted
state is the two-half-step solution, with no extrapolation. Their temperature
difference estimates the first-order local error. The maximum over **all**
unknowns of `abs(T_half2-T_full)/(atol_i + rtol*max(abs(T_old),abs(T_half2)))`
must not exceed one. Default absolute tolerance is `1e-5 K`, relative tolerance
`1e-6`; optional positive per-equation absolute tolerances use equation order.
The controller uses `0.9/sqrt(error)` clipped to `[0.5,2]` after acceptance and
`0.8/sqrt(error)` clipped to `[0.1,0.5]` after a tolerance rejection. Failed
nonlinear/domain trials reduce the step by four. No trial changes committed
thermal/event/duty/energy state. Attempts retain time bounds, error and reason;
failures, minimum-step/time-representability and iteration/fill/attempt limits
produce an invalid run with the last committed checkpoint, never a successful
partial trajectory.

Newton uses the owned sparse LU and analytic enthalpy Jacobian. Frozen row
limits within each nonlinear solve use `max(1e-12 W, 1e-12*abs(Jij)*Tscale_j)`;
initial fixed-temperature rows use `1e-10 K`. Both normalized power residual and
a fresh correction (`1e-10 K + 1e-12*Tscale`) must pass, including a Jacobian rank
check. Temperature trials respect nonnegative K and each storage material's
validity range. Nonfinite callbacks, malformed derivatives and callback failures
are fatal; recoverable physical-domain trials can backtrack/reject. A property
law's exact nondifferentiable endpoint reports `nondifferentiable` rather than
inventing a derivative.

`output_times` must strictly increase from the original `start` through `end`.
The integrator clips steps at requested times, schedule knots and the horizon,
then re-solves; it does not interpolate requested temperatures. Results also
include committed event samples and the restart point. Default initial/maximum
steps are `0.01/1 s`, minimum step `1e-12 s`, with 100,000 attempts, 10,000 events
and 30 Newton iterations. Scalar result storage is bounded separately (default
two million values); exceeding it returns `result_limit`. There is no mandatory
dense network matrix or unbounded output buffer.

## Heater/schedule events and restart (WP-11.8)

Active controls are loaded into typed UUID-ordered `Data::controls`. An assembly
with controls needs an explicit `OperatingState`; `initial_operating_state(model)`
starts heaters off. Initial consistency then switches a heater on at or below
`on_below`, off at or above `off_above`, and retains the supplied state inside the
deadband. Positive hysteresis width is required. Two controls cannot own the
same load. The controlled load and its declared temperature derivatives are
gated together; native callbacks remain pure functions of the supplied snapshot.

`LoadSchedule` contains a load UUID and strictly increasing `(time_s,factor)`
points. Schedules are sorted by UUID, start no later than the original run, and
use nonnegative right-continuous multipliers. The old multiplier is frozen on
the interval ending at a knot; the new multiplier applies immediately after it.
Thus no implicit step averages a heater/schedule discontinuity. Schedules multiply
the native load (including a registered load callback); they do not replace its
power or bypass a heater gate. Boundaries and other callbacks must be smooth
within a step; arbitrary undeclared time discontinuities are not supported.

Directional heater guards are inspected at both accepted half-step endpoints.
The first detected crossing is localized by bounded bisection, repeatedly solving
the implicit path rather than accepting interpolated temperatures. Default event
time tolerance is `1e-8 s`; roots within that tolerance form one batch at the first
root. Continuous guards must have no hidden crossing-and-return within a half
step; callers choose `maximum_step` accordingly for oscillatory native forcing.
Exact sampled threshold hits can switch; hidden tangencies have no detection guarantee. This is an
explicit supported detection contract, not a promise to detect arbitrary
oscillation inside an unsampled interval.

At a batch, schedules apply in load UUID order, then heater switches in control
UUID order using the same pre-event temperatures/state. The assembly is replaced
immutably and algebraic consistency is solved again while differential
enthalpy/temperature stays fixed. Any newly triggered algebraic-sensor switches
are processed in another bounded batch. A repeated switch within
`minimum_event_separation` (default `1e-10 s`), 32 nonsettling reinitializations,
or the event limit fails with `chattering`/`event_limit`. Failed batches do not
publish provisional events or a new checkpoint. On-time is integrated only for
accepted pre-event intervals; duty is on-time divided by original elapsed time.

A version-one checkpoint contains original/committed temperatures, original and
current time, next step, heater and scheduled factors, last-switch times,
on-time, accepted/rejected/event counts and cumulative energy. SHA-256 binds
all these values. The configuration digest also binds preparation identity,
compiled source revision, numerical tolerances/limits/backend settings, original
operating state, schedules and native callback revision. Callback callers must
supply their exact registration/build SHA-256 as `callback_revision`; changing
callback semantics without changing that digest violates the API contract.
The CLI computes this digest from its explicit constant environment bindings.

A restart validates the checksum/configuration, finite dimensions, active state,
schedule position, duty/time bounds and algebraic consistency before advancing.
A changed end time/requested sampling horizon is allowed; numerical configuration,
original start and physics must match. Include any comparison/restart split as
an output boundary in both runs for identical adaptive paths. The new run emits
the checkpoint sample, then samples after it; earlier output times are not
fabricated. This native checkpoint is separate from the frozen durable-worker
transport checkpoint and does not claim job/HDF5 publication support.

## Results, conservation and profiling (WP-11.9/11.10)

Each valid committed sample includes full-node temperature, conductive/load/
radiation/environment/storage/boundary power, oriented conductor flows, equation
residuals, differential rates, exact storage change since the original start,
operating state and duty cycles. Units are K, W, K/s, J and SI seconds. Node,
conductor and equation UUID arrays define every vector index in the CLI.
Algebraic/prescribed storage is exactly zero. Prescribed reservoir power remains
positive into the modeled network. Prefix samples can be valid when the overall
run fails; only `TransientResult.valid` / CLI `status: passed` denotes completion.

Each accepted half step independently checks exact enthalpy change against its
endpoint power quadrature, per unknown equation and globally. Internal radiation
is never external energy; each registered internal radiation term must balance
on its own before terms can cancel. Two half-step budgets are combined for the
accepted interval; rejected trials contribute nothing. Cumulative storage is
recomputed from original enthalpy, not integrated `C*Tdot` or accumulated rounded
small changes. Global run defect is storage minus external energy (loads,
environment and prescribed reservoirs). Default energy acceptance is `1e-8 J +
1e-8*absolute_exchanged_energy`; it uses actual exchanged powers, not `G*T`.
Step and cumulative budgets include per-node storage/external/conductive/boundary
energy, absolute exchange and defect. Endpoint quadrature is the stated backward
Euler discretization, not a claim of exact continuous power integration.

Provenance carries model/preparation/configuration hashes and compiled source,
compiler/version and backend IDs. Native counters measure residual/Jacobian
evaluations, sparse LU solves, Newton iterations and event probes. Monotonic
wall-clock timings cover assembly, sparse factor/solve work and the full native
integration call; they include rejected/probe work. These are measured profiling
records, not hardware-normalized throughput promises. `--thermal-capabilities`
returns the explicit owned LU/Newton/transient backend, stiff/index-one DAE,
enthalpy/event/checkpoint support and `external_reference: false`. No external
reference execution mode can pass native acceptance. Paired vendor/reference
runs belong to their separate qualification modes and reports.

## Standalone transient CLI and acceptance

`fcst-worker --thermal-transient` consumes a bounded one-MiB JSON object:

```json
{
  "thermal_input": {"contract_version": "1.0.0", "model": {}, "material_laws": [], "node_storage": []},
  "transient": {"start": 0, "end": 10, "output_times": [0, 5, 10]}
}
```

The abbreviated `model` above must be a complete valid model-v1 snapshot. The
`transient` object accepts the named scalar limits/tolerances above, optional
`temperature_tolerances` and `schedules` (`load_id`, `points` with `time`/`factor`).
Optional top-level `initial_operating` has `heaters` and `load_factors` maps;
`checkpoint` accepts the exact serialized native checkpoint from a prior run.
Optional `environment_power_W` explicitly maps active environment UUIDs to
constant full-node W arrays. Zero exchange must be explicitly supplied; geometry,
unknown radiation laws, expression execution and spatial elements are not silently
omitted. Native API users supply their own registered nonlinear bindings.
Unknown keys/modes, bad JSON/types/counts and stale/mutated checkpoints fail with
bounded codes. The adapter never evaluates imported source code or echoes unknown
input text. Exit zero requires completed native acceptance of the trajectory.
`--build-info` adds `transient_available: true`; durable-job `solver_available`
remains false until that transport's result integration is implemented.

`tools/check_thermal.py` requires all five compiled binary hashes and native
execution/build identity in report schema five. Both Windows presets run the
same required cases and privacy-clear the exact summary before upload. Cases
cover analytic single/two-node cooling and conservation, a 10 ns fast mode,
nonlinear specific heat/enthalpy, consistent DAE/boundary power, tolerance
refinement, an independent explicit RK4 nonlinear ODE comparison at two refined
steps, exact sampling, rejection accounting, heater timing/duty, schedules,
simultaneous ordering, checkpoint/restart equivalence and tamper rejection,
chattering, energy defects, storage/fill/attempt/domain failures and profiling.
The independent oracle never calls owned assembly/implicit/property-integral
code; external solver results cannot replace any required native case. Public
evidence is bounded source/build/hash/verdict data. Raw trajectory/checkpoint
arrays, binaries and compiler/backend logs stay local under TST-021.


The consistency and sign-change event assumptions were cross-checked against
[the SUNDIALS IDA mathematical discussion](https://sundials.readthedocs.io/en/v7.7.0/ida/Mathematics_link.html)
and [LLNL usage notes on discontinuities and reinitialization](https://computing.llnl.gov/projects/sundials/usage-notes).
These references are background, not executable dependencies or acceptance substitutes;
the owned method and its thresholds are specified above.


## Requirement qualification and captured references

[The qualification/oracle register](../ci/thermal-qualification-v1.json) maps
ARC-009/015, PHY-001/005/006/007 and TST-004 to mandatory native case IDs.
Report schema five derives each native requirement verdict from those actual
case records. Missing, duplicate, failed or substituted required cases fail the
owned gate. Event metrics must demonstrate error reduction under fixed step-cap
halving; network metrics must come from 256 equations/766 CSR entries. Source
comparison receipts bind the exact fixture/source bytes and report numerical
errors across capacitive, algebraic and prescribed nodes. The assessor rejects
stale fixture hashes, wrong execution modes, missing coverage and inflated
vendor/Q1 claims. This is actual coverage evidence alongside the planning CSV,
whose `planned` statuses intentionally do not serve as test results.

The event-refinement fixture uses the independent analytic heater times
`log(16/5) + k*log(3)` after its initial switch. Temperature tolerances are loose
so caps 0.2, 0.1 and 0.05 s actually govern accepted steps. The maximum event-time
error must shrink by at least a factor of 0.65 on each halving, reach below
0.07 s at the finest cap, and the finest duty error must be below 0.02.
The tighter existing adaptive heater checks remain required separately; the
root-localization tolerance is not a continuous-solution error guarantee.
The workload profile manufactures `T=300+t` on a strongly coupled 256-node
capacitive chain plus a prescribed ramp, with one watt per capacitive node.
Every final temperature and total storage has an independent exact value.
Profiling includes all sparse Jacobian and LU work; timings imply no hardware
qualification or throughput guarantee.

Owned source-literal fixtures describe the same three-node network in constant
SINDA 6.3 and ESATAN 2018-SP1 syntax, using K and degC respectively. Independent
file adapters reconstruct the models; the C++ CLI solves each with all three
node classes. Frozen constants give `Tcap=304+6*exp(-t/2)`,
`Talg=(Tcap+300)/2`, `Tboundary=300`, reservoir power `-(Tcap-300)` W and
storage `2*(Tcap-310)` J. Steady values, transient samples, physical constants,
identities and energy are checked; changed loads/temperatures/powers/storage,
missing times, NaN and reference-mode substitution reject. These tests do not
execute SINDA, AutoCAD/TD or ESATAN and do not count as licensed comparisons.

`python tools/compare_thermal_reference.py --manifest LOCAL_MANIFEST --worker
WORKER_EXE --report LOCAL_REPORT` supplies the offline captured-result path.
Without a manifest it writes a bounded `blocked` report and exits two. A manifest
has version `fcst-thermal-captured-reference/1`, execution mode
`reference_external`, ecosystem `sinda` or `esatan`, explicit source version and
five units (temperature, capacity, conductance, power, time). `model`, `results`
and `receipt` are relative path/SHA-256/byte-length artifact references.
The model must be one fully supported constant source deck; includes/unsupported
physics cannot be dropped. Originals are read unchanged and parsing occurs in
an isolated temporary copy. Traversal, links, changed lengths/hashes and
unresolved source semantics reject before comparison.

The receipt binds execution mode/ecosystem/source version, source-model and
result hashes, and SHA-256 identities for executable, settings, run and review
decision. SINDA results use the bounded assigned-value print reader; ESATAN
results require the exact `TmdBinding` object in `tmd_binding`, including matching
result/canonical-model hashes, case, producer/schema and model namespace map.
The existing safe HDF5 reader checks the TMD payload. The tool executes only the
explicit owned worker, with host/Python/vendor search paths absent from its
native process, and matches every node and source time without interpolation.
Frozen temperature limits are 0.01 K plus 1e-6 relative. Unknown modes, malformed
receipts, missing/ambiguous identities, truncated times, nonfinite values and
numerical mismatches fail. Reports contain hashes, bounded counts/errors and
fixed verdicts; raw decks, result arrays and receipts remain local.

A passing captured comparison **does not authenticate a receipt or verify a
license**. It always retains `vendor_qualified: false` and `q1_qualified: false`;
reviewed licensed-profile admission belongs to the separate Q1 gate. The public
contract test uses explicitly synthetic printed samples and receipts and proves
that a successful replay cannot promote its qualification. With no approved
runner/reference pair available, `native_qualification.licensed_paired_status`
stays `blocked`. Full qualification also retains the host/MCP and coupled
radiation/environment obligations assigned to their owning packages. No missing
licensed gate is skipped, relabeled passed, or assigned as a manual user test.


The workload suite also runs a localized one-watt load into the first node of
that 256-node conductive chain with a fixed 300 K reservoir. It checks maximum
principles, total enthalpy, energy defects and actual repeated compiled work.
This case exposed spurious LU `linear_residual` failures in subnormal diffusion
correction tails. The componentwise check now subtracts a conservative arithmetic
allowance before forming its relative error: `(4*nz+2)*eta` for rounded row
operations plus `2*abs(Aij)*eta` for each subnormal solution component, where
`eta` is `double::denorm_min()`. The propagated term accounts for quantization of
an unrepresentably small correction before multiplication by a large coefficient.
Normal-component backward error, pivots, matrix equations, nonlinear/temperature
criteria and independently recomputed global residual/physical energy checks
retain their existing limits. There is no new capacity, diagonal regularization
or user-tolerance relaxation. An analytic tridiagonal geometric-tail regression
checks representable entries and subnormal absolute errors; an `eta/3` problem
must still fail relative-only global residual acceptance.

The arithmetic rationale is the gradual-underflow absolute-error property in
[Oracle's numerical computation guide](https://docs.oracle.com/cd/E77782_01/html/E77791/z4000ac020351.html).
The safeguard and its regression are owned code, not a copied numerical library
implementation. Profiles remain measured workloads rather than performance
qualification on a reference hardware profile.

## Independent numerical sign-off

The user-approved [alternative reference profile](../ci/thermal-reference-v1.json)
requires a separate executable SUNDIALS IDA 7.3.0 full-DAE formulation and SciPy
1.15.2 Radau reduced-ODE formulation across eight owned cases. Pycanha core
0.23.0 additionally runs refined constant-capacity cooling, closed-network and
zero-capacity-DAE trials. [The reference contract](../references/thermal/README.md)
specifies equations, accuracy settings, analytic oracles, event/energy/steady
comparisons, artifact identities and explicit adapter exclusions. The native
subject alone uses engine model loading, assembly and algorithms. External
reference code never links/imports those implementations.

`python tools/check_thermal_references.py --subject PATH_TO_SUBJECT
--configuration Debug --report .local/thermal-references.json` runs the same gate
as both Windows verification presets. It requires 46 distinct run receipts and
63 comparisons; all 80 existing native cases remain mandatory. The public
summary is candidate/source/binary/runtime bound and the standard-library
assessor rejects missing, stale, failed, nonfinite, duplicated or substituted
reference evidence. CI scans the exact summary before upload and the foundation
aggregate reassesses it. Compiler/runtime logs, downloaded dependencies,
binaries and raw numerical arrays remain local.

The new exact-grid enthalpy benchmark exposed a decimal capped-step remainder
smaller than the allowed minimum step just before the requested end time. The
native integrator now splits the remaining interval when a capped step would
leave such a remainder. Both subintervals are solved with their actual duration;
no elapsed time is skipped and no step cap or accuracy criterion is relaxed.
The native enthalpy acceptance case checks every requested knot and final energy.

Passing this profile closes engine numerical sign-off under PHY-001; absence
of a licensed reference runner does not block that claim. Vendor-specific
TD/SINDA and ESATAN compatibility remains unqualified, and their wider source
semantics, host/MCP parity, radiation/environment and durable-job integration
retain the owning work packages and project Q1 gates. No external solver is a
production dependency or a substitute for native acceptance.
