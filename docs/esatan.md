# Independent ESATAN exchange (WP-09)

WP-09 is **in progress**. The owned D-deck converter supports a declared constant
network subset. Direct ERG/ERE/ERK syntax inventories and safe TMD and XML readers
provide additional inspection paths. Full native-project, campaign, geometry,
environment, motion, source-runtime and Q1 compatibility qualification remain open.
No ESATAN, ESARAD, license, prior vendor export or remote converter is required.

## Declared D-deck profile

`EsatanAdapter(EsatanUnits(...), source_version=...)` requires an explicit source
release (`2018-sp1` or `2020`) and temperature, capacity, conductance, power and
time units. These release identifiers scope inspected syntax, not support for
every construct of either release. The profile is `esatan-d-constant/1`.

Supported records are nested `$MODEL`/`$ENDMODEL`, scalar `$LOCALS` with `$REAL`
or `$INTEGER`, constant `$NODES`, `$CONDUCTORS` GL pairs and static `$INITIAL`
temperature and internal-power assignments. `$INCLUDE` resolves inert data within
the declared root. Constants use bounded pure arithmetic and reviewed intrinsics;
source programs are never evaluated. D nodes with zero or omitted capacity map to
algebraic nodes; B nodes are prescribed. X nodes are explicitly retained and hold
complete reconstruction. Quoted labels, D exponents, comments, semicolon records,
line-based initial statements, Unicode and CRLF byte offsets are preserved.

Unknown node attributes, GR radiation, arrays, cases, runtime procedures and
unsupported sections remain required diagnostics. A partial node inventory can be
inspected but cannot be packaged as a native-ready model or written as a complete
new network. `runnable` means complete reconstruction on this subset, not an
available or qualified solver. `qualified` is always false.

Previews are immutable and bind units, release and exact source bytes. Includes
reject traversal, absolute/network paths, device names, hard links, reparse
points, aliases, cycles, repeated context and unresolved dependencies. Defaults
are 128 files, 16 MiB/file, 64 MiB total, 64 KiB/line, 100,000 records and depth 32.
Undeclared sibling files or directories block complete export.

## Preservation, edits and new models

`adapter.export(preview, new_destination, patches)` uses the common atomic
new-tree exporter. Patches bind exact byte ranges and SHA-256 values; assignment
identities, conductor endpoints, attribute names and line endings cannot change.
Reopen validates every changed tree before publication. Unknown required semantics
block editing. Originals, existing destinations and stale previews are protected.

`esatan_writer.export_model` writes new constant networks from validated canonical
entities and verifies reopened quantities, source identities and topology. The
receipt supplies the canonical-to-source identity map. An independent literal and
topology oracle supplements the reader/writer round trip. Unsupported entities,
hierarchies, unrepresentable labels, multiple loads on a node and parallel duplicate
GL pairs are rejected rather than silently discarded. Source annotation and
complete native-project generation remain outside this writer's scope.

`source_package(preview)` retains exact original files and fidelity evidence in
the existing versioned `.fcst` package only after complete native reconstruction.

## Native and XML inspection

`inspect_native` scans original ERG, ERE and ERK files directly. It inventories
declarations, vectors/arrays, named-argument definitions, variants, symbols and
unresolved expressions while preserving every source byte. This is a syntax
inventory, with required semantics retained as opaque, not a geometry solver or
a native-project writer. Unknown syntax and malformed constructs remain explicit.
Generic XML inspection rejects DTDs, entities, processing instructions, XInclude,
unsupported encodings and allocation/depth excess. LFS pointers are identified
separately from actual XML.

The acquired large XML was recovered from AcubeSAT's original GitLab repository,
at the same revision as the GitHub mirror. Its 211,760,264 bytes match the SHA-256
in the immutable original LFS pointer. The root is `postprocessdatafile`: this is
postprocessing chart/result data, **not a native project descriptor**. Streaming
inspection visits all 2,444,480 elements, including 838 series and 2,432,973 points,
without materializing their values. The reader bounds bytes, elements, depth and
attributes and rejects active XML constructs before parsing them. This recovery
closes the missing payload, not the native project/campaign schema requirement.

