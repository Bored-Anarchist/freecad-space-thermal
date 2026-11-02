# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded verification scheduling and exact, candidate-bound unit receipts."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from .gate import evaluate
from .foundation import input_hashes


def unit_inputs(root):
    """Include every workflow inspected by the unit suite, not just Foundation CI."""
    from hashlib import sha256
    result = input_hashes(root)
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        result[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()
    return result


def check_unit_report(report, candidate, inputs, manifest_hash, expected):
    if (report.get("scope") != "unit-tests" or report.get("candidate") != candidate
            or report.get("input_sha256") != inputs
            or report.get("coverage_manifest_sha256") != manifest_hash
            or report.get("gate") != evaluate(expected, report.get("cases", []))
            or report["gate"]["status"] != "passed"):
        raise ValueError("unit_receipt_stale_or_incomplete")
    return report["cases"]


def schedule(stages, execute, jobs=2):
    """Run stages once; serialize users of the mutable SUNDIALS download/build inputs."""
    if not 1 <= jobs <= 4 or len(stages) != len(set(stages)):
        raise ValueError("verification_schedule")
    shared = {"thermal-reference-comparison", "numerical-checkpoint"}
    pending = list(stages)
    running = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        while pending or running:
            for stage in list(pending):
                if len(running) >= jobs:
                    break
                if stage in shared and any(s in shared for s in running.values()):
                    continue
                pending.remove(stage)
                running[pool.submit(execute, stage)] = stage
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                stage = running.pop(future)
                yield stage, future.result()


def prioritize(stages, estimates):
    """Historical costs change order only; new stages still execute exactly once."""
    import math
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0
           for v in estimates.values()):
        raise ValueError("verification_estimates")
    return sorted(stages, key=lambda stage: -estimates.get(stage, 0))


def check_native_inventory(inventory, thermal, radiation, build, root):
    """Every omitted CTest invocation must have the identical acceptance owner."""
    config = Path(build)
    fixture = Path(root) / "tests/fixtures/thermal"
    expected = {
        "native-build-info": [config / "fcst-worker.exe", "--build-info"],
        "native-self-test": [config / "fcst-worker.exe", "--self-test"],
    }
    prefixes = (("native-", "thermal-", "fcst-thermal-tests.exe"),
                ("assembly-", "thermal-assembly-", "fcst-thermal-assembly-tests.exe"),
                ("steady-", "thermal-steady-", "fcst-thermal-steady-tests.exe"),
                ("transient-", "thermal-transient-", "fcst-thermal-transient-tests.exe"))
    for case in thermal["required_cases"]:
        if case == "native-preparation" or case.startswith(("steady-cli-", "transient-cli-")):
            continue
        for prefix, label, executable in prefixes:
            if case.startswith(prefix):
                argument = case.removeprefix(prefix)
                path = fixture / "material-network.json" if prefix == "native-" else fixture
                expected[label + argument] = [config / executable, argument, path]
                break
    for case in radiation["native_cases"]:
        expected["radiation-" + case] = [config / "fcst-radiation-tests.exe", case, fixture]
    tests = inventory["tests"]
    if len(tests) != len(expected) or {t["name"] for t in tests} != set(expected):
        raise ValueError("native_acceptance_coverage")
    def normalized(command):
        # Windows paths are case-insensitive; native case names and flags are not.
        return [str(value).replace("\\", "/").casefold() if index == 0 or index == 2 else str(value)
                for index, value in enumerate(command)]
    for test in tests:
        if normalized(test["command"]) != normalized(expected[test["name"]]):
            raise ValueError("native_acceptance_command")
    return True
