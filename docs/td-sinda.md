# Thermal Desktop / SINDA implementation (WP-08)

**29 October scope correction:** product import/export must be independent of
TD, OpenTD, AutoCAD and SINDA installations. The
[independent exchange decision](decisions/0004-independent-thermal-exchange.md)
supersedes the OpenTD-first migration design. The direct SINDA subset already
works without those tools. Direct DWG node, conductor and heat-load profiles,
property readers, native constant-network import, portable storage, canonical
scalar edits and source-free constant-network DWG export are implemented.
Constant property libraries and static SINDA arrays have independent readers and
writers. Complete-model thermal compatibility remains open.
The OpenTD implementation below is retained only for optional external reference
work and cannot satisfy the product's import/export requirement.

WP-08 supplies independent format slices and optional pinned TD 6.3 reference tooling. **Q1
qualification remains open.** The user authorized pushing this tested delivery
with the dependent qualification holds retained. No licensed AutoCAD host is
available on the development machine. Owned-engine thermal/radiation/environment
comparisons and paired ESATAN qualification remain WP-11/WP-12 and WP-09 work.
Required source semantics and other target versions still need qualification.

`ci/td-profiles.json` freezes the observed Thermal Desktop **6.3.022**,
SINDA/FLUINT **6.3.15**, OpenTD assembly **6.3.0.0** and its exact SHA-256.
The actual assembly targets **.NET Framework 4.6**. The owned C# sidecar builds
with the Windows x64 Framework compiler against the separately installed assembly;
it does not redistribute vendor DLLs. 2025 R2 and 2026 R1 profiles are explicitly
unimplemented. An absent or mismatched profile fails before source mutation.

## Independent DWG profiles and exports

`python tools/build_independent_dwg.py` builds the locked separate GPL backend
and runs seventeen unattended native checks, including the actual vendor-free CLI,
new-model generation, compressed scalar edits and fresh-process reopen. Select
its trusted installation receipt explicitly, outside imported project data.

```text
fcst td-preview source main.dwg --backend .local/dwg-backend/install/backend.json --work .local/new-preview
fcst td-export-source source main.dwg derived-source --backend .local/dwg-backend/install/backend.json --work .local/new-export-preview
fcst td-export-source source main.dwg edited-source --edits edits.json --backend .local/dwg-backend/install/backend.json --work .local/new-edit-preview
fcst td-write-model native.fcst new-td-project --backend .local/dwg-backend/install/backend.json --work .local/new-writer
```

These commands require no TD/OpenTD/AutoCAD/SINDA installation, API, license,
prior vendor conversion or service. Original files remain immutable. Exports
publish a new tree atomically after validation; existing destinations, source/work
overlap, stale sources and unrequested changes reject.

The declared binary payload profiles are **RcNode v22**, **RcConductor v22** and
**RcHeatLoad v17**. These are serialization versions, not TD release claims.
Readers consume the entire data, separate UCS-2 text and reference streams;
unsupported versions remain opaque with an explicit diagnostic. They inventory
source expressions, tables, logic and unresolved selectors without executing or
guessing their meaning. Preview reports contain counts, handles and bounded
status codes, never source names, material values, source logic or decoded bytes.
Without explicit units or with unresolved required fields/dependencies, native
readiness remains false. Closed constant networks can now be reconstructed into
the native model. Q1 compatibility and production-solver qualification remain open.

`edits.json` is a bounded array of closed edit records. For example, using handles
from the local preview:

```json
[
  {"handle": 101, "changes": {"initial_temperature": 305}},
  {"handle": 103, "changes": {"value": 0.75}},
  {"path": "materials.tdp", "changes": [{"entry": "OWNED MATERIAL", "field": "SPECHEAT", "value": 900}]}
]
```

Node source fields `initial_temperature` and `mass_value`, conductor `value` and
heat-load `value` are supported when their constant-field guards pass. Values
are serialized source values; this interface does not imply a canonical unit or
change a material/volume/capacitance mode. Dynamic expressions, source logic,
nonconstant conductor laws, time tables and unsupported heat-load distributions
reject affected edits. Compressed zero/one doubles can expand by 64 bits; separate
text and handle streams move intact. All other object payloads, datastorage,
classes, ordered standard logical fields, companions and empty directories are
checked and retained. `td-audit-rewrite` remains a separate private preservation
audit; it does not grant full-model readiness.

