# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent Pycanha core trial of constant-capacity benchmark networks.

Uses genuine zero capacitance for the middle DAE node. No FCST imports.
Raw backend diagnostics go to local stderr, never the public report.
"""
import contextlib
import json
import sys
from importlib.metadata import version
from pycanha_core import tmm, solvers


def execute(name, level):
    step = {"coarse": .001, "fine": .0005}[level]
    # Native input guess 350 is reconciled to 305 analytically here; no fake C.
    definitions = {"cooling": ([(310, 2, False), (300, 0, True)], [(1, 2, 1)], 4),
                   "closed": ([(310, 2, False), (290, 3, False)], [(1, 2, 4)], 2),
                   "dae": ([(310, 2, False), (305, 0, False), (300, 0, True)], [(1, 2, 2), (2, 3, 2)], 4)}
    nodes, links, end = definitions[name]
    model = tmm.ThermalMathematicalModel("owned_synthetic_reference")
    for number, (temperature, capacity, boundary) in enumerate(nodes, 1):
        node = tmm.Node(number); node.T = temperature; node.C = capacity
        if boundary: node.type = tmm.NodeType.BOUNDARY
        model.add_node(node)
    for a, b, conductance in links: model.add_conductive_coupling(a, b, conductance)
    solver = solvers.TSCNRLDS(model); solver.engine = solvers.SolverEngine.EIGEN
    solver.abstol_temp = 1e-10; solver.abstol_enrgy = 1e-10
    solver.set_simulation_time(0, end, step, .1 if name == "closed" else .5)
    solver.initialize()
    try:
        solver.solve()
        times = solver.output_model.T.times.tolist()
        values = solver.output_model.T.values
        indices = [model.nodes.get_idx_from_node_num(n) for n in range(1, len(nodes)+1)]
        samples = [dict(time=time, temperature=[float(row[i]) for i in indices]) for time, row in zip(times, values)]
    finally:
        solver.deinitialize()
    return dict(status="passed", execution_mode="reference_external", backend="pycanha_core", version=version("pycanha-core"), case=name, level=level, step_s=step, samples=samples)


if __name__ == "__main__":
    try:
        with contextlib.redirect_stdout(sys.stderr): result = execute(*sys.argv[1:])
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
    except Exception:
        print('{"status":"failed","reason":"pycanha_reference_failure"}', file=sys.stderr)
        sys.exit(1)
