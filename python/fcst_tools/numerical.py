# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent Q0 oracle and fail-closed evidence assessment (no SUNDIALS)."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from .gate import evaluate

REQUIRED_CASES = ["coverage", "analytic-seed-dense", "analytic-seed-band", "stiff-nonlinear-heater-dense",
    "stiff-nonlinear-heater-band", "oracle-refinement", "backend-equivalence", "restart-dense", "restart-band",
    "invalid-input", "inconsistent-initialization", "scale-dense-128", "scale-band-128", "scale-band-1000",
    "scale-band-10000", "scale-band-100000", "engine-only-install", "steady-dense", "steady-band",
    "analytic-seed-adams", "stiff-nonlinear-heater-adams", "restart-adams", "property-domain"]


def validate_policy(criteria, fixture):
    if criteria["required_cases"] != REQUIRED_CASES or len(set(REQUIRED_CASES)) != len(REQUIRED_CASES):
        raise ValueError("required_coverage_changed")
    for name in ("temperature_K", "energy_J", "algebraic_W", "jacobian", "event_time_s", "restart_K", "scale_error", "scale_residual"):
        values = criteria[name]
        if any(not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in values.values()) or values["normalization_floor"] <= 0:
            raise ValueError("invalid_criterion")
    if set(fixture["cases"]) != {"analytic-seed", "stiff-nonlinear-heater"}:
        raise ValueError("fixture_coverage_changed")
    for case in fixture["cases"].values():
        if len(case["parameters"]) != 13 or len(case["initial"]) != 3 or not case["oracle"]:
            raise ValueError("invalid_fixture")
    stats = criteria["statistical_policy"]
    if len(stats["seeds"]) != len(set(stats["seeds"])) or stats["replicates"] != len(stats["seeds"]) or stats["coverage"] != .95:
        raise ValueError("invalid_ensemble")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def native_cache_root(checkout, local_app_data):
    """Keep MSVC object/library paths short and isolate concurrent checkouts."""
    key = digest(str(Path(checkout).resolve()).casefold().encode("utf-8"))[:12]
    return Path(local_app_data) / "fcst-q0" / key


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def within(value, reference, criterion):
    return (finite_number(value) and finite_number(reference) and
            abs(value - reference) <= criterion["atol"] + criterion["rtol"] * abs(reference))


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def valid_sample(row):
    return (isinstance(row, dict) and isinstance(row.get("state"), list) and len(row["state"]) == 3
            and isinstance(row.get("heater"), bool)
            and all(finite_number(v) for v in [row.get("time_s"), row.get("algebraic_K"), *row["state"]]))


def algebraic(p, y):
    c1, c2, s1, s2, g, g2, gb, slope, rad, tb, power, low, high = p
    if not g2:
        return tb
    # Newton rather than the native bisection; same declared physical equations.
    a = (y[0] + y[1] + tb) / 3
    for _ in range(30):
        conductance = g * (1 + slope * (y[0] + a - 2 * tb))
        residual = conductance * (y[0] - a) - g2 * (a - y[1]) - rad * (a**4 - tb**4)
        derivative = g * slope * (y[0] - a) - conductance - g2 - 4 * rad * a**3
        step = residual / derivative
        a -= step
        if abs(step) < 1e-12:
            return a
    raise ValueError("oracle_algebraic_not_converged")


def rate(p, y, heater):
    c1, c2, s1, s2, g, g2, gb, slope, rad, tb, power, low, high = p
    a = algebraic(p, y)
    flow = g * (1 + slope * (y[0] + a - 2 * tb)) * (y[0] - a)
    incoming = power if heater else 0
    external = incoming - gb * (y[1] - tb) - rad * (a**4 - tb**4) if g2 else incoming - flow
    return [(incoming - flow) / (c1 + s1 * (y[0] - tb)),
            (g2 * (a - y[1]) - gb * (y[1] - tb)) / (c2 + s2 * (y[1] - tb)) if g2 else 0,
            external]


def rk4(p, y, heater, h):
    k1 = rate(p, y, heater)
    k2 = rate(p, [a + h*b/2 for a, b in zip(y, k1)], heater)
    k3 = rate(p, [a + h*b/2 for a, b in zip(y, k2)], heater)
    k4 = rate(p, [a + h*b for a, b in zip(y, k3)], heater)
    return [a + h*(b+2*c+2*d+e)/6 for a, b, c, d, e in zip(y, k1, k2, k3, k4)]