The direct UTF-8 `[UNICODE]` `.tdp`/`.rco` readers retain original bytes, comments,
unknown tags and nested composite blocks. Documented optional scalar defaults are
handled explicitly. Counted one-dimensional conductivity/specific-heat and optical
property tables have bounded typed readers. Table IR requires explicit units and
interpolation/extrapolation choices; active table physics is not silently reduced
to constants. Existing table values can be edited with the same point count and
increasing axis, preserving all unselected bytes and source modes. Allowlisted constant numeric edits
preserve every unselected byte and independently reparse. Stored thermophysical
scalars use SI; scalar edits cannot switch property modes. Temperature/pressure
vectors and selected existing composite component numbers also have guarded
source edits. These readers do not yet reconstruct all
material/optical models or their complete drawing dependencies.

`td-write-model` accepts a native `.fcst` model containing only explicit submodels,
capacitive/algebraic/prescribed nodes, linear conductors and scalar loads. It
rejects unsupported entities, fields, associations and empty submodels. It
serializes new thermal objects and a new AC1032 container from owned inputs,
without borrowing an existing DWG or vendor template. A fresh native process
reopens the result; every intended class, identifier, scalar, string and connection
must match. `canonical.json` and `identity-map.json` retain canonical annotations
and deterministic source identities beside `network.dwg`. This is a tested
constant-network structural export, not a qualified full Thermal Desktop model.

Private corpus checks decoded all 918 nodes, 46 conductors and 14 heat loads in
the available drawing, and 21 thermophysical/22 optical database entries. Three
representative DWG source-field edits, including compressed expansion, reopened
without unrequested changes. All original bytes were preserved. These counts do
not establish coverage for geometry, cases, managers, dynamic laws or other
serialization/source versions.

## Native import, portable editing and export

```text
fcst td-package source main.dwg native.fcst --backend .local/dwg-backend/install/backend.json --work .local/import-job --temperature-unit K --capacity-unit J/K --conductance-unit W/K --power-unit W --time-unit s
fcst td-export-native edited.fcst derived-source --backend .local/dwg-backend/install/backend.json --work .local/export-job
```

The same five unit options can be supplied to `td-preview`. All five are required
together; no unit system or TD product release is inferred from AC1032. The
`td-independent-network/1` converter accepts the declared complete constant node,
conductor and load profiles only. It verifies every serialized field, node class,
submodel/number, connection and required common reference against that profile.
Clones, material-derived capacitance, unknown switches, active expressions/laws,
selection sets, required geometry/cases/managers, extended data and unparsed
storage prevent promotion. Unknown companions also hold native reconstruction.
Known property databases are catalogued, and material references are classified
as resolved, missing or ambiguous; resolving a name does not qualify its physics.

`native_ready=true` means a validated canonical network exists. It does not claim
an available production solver or complete TD compatibility. The source drawing
remains authoritative for thermal values. Owned canonical/identity companions
must bind the drawing hash and independently match all decoded quantities and
references before their IDs, labels and other annotations are restored.

`package_td` retains every source byte and empty directory in a portable `.fcst`
project. Vendor filenames map to safe aliases with an inert private source map.
No local source path or installed backend path is embedded. `restore_td` validates
that map, paths, roles, budgets and source revision before atomic restoration.
Changing a portable package's native scalar values can then drive
`td-export-native`; it revalidates the package, restores the original tree,
rewrites only supported fields and independently reopens every requested value
and unrequested logical field. Celsius/Fahrenheit offsets and power scaling are
explicit. Loss of precision, topology/classification/label changes, existing
targets and unresolved semantics reject before publication. Canonical companions
are regenerated after successful verification. 64-bit handles are stored as
strings in new identity receipts so JSON number precision cannot alter them.

## Independent property conversion

