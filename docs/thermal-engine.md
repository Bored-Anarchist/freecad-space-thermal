# Owned thermal model preparation

WP-11.1 and WP-11.2 provide the C++20 API in
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
python tools/check_thermal.py --worker WORKER_EXE --native-tests NATIVE_TEST_EXE --report .local/thermal.json
python -S tools/check_security.py
```

The [acceptance register](../ci/thermal-acceptance.json) requires native analytic
constant/linear/step/clamp integrals, derivative and enthalpy checks, storage
conservation, tensor heat-flux checks, immutable/source/case loading and hostile
JSON/structure/table/binding cases. The native acceptance executable runs in
CTest and the report driver; the installed worker runs with only its own directory
on PATH and Python/host/vendor search variables removed. Both CI configurations
require `thermal.json`, validate its exact case coverage and source hashes in the
aggregate, and privacy-clear its actual bytes before upload. Raw compiler output,
input/output values, executable/debug files and restricted engineering models
remain local. WP-11.3 through WP-11.10, production solves, solver job integration
and full WP-11 qualification remain open.
