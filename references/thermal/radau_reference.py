# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent reduced ODE equations, without FCST imports or model parsing.

Algebraic temperatures are eliminated, not given artificial thermal mass.
Energy integrals are independent differential states. Events restart Radau.
"""
import json
import math
import sys
import scipy
from scipy.integrate import solve_ivp
from scipy.optimize import brentq


def execute(name, level):
    tolerance = {"coarse": 1e-9, "fine": 1e-11}[level]
    initial = {"cooling": [310.], "closed": [310., 290.], "dae": [310.], "enthalpy": [300.], "stiff": [310., 300.], "heater": [294.], "schedule": [300.], "nonlinear": [300.]}[name]
    times = {"cooling": [0, .5, 1, 2, 4], "closed": [0, .1, .5, 1, 2], "dae": [0, .5, 1, 2, 4], "enthalpy": [0, .5, 1, 2, 5, 10], "stiff": [0, 1e-6, 1e-4, .01, .1, .5, 1], "heater": [0, .5, 1, 2, 3, 4, 5], "schedule": [0, .5, 1, 1.5, 2, 3, 4], "nonlinear": [0, .5, 1, 2, 3, 4, 5]}[name]
    on, power, last_switch, on_seconds = True, 0., 0., 0.
    events = ([dict(time=0, kind="heater", before=0, after=1)] if name == "heater" else
              [dict(time=0, kind="schedule", before=1, after=0)] if name == "schedule" else [])

    def temperature(z):
        if name == "closed": return list(z[:2])
        if name == "stiff": return [z[0], z[1], 290.]
        if name in ("cooling", "heater"): return [z[0], 300. if name == "cooling" else 290.]
        if name == "dae": return [z[0], (z[0]+300)/2, 300.]
        if name == "nonlinear":
            # Unique monotone flux balance, solved independently of FCST/IDA.
            a = 1e-8*(320**4-310**4)/60
            mid = brentq(lambda b: 2*(z[0]-b)-2*(b-300)+1e-8*(z[0]**4-b**4)-a*(b-250), 0, 600, xtol=1e-12)
            return [z[0], mid, 300.]
        return [z[0]]

    def quantities(z):
        t = temperature(z)
        if name in ("cooling", "heater"):
            links = [t[0]-t[1]]; boundary = -links[0]
            q = boundary + (20 if on and name == "heater" else 0)
            rate = [q/(2 if name == "cooling" else 1)]
            storage = (2 if name == "cooling" else 1)*(t[0]-initial[0])
        elif name == "closed":
            links = [4*(t[0]-t[1])]; boundary = 0; q = 0
            rate = [-links[0]/2, links[0]/3]; storage = 2*(t[0]-310)+3*(t[1]-290)
        elif name == "dae":
            links = [2*(t[0]-t[1]), 2*(t[1]-300)]; boundary = -links[1]; q = boundary
            rate = [-links[0]/2]; storage = 2*(t[0]-310)
        elif name in ("enthalpy", "schedule"):
            links = []; boundary = 0; q = 5 if name == "enthalpy" else power
            rate = [q/(.02*t[0])]; storage = .01*(t[0]**2-90000)
        elif name == "stiff":
            links = [1e4*(t[0]-t[1]), t[1]-290]; boundary = -links[1]; q = boundary
            rate = [-links[0]/1e-4, links[0]-links[1]]; storage = .0001*(t[0]-310)+(t[1]-300)
        else:
            links = [2*(t[0]-t[1]), 2*(t[1]-300)]; boundary = -links[1]+5
            k = 1e-8*(320**4-310**4)
            q = 27+k-.1*(t[0]-250)-k/60*(t[1]-250)-5+boundary
            rate = [(27+k-links[0]-1e-8*(t[0]**4-t[1]**4)-.1*(t[0]-250))/(.02*t[0])]
            storage = .01*(t[0]**2-90000)
        return t, links, boundary, q, rate, storage

    def rhs(_, z):
        _, _, boundary, external, rate, _ = quantities(z)
        return rate+[external, boundary]

    time, z, nfev = 0., initial+[0., 0.], 0

    def advance(target):
        nonlocal time, z, nfev, on, power, last_switch, on_seconds
        while time < target:
            stop = min(target, 1 if time < 1 else 2 if time < 2 else target) if name == "schedule" else target
            def crossing(_, state): return state[0]-(305 if on else 295)
            crossing.terminal = True
            crossing.direction = 1 if on else -1
            result = solve_ivp(rhs, (time, stop), z, method="Radau", rtol=tolerance, atol=tolerance, max_step=.025, events=crossing if name == "heater" else None)
            if not result.success: raise ValueError("radau_integration_failed")
            time, z = float(result.t[-1]), result.y[:, -1].tolist(); nfev += result.nfev
            if result.status == 1:
                if len(events) > 10000 or time-last_switch < 1e-9: raise ValueError("chatter")
                if on: on_seconds += time-last_switch
                events.append(dict(time=time, kind="heater", before=int(on), after=int(not on)))
                on = not on; last_switch = time
            elif name == "schedule" and time in (1, 2):
                next_power = 5 if time == 1 else 0
                events.append(dict(time=time, kind="schedule", before=power/5, after=next_power/5)); power = next_power

    samples = []
    for target in times:
        advance(target)
        t, links, boundary, _, _, storage = quantities(z)
        samples.append(dict(time=target, temperature=t, links=links, boundary_power=boundary, storage_change=storage, external_energy=z[-2], boundary_energy=z[-1], energy_defect=storage-z[-2], duty=(on_seconds+(target-last_switch if on else 0))/target if name == "heater" and target else 0))
    steady = None
    if name in ("cooling", "dae", "stiff", "nonlinear"):
        advance(100)
        t, _, boundary, _, _, _ = quantities(z)
        steady = dict(temperature=t, boundary_power=boundary)
    return dict(status="passed", execution_mode="reference_external", backend="scipy_radau", version=scipy.__version__, case=name, level=level, tolerance=tolerance, samples=samples, events=events, steady=steady, statistics=dict(rhs_evaluations=nfev))


if __name__ == "__main__":
    try:
        print(json.dumps(execute(*sys.argv[1:]), allow_nan=False, separators=(",", ":")))
    except Exception:
        print('{"status":"failed","reason":"radau_reference_failure"}', file=sys.stderr)
        sys.exit(1)