```text
fcst td-import-properties source materials.tdp material.fcst --kind tdp --temperature-min 150 --temperature-max 450 --name "OWNED MATERIAL"
fcst td-import-properties source optics.rco optical.fcst --kind rco
fcst td-export-property-source edited-material.fcst derived-property-source
fcst td-write-properties property-project.fcst new-property-library
fcst td-read-properties new-property-library reopened-properties.fcst
fcst td-import-properties source materials.tdp orthotropic.fcst --kind tdp --temperature-min 150 --temperature-max 450 --material-frame material-axes.json
fcst td-read-property-laws source materials.tdp property-laws --kind tdp
fcst td-write-property-laws property-laws property-laws.json new-law-source
```

Original `.tdp` and `.rco` documents can be imported directly without a prior
conversion or companion. Material validity limits must be supplied in kelvin;
they are not fabricated from constant property values. Optional explicit entry
selection preserves the entire original document, including unselected records,
in the native package. Without selection every entry must be representable.

`td-export-property-source` applies native constant-property edits to the retained
original document. It preserves comments, names, unselected entries and inactive
data, inserts documented optional scalar headers when necessary, and verifies
physical values after reparsing. Identity/mode changes reject. Canonical companions
retain explicit validity and annotations in the new export tree.

The canonical material profile covers constant isotropic and orthotropic
conductivity, density, specific heat and their supported multipliers. Orthotropic
import requires an explicit canonical frame entity in `--material-frame`; a
property database defines local axes but cannot establish their placement in a
drawing. All three scaled conductivities map to a diagonal tensor in that frame.
Source-free libraries preserve the declared frame and validity in their canonical
companion and independently check all three axes against the original-format
properties. Native source export preserves the original multipliers and refuses
frame/mode changes. General tensors with off-diagonal terms require a separate
axis mapping and reject this writer. The optical canonical profile covers constant
absorptivity, emissivity, equivalent solar/IR specular fractions and transmission.
Variable/composite and separate-band/refraction bindings into the canonical model
remain holds. Separate source-free property-library export accepts a native
property-only project, writes deterministic `.tdp`/`.rco` definitions and retains
validity/annotations in canonical companions. The reader reconstructs each source
property and compares all values/identities before accepting those companions.
Changed hashes alone cannot bless changed physical values. These are property
library operations; drawing assignments and complete thermal geometry are separate.

The separate `td-property-laws/1` interchange reads and writes the original
bracketed documents without a vendor installation, prior conversion or template.
Each entry retains its name, scalar switches, counted 1D tables and counted grid
vectors. Basic material laws cover conductivity along each property axis,
specific heat versus temperature, density/scales, effective emissivity, and
conductivity versus temperature and pressure. Grid storage varies temperature
first. The evaluator requires explicit `linear` or `previous` interpolation and
`error` or `clamp` extrapolation; these are declared owned policies, not a claim
that a vendor solver uses them. Temperatures are kelvin, pressures pascals and
thermophysical quantities SI. Angle tables use the serialized source coordinate;
the caller must establish the angle convention before physical evaluation.

Optical laws retain separate solar and infrared constants, reflected and
transmitted specularity, refractive-index ratios, angle tables, temperature
tables and the wavelength-dependent-radks switch. Temperature-dependent
absorptivity/emissivity takes precedence over all angle tables in that band.
Energy bounds are checked at the table knots. This two-band representation does
not claim arbitrary wavelength-spectrum or radiation-solver support.

Laminate/aggregate definitions retain ordered component references, thickness,
orientation, weights, conductivity scaling and override settings. Every component
must resolve to a basic property in the document. The interchange rejects missing,
composite-to-composite and cyclic references. It does not calculate effective
mixture properties or silently replace a composite with a constant. Unknown
fields, fusion, recession, thermoelectric and stress modes remain unsupported
by this semantic profile and retained by the byte-preserving document reader.

The new CLI commands write a new output directory and independently reparse it.
Law JSON contains engineering data and stays local; console/CI reports contain
counts and verdicts. They always report `native_ready=false` and `qualified=false`.
They are a separate format interchange, not a variable-law binding into `.fcst`
native execution. Existing `td-export-source --edits` can change a grid vector
using `{entry, field, values}`, or an existing component number using
`{entry, component, field, value}` with a zero-based component index. Counts,
references and modes remain fixed; all unselected source bytes are preserved.

## Geometry and remaining format evidence

