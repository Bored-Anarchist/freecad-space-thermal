# SPDX-License-Identifier: MIT OR Apache-2.0
"""Generate the independent spatial v2 capability without changing v1 schemas."""
def schema(obj, arr, enum):
    # Local primitives deliberately do not inherit a model's entity union.
    uid = {"type": "string", "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"}
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    n = {"type": "number"}
    pos = {"type": "number", "exclusiveMinimum": 0}
    index = {"type": "integer", "minimum": 0, "maximum": 4095}
    vec = arr(n, minItems=3, maxItems=3)
    matrix = arr(vec, minItems=3, maxItems=3)
    ids = arr(uid, minItems=1, maxItems=4096, uniqueItems=True)
    field = lambda quantity, unit, components: obj({
        "quantity": {"const": quantity}, "unit": {"const": unit},
        "components": {"const": components}, "location": {"const": "mesh_vertex"},
        "entity_ids": ids, "frame_id": uid, "projection": {"const": "raw"},
        "provenance": digest,
        "values": arr(arr(arr(n, minItems=len(components), maxItems=len(components)), minItems=1, maxItems=4096), minItems=1, maxItems=64)})
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:fcst:contract:spatial:2.0.0", **obj({
        "contract_version": {"const": "2.0.0"}, "minimum_reader": {"const": "2.0.0"},
        "capability": {"const": "spatial-linear-vertex-v2"},
        "id": uid, "project_id": uid, "model_hash": digest, "mesh_revision": digest,
        "execution_mode": enum("fcst_native", "reference_external"),
        "vertex_ids": ids, "vertices": arr(vec, minItems=3, maxItems=4096),
        "cells": arr(obj({"id": uid, "topology": enum("tet4", "tri3"),
            "order": {"const": 1}, "vertices": arr(index, minItems=3, maxItems=4, uniqueItems=True)}), minItems=1, maxItems=4096),
        "frames": arr(obj({"id": uid, "basis": matrix}), minItems=1, maxItems=16),
        "material": obj({"conductivity": matrix, "conductivity_unit": {"const": "W/(m*K)"},
            "frame_id": uid, "density": pos, "density_unit": {"const": "kg/m3"},
            "specific_heat": pos, "specific_heat_unit": {"const": "J/(kg*K)"}}),
        "times": arr({"type": "number", "minimum": 0}, minItems=1, maxItems=64),
        "fields": arr({"oneOf": [field("temperature", "K", ["scalar"]), field("heat_flux", "W/m2", ["x", "y", "z"])]}, minItems=1, maxItems=2),
        "mappings": arr(obj({"from_id": uid, "from_kind": enum("cad_face", "facet", "element", "mesh_vertex"),
            "to_id": uid, "to_kind": enum("facet", "element", "thermal_node"),
            "weight": pos, "area_m2": pos, "provenance": digest}), maxItems=4096),
        "cad_face_ids": arr(uid, maxItems=4096, uniqueItems=True),
        "thermal_node_ids": arr(uid, maxItems=4096, uniqueItems=True),
        "source_license_hash": digest, "boundary": obj({"kind": enum("none", "surface_flux", "total_power", "prescribed_temperature"),
            "value": n, "unit": enum("1", "W/m2", "W", "K"), "cell_ids": arr(uid, maxItems=4096, uniqueItems=True)})})}
