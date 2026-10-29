# Independent Thermal Desktop import and export

Decision date: 29 October 2026. Status: accepted product constraint; direct DWG
thermal codecs and product deployment remain unimplemented.

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
solids and case/logic managers. Their payloads remain opaque today.

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

## Measured feasibility and rejected shortcuts

A local read-only experiment used the official LibreDWG 0.14 Windows x64 release.
The archive, executables and runtime DLLs are hash-pinned in
[the probe profile](../../ci/independent-dwg-probe.json). The source drawing,
decoded inventories, rewritten drawing and raw diagnostics stay in ignored local
storage. No vendor process, assembly, registry or license was used. The original
drawing hash remained unchanged.

The reader decoded an acquired `AC1032` drawing and the writer produced another
`AC1032` drawing which the reader reopened. An exploratory JSON comparison found
matching opaque-object identities, bit-count declarations and stored payload
strings. This establishes a viable independent container experiment, not a
lossless or thermal compatibility result. The strict audit found these blockers:

- The serializer emits duplicate JSON keys. A normal JSON dictionary reader
  silently discards earlier values; the new audit rejects this ambiguity.
- Serialized opaque payload byte counts can disagree with the declared bit
  count. Upstream `src/out_json.c` at tag `0.14` computes the extra byte using
  `num_unknown_bits & 8`; a non-byte-aligned bit count requires a remainder
  check. Agreement between two truncated JSON representations is insufficient.
- The exploratory rewrite changes a decoded class field and standard object
  fields. These must be fixed or given independently verified semantics before
  promoting rewritten files. Matching opaque payloads alone cannot pass export.
- No owned TD-specific thermal field codec exists yet. A successfully opened
  drawing cannot be labeled native-ready or used to claim complete import.

Use a verified native API binding or a corrected, pinned serialization bridge
that preserves every bit and distinct field. Evaluate the writer independently.
LibreDWG is currently a research candidate, not an adopted product dependency.
Its GPL-3.0-or-later distribution and corresponding-source requirements require
an explicit packaging/license disposition before shipping a component. Keep
any adopted component's original notices and exact source/build provenance.

ACadSharp is another open-source candidate, with an MIT license and modern DWG
reading/writing. The inspected revision
`25b534813c1e5beb19ce78dd8f671781fd4d052f` deliberately rejects `UnknownEntity`
in its DWG writer, while its unknown-object classes retain basic metadata rather
than the complete custom payload. It therefore cannot be substituted unchanged
as a lossless TD converter. An extension would need full payload/reference and
class-codec support, not only a different DLL.

References: [LibreDWG project](https://www.gnu.org/software/libredwg/),
[pinned 0.14 serializer source](https://github.com/LibreDWG/libredwg/blob/0.14/src/out_json.c),
[LibreDWG 0.14 release](https://github.com/LibreDWG/libredwg/releases/tag/0.14),
[pinned ACadSharp writer](https://github.com/DomCR/ACadSharp/blob/25b534813c1e5beb19ce78dd8f671781fd4d052f/src/ACadSharp/IO/DWG/DwgStreamWriters/DwgObjectWriter.cs).
Older LibreDWG documentation understates newer writer capabilities; the measured
0.14 same-version experiment, its failures and exact binary hashes take precedence
over an inferred modern-write support claim.

## Implementation and unattended acceptance

WP-08 remains in progress. Deliver these slices in order:

1. Correct and pin the independent container bridge. Verify real bit lengths,
   duplicate-free field representation, handle/reference closure and every
   unrequested field through same-version rewrites. Preserve all source files.
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

The repeatable local research driver is
`python tools/probe_independent_dwg.py --drawing <local.dwg> --tools <pinned-tool-directory> --work <new-private-directory> --report <new-local-report.json>`.
It downloads nothing, uses the existing bounded converter runner and operates on
copies in a fresh directory. Its derivatives are research artifacts, never user
exports. A successful probe invocation means the experiment completed; the
bounded verdict still reports blocked decoder contracts and always reports
`native_ready=false`, `qualified=false`.

`tests/test_independent_dwg.py` uses owned synthetic fixtures to test missing
opaque bits, changed references/properties/classes, duplicate JSON/identities,
size/depth/value budgets and private-value withholding. Its SINDA end-to-end
case forbids vendor-related imports while running preview, export and .fcst
packaging. These tests are included in unattended Windows verification. They
cannot qualify unimplemented TD thermal codecs.

## Publication privacy

Scan actual new source, synthetic tests, dependency hashes, documentation and
bounded probe summaries before any publication. Raw DWG/dependencies, proprietary
class payloads, decoded JSON, metadata, private paths, binaries and raw logs remain
local. Preserve the original corpus and its hashes. No source fixture is altered
to manufacture a public example; no proprietary binary is redistributed.