The RcRectangle v7 reader now extracts six serialized geometric parameters,
origin and basis while preserving the remaining thermal attributes/text/handles
as opaque source ranges. All 16 rectangles in the local example pass this prefix
reader. This is a partial envelope, with units and parameter interpretations still
unresolved; it cannot enable thermal geometry edits or native reconstruction.

Remaining independent implementation needs verified layouts/semantics for complete
surface/solid/mesh, material-derived node modes, canonical variable/composite and
spectral bindings, composite effective physics, case/manager, orbit/environment
and dynamic source constructs. Those
fields cannot be reconstructed by guessing from display geometry or neutral
selector numbers. Additional serialization versions, including the planned
2025 R2/2026 R1 coverage, need suitable format/fixture evidence. Required unknown
objects still prevent importing the entire available example as a native model.
The closed-network, property, array and preservation work above does not depend
on WP-09/WP-11/WP-12. Their paired ESATAN and owned-engine comparisons remain
separate Q1 completion dependencies. No user-executed acceptance is required.

See the decision and `adapters/libredwg/README.md` for pinned provenance and
component license obligations. Raw inventories and source data remain local.

## SINDA 6.3 constant-network profile

`fcst_exchange.sinda.SindaAdapter` reads the declared
`sinda-6.3-network/1` ASCII subset. Units are supplied explicitly through
`SindaUnits(temperature, capacity, conductance, power, time)` and checked against
the frozen native dimensions. File extensions never select units or grammar.

Supported declarations:

- `HEADER REGISTER DATA`: immutable scalar registers with constants, identifiers,
  parentheses, unary signs and `+ - * /`; SINDA `D` exponents are recognized.
  Resolution is bounded and detects unresolved symbols/cycles. No source is evaluated
  through Python `eval`, Fortran, shell commands or arbitrary function calls.
- `HEADER NODE DATA, SUBMODEL`: `id, temperature, capacity`. Negative declaration
  IDs mean prescribed boundary nodes with zero capacity; positive IDs with positive
  capacity are capacitive, and positive IDs with zero capacity are algebraic.
  References use the absolute node number. Submodel names are case-insensitive.
- `HEADER CONDUCTOR DATA, SUBMODEL`: `id, from, to, conductance` for positive IDs
  and linear scalar conduction. Cross-submodel references use `SUBMODEL.number`.
  Negative radiation-conductor IDs stay explicitly unsupported.
- `HEADER SOURCE DATA, SUBMODEL`: `node, power`, including negative cooling loads.
- Single-line static node `GEN start,count,step,temperature,capacity` and conductor
  `GEN start,count,idstep,from,fromstep,to,tostep,value`. Expansion is bounded and
  inventories every generated identity. Dynamic generators and continuation logic
  are retained instead of guessed.
- `INSERT filename`, including quoted filenames with spaces/parentheses, scoped
  to the containing file's directory and inherited source section. Quoted dollar
  signs cannot hide invalid include paths. Dollar suffixes outside quotes are
  comments; fixed-form column-one `C`, `*` and `!` comments retain original bytes.

The static numeric profile also supports bounded integer powers and the explicit
intrinsics `ABS`, `SQRT`, `EXP`, `LOG`, `SIN`, `COS`, `MIN` and `MAX`. Arguments are
parsed as owned syntax trees; imported functions, function-shadowing registers,
Python numeric extensions, malformed delimiters, overflow and literal underflow
reject. Commas inside intrinsic arguments remain part of that expression.

`ARRAY DATA` supports numbered `id = values` declarations, line continuations,
static register expressions and bounded `SPACE`/`ALLSAME` allocation. Integer/real
storage kinds and submodel identity are retained. Mixed storage without a mapped
source option, ambiguous legacy syntax, dynamic allocation, malformed/duplicate
IDs and budgets fail. Unreferenced constant arrays can accompany a native network;
active consumers still need reviewed translation. Single-line literal-array
preservation edits retain identity, length and storage kind. `sinda_arrays.table_ast`
requires explicit axis/value units, input binding, interpolation, extrapolation
and discontinuities; array shape alone never selects these semantics. It produces
IR for the normal canonical type/reference validator, not an implicit source solve.

