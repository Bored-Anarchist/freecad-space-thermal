# WP-11 qualification and remaining gates

All ten numbered native implementation substeps are present. The remaining
locally executable acceptance work adds fixed-step event/duty refinement,
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
| PHY-001 | Analytic and independent RK4 cases; mixed capacitive/algebraic/prescribed SINDA/ESATAN literal-source comparisons | Licensed paired-source profile/reference admission |
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

WP-11 therefore retains `in_progress` for its full Q1 completion gate. Native
coverage can pass while paired qualification remains blocked. Durable-job/HDF5,
host and MCP integration is follow-on work across WP-06/13/14/15, not an omitted
eleventh native-engine implementation substep. This PR is not automatically
merged and its work-package issue is not closed on partial qualification.
