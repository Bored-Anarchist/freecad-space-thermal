# Independent Thermal Desktop import and export

Decision date: 29 October 2026. Status: accepted product constraint; direct DWG
typed constant-network profiles implemented; full-model semantics and
qualification remain open.

## Required behavior

Thermal Desktop compatibility must work with Thermal Desktop, OpenTD, AutoCAD,
CRTechCAD and SINDA/FLUINT absent. This applies to first import, editing, export
and later reopen, as well as native FCST authoring and solving. A remote vendor
conversion service or a requirement to export/convert the file in TD beforehand
does not meet the requirement. A SINDA deck or generic geometry conversion is a
useful separate format path, not a replacement for original TD drawing support.

The previous OpenTD-first source migration design is superseded. Retain its
code only as an optional external comparison/reference harness. Product
import/export cannot call it, silently fall back to it, or require its runtime
probe to succeed. Vendor absence must not become a reason to postpone direct
format development. Historical WP-08 delivery evidence retains its original
scope and does not qualify this new direct-file path.

## Selected architecture

Use an independently deployable open-source DWG container reader/writer, with
owned, versioned Thermal Desktop serialization codecs above it:

```text
Original DWG + original companion files
                 |
  independent DWG container reader/writer
                 |
  owned TD class codecs + dependency/database readers
                 |
        canonical FCST thermal model
                 |
      owned thermal engine and .fcst storage
```

DWG is a container; an entity's display/proxy geometry does not identify its
thermal properties. Decode class-specific payloads, common object fields,
handles/references, node/submodel identity, geometry/mesh association, properties,
optics, cases, controls, expressions and dependency files. Freeze a separate
codec profile for the TD serialization version and DWG container version; the
`AC1032` container marker alone cannot identify a TD release. Custom classes
observed in the local research include nodes, conductors, loads, surfaces,
solids and case/logic managers. Node, conductor and heat-load structures now
have owned readers; the other required classes remain explicit holds.

The writer must serialize supported edits and reconstruct the object graph,
including reference relocation, bit alignment, compression and checksums. Keep
untouched original fields and required opaque regions exactly, or refuse the
affected edit/export. Do not downgrade a container while copying opaque binary
payloads across incompatible versions. No placeholder, dummy or proxy-geometry
substitution may be advertised as a thermal round trip.

Continue the direct SINDA parser/writer path alongside DWG. The existing reviewed
constant-network subset already imports, copies/edits and packages without
vendor software. Complete required SINDA constructs incrementally using owned
parsers/translators; do not execute imported Fortran or use SINDA as the solver.
An export from a new native model needs a separately tested canonical-to-source
writer; an unchanged source copy does not establish that capability.

## Corrected independent container implementation

`adapters/libredwg` builds a separate static Windows executable from the locked
LibreDWG 0.14 source and an owned preservation patch. `ci/dwg-backend.json` pins
the public source archive, compiler archive, exact patch pre/post images, owned
bridge/configuration/build sources and runtime protocol. CMake builds without
an installed vendor product. The component retains GPL-3.0-or-later notices;
its README records distribution and corresponding-source obligations. Core
Python/engine licensing remains separate; this is not a linked core dependency.
No executable or proprietary model is published by these checks.

The initial stock-binary research profile is historical. Its discovered losses
are addressed in the corrected backend: partial-byte rounding, layer material
references, zero class/producer versions, and complete unparsed AcDs datastorage.
The native protocol retains complete opaque bit strings and class records.
Standard JSON fields retain every ordered key occurrence, including repeated
subclass fields, instead of discarding values in a dictionary. Comparison excludes
only documented regenerated physical offsets, page IDs/counts, checksums and
encoded object sizes; all logical fields and opaque native records are compared.

A private same-version AC1032 experiment preserved 1,219 object records, 54 class
records, 1,025 objects with opaque payloads and the complete raw datastorage
section through rewrite and fresh-process reopen. All logical standard fields
matched. Original bytes remained unchanged. These observations establish the
tested container slice. Warning bits for unhandled classes/unparsed datastorage
remain explicit. AC1032 does not identify the TD release. The new typed profiles
below extend the implementation without qualifying complete thermal models.