`END OF DATA`, header spelling, whitespace, comments and line endings survive
unchanged export. Repeated/ambiguous inserts, section leakage, cycles, missing
files, traversal, absolute/network/device paths, links/hard links, case aliases
and size/depth/entity budget overruns fail closed. Default limits reuse WP-07's
128 files, 1 MiB/file, 8 MiB total, 10,000 records and depth 32.
Noncomment data after `END OF DATA`, ambiguous terminators inside INSERT files
and data headers without an explicit submodel also reject native reconstruction.

Active property-array consumers, runtime controls/cases, dynamic registers, unreviewed procedures,
advanced radiation/fluid constructs and unknown syntax remain inert, with explicit
source locations and fidelity limits. This profile does not claim complete SINDA
language execution. Unsupported required semantics block native readiness and
controlled edits; complete unchanged source copies can still preserve opaque data.

The parser maps its reviewed subset into the frozen canonical model, with stable
submodel/node/conductor/load identities and dimension/temperature checks. Per-record
and per-operation reports use the shared fidelity schema. Static parsing cannot
qualify source execution, editing, the native solver or an entire compatibility profile.

## Source export and portable packages

`SindaAdapter.export` uses WP-07's atomic new-tree exporter through an explicitly
supplied trusted adapter. Supported `Patch` edits bind exact source byte ranges,
original hashes, record kinds and identities. GEN identity templates cannot be
changed by a value patch. The complete copied closure must reopen and validate;
all other bytes remain unchanged. Opaque content, stale sources, undeclared files,
existing destinations and unsafe edits reject publication to the new tree.

`package_sinda` persists a fully reconstructed import in manifest v2. Vendor names
map to safe hash-derived package paths; an inert evidence map retains the original
relative names and dependency graph. Exact original bytes are preserved. Packages,
source maps and fidelity inventories containing real source data remain local
until independently cleared for publication.

## New-model SINDA export

`fcst sinda-write-model native.fcst new-source` with the same explicit unit flags
as preview writes a deterministic new constant-network deck. It accepts only
submodels, nodes, linear conductors and scalar loads, assigns stable source IDs
and reopens the deck through the independent parser before an atomic commit.
Every mapped quantity/identity/reference must match within the declared numeric
precision. Unsupported fields, overlapping load aggregation and unrepresentable
precision fail before publication. Labels are escaped inert annotations; the
receipt records native-to-source identities. No original deck or vendor is needed.

## Optional external reference: OpenTD sidecar and copied DWG projects

`adapters/opentd63/Program.cs` is owned adapter source compiled against the installed
API. `Runtime.probe()` and `discover_runtime()` only read installation metadata and
hashes: they do not connect to TD, start AutoCAD, read keys or test out a license.
`probe_td.py --api-smoke` builds the sidecar and tests actual API dimensional types
and a factory-created node DTO without opening a drawing or invoking a solver.
Binary/source/compiler hashes seal cached builds; changed bytes require a new build
and a newly reviewed execution hash.

Host operations require all installed prerequisites and `HostAuthorization`, bound
to the exact sidecar, source drawing, reviewed fixture kind and controlled source-open
policy. The controlled licensed host must prevent unreviewed drawing-associated code
from acquiring authority; that security policy is a qualification prerequisite.
Source text cannot create registrations, grant authorization or supply commands.

`capture_project` freezes a bounded complete project tree, including companion
property databases and empty directories. Defaults are 2,048 files, 64 MiB/file,
256 MiB total, depth 32, a 180-second watchdog and 4 GiB process-tree memory.
Links, case aliases, modified originals and original/derived tree overlap fail.
`OpenTdAdapter` works only on new copied trees in its job's `project/` directory;
request/response/control files stay outside that source copy.

The sidecar always requests `START_NEW_TD` with a hidden window and never attaches
to a user's existing document. It sets API working units to SI and uses `GetModel`
to inventory geometry, nodes, submodels, GMM/TMM assignments, thermal/optical
properties, cases, controls, dependencies and source logic. Complete structured
IR retains non-native data. Generic DWG content without a thermal network is labeled
`geometry-only`. Only reviewed constant network fields map into native entities;
unmapped geometry/material/table/case/logic semantics remain explicit and block
native readiness. Empty SDK code-unit descriptors are not mistaken for executable
logic; nonempty source procedures stay inert.

