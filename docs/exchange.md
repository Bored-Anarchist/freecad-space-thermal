# Shared source exchange (WP-07)

`fcst_exchange` supplies explicit adapter discovery/runtime probes, bounded dependency
resolution, immutable import previews, source identity mapping, typed semantic IR,
fidelity inventories, safe new-tree exports, source-result queries and reviewed
converter execution. It has no production dependencies beyond the standard library;
HDF5 package validation uses the existing optional arrays installation.

The registered executable reference profile is **fcst-network/1**. This public
synthetic grammar exercises the SDK; it does not claim SINDA, Thermal Desktop,
ESATAN or STEP-TAS language compatibility. Those version-specific implementations
and source-tool reopen/run comparisons remain with WP-08, WP-09 and WP-10.
`Registry` receives trusted adapter objects from application code. It never imports
plugins, scripts, commands or policy from a source project or filename extension.

## Reference grammar and mapping

Each UTF-8 line contains an uppercase record word, whitespace and one strict JSON
object. Blank lines and lines beginning with `#` are comments. Preserve every byte,
including line endings, comments, malformed records and unknown/undecodable regions.
There are no inline comments, executable includes, continuation lines or macros.
Duplicate JSON keys, nonfinite values and JSON nesting over 64 fail closed.

| Record | JSON fields | Meaning |
| --- | --- | --- |
| ENTITY | namespace, handle, entity | Closed canonical v1 entity fields, omitting id |
| CASE | namespace, handle, entity | Same, requiring kind=case |
| MAPPING | namespace, handle, mapping | Canonical v1 mapping, omitting id |
| ATTACHMENT | namespace, handle, attachment | Canonical v1 attachment, omitting id |
| EXPRESSION | namespace, handle, language, text, dimension | Reviewed fcst-expr/1 expression |
| PROCEDURE | namespace, handle, language, text, dimension | Reviewed fcst-pure-return/1 pure return expression |
| INCLUDE | path | Read another network file relative to this file |
| DATA | path | Retain a referenced immutable geometry/mesh artifact as data |
| RESULT | path | Read an fcst-results/1 JSON table as data |

For example:

```text
ENTITY {"namespace":"demo","handle":"sub","entity":{"kind":"submodel"}}
ENTITY {"namespace":"demo","handle":"101","entity":{"kind":"node","submodel_id":{"source_ref":["demo","sub"]},"classification":"capacitive","temperature":{"value":20,"unit":"degC"},"capacity":{"value":100,"unit":"J/K"}}}
EXPRESSION {"namespace":"demo","handle":"power","language":"fcst-expr/1","text":"quantity(10,\"W\") / 2","dimension":"power"}
```

Namespace and handle are explicit, case-sensitive identifiers (1–64 ASCII letters,
digits, `_`, `.` or `-`, starting with a letter/digit/underscore). Stable UUIDv5
targets use the namespace/handle pair; duplicate handles across namespaces work,
duplicate pairs fail. Use `{"source_ref":["namespace","handle"]}` for canonical
references. All other canonical entity fields, including node classification,
units, frames, normals, active sides, property tables, controls, cases and typed
expression ASTs, pass through the frozen v1 contract without guessed defaults.
Mappings and attachments are explicit records. Unknown fields are reported and
retained rather than discarded. Dangling references, unit errors, collisions,
invalid sides and expression cycles block native readiness.

`DATA` paths resolve relative to their containing network file. Canonical artifact
paths identify those resolved files relative to the declared source root, with
exact length/SHA-256 checks. Missing or changed artifact bytes block native
readiness. Package creation separately validates complete native array artifacts
using WP-05's readers; a descriptor alone never qualifies geometry or meshing.

The resolver reads only the declared dependency closure within a caller-supplied
root. It rejects traversal, absolute/network/drive/alternate-stream paths, Windows
device names, hard links, symlinks/reparse points, cycles and case aliases, including directory
aliases. Limits default to 128 files, 1 MiB/file, 8 MiB total, 64 KiB/line, 10,000
records and include depth 32. It records a graph and file/line/byte locations.
Missing includes produce diagnostics and prevent complete exports or packaging.
Unknown required regions prevent native readiness but can survive unchanged export.
Export additionally requires the declared closure to cover the entire source root,
including directory structure. Undeclared files or empty directories reject export
explicitly; native reconstruction does not imply export support. Declare inert
dependencies with `DATA` or use a root containing the complete declared project.
This prevents opaque content's uninterpreted dependencies from being silently
omitted. Export rechecks the tree so newly added files also invalidate the preview.

## Logic, fidelity and execution boundaries

`fcst-expr/1` and `fcst-pure-return/1` use decimal scalar literals,
`quantity(number,"unit")`, same-namespace expression symbols, arithmetic `+ - * /`,
unary minus, `abs`, `sqrt`, `exp`, `log`, `sin`, `cos`, `min` and `max` with closed
arity. Precedence follows the documented Python expression grammar for those
operators only; division is real, quantities use FCST unit/absolute-temperature
rules, and symbols are pure expression references. Translation walks a bounded
AST; it never calls `eval`, executes source or accepts attributes, imports,
assignments, loops, arbitrary calls or keyword arguments. Translated procedures
have only pure return semantics. Vendor procedural languages need independently
reviewed translators and regression evidence. Runtime domain/event evaluation
remains WP-11; readiness describes reconstruction, not a completed thermal solve.