The independently usable product slice exposes `td-preview` and
`td-export-source`: inspect native container records and retain the entire
immutable source tree exactly, including opaque companions and empty directories.
Without explicit units these remain structural operations. Native reconstruction
is now available for the declared closed constant-network profile; required
unresolved fields or dependencies still hold the whole import. Guarded source-field
edits remain separately available for declared constant fields. `td-audit-rewrite` is a private preservation experiment and is
never promoted to a user export. No operation imports or falls back to OpenTD.

Owned `RcNode` v22, `RcConductor` v22 and `RcHeatLoad` v17 codecs now consume
complete data, text and reference streams. Separate UCS-2 text lengths, common
references, expression/table/logic structures and stream boundaries are verified.
Neutral names retain unresolved selector fields; the reader never fabricates a
semantic interpretation or executes source logic. Native protocol v2 fixes full
Unicode class identity and normalizes LibreDWG's LSB-packed final partial byte
to MSB-first wire order. Unknown layouts stay opaque.

Guarded source-field export supports node temperature/mass values, constant
conductor values, scalar loads and allowlisted constant `.tdp`/`.rco` fields.
Dynamic modes and unsupported laws/distributions reject. Compressed zero/one
fields can grow by 64 bits, preserving every following stream bit. A native
rewrite and fresh process reopen must match every requested payload and all
unrequested logical fields, datastorage, classes, companions and directories.
Original bytes are checked again before atomic publication to a new tree.

`td-write-model` generates a new constant network from a native `.fcst` model,
without a source drawing/template. It constructs thermal objects, a fresh DWG
container, text/handle streams and deterministic identities from owned data.
Every generated field/reference is independently decoded and compared before
publication. Companion canonical metadata and identity receipts preserve labels
and source mappings. Unknown entities/fields/associations and empty submodels
reject. The preservation patch disables dummy/point substitution; an export
missing its thermal objects cannot pass the fresh-reader check.

Private original-file validation structurally decoded 918 nodes, 46 conductors,
14 heat loads and both property databases (21 thermophysical/22 optical entries).
Three guarded DWG edits, including compressed expansion, preserved every
unrequested field after fresh reopen. No original or sampled proprietary payload
is a public fixture. Public tests build independently owned analytic inputs.
These are serialization and preservation checks; full canonical reconstruction,
geometry/case/manager/environment/dynamic semantics, required dependency closure,
full-model reverse mapping and target-product qualification remain incomplete.

The direct SINDA path now also writes a new source tree from a native FCST model,
without needing an imported deck. Its closed constant-network subset covers
submodels, capacitive/prescribed/algebraic nodes, linear conductors and scalar
loads. It assigns deterministic source IDs, uses explicit units and reopens the
generated deck to compare every mapped identity, connection and quantity.
Unsupported semantics, ambiguous load aggregation and precision loss reject
before atomic publication. This does not qualify full SINDA language execution.


The independent product now also maps complete closed constant networks into the
canonical model, with explicit source units, identity/reference checks and native
contract validation. Portable packages retain exact originals and empty directories
under private alias maps. Canonical scalar export restores that closure, applies
only supported values and verifies fresh decoded semantics before atomic source
publication. Owned annotation companions are hash-bound and checked against source
quantities/references; large native handles use string identities.

Original property documents can be imported with explicit entry selection and
material validity bounds. Constant isotropic/orthotropic materials and equivalent-band optics
also have an owned source-free library writer and independent reader, preserving
canonical validity/annotations separately. Unrepresented active modes reject.
Orthotropic conversion requires a caller-declared property-axis frame, preserves
all three scaled conductivities and rejects general off-diagonal tensors. The
independent property-law interchange now reads/writes temperature/pressure grids,
active 1D basic material laws, separate optical bands and ordered laminate/aggregate
definitions. Evaluator policies are explicit. Component references must close on
basic properties; effective composite physics and canonical variable/spectral
bindings remain implementation work. Guarded grid/component edits retain every
unselected source byte, and a fresh reader verifies exports without vendor tools.
Static SINDA arrays now retain storage/identity and support bounded continuations
and allocation; reviewed intrinsics and explicit table-IR construction do not run
source code. Active control/array consumers require separate reviewed mappings.

