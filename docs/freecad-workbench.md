# FCST thermal workbench

WP-13 adds a Windows FreeCAD 1.1.4/cp311 workbench around the shared project,
transaction and owned-engine interfaces. The model tree, CAD selection and
result history are linked. Thermal Desktop's temperature/heat-flow review and
ESATAN's adjacent geometry and charts inform the layout; no vendor artwork,
source, engineering model or visual asset is included.

## Install and use

Install into an explicitly selected FreeCAD Mod directory:

```text
python tools/install_workbench.py --mod-directory PATH_TO_FREECAD_MOD
```

The installer writes a new `FCST` directory and refuses an existing destination.
It copies the host adapter, canonical contracts and application service without
changing the embedded Python environment. Select **FCST Thermal** after starting
the pinned host. The owned native worker is built separately by the ordinary
Windows verification driver; select that executable on the first **Solve**.

Use **New thermal model** and the **Create** menu to add submodels, nodes,
materials/optics, conductors, loads, frames, environments, cases and controls.
Editors expose quantities with units, entity references, enumerations and inert
structured fields. The shared contract reader validates the complete proposed
model; invalid edits remain in the dialog with a structured diagnostic.
**Open analytic network** supplies an owned, geometry-free starting example.

Use **Capture selected CAD face** to freeze a selected body's BREP and create its
frame, geometry and signed surface through a shared transaction. The BREP retains
FreeCAD's native millimetres; canonical area is square metres. Imported canonical
spatial descriptors explicitly use metres and convert by 1000 at the host edge.
The frozen geometry copy is independent of later edits to the original CAD body.
The original body is hidden after capture. Canonical frame rotations and
metre-valued origins are applied when rebuilding the displayed placement.
Use **Link selected entity to CAD face** for a review attachment. Persistent
subelement references, geometric signatures and source-geometry revision hashes
are retained together. Review links do not invent a production FE assignment.
Mapping lines connect abstract nodes to their CAD faces; selecting a mapped face
selects its thermal node, and current node results color that face.

The assignment table exposes missing and invalid attachments and selects their
canonical entities. CAD, conduction elements, radiation facets and thermal nodes
retain separate identities. Surface normals, material axes and heat-flux vectors
are available with supported canonical spatial fields. Contact/conductor links
and geometry-free nodes use an explicitly abstract network layout.

## Solving and reviewing

**Solver settings** selects `steady` or `transient`, start/end times, bounded
sampling and transient temperature tolerances. A selected canonical case supplies
its own mode and time interval. Native input validation remains decisive for
unsupported physics or incomplete material-law definitions.

Solves run in a supervised process. The Qt loop remains responsive for selection,
viewing, cancellation and edits. The immutable request and executable hash are
bound to the result. A late result from an edited revision is rejected. Failed,
cancelled, timed-out or interrupted runs cannot publish partial results.
Operational run states are retained in the local SQLite store. This explicit
native execution adapter leaves WP-06's frozen worker transport unchanged.

Select a node to inspect its complete temperature history. The time slider links
node colors, heat-flow terms, boundary/storage energy and heater duty. Temperature
can be shown in kelvin or degrees Celsius; power, energy and time retain W, J and
s. Colors use one scale across the complete history. Results are queried from
the shared data service, rather than solved again by the widgets.

**Open canonical spatial field** uses the qualified foundation's linear vertex
descriptor, preserving raw temperature, global heat-flux vectors, IDs, units,
frames and sample times. FEM's mesh and result objects and native `NodeColor`
setter render contours. Bundled Coin adds vectors, normals and material axes.
The exact [reuse assessment](../ci/host-reuse.json) records source hashes,
dependencies, licenses and the pinned `NodeColor` getter limitation. The native
`NodeColorArray` and underlying fields, rather than the unavailable getter, are
used for acceptance. Original upstream notices remain in the official bundle.

Edits hide current contours and histories. Direct host edits, document Undo/Redo
or changed topology leave the host dirty. **Undo thermal edit** executes a shared
inverse transaction; ordinary host Undo alone cannot change canonical truth.
**Rebuild host from project** explicitly restores that truth. Face split, merge,
deletion, reordering and ambiguous signatures require explicit reassignment.

**Save project** coordinates a portable `.fcst` file and companion `.FCStd` file
through the durable two-file journal. Reopening rebuilds the host projection from
validated canonical data and frozen BREP; package-supplied Python proxies never
run. Settings, review links and immutable result histories survive reopening.
An interrupted or competing save stays dirty until exact-byte reconciliation.

## Unattended acceptance and publication

```text
python tools/check_host.py --worker PATH_TO_TESTED_WORKER --report .local/host.json
python tools/verify.py --preset windows-debug
python tools/verify.py --preset windows-release
python -S tools/check_security.py
```

The same drivers run in GitHub Actions. The isolated GUI supervisor installs a
fresh workbench, verifies the official bundle and FEM source/notice hashes, uses
separate preferences, invokes real commands and widgets, checks numerical/data
assertions and captures supplementary local render evidence. Missing, duplicate,
skipped, stale or substituted host coverage fails the aggregate gate. The host
worker hash must match the thermal acceptance worker in each configuration.
No acceptance clicks are assigned to the user.

TST-021 scans exact sources, synthetic fixtures, reuse manifests, bounded
`host.json` summaries and final publication prose, plus staged bytes, outgoing
history and approved identities. CI scans reports before upload. Generated CAD,
portable projects, spatial/result containers, screenshots, raw native output,
logs, preferences and operational databases stay local. Existing engineering
originals and restricted evidence remain unchanged.

WP-16 retains production FD/FE, contact physics, mesher generation and full
spatial assignment qualification. WP-14/15 retain MCP and integrated P0 parity;
WP-17/18 retain production environment/campaign workflows. These host tests do
not qualify TD/ESATAN compatibility or grant a complete Q1 release.