def oracle(case, step):
    p, y = case["parameters"], case["initial"][:]
    t, heater, events, samples = 0.0, True, [], []
    targets = [i * case["sample_s"] for i in range(round(case["end_s"] / case["sample_s"]) + 1)]
    for target in targets:
        while t < target - 1e-12:
            h = min(step, target - t)
            next_y = rk4(p, y, heater, h)
            threshold = p[-1] if heater else p[-2]
            crossing = next_y[0] >= threshold if heater else next_y[0] <= threshold
            if crossing:
                left, right = 0.0, h
                for _ in range(38):
                    middle = (left + right) / 2
                    hot = rk4(p, y, heater, middle)[0] >= threshold
                    if hot == heater:
                        right = middle
                    else:
                        left = middle
                h = (left + right) / 2
                next_y = rk4(p, y, heater, h)
                heater = not heater
                events.append(t + h)
            t += h
            y = next_y
        samples.append({"time_s": target, "state": y[:], "algebraic_K": algebraic(p, y), "heater": heater})
    return {"samples": samples, "events_s": events}


def steady_oracle(p):
    """Independent scalar heat balance, followed by inverse branch conductance."""
    c1, c2, s1, s2, g, g2, gb, slope, rad, tb, power, low, high = p
    left, right = tb, tb + 100
    for _ in range(90):
        a = (left + right) / 2
        second = (g2*a + gb*tb) / (g2+gb)
        if gb*(second-tb) + rad*(a**4-tb**4) > power:
            right = a
        else:
            left = a
    a = (left+right)/2
    second = (g2*a + gb*tb) / (g2+gb)
    # Solve the conductance quadratic using its positive root without cancellation.
    base = 1 + 2*slope*(a-tb)
    difference = 2*power/g/(base+math.sqrt(base*base+4*slope*power/g))
    return [a+difference, second, a]


def compare(case, observation, reference, criteria):
    """Assess each sample, critical node and event; averages cannot hide failures."""
    errors = []
    if observation.get("status") != "completed":
        return ["execution_incomplete"], {}
    rows, expected = observation.get("samples", []), reference["samples"]
    if len(rows) != len(expected) or not rows:
        return ["sample_coverage"], {}
    p = case["parameters"]
    temps, energy, balances = [], [], []
    for row, ref in zip(rows, expected):
        if not valid_sample(row):
            return ["invalid_sample"], {}
        if row["time_s"] != ref["time_s"] or row["heater"] != ref["heater"]:
            errors.append("sample_or_control_mismatch")
        for v, r in zip(row["state"][:2] + [row["algebraic_K"]], ref["state"][:2] + [ref["algebraic_K"]]):
            temps.append(abs(v-r))
            if not within(v, r, criteria["temperature_K"]):
                errors.append("temperature_error")
        y = row["state"]
        enthalpy = sum(c*(v-p[9]) + s*(v-p[9])**2/2 for c, s, v in zip(p[:2], p[2:4], y[:2]))
        initial_h = sum(c*(v-p[9]) + s*(v-p[9])**2/2 for c, s, v in zip(p[:2], p[2:4], case["initial"][:2]))
        delta = enthalpy - initial_h - (y[2] - case["initial"][2])
        energy.append(abs(delta))
        if not within(delta, 0, criteria["energy_J"]):
            errors.append("energy_balance")
        a = row["algebraic_K"]
        balance = (p[4]*(1+p[7]*(y[0]+a-2*p[9]))*(y[0]-a) - p[5]*(a-y[1]) - p[8]*(a**4-p[9]**4)) if p[5] else a-p[9]
        balances.append(abs(balance))
        if not within(balance, 0, criteria["algebraic_W"]):
            errors.append("algebraic_balance")
    events, ref_events = observation.get("events_s", []), reference["events_s"]
    if len(events) != len(ref_events) or any(not within(a, b, criteria["event_time_s"]) for a, b in zip(events, ref_events)):
        errors.append("event_error")
    if not within(observation.get("jacobian_error", math.inf), 0, criteria["jacobian"]):
        errors.append("jacobian_error")
    return sorted(set(errors)), {"max_temperature_error_K": max(temps),
        "rms_temperature_error_K": math.sqrt(sum(x*x for x in temps)/len(temps)),
        "p95_temperature_error_K": sorted(temps)[math.ceil(.95*len(temps))-1],
        "max_energy_error_J": max(energy), "max_algebraic_residual_W": max(balances), "events": len(events)}


