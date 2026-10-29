# Thermal Desktop / SINDA implementation (WP-08)

WP-08 supplies an implementation delivery for the pinned TD 6.3 path. **Q1
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

`END OF DATA`, header spelling, whitespace, comments and line endings survive
unchanged export. Repeated/ambiguous inserts, section leakage, cycles, missing
files, traversal, absolute/network/device paths, links/hard links, case aliases
and size/depth/entity budget overruns fail closed. Default limits reuse WP-07's
128 files, 1 MiB/file, 8 MiB total, 10,000 records and depth 32.
Noncomment data after `END OF DATA`, ambiguous terminators inside INSERT files
and data headers without an explicit submodel also reject native reconstruction.

Property arrays, runtime controls/cases, dynamic registers, unreviewed procedures,
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

## OpenTD sidecar and copied DWG projects

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

`td_qualification.assess` retains the Q1 gates for exact runtimes, controlled
licensed host, dependency closure, unchanged/edited reopen/run, independent native
source edits, result provenance, owned thermal/radiation/environment comparisons
and paired ESA qualification. Missing/stale/duplicate cases, SDK shims, parser-only
tests, upstream output and external fallback labels cannot close those gates.

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

TST-021 scans actual adapter/C# sources, fixtures, summaries, evidence and final
GitHub prose. Policy v4 adds `.cs` to inspected text types with unchanged sensitive
patterns, binary rejection and inspection budgets. Originals, property databases,
DWG/deck/result bytes, private profiles, compiled sidecars, vendor DLLs and raw logs
stay local. Scan staged bytes and outgoing history before upload; the scopes may
be scanned separately, and neither may be omitted. No scanner finding is suppressed
to publish a fixture or report.