RcRectangle v7 geometry has a tested prefix reader for six serialized parameters,
origin and basis; all thermal attributes remain opaque. This adds no native thermal
geometry or edited-geometry claim. Complete geometry, manager/case, material-derived,
variable and additional-version semantics still require verified format evidence.
WP-09/WP-11/WP-12 are needed for cross-tool/owned-engine qualification, and are not
prerequisites for implementing the independent paths above.

## Implementation and unattended acceptance

WP-08 remains in progress. Deliver these slices in order:

1. Retain the corrected container bridge and its native/ordered-field contracts.
   Its owned fixture is built, rewritten and reopened unattended in public CI.
   Extend independently verified preservation coverage before thermal promotion;
   container agreement alone never establishes class semantics.
2. Specify owned class codecs from authorized file-format observations and
   independently authored fixtures. Start with nodes, linear conductors and
   scalar loads, then required geometry/material/optical/case/logic classes.
   Retain versioned opaque regions and refuse unsupported required semantics.
3. Read/write each required companion format directly, preserving source
   identity and dependency closure; never guess private database schemas.
4. Map decoded data into canonical FCST entities and implement the reverse
   mapping for supported edits and new-model exports. Reopen exports through an
   independent reader and compare discrete identities and all thermal fields.
5. Run the required workflow in an offline Windows environment containing no
   vendor installations, vendor assemblies, license services or conversion
   servers. Test first import, changed export, fresh-process reopen, .fcst
   persistence and owned-engine execution separately. Detect any process/import
   attempt to use TD/OpenTD/AutoCAD/SINDA. No user-executed acceptance is required.
6. Compare numerical behavior with analytic fixtures and independently obtained
   baselines. A licensed source tool may supply optional comparison evidence on
   another runner; it is never an installed-product prerequisite. Compatibility
   claims still require sufficient target-format evidence. Missing reference
   evidence must be reported rather than invented.

Build and self-test with `python tools/build_independent_dwg.py`. This downloads
only locked public source/toolchain assets, keeps build artifacts local and
produces a bounded `dwg-backend.json` report. Foundation CI requires that job and
checks its candidate, source hashes, required cases and nonqualification flags in
the final handoff. It publishes only the privacy-cleared summary.

For private corpus research use
`python tools/probe_independent_dwg.py --drawing <local.dwg> --backend <trusted-install/backend.json> --work <new-private-directory> --report <new-local-report.json>`.
The driver downloads nothing and preserves originals. Decoder values and derived
drawings remain local. Success always retains `native_ready=false` and
`qualified=false` because complete thermal semantics remain incomplete.

`tests/test_native_dwg.py`, `tests/test_sinda_writer.py`,
`tests/test_td_payloads.py`, `tests/test_td_properties.py`,
`tests/test_td_property_laws.py` and the existing SINDA,
container and optional-reference tests run in both Windows configurations and
the standard-library security job. They cover retained duplicate occurrences,
partial payload bytes, Unicode/stream bounds, fixed-width and compressed scalar
edits, dynamic-profile refusal, new-model generation, property modes,
unrequested field changes, safe source patches/caches,
source overlap/staleness, exact source copies, new-model SINDA generation and
vendor-import rejection. No manual acceptance execution is assigned to the user.

## Publication privacy

Scan actual new source, synthetic tests, dependency hashes, documentation and
bounded probe summaries before any publication. Raw DWG/dependencies, proprietary
class payloads, decoded JSON, metadata, private paths, binaries and raw logs remain
local. Preserve the original corpus and its hashes. No source fixture is altered
to manufacture a public example; no proprietary binary is redistributed.
Property-law JSON, source definitions, frame companions and edited engineering
files also stay local. Publish only owned synthetic property/layer/grid fixtures,
public source hashes and bounded verdicts. TST-021 scans staged bytes, outgoing
history/identity and the exact final reports/GitHub prose before publication.