def compare_restart(partial, resumed, uninterrupted, split, criteria):
    """Compare complete checkpoint/resume coverage, controls and SI quantities.

    Prefix zip comparisons are insufficient: a shortened successful-looking
    resume must fail even when every remaining value is accurate.
    """
    errors, temperature_errors, energy_errors = [], [], []
    expected = uninterrupted.get("samples", [])
    if uninterrupted.get("status") != "completed" or not expected or not all(valid_sample(r) for r in expected):
        return ["invalid_reference"], {}
    for observed, rows, status in ((partial, [r for r in expected if r["time_s"] <= split], "cancelled"),
                                    (resumed, [r for r in expected if r["time_s"] >= split], "completed")):
        actual = observed.get("samples", [])
        if observed.get("status") != status:
            errors.append("execution_incomplete")
        if not within(observed.get("jacobian_error"), 0, criteria["jacobian"]):
            errors.append("jacobian_error")
        if not rows or len(actual) != len(rows) or not all(valid_sample(r) for r in actual):
            errors.append("sample_coverage")
            continue
        if (status == "cancelled" and actual[-1]["time_s"] != split
                or status == "completed" and actual[0]["time_s"] != split):
            errors.append("checkpoint_time")
        for row, reference in zip(actual, rows):
            if row["time_s"] != reference["time_s"] or row["heater"] != reference["heater"]:
                errors.append("sample_or_control_mismatch")
            for value, target in zip(row["state"][:2] + [row["algebraic_K"]], reference["state"][:2] + [reference["algebraic_K"]]):
                temperature_errors.append(abs(value-target))
                if not within(value, target, criteria["restart_K"]):
                    errors.append("restart_temperature")
            energy_errors.append(abs(row["state"][2]-reference["state"][2]))
            if not within(row["state"][2], reference["state"][2], criteria["energy_J"]):
                errors.append("restart_energy")
        events = [t for t in uninterrupted.get("events_s", []) if (t <= split if status == "cancelled" else t > split)]
        actual_events = observed.get("events_s", [])
        if len(actual_events) != len(events) or any(not within(a,b,criteria["event_time_s"]) for a,b in zip(actual_events,events)):
            errors.append("event_error")
    return sorted(set(errors)), {"max_temperature_error_K": max(temperature_errors, default=0),
                                "max_energy_error_J": max(energy_errors, default=0)}


def compare_steady(parameters, observation, reference, criteria):
    rows = observation.get("samples", [])
    if observation.get("status") != "completed" or len(rows) != 1 or not valid_sample(rows[0]):
        return False
    row, residual = rows[0], observation.get("residual")
    if (not finite_number(residual) or not 0 <= residual < 1e-10 or row["time_s"] != 0 or not row["heater"]
            or not all(within(a,b,criteria["temperature_K"]) for a,b in zip(row["state"][:2]+[row["algebraic_K"]], reference))):
        return False
    # Independently check physical heat balance rather than trusting a reported norm.
    p, y, a = parameters, row["state"], row["algebraic_K"]
    q = p[4]*(1+p[7]*(y[0]+a-2*p[9]))*(y[0]-a)
    return all(within(value, 0, criteria["algebraic_W"]) for value in
               (p[10]-q, p[5]*(a-y[1])-p[6]*(y[1]-p[9]), q-p[5]*(a-y[1])-p[8]*(a**4-p[9]**4)))


def assess_attempt(path):
    """Replay only sealed bytes; new criteria require a new immutable attempt."""
    path = Path(path)
    manifest_bytes = (path / "manifest.json").read_bytes()
    seal = json.loads((path / "seal.json").read_bytes())
    manifest = json.loads(manifest_bytes)
    if digest(manifest_bytes) != seal["manifest_sha256"]:
        raise ValueError("manifest_changed")
    if set(manifest["artifacts"]) != {"criteria.json", "fixture.json", "observations.json", "assessment.json"}:
        raise ValueError("artifact_coverage_changed")
    for name, expected in manifest["artifacts"].items():
        if name not in {"criteria.json", "fixture.json", "observations.json", "assessment.json"} or digest((path / name).read_bytes()) != expected:
            raise ValueError("artifact_changed")
    for name, expected in manifest.get("local_artifacts", {}).items():
        if Path(name).name != name or not name.endswith((".log", ".json")) or digest((path/name).read_bytes()) != expected:
            raise ValueError("local_artifact_changed")
    criteria = json.loads((path / "criteria.json").read_bytes())
    validate_policy(criteria, json.loads((path / "fixture.json").read_bytes()))
    assessment = json.loads((path / "assessment.json").read_bytes())
    gate = evaluate(criteria["required_cases"], assessment["cases"])
    if manifest.get("require_reference") and not manifest.get("reference_match"):
        gate["status"] = "failed"
        gate["problems"].append("reference_profile_mismatch")
    if gate != assessment["gate"] or manifest["state"] != "completed":
        raise ValueError("assessment_incomplete")
    return gate
