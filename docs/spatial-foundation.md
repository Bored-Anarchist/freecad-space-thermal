# Spatial foundation handoff (WP-05.5)

The spatial capability `spatial-linear-vertex-v2` is a bounded preparation for the
production spatial solver and workbench. It accepts positive-volume linear
tetrahedra (tet4) and nondegenerate surface triangles (tri3). A triangle is an
oriented facet, with area equal to half the cross-product magnitude; it does not
imply a shell formulation or thickness. Tet volume is the positive determinant
of its three local edges divided by six. Connectivity is zero-based and ordered
as written; right-handed tet ordering and triangle outward orientation belong
to the immutable mesh revision. No midside node is discarded. Shells, mixed
orders, higher-order cells, integration-point fields, tensors as result fields
and projected/averaged results fail explicitly.

CAD faces, mesh vertices, conduction elements, surface facets and thermal nodes
have separate UUID domains. Maps carry positive areas, provenance and weights
that sum to one per source and target kind. An ordering change requires an
explicit remapping and a new mesh revision. Ambiguous split/merge/delete or
replacement attachments require reassignment, even when signatures match.

Coordinates, conductivity, density, heat capacity, boundary values and sampled
fields use SI. Frames are right-handed orthonormal local-to-global matrices.
Conductivity is a symmetric positive definite tensor in its declared frame;
isotropy uses equal diagonal entries. Temperature is absolute K. Heat flux is
the raw vector `q = -K grad(T)` in W/m2, with x/y/z components and explicit frame,
vertex UUID order and sample times. Positive boundary power is `area * q dot n`
for the declared outward normal. Integrated power in W cannot masquerade as
heat flux. Only static prescribed temperature, surface flux and total power
boundary declarations are accepted; time-dependent boundary laws remain later
work. Synthetic sample data do not claim an executed spatial solve.

The generated [spatial schema](../spec/schemas/spatial-v2.schema.json) and
[manifest v2](../spec/schemas/manifest-v2.schema.json) form a separate major
capability. Model, operation, worker and released v1 result contracts remain
1.0.0. Old readers reject v2 envelopes before mutation; new readers retain v1
behavior and exact fixture hashes. A package selects manifest v2 when it contains
the `spatial` artifact role. Lossy downgrade fails. There is no automatic upgrade
of scalar v1 results to a vector field and no executable migration in a package.
Lossless envelope construction retains the v1 model and immutable artifacts.

HDF5 v2 uses root attributes `contract_version=2.0.0`, `artifact_role=spatial`
and the canonical descriptor semantic hash. Flat datasets are `descriptor`
(uint8 JSON), `vertex_uuid`/`cell_uuid` (uint8 Nx16), `vertices` (float64 Vx3 m),
`time` (float64 T s), `offsets`/`connectivity` (uint64, zero-based), and exactly
the declared `temperature` (TxVx1 K) and/or `heat_flux` (TxVx3 W/m2).
Each dataset has exactly one unit attribute. The descriptor retains frames,
maps, materials, source/license hash, mesh revision, sample identity and original
model hash. Every array is compared with its declaration after checking all
shapes and allocation budgets. Links, aliases, external/virtual storage, filters,
chunks and unknown attributes/datasets are rejected. Dynamic plugins are disabled.
Artifact byte hashes stay distinct from normalized engineering hashes. Historical
results retain their original model binding after an edit; live access uses the
store's dependency/invalidation guard.

The joint supported budget is 4096 vertices, 4096 cells, 64 times, 16 frames,
1 MiB JSON, 64 MiB per array/member and 256 MiB per package (2048 members).
These bounds apply together: the JSON limit may reject a full nominal grid.
The acceptance driver measures a 128-vertex/64-cell representative fixture and
tests oversized logical arrays before reads. This is not the later 100,000-node
performance qualification. Existing growing-file and archive guards remain active.

The [reuse manifest](../ci/fem-reuse.json) records six candidate groups, exact
official-bundle paths/hashes, pinned upstream revision, file license/notice hashes,
public symbols, dependencies, deployment and owner dispositions. No upstream
source or examples are copied. LGPL notices remain in the official host bundle;
the independently authored host adapter is LGPL-2.1-or-later. Standalone readers
remain independent of FreeCAD. The selected offline path is `FemMesh.write` and
`Fem.read` with UNV. FreeCAD uses mm; the adapter converts explicitly to/from m.
UNV may renumber element rows, so topology and IDs are inspected by imported
element family; canonical UUIDs are stored separately. Gmsh and Netgen generation
are deferred, as are both optional CalculiX/Elmer comparisons. None satisfies
native engine coverage.

Run `tools/fem_probe.py` with locked standalone tooling. It verifies the official
asset, runs the original geometry smoke separately, checks selected source/license
hashes and starts a fresh pinned-host attempt with isolated preferences, embedded
cp311, application-thread assertions and a 180-second supervisor deadline. It
tests FEM creation, mesh I/O, selections/material/load references, result arrays,
save/reopen, service parity, undo, reassignment and interrupted synchronization.
No mesher executable or pip modification to embedded Python is required. Full
asynchronous GUI/editor behavior remains WP-13.

Independent rod, transient-mode, rotated-anisotropy and boundary-power oracles
are in `fcst_tools.spatial_oracles`; equations, samples, tolerances and future
mesh/time refinement sequences are frozen in `ci/spatial-criteria-v1.json`.
Production FE convergence remains WP-16. Existing WP-04 network evidence and
the eight audited finding groups are pinned and retained.

The common local/CI driver collects 19 standalone WP055 acceptance IDs; the
pinned host collects four. `tools/check_foundation_handoff.py` requires both
Windows configurations, all existing regression gates, exact candidate/source
hashes, the host profile and consumer/register consistency before collecting the
two handoff IDs. Missing, duplicate, skipped, stale or substituted coverage fails.
Planning CSV rows are definitions and cannot substitute for collected evidence.

Publication privacy (TST-021): exact source/manifests/fixtures and bounded reports
are scanned, then staged content, complete outgoing history, approved identities
and final GitHub prose are scanned before upload. CI clears each final report.
Raw host/mesh/package/database files and logs stay local; originals are retained.
The Git scanner batches blob reads with a bounded byte cache, while scanning every
commit's metadata and every path/mode/type and policy context independently.
The measured workload and legacy/batch equivalence tests include restricted paths,
deleted secrets and unapproved identities. Clearance is never cached by blob hash.
