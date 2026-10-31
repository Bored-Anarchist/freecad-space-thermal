# Independent WP-11 numerical references

These test programs contain separately written literal equations for owned
synthetic networks. They do not import FCST Python modules, decode FCST models,
include engine headers or link `fcst_core`. The native subject adapter alone
loads the engine fixtures and uses the engine assembly and solvers.

The frozen [comparison policy](../../ci/thermal-reference-v1.json) requires:

| Reference | Pinned implementation | Formulation |
| --- | --- | --- |
| SUNDIALS IDA | 7.3.0, exact source archive and revision in `ci/probe-sources.json` | Full residual DAE, BDF; algebraic/prescribed states have exactly zero differential IDs |
| SciPy Radau | 1.15.2, hash-locked wheels | Reduced ODE, implicit Radau IIA; linear algebraic elimination or independent monotone Brent root solve |
| Pycanha core | 0.23.0, hash-locked CP313 Windows wheel and numerical runtime | `TSCNRLDS` Crank-Nicolson, Eigen sparse solver; cooling, closed network and true zero-capacity DAE |

The eight mandatory IDA/Radau cases are cooling, closed two-node exchange,
capacitive/algebraic/prescribed DAE, variable heat capacity, stiff two-timescale
exchange, hysteretic heater, load schedule and nonlinear radiation/environment
callbacks. The native stiff fixture has a 10 ns fast mode. The native benchmark
uses the actual callback/steady/transient APIs; the references never call them.

Both external methods integrate external and boundary energy as additional
differential states. They solve heater roots directionally, stop/restart at
schedule knots and preserve accumulated energy. Requested samples include the
initial state and exact discontinuity times. Native event samples are additional
observations; comparisons use every requested time without interpolation and
separately require identical event kind/action ordering and bounded time error.
Four cases also compare native steady solutions against independently integrated
equilibria and manufactured exact equilibria. Analytical solutions independently
check seven transient cases, including both exponential modes of the stiff case.

IDA/Radau must agree under tolerance refinement from 1e-9 to 1e-11 and agree
with each other. Pycanha uses 0.001/0.0005 s step refinement and analytical
temperature checks. Its adapter initializes the algebraic temperature to the
exact consistent 305 K and assigns zero capacity; it does not test Pycanha's
handling of an inconsistent 350 K guess. The native and IDA tests do start from
that inconsistent guess. Pycanha exclusions are explicit adapter scope limits,
not claims that the package cannot implement variable properties or events.
It is an additional reference, not a replacement for either mandatory solver.

Normal native limits are 0.002 K, 0.005 W, 0.02 J, 0.003 s for event time and
0.002 duty fraction. The stiff native temperature/power limits are 0.01 K/0.02 W.
The exact policy also freezes tighter reference agreement and steady limits.
Initial trials at 1e-6 K native tolerance missed the closed-network flow and
heater temperature limits. Native tolerances were tightened to 1e-7 K, 5e-8 K
for the heater, retaining 1e-5 K for the stiff case; comparison limits were not
relaxed. Local-error settings are not a global-error guarantee.

`tools/check_thermal_references.py` builds IDA separately and provisions a
portable CPython 3.13.2 Pycanha environment under `.local`. All downloads have
exact archive/wheel hashes. It verifies every regular SUNDIALS source member
before rebuilding and installed wheel RECORD hashes before running references.
Reference children use isolated Python, fresh bytecode search paths and no
bytecode writes. Installed bytecode caches are neither trusted nor fingerprinted.
Native/IDA children execute with only their own binary directory on PATH.
The production engine has no reference dependencies.

Python uses the PSF license; SUNDIALS and SciPy use BSD licenses; Pycanha core
uses MIT. NumPy and the Intel numerical runtime components retain their upstream
license notices in the local installations. Exact artifacts, versions and
upstream license metadata are in the runtime manifest and locks; no wheel,
runtime or third-party source is vendored or uploaded by this workflow.

Both Windows verification presets require the reference gate in addition to all
80 native acceptance cases. The public `thermal-references.json` has 46 bounded
run receipts and 63 comparison verdicts, exact source/native/reference runtime
hashes, frozen limits and maximum errors. Raw arrays, checkpoints, binaries,
compiler/runtime diagnostics and dependency artifacts remain local. TST-021
scans the exact summary before upload; the aggregate rejects missing, stale,
substituted, duplicate, failed or inflated evidence.

This profile qualifies the engine's numerical behavior on the declared
benchmarks. It does not certify TD/SINDA or ESATAN compatibility, authenticate
licensed vendor results, qualify a hardware performance profile or grant the
project-wide Q1 gate. Those claims retain their own evidence requirements.
