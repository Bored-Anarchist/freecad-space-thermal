# Owned CPU radiation engine (WP-12)

The native C++20 engine in `fcst/radiation.hpp` supplies immutable radiation
meshes, a median-split BVH, deterministic sampling, sparse exchange artifacts,
diffuse-gray radiosity and thermal residual/Jacobian bindings. It runs on the
supported Windows build without Python, FreeCAD, Embree or licensed solvers.
Python is used by the unattended qualification driver and independent reference
calculations. Specular, transmissive and wavelength-dependent transport remain
WP-20; orbital/projected environmental loads remain WP-17.

Each triangle has a stable facet ID, surface ID, full thermal-node index, group,
SI coordinates and separately activated front/back optics. Winding defines the
front. Surface/side aggregation requires identical node, group and optical
assignments; a curved surface may contain many triangles. Construction rejects
duplicate or unknown identities, inconsistent mappings, degenerate geometry,
nonfinite coordinates and out-of-range optical properties before tracing.
Coordinates are limited to magnitude 1e12 m and triangle area must exceed 1e-24
m2. CAD repair, intersection between input triangles and general nonmanifold
topology repair are outside this API; callers provide a conforming triangulation.

Optical datasets distinguish solar and infrared band labels, temperature domain,
BOL/EOL/unspecified condition, absolute uncertainty and provenance. These are
constant opaque diffuse-gray properties over the declared domain, with no
specular or transmission terms. Native constant-property callers get explicit
caller-declared defaults; the worker requires the complete dataset declaration.
Property uncertainty is retained separately from sampling uncertainty and is
not propagated as a probabilistic material model. Solar absorptance is never
substituted for infrared emittance.

`Mesh::intersect` returns the nearest two-sided hit with deterministic ID ordering
for exact ties. Tests exercise hits, misses, edges, parallel rays, back faces and
subdivided geometry independently of Monte Carlo estimators. The backend is
replaceable through `IntersectionBackend`. A source facet is ignored and origins
are moved one representable coordinate toward the emitting side. Surface points
are sampled uniformly by triangle area and directions with cosine-weighted
hemispherical density. SplitMix64, a specified 53-bit uniform map and FNV-1a
surface/side identity hashing define independent streams; source traversal,
input ordering and thread scheduling do not select new streams. Replay is
qualified on the same reference floating-point/toolchain configuration.

Explicit facet exclusions remove geometry from tracing. A nearest hit on an
inactive side or another radiation group is counted as **blocked**, separately
from geometric escape. Such hits terminate at the specified isothermal black
reservoir; they do not transmit through an opaque blocker. Use a separate active
group/model when a blocker must have its own solved temperature. This boundary
assumption is part of the model, and must match any source comparison.

`trace_row` streams a bounded sparse histogram and retains every hit, blocked and
escape count. There is no dense facet-by-facet matrix. `Exchange` validates exact
row accounting and stores raw evidence separately from corrected area factors.
It averages reciprocal `A_i F_ij` estimates, applies symmetric endpoint row caps,
and assigns the remaining fraction to the explicit reservoir. For entirely
closed ensembles, symmetric diagonal balancing restores row closure, or fails
explicitly if its 10000-iteration limit cannot be met. Raw closure, maximum raw
reciprocity defect and maximum directed view-factor correction are reported.
Independent tests check bounds, reciprocity, closure, analytical agreement and
the correction magnitude. Corrected factors never replace raw estimator counts
in statistical acceptance. `page` limits edge queries to 4096 records.

IR radiosity solves

```text
J_i = epsilon_i sigma T_i^4 + (1-epsilon_i) [sum_j F_ij J_j + escape_i sigma T_env^4]
```

by sparse fixed-point iteration with a separately recomputed equation residual.
Unanchored perfectly reflecting components, iteration exhaustion, nonfinite
states and invalid domains fail explicitly. A separate solar radiosity solve
uses absorptance and caller-supplied incident W/m2, including diffuse multiple
reflection. These inputs must already include environment projection and
occlusion. Internal power is assembled once per reciprocal edge with equal and
opposite contributions; background exchange and absorbed solar power are
external terms. Powers and analytic derivatives are coupled to the WP-11 thermal
assembly through separate radiation and environment bindings, preventing
double counting in its energy budget.