`tools/acquire_esatan_xml.py` repeats the hash-bound mirror acquisition to a new
local destination. `ci/esatan-acquisition.json` pins provenance, length and hashes.
Neither the baseline pointer nor engineering originals are overwritten or published.

## TMD results

`read_tmd` implements an inspected AnalysisSet/DataGroup dataset profile from the
acquired **2025-produced TMD files**. Their producer version is independent of the
2018-SP1 D-deck header. HDF5 readability alone does not qualify another schema.

`TmdBinding` requires exact source and canonical model hashes, selected analysis
and solution, case identity, numeric model indices, model names/paths and source
namespaces. Temperature and total internal power arrays map to canonical node
identities with explicit units, signs, time and discontinuities. Complete active
node coverage and node types must match; inactive X rows require a separate exact
binding and are counted in provenance. A source/runtime type difference blocks a
query until the binding and model accurately represent the result. No same-name
heuristic upgrades a mismatched model. Root-model layouts only are currently frozen.

The reader checks links, aliases, virtual/external storage, variable-length data,
filters, logical allocation, shapes, producer version and attribute vocabulary
before materializing selected arrays. Default interpolation is disabled; linear
or previous-sample policies are explicit and cannot silently cross an event.
Other result quantities, conductor histories and complete network reconstruction
from a TMD remain unimplemented. Returned provenance binds source/model/case and
the full selection binding. Public acceptance reports contain no result arrays.

## Commands and automated verification

CLI commands are `esatan-preview`, `esatan-export`, `esatan-package`,
`esatan-write-model`, `esatan-native-inspect` and `esatan-tmd-query`. Network commands
require all five `--*-unit` options and the declared `--source-version`. Native
inspection explicitly selects `--family erg|ere|erk|xml|postprocess-xml`; detailed
engineering inventories go to a new local output file. TMD queries take a local
JSON binding and expose explicit interpolation/discontinuity options.

```text
python tools/check_esatan.py --report .local/esatan.json
python tools/probe_esatan.py --resolved-xml .local/wp09/lfs/project.xml
python tools/verify.py --preset windows-debug
python tools/verify.py --preset windows-release
python -S tools/check_security.py
```

`ci/esatan-acceptance.json` freezes implementation cases and open qualification
holds. Both Windows drivers run the cases, including fresh-process conversion
with process/network/vendor-import guards, independent writer checks, malformed
input/fuzzing, real filesystem protection, source preservation, hostile HDF5 and
streaming XML attacks. CI clears the exact bounded `esatan.json` before upload;
the aggregate handoff checks candidate, coverage, input hashes and retained holds.
Optional-array acceptance runs in the locked tooling environment; the standard
library security path remains independent of h5py and numpy.

TST-021 also covers staged/outgoing history, approved author metadata, exact new
sources, synthetic fixtures, profile/acquisition manifests and final GitHub prose.
Raw originals, resolved XML, source dumps, TMD arrays, engineering inventories,
packages and failure logs stay local. A passing implementation gate cannot close
native-project/campaign coverage, owned-engine numerical comparisons or either
paired TD/ESA qualification direction.

## Source review

PyCanha's MIT-licensed implementation was reviewed at revision
`01c5e219c086ea25fbe00868ecd0e27994619fb3`, including its
[D-deck/TMD reader](https://github.com/pycanha-project/pycanha/blob/01c5e219c086ea25fbe00868ecd0e27994619fb3/src/pycanha/io/esatan_reader.py)
and [native grammar](https://github.com/pycanha-project/pycanha/blob/01c5e219c086ea25fbe00868ecd0e27994619fb3/src/pycanha/io/esatan/grammars/esatan_geometry.lark).
It informed format research; no upstream implementation was copied and no
PyCanha runtime is required. Its own geometry coverage has losses and omissions,
so it cannot establish complete preservation or campaign qualification for FCST.
Public attribution remains with PyCanha and its upstream license.
