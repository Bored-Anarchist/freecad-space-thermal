# WP-11 qualification and remaining gates

WP-11 engine implementation and independent numerical sign-off are complete.
Windows Debug and Release each passed 344 checks on the implementation candidate
recorded in [the evidence](evidence/WP-11.json), including all 80 native cases and
63 reference comparisons from 46 runs. Project-wide Q1 and vendor-specific
compatibility remain separate and unqualified.

All ten numbered native implementation substeps are present. Native
qualification acceptance includes fixed-step event/duty refinement,
representative manufactured/localized compiled-network profiling, subnormal-tail
linear-solve acceptance, independent source-literal oracles,
captured-result contract checks and requirement coverage receipts.

Actual verdicts belong to candidate/input/five-binary-bound `thermal.json` and
[the implementation evidence](evidence/WP-11.json). The versioned
[qualification/oracle register](../ci/thermal-qualification-v1.json) specifies
required cases and thresholds. Both Windows presets execute the same register.
The planning [traceability CSV](requirement-traceability.csv) intentionally keeps
`planned` statuses; its validator explicitly rejects using that plan as an
unsubstantiated test-result ledger. Native receipts now make coverage executable
without changing those planning semantics or claiming full Q1 qualification.

| Requirement | Native acceptance evidence | Remaining wider Q1 obligations |
| --- | --- | --- |
| ARC-009 | Installed C++ worker, preparation and native steady/transient cases with host/vendor search paths absent | Release/profile qualification belongs to WP-19 |
| ARC-015 | Compiled assembly/LU counters and timings on manufactured and localized 256-equation networks; Python-orchestrated source/CLI comparisons | Host and MCP parity in WP-13/WP-14 |
| PHY-001 | Analytic/RK4 and independently formulated IDA/Radau benchmarks; Pycanha cooling/closed/DAE trials; source-literal comparisons | Vendor compatibility requires its own source-profile admission |
| PHY-005 | Fixed 0.2/0.1/0.05 s event-time/duty refinement, schedules, simultaneous ordering, restart and chatter rejection | Broader environment-dependent controls with WP-17 |
| PHY-006 | Singular/nonconvergent/fill/step/attempt failures, rejected trials and explicit termination diagnostics | Job/result orchestration remains follow-on integration |
| PHY-007 | Closed/open energy, enthalpy, boundary power and explicit defect failures | Coupled radiation/environment implementations in WP-12/WP-17 |
| TST-004 | Native-only required cases and deliberately perturbed model/result/mode/identity/time regressions | Full radiation/environment suites with their implementations |

The owned SINDA/ESATAN decks use frozen, independently specified physical
constants. They establish source decoding plus owned-engine execution against an
analytic oracle. They do not contain acquired engineering data, execute vendor
software or supply licensed vendor result evidence.

The offline [captured-reference tool](../tools/compare_thermal_reference.py)
checks source/result/receipt byte hashes and explicit units, model/node identity,
time grids, native execution mode and numerical agreement. Its detailed bounded
contract is in [the engine documentation](../docs/thermal-engine.md). Success is
a comparison receipt only: it does not prove the receipt's authenticity or
license validity, and cannot grant vendor/Q1 qualification. Synthetic contract
tests explicitly exercise this distinction.

No approved reference runner or captured reference pair is available, as
confirmed during this work. [GAP-LICENSES and GAP-RESULTS](../inventory/gaps.json)
remain blocked under their existing owners. Public CI continues to execute the
owned suite unattended; it cannot replace those licensed gates. Raw source
models, printed/TMD arrays, operational/reviewer/license data, native binaries
and logs remain local under TST-021. Only separately privacy-cleared bounded
verdict/hash/count/timing evidence is published.

The user approved independent alternatives for engine numerical qualification,
including a Pycanha trial. [The frozen profile](../ci/thermal-reference-v1.json)
requires separately formulated IDA and Radau equations for eight benchmarks,
reference refinement and agreement, seven analytical transient oracles, four
manufactured steady equilibria and three refined Pycanha trials. The
[reference contract](../references/thermal/README.md) records formulation,
settings, exclusions and reproducible pinned runtime provision. Both Windows
presets require 46 run receipts and 63 comparisons alongside all 80 native cases;
no external receipt satisfies a native case. Missing/stale/substituted or
inflated evidence fails. The exact-grid enthalpy regression also checks the
native correction for sub-minimum decimal step remainders.

Engine numerical completion is assessed against this independent profile and
the native register. Licensed paired results are optional additional evidence
for that numerical scope. Their absence retains vendor compatibility holds,
without blocking PHY-001's analytical/independent-solver requirement. Project Q1
remains unqualified: TD/ESA source semantics, host/MCP parity, coupled physics,
durable-job/HDF5 and release integration retain their own work packages.
The work-package evidence separates engine completion from those wider gates;
its actual tested candidates and bounded report hashes are recorded after both
Windows presets pass. This PR is not automatically merged.