Radiative derivative columns solve the same sparse radiosity operator. The
thermal binding currently allows at most 65536 node dependencies (256 distinct
nodes by default); it rejects larger fully coupled Jacobians before allocating
them. This limit applies to coupled thermal nodes, not triangle count. Standalone
radiosity and row tracing remain sparse. Constant fourth-power reduced couplings
are appropriate only for frozen geometry/visibility, areas and constant optics;
they must be rebuilt when those change. Temperature-dependent or moving optics
are not silently frozen by this implementation.

The installed worker accepts a strict, at-most-1 MiB JSON envelope on stdin:

```text
fcst-worker --radiation-evaluate < tests/fixtures/radiation/plates.json
fcst-worker --radiation-steady < tests/fixtures/radiation/steady.json
```

The synthetic fixtures document version 1 fields and units. The bounded worker
allows up to 4096 input facets, 4096 sparse entries and one million rays per
patch. The C++ streaming API supports larger meshes (up to two million facets)
and declared resource budgets. The steady envelope embeds `thermal_input` and
omits `temperatures_K`; it supports one diffuse radiation entity and its sole
environment, checks facet IDs, areas, active sides and optical assignments against
the normalized thermal model, and uses canonical full-node order. Case overlays
and nonzero environmental solar flux reject in this command until their WP-17
integration exists. Native callback bindings also support WP-11 transient solves;
durable jobs and GUI wiring retain their existing separate qualification gates.

`tools/check_radiation.py` executes native acceptance, installed-worker boundary
and replay tests, coupled steady acceptance, and the original WP-04 ensemble:
16 fixed seeds at 4096/16384/65536 rays. The quantities in
`ci/radiation-acceptance-v1.json` are frozen before execution. All 576 intervals
share a Bonferroni family; every observation/miss is retained, every final-size
quantity must meet 0.01 absolute error, and aggregate RMS error must decrease at
both refinements. Missing/duplicate/substituted runs and altered metrics reject.
Failed attempts remain local; selective reruns cannot replace failed evidence.

Analytical plate references follow [Howell's C-11 configuration-factor
catalog](https://www.thermalradiation.net/calc/sectionc/C-11.html). An independent
SciPy quadrature integrates the square-plate kernel. Cube opposite faces use the
same geometry. Concentric-sphere references use reciprocity and closure as in
the [COMSOL verification formulation](https://doc.comsol.com/6.4/doc/com.comsol.help.models.heat.view_factor/view_factor.html),
with independently generated homothetic triangulations of radii 1 and 2.
Separate NumPy dense IR/solar solves and a scalar steady root compare actual
native powers and temperatures. These are analytical/formulation comparisons,
not executions of COMSOL or licensed TD/ESATAN. Vendor compatibility and overall
project Q1 remain unqualified under their existing WP-19 gates.

Three retained repetitions at each sample count measure 1024, 10000, 99856 and
1000000 facets. The public `radiation.json` contains build time, ray throughput,
accounted storage, measured process peak working set, error and input/build/raw
hashes for every repetition. Process peak includes construction allocations;
accounted storage is an estimate excluding allocator overhead. Timings describe
the measured configuration and are not a throughput promise. Both Windows CI
presets run the same driver, and the foundation handoff recomputes statistical
and scaling coverage against the exact candidate and source hashes.

TST-021 preflight scans exact staged/history/identity bytes, synthetic fixtures,
native/Python sources, frozen criteria, documentation, final GitHub prose and
the bounded `radiation.json` before publication. Raw trajectories, mesh/result
containers, executables, debug information, compiler/runtime logs, engineering
originals and local environment identity remain local. CI clears the exact final
report before artifact upload; no privacy exception is introduced.
