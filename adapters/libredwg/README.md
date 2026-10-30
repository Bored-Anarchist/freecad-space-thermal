# Independent DWG executable

This separately built program and its linked LibreDWG backend are licensed under
GPL-3.0-or-later; see LICENSE. LibreDWG is copyright the Free Software Foundation
and its contributors. The FCST thermal engine does not link this component.
The Python source-exchange interface communicates with the executable through
bounded local files and a closed command protocol.

Build from the exact upstream source archive and preservation patch pinned in
the backend profile. Retain the complete corresponding source, modifications,
build recipe and upstream notices with any distributed binary; distribution
packaging and release evidence must satisfy this component's license. No vendor
binary or licensed Thermal Desktop/AutoCAD runtime is used or redistributed.

The program reads native DWG structures directly. It emits authoritative opaque
payload bit counts/bytes, class records and raw unparsed datastorage sections.
The standard field stream retains repeated subclass/field occurrences through
the application's ordered field representation. Native rewrites are reopened and
audited before they can be accepted. Reading the container does not implement TD
thermal-class semantics or qualify native thermal editing.

`fixture` creates only an owned synthetic geometry/container example. It never
creates an alleged Thermal Desktop model or supplies TD qualification evidence.

Protocol `fcst-dwg-native/2` retains full Unicode class names and normalizes partial
opaque bytes to MSB-first wire order. Stream coordinates are explicit. The owned
`rewrite-edited` packet permits only bounded RcNode/RcConductor/RcHeatLoad payload
replacements tied to exact original bytes. Application codecs guard permitted
scalar fields; independent reopen checks all unrequested logical fields.

`create-network` consumes an owned bounded binary packet and creates new node,
conductor, heat-load, rectangle and brick objects in a new container, including separate text and
reference streams. It uses no source model template. The preservation patch
removes upstream dummy/point substitution; missing thermal objects or changed
fields fail the required fresh-process decoder comparison. Neither a structural
round trip nor a synthetic fixture grants target-product/full-model qualification.

The required Windows self-test exercises the frozen cases, including actual
vendor-denied CLI import to a portable native project, canonical scalar editing,
source export and fresh semantic reopen; constant property library/document
conversion and source-preserving native property edits; Celsius offsets/scaled
power; and refusal to promote unsupported modes. Source locks bind the Python
conversion/contract/CLI sources as well as the native bridge and patch.
Complete rectangle/brick wire generation and two-parameter compressed source edits
are also reopened through fresh native processes. Actual solid class spelling is
retained independently of its C++ name. The bridge accepts only the five declared
classes for edits, exact original bytes and bounded 0/64/128-bit expansion. The
application guards parameter expressions and verifies every unrequested field;
full geometric/thermal interpretation and mesh regeneration remain unimplemented.
CLI diagnostics stay local; the published self-test artifact contains verdicts,
source hashes and nonqualification flags only.
