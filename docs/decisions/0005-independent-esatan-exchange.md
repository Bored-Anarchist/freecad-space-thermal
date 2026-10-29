# Independent ESATAN file conversion

Status: accepted product constraint and WP-09 implementation plan. ESATAN
conversion remains planned; this document does not claim implemented readers,
writers, native execution or qualified compatibility.

## Required behavior

ESATAN import, editing, export and fresh-process reopen must work without
ESATAN-TMS, ESARAD, vendor APIs, license servers, remote conversion services or
a prior conversion/export in a vendor product. This applies to original native
source projects, their campaign/case/dependency files and the required network
and result formats. It extends the
[independent TD exchange decision](0004-independent-thermal-exchange.md) to WP-09.

Direct file readers/writers and owned versioned semantic codecs are the product
path. A separately installed licensed reference tool may produce optional
comparison evidence; it cannot be a consumer dependency, an implicit fallback or
the implementation of first import or export. Missing vendor access must not
stop direct-format implementation or independent tests. A previous mandatory
native-API/export bridge in the WP-09 plan is superseded.

## File and semantic coverage

Keep these independently tested operations and version profiles separate:

| Source | Owned implementation needed | Acceptance boundary |
|---|---|---|
| Native GMM geometry, including required `.erg` dialects | Bounded lexer/parser, symbol/expression handling, transforms, topology and typed geometry/mesh associations | Geometry alone cannot establish a complete thermal model |
| Environment/kinematics companions, including required `.ere` and `.erk` dialects | Direct parsing/writing of environments, articulations, coordinate frames and referenced datasets | No silent defaults for missing environment or motion data |
| Project/campaign descriptors and analysis templates | Safe XML/text readers/writers, case inheritance/overlays, referenced files and full dependency closure | No external XML entities, shell evaluation or source-program execution |
| TMM / `.d` network decks | Versioned syntax-preserving readers/writers for nodes, submodels, properties, couplings, arrays, expressions, controls and reviewed source logic | Static source retention does not implement runtime semantics |
| Required result files, including acquired HDF5 `.tmd` families | Independent dataset/schema readers with node/case identity, quantities, units, signs and time/event grids | HDF5 readability alone does not establish the vendor dataset schema |
| STEP-TAS supplied as actual input/output | Schema/dictionary-backed owned readers/writers and required companion data under WP-10 | Never require a user to generate STEP-TAS in ESATAN before import |

These are scoped required format families, not an assertion that each extension
has one universal grammar. The acquired corpus identifies 2018 SP1 and 2020
families; additional proposed versions need their own fixtures and complete
read/represent/edit/write coverage. Container syntax, source release, units,
geometry/network correspondence and procedure semantics must be declared, not
inferred from filenames. Binary formats need reviewed binary codecs; undocumented
fields stay explicitly unresolved. Never invent an interpreted binary schema.

## WP-09 delivery sequence

1. Inventory original native projects and all required companions/results without
   invoking a vendor tool. Freeze exact dialect/schema/source-version profiles,
   source hashes, fixture rights and required feature/direction coverage. Keep
   restricted model values and metadata in authorized local storage.
2. Implement safe direct lexers/parsers and complete dependency resolution. Retain
   source byte ranges, comments, case identifiers, expressions and unrecognized
   regions. Bound bytes/files/depth, parsing complexity and result arrays. Reject
   traversal, links, aliases, cyclic includes and unresolved required references.
3. Translate required thermal, geometry, material, optical, environment, kinematic,
   case and procedure constructs into the shared typed canonical model/IR. Required
   logic executes through reviewed owned-engine semantics; imported Fortran or
   scripts never become a conversion interpreter. Report unsupported required
   entities/cases precisely and block native readiness.
4. Implement reverse serializers for supported edits and new models. Export only
   into a new complete tree, preserve every unrequested source field and opaque
   region, and keep originals immutable. Reopen through independently exercised
   direct readers; an unchanged source copy is not a new-model writer.
5. Implement direct result readers with exact source identity, unit/sign/time
   provenance, event-aware sampling and explicit interpolation. Retain original
   result bytes locally. Match result records to the correct model/campaign/case;
   reject ambiguous, duplicate, missing or unmapped records.
6. Qualify all required directions in an offline Windows environment where vendor
   installations, assemblies, processes, license services and conversion servers
   are absent. Attempted vendor use fails acceptance. No manual test execution
   or prior vendor-side export is assigned to the user.
7. Compare owned-engine results with independent analytic/reference baselines and
   complete the paired TD/ESA common profile. Optional source-tool comparisons
   remain separately labeled evidence. Missing reference or schema evidence holds
   the relevant compatibility claim; it does not authorize a runtime dependency.

## Unattended acceptance to implement with the feature

WP-09's acceptance manifest must bind every case to exact input/output, codec,
criteria, build and observation hashes. Required cases include:

- First import of a complete original native project with all vendor tools absent.
- Separate first import of the required network and result dialects.
- Unchanged, load, material/table, geometry/topology, property, environment/motion
  and campaign/case edits, with independently checked identity and preservation.
- New-model native-project and network export, then fresh-process direct reopen.
- Source dependency and geometry/network/result mapping closure after every edit.
- Malformed/future syntax, unknown required semantics, arrays/logic, missing files,
  aliases/links/traversal, recursive includes, XML entity attacks, resource limits
  and parser fuzzing; input text cannot grant process or network authority.
- Offline process/import/network guards proving no ESATAN, TD/OpenTD, license
  service, vendor API or conversion-server call participates in conversion.
- Owned-engine numerical comparisons and both TD-to-ESA and ESA-to-TD directions,
  with separate fidelity reports and explicit losses. Progress in one direction
  does not compensate for the other or close its required coverage.

Source files, campaign metadata, full inventories and numerical arrays can contain
restricted engineering or personal information. TST-021 must scan exact outgoing
owned source, synthetic fixtures, manifests, bounded summaries and final GitHub
prose. Preserve originals locally; never publish raw native models, decoder dumps,
private paths, user procedures, binary libraries or raw logs as test evidence.

WP-09 stays Planned until implementation starts. Documentation changes and an
available ESATAN installation cannot qualify the independent conversion path.