Supported API edits use a closed field allowlist: node temperature/capacity,
linear-conductor value, scalar heat load, rectangle dimensions/thickness, constant
material properties and optical `Alph`/`Emis`. Numeric/range/identity checks happen
before copying/opening. The copied source is saved, closed, then inspected in a
separate process and fresh TD instance. Every unrequested semantic field must match;
dependency mappings bind actual copied bytes rather than merely matching filenames.
Opaque source logic/cases and unresolved dependencies hold edits. These paths
compile against the real installed API, but licensed save/reopen/run acceptance is
still unqualified without a host.

Windows Job Objects bound memory, process count and descendant lifetime; wall time,
logs and the job tree are bounded. Raw compiler/vendor logs and complete inventories
remain local. A working directory is not an OS filesystem/network sandbox: only
reviewed installed tools and controlled host policies are supported.

## Reference runs, result queries and qualification

The sidecar can construct an owned two-node reference model and steady/transient
cases, then run them through TD/SINDA on an authorized licensed host. It cannot
execute arbitrary imported cases through that reference entry point. Frozen criteria
in `ci/td-reference-criteria-v1.json` compare the external results with independent
constant-network analytic solutions, including temperature identity and time-grid
checks. Results remain `reference_external`; passing this experiment cannot close
an owned-engine gate.

`read_print` implements the declared assigned-value TPRINT/QPRINT subset: explicit
`TIMEN = number` frames, `SUBMODEL NAME = identifier` context, and `T number=value`
or `Q number=value` rows. Units, quantity, namespace prefix and interpolation policy
are explicit. Missing/duplicate/unmapped samples, partial frames, invalid units and
nonmonotonic time grids fail. Original result hashes and unit/sign/time provenance
survive conversion to WP-07's SI results/query interface. Other vendor output layouts
require separately reviewed readers and are not guessed.

`td_qualification.assess` now requires the independent product profile, complete
class/dependency coverage, offline vendor-absent import/edit/export/reopen and
new-model export evidence with exact codec/input/output hashes. A vendor call
attempt or unresolved required class blocks qualification. Owned thermal/radiation/
environment comparisons and paired ESA evidence remain required. Licensed hosts
are optional external reference infrastructure, not product prerequisites.
Missing/stale/duplicate cases, SDK shims, parser-only tests, upstream output and
external fallback labels cannot close the independent product gates.

```text
fcst td-probe
fcst sinda-preview source network.inp --temperature-unit degC --capacity-unit J/K --conductance-unit W/K --power-unit W --time-unit s
python tools/check_td.py --report .local/td.json
python tools/probe_td.py --api-smoke --report .local/td-probe.json
python tools/run_td_reference.py --report .local/td-reference.json
```

The reference driver fails with a bounded blocked report when no licensed host
exists. A runner-local private profile can specify the host, authorization decision,
reviewed sidecar hash, source-open policy hash and explicit source-output paths.
It is never uploaded or inferred from imported model content. The existing private
validation repository stays disabled; no privileged runner is added to public PRs.

## Unattended verification and publication privacy

Both Windows drivers run the frozen `ci/td-acceptance.json` cases and upload only
privacy-cleared `td.json` summaries. They cover real SINDA grammar, static GEN,
byte preservation, package reconstruction, CLI use, unsafe includes, static arithmetic,
source logic inertness, controlled edits, TPRINT identity/time/units, source-copy
guards, native-readiness limits and false-qualification rejection. Public tests
never claim licensed TD execution; the separate installed-API smoke is local evidence.

TST-021 scans actual adapter/C#/native bridge/configuration/patch sources, preserved
third-party notices, locked public provenance, fixtures, summaries, evidence and final
GitHub prose. Policy v5 inspects `.cs`, native `.h` and `.patch` text with unchanged sensitive
patterns, binary rejection and inspection budgets. Originals, property databases,
DWG/deck/result bytes, private profiles, compiled sidecars, vendor DLLs and raw logs
stay local. Scan staged bytes and outgoing history before upload; the scopes may
be scanned separately, and neither may be omitted. No scanner finding is suppressed
to publish a fixture or report.
