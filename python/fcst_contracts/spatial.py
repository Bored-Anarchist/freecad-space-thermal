# SPDX-License-Identifier: MIT OR Apache-2.0
"""Spatial v2 semantics. SI only, explicit identity and raw vertex fields."""
import math
from . import fail


def mesh_hash(value):
    from hashlib import sha256
    from . import canonical
    return sha256(b"FCST-mesh-v2\0"+canonical({k:value[k] for k in ("vertex_ids","vertices","cells")})).hexdigest()


def determinant(m):
    return (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
            - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
            + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))


def transform(basis, vector):
    return [sum(row[i]*vector[i] for i in range(3)) for row in basis]


def check(value):
    vertices, ids = value["vertices"], value["vertex_ids"]
    if len(vertices) != len(ids):
        fail("spatial_shape")
    frames = {f["id"]: f["basis"] for f in value["frames"]}
    groups = [ids, [c["id"] for c in value["cells"]], list(frames), value["cad_face_ids"], value["thermal_node_ids"]]
    flat = [i for g in groups for i in g]
    if len(frames) != len(value["frames"]) or len(set(flat)) != len(flat):
        fail("spatial_identity")
    for basis in frames.values():
        if (abs(determinant(basis)-1) > 1e-12 or any(abs(sum(basis[k][i]*basis[k][j] for k in range(3))-(i == j)) > 1e-12 for i in range(3) for j in range(3))):
            fail("spatial_frame")
    for cell in value["cells"]:
        indices = cell["vertices"]
        if len(indices) != (4 if cell["topology"] == "tet4" else 3) or any(i >= len(ids) for i in indices):
            fail("spatial_connectivity")
        points = [vertices[int(i)] for i in indices]
        edges = [[p[k]-points[0][k] for k in range(3)] for p in points[1:]]
        if cell["topology"] == "tet4":
            valid = determinant(edges) > 1e-18
        else:
            valid = sum((edges[0][(k+1)%3]*edges[1][(k+2)%3]-edges[0][(k+2)%3]*edges[1][(k+1)%3])**2 for k in range(3)) > 1e-24
        if not valid:
            fail("spatial_orientation")
    if value["mesh_revision"] != mesh_hash(value):
        fail("spatial_mesh_revision")
    material = value["material"]
    k = material["conductivity"]
    if material["frame_id"] not in frames:
        fail("spatial_reference")
    if (any(abs(k[i][j]-k[j][i]) > 1e-12 for i in range(3) for j in range(3)) or k[0][0] <= 0
            or k[0][0]*k[1][1]-k[0][1]**2 <= 0 or determinant(k) <= 0):
        fail("spatial_material")
    if any(a >= b for a, b in zip(value["times"], value["times"][1:])):
        fail("spatial_time")
    quantities = set()
    for field in value["fields"]:
        if field["quantity"] in quantities:
            fail("spatial_identity")
        quantities.add(field["quantity"])
        if field["entity_ids"] != ids or field["frame_id"] not in frames:
            fail("spatial_reference")
        if len(field["values"]) != len(value["times"]) or any(len(row) != len(ids) for row in field["values"]):
            fail("spatial_shape")
        if field["quantity"] == "temperature" and any(x[0] < 0 for row in field["values"] for x in row):
            fail("spatial_range")
    domains = {"cad_face": set(value["cad_face_ids"]), "thermal_node": set(value["thermal_node_ids"]), "mesh_vertex": set(ids),
               "element": {c["id"] for c in value["cells"] if c["topology"] == "tet4"},
               "facet": {c["id"] for c in value["cells"] if c["topology"] == "tri3"}}
    weights, pairs = {}, set()
    for m in sorted(value["mappings"], key=lambda m: (m["from_id"], m["to_id"])):
        a, b = m["from_kind"], m["to_kind"]
        if (a, b) not in {("cad_face", "facet"), ("cad_face", "element"), ("facet", "thermal_node"), ("element", "thermal_node"), ("mesh_vertex", "thermal_node")} or m["from_id"] not in domains[a] or m["to_id"] not in domains[b]:
            fail("spatial_reference")
        pair = (m["from_id"], m["to_id"])
        if pair in pairs:
            fail("spatial_identity")
        pairs.add(pair)
        key = (m["from_id"], b)
        weights[key] = weights.get(key, 0) + m["weight"]
    if any(abs(w-1) > 1e-12 for w in weights.values()):
        fail("spatial_weight")
    boundary = value["boundary"]
    unit = {"none": "1", "surface_flux": "W/m2", "total_power": "W", "prescribed_temperature": "K"}[boundary["kind"]]
    if boundary["unit"] != unit or boundary["kind"] == "prescribed_temperature" and boundary["value"] < 0:
        fail("spatial_boundary")
    if (boundary["kind"] == "none" and (boundary["cell_ids"] or boundary["value"] != 0)
            or boundary["kind"] != "none" and not boundary["cell_ids"]
            or any(i not in domains["facet"] for i in boundary["cell_ids"])):
        fail("spatial_reference")


def field_global(value, quantity, sample=0):
    from . import read
    value = read("spatial", value)
    f = next(f for f in value["fields"] if f["quantity"] == quantity)
    basis = next(b["basis"] for b in value["frames"] if b["id"] == f["frame_id"])
    return [transform(basis, v) if len(v) == 3 else v for v in f["values"][sample]]


def downgrade(value, version):
    from . import read
    if version != "2.0.0":
        fail("lossy_downgrade")
    return read("spatial", value)


def integrated_boundary_power(value, cell_id, sample=0):
    """Exact linear triangle integral of vertex flux; positive outward, in W."""
    from . import read
    value=read("spatial",value)
    cell=next((c for c in value["cells"] if c["id"]==cell_id and c["topology"]=="tri3"),None)
    if cell is None: fail("spatial_reference")
    points=[value["vertices"][int(i)] for i in cell["vertices"]]
    a,b=([p[k]-points[0][k] for k in range(3)] for p in points[1:])
    area_normal=[(a[(k+1)%3]*b[(k+2)%3]-a[(k+2)%3]*b[(k+1)%3])/2 for k in range(3)]
    flux=field_global(value,"heat_flux",sample)
    average=[sum(flux[int(i)][k] for i in cell["vertices"])/3 for k in range(3)]
    return sum(q*n for q,n in zip(average,area_normal))