`spec/schemas/exchange-fidelity-v1.schema.json` defines the machine-readable report.
Every substantive record has source and target IDs (null when no target exists),
category, operation, source location, byte hash, regression links, limitations and
required status. The five statuses remain distinct: `native-reconstructed`,
`bridged-executable`, `retained-opaque`, `approximated`, `unsupported`.
Per-operation records distinguish native readiness, unchanged export, controlled
editing and vendor qualification. `qualified` remains false in this common SDK.
External execution cannot upgrade opaque content or qualify a native solver.
Fidelity source IDs and paths are local evidence and require privacy clearance
before publication; raw imported text never appears in diagnostics.

`Preview` holds immutable bytes and returns defensive report/model copies.
`Preview.plan(operation)` produces an immutable conversion plan bound to the
profile and exact source revision, required source IDs and explicit limitations.
`require_native()` rejects unresolved required semantics; `source_package()` uses
that boundary before creating a manifest v2 package. Native model v1, manifest
v1/v2 and spatial v2 reads reuse the completed foundation contracts. Unsupported
versions, higher-order elements, unknown fields and lossy truncations are rejected.

## Export and preservation

`export_tree(preview, new_destination, patches)` checks original bytes against the
preview and writes the complete closure in a temporary sibling directory, flushes,
reopens and validates it, then renames it to a new destination. Existing targets,
source/target overlap, linked ancestors and stale originals fail. Errors leave
originals unchanged and clean the temporary tree. No overwrite API is provided.
Brief Windows access/sharing locks get at most 20 publication attempts over about
one second; every attempt still rejects an existing destination. Permanent or
unrelated errors remain failures.

A `Patch` binds an exact record byte range and original SHA-256 to a replacement
record. Controlled edits require a complete native preview, preserve record kind,
source identity and line termination, reject overlap or additional lines, and must
reopen as a complete valid conversion. Any opaque required region blocks editing
throughout that project because its dependencies are unknown. Unchanged copies
preserve unknown regions byte for byte. This conservative rule rejects edits that
cannot be proven safe. The new-tree result includes original/export revision
hashes and per-file hashes. `source_package` retains source originals, dependencies
and the fidelity report under manifest v2, alongside the validated canonical model.

## Results

`fcst-results/1` is a closed JSON table with fields `version`, `identities`
(`[namespace,handle]` pairs), `quantity`, `unit`, `time_unit`, `sign`, `time`,
`values` (time by entity), `interpolation` and `discontinuities` (right-hand sample
indices). Temperature uses absolute sign, power explicitly uses
`positive_into_node` or `positive_out_of_node`, and scalar flux uses
`source_positive` with face/facet/element identity. Vector flux is read through
the spatial v2 contract, preserving its frame rather than flattening it.

The reader verifies source identities/kinds, unique ordered time grids, matrix
shape, units, finite/range values and break indices, then converts to SI and
positive-into-node power. Provenance retains original units, sign, source hash,
time units, interpolation and discontinuities. Queries use exact samples,
`linear`, `previous` or `none`; extrapolation fails. A query crossing a declared
discontinuity fails unless its caller explicitly requests the previous-sample
policy. Exact samples at a discontinuity retain the new value.

## External converters

`ToolRunner` accepts trusted application registrations with exact executable/asset
hashes and fixed arguments. Its caller supplies an `Authorization` bound to the
registered profile and conversion operation. Imported data cannot create either
registration or authorization. Discovery/hash checks run before source mutation.
The Windows process starts suspended, enters WP-06's kill-on-close Job Object,
then resumes with bounded tree memory, process count, wall time and discarded,
bounded stdout/stderr. A monitored working tree limits observed file count,
depth and bytes; declared outputs are checked again after termination. Polling
is not a kernel disk quota and can allow transient excess. Input mutation,
undeclared outputs, missing outputs and links fail. A clean minimal environment
does not inherit credentials. Reports retain hashes and an opaque authorization
decision hash, without raw logs or installed paths.

The working root is an exchange boundary, not an OS filesystem/network sandbox.
Only trusted converters are supported; untrusted executable isolation and licensed
vendor provisioning remain with their controlled runner packages. The runner does
not download or bundle proprietary binaries and does not grant source content
application authority.

## Commands and unattended acceptance

```text
fcst exchange-preview source main.txt --dialect fcst-network/1
fcst exchange-export source main.txt copy --dialect fcst-network/1
fcst exchange-package source main.txt converted.fcst --dialect fcst-network/1
fcst exchange-result source main.txt result.json 30 --dialect fcst-network/1
python tools/check_exchange.py --report .local/exchange.json
python tools/verify.py --preset windows-debug
python tools/verify.py --preset windows-release
```

`ci/exchange-acceptance.json` freezes required case IDs and requirement mappings.
Both Windows verification drivers run them plus schema conformance, deterministic
parser fuzzing, real converter process containment, original-byte persistence,
controlled-edit reopen and independent result/translated-expression oracles.
Missing, duplicate, skipped or failed cases fail the gate. The synthetic tests
require no licensed installations or user-executed acceptance steps.
