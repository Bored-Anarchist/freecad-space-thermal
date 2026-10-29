# SPDX-License-Identifier: MIT OR Apache-2.0
"""Generate the v1 contract bundle and native schema table; --check rejects drift."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def obj(properties, optional=()):
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": [key for key in properties if key not in optional]}


def arr(items, **limits):
    return {"type": "array", "items": items, **limits}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def enum(*values):
    return {"enum": list(values)}


def build():
    number = {"type": "number"}
    positive = {"type": "number", "exclusiveMinimum": 0}
    nonnegative = {"type": "number", "minimum": 0}
    integer = {"type": "integer", "minimum": 0, "maximum": 9007199254740991}
    text = {"type": "string", "minLength": 1, "maxLength": 256}
    uuid = {"type": "string", "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"}
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    version = {"const": "1.0.0"}
    vector = arr(number, minItems=3, maxItems=3)
    units = {
        "1": ["scalar", 1, 0], "K": ["temperature", 1, 0],
        "degC": ["temperature", 1, 273.15], "degF": ["temperature", 5 / 9, 255.3722222222222],
        "delta_K": ["temperature_difference", 1, 0], "delta_degC": ["temperature_difference", 1, 0],
        "delta_degF": ["temperature_difference", 5 / 9, 0],
        "m": ["length", 1, 0], "mm": ["length", .001, 0], "in": ["length", .0254, 0],
        "m2": ["area", 1, 0], "s": ["time", 1, 0], "min": ["time", 60, 0],
        "W": ["power", 1, 0], "mW": ["power", .001, 0],
        "J/K": ["capacity", 1, 0], "W/K": ["conductance", 1, 0],
        "W/(m*K)": ["conductivity", 1, 0], "kg/m3": ["density", 1, 0],
        "J/(kg*K)": ["specific_heat", 1, 0], "W/m2": ["flux", 1, 0],
        "rad": ["angle", 1, 0], "kg": ["mass", 1, 0],
    }
    si = {value[0]: key for key, value in reversed(list(units.items())) if value[1:] == [1, 0]}
    dims = {"scalar": [0, 0, 0, 0], "temperature": [0, 0, 0, 1],
            "temperature_difference": [0, 0, 0, 1], "length": [0, 1, 0, 0],
            "area": [0, 2, 0, 0], "time": [0, 0, 1, 0], "power": [1, 2, -3, 0],
            "capacity": [1, 2, -2, -1], "conductance": [1, 2, -3, -1],
            "conductivity": [1, 1, -3, -1], "density": [1, -3, 0, 0],
            "specific_heat": [0, 2, -2, -1], "flux": [1, 0, -3, 0],
            "angle": [0, 0, 0, 0], "mass": [1, 0, 0, 0]}
    defs = {"uuid": uuid, "quantity": obj({"value": number, "unit": enum(*units)}),
            "artifact": obj({"path": {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9._/-]*$"},
                             "sha256": digest, "byte_length": integer}),
            "diagnostic": obj({"code": enum("invalid_json", "schema", "version", "duplicate_id", "reference",
                                  "dimension", "range", "frame", "attachment", "expression", "cycle", "artifact",
                                  "unsupported_operation", "not_implemented", "cancelled", "stale_revision",
                                  "idempotency_conflict", "unauthorized", "capability", "limit", "unavailable"),
                               "entity_id": uuid, "source_map_id": uuid, "pointer": {"type": "string", "maxLength": 256}},
                              ("entity_id", "source_map_id"))}
    q = ref("quantity")
    entities = {}

    def entity(kind, fields, optional=()):
        entities[kind] = obj({"id": uuid, "kind": {"const": kind}, "label": text, **fields}, ("label", *optional))

    entity("submodel", {"parent_id": uuid}, ("parent_id",))
    entity("frame", {"parent_id": uuid, "origin": arr(q, minItems=3, maxItems=3),
                     "rotation": arr(vector, minItems=3, maxItems=3)}, ("parent_id",))
    entity("geometry", {"frame_id": uuid, "artifact": ref("artifact"), "revision": integer})
    entity("face", {"geometry_id": uuid, "persistent_ref": text, "signature": digest, "area": q})
    entity("mesh", {"frame_id": uuid, "artifact": ref("artifact"), "role": enum("radiation", "conduction")})
    entity("facet", {"mesh_id": uuid, "area": q, "side": enum("front", "back"), "optics_id": uuid})
    entity("element", {"mesh_id": uuid, "material_id": uuid, "frame_id": uuid, "volume": positive,
                       "topology": enum("triangle", "quadrilateral", "tetrahedron", "hexahedron")})
    entity("node", {"submodel_id": uuid, "classification": enum("capacitive", "algebraic", "prescribed"),
                    "temperature": q, "capacity": q})
    entity("material", {"density": q, "specific_heat": q, "conductivity": q,
                        "conductivity_tensor": arr(vector, minItems=3, maxItems=3), "frame_id": uuid,
                        "valid_temperature": arr(q, minItems=2, maxItems=2)}, ("conductivity_tensor", "frame_id"))
    entity("optics", {"solar_absorptivity": nonnegative, "ir_emissivity": nonnegative,
                      "specular_fraction": nonnegative, "transmissivity": nonnegative})
    entity("conductor", {"from_node_id": uuid, "to_node_id": uuid, "conductance": q})
    entity("load", {"node_id": uuid, "power": q, "expression_id": uuid}, ("expression_id",))
    entity("radiation", {"facet_ids": arr(uuid, minItems=1, uniqueItems=True), "environment_id": uuid,
                         "method": enum("diffuse", "raytrace"), "excluded_facet_ids": arr(uuid, uniqueItems=True)})
    entity("environment", {"frame_id": uuid, "background_temperature": q, "solar_flux": q,
                           "epoch": {"type": "string", "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$"},
                           "time_scale": enum("TAI", "TT"), "time_origin": q})
    entity("case", {"mode": enum("steady", "transient"), "start": q, "end": q,
                    "environment_id": uuid, "load_ids": arr(uuid, uniqueItems=True), "control_ids": arr(uuid, uniqueItems=True),
                    "overlays": arr(obj({"entity_id": uuid, "field": enum("temperature", "power", "conductance"), "value": q}))})
    entity("control", {"sensor_node_id": uuid, "load_id": uuid, "on_below": q, "off_above": q})
    ast = {"oneOf": [obj({"op": {"const": "literal"}, "quantity": q}),
                     obj({"op": {"const": "symbol"}, "expression_id": uuid}),
                     obj({"op": enum("add", "subtract", "multiply", "divide", "min", "max", "negate", "abs", "sqrt", "exp", "log", "sin", "cos"),
                          "args": arr(ref("ast"), minItems=1, maxItems=2)}),
                     obj({"op": {"const": "table"}, "input": ref("ast"),
                          "x": arr(q, minItems=2), "y": arr(q, minItems=2),
                          "interpolation": enum("linear", "previous"), "extrapolation": enum("error", "clamp"),
                          "discontinuities": arr(integer, uniqueItems=True)})]}
    defs["ast"] = ast
    entity("expression", {"dimension": enum(*dims), "ast": ref("ast")})
    for kind, schema in entities.items():
        defs[kind] = schema
    model = obj({"contract_version": version, "minimum_reader": version,
                 "project_id": uuid, "revision": integer,
                 "entities": arr({"oneOf": [ref(kind) for kind in entities]}),
                 "assumptions": arr(text), "limitations": arr(text),
                 "source_maps": arr(obj({"id": uuid, "version": version, "source_revision": digest,
                     "source_tool": text, "source_version": text,
                     "entries": arr(obj({"namespace": text, "handle": text, "entity_id": uuid,
                                         "submodel_handle": text, "node_number": integer}, ("submodel_handle", "node_number")))})),
                 "mappings": arr(obj({"id": uuid, "from_id": uuid, "to_id": uuid, "weight": positive,
                                      "area": q, "provenance": digest})),
                 "attachments": arr(obj({"id": uuid, "entity_id": uuid, "face_id": uuid, "source_revision": integer,
                     "persistent_ref": text, "signature": digest, "state": enum("resolved", "reassignment_required")})),
                 "audit": obj({"timestamp": text}), "gui": obj({"selection": arr(uuid)})}, ("audit", "gui"))
    args = {
        "model.validate": obj({"snapshot": model}),
        "model.hash": obj({"snapshot": model}),
        "capabilities.get": obj({"reader_version": version}),
        "thermal.conductor.create": obj({"id": uuid, "from_node_id": uuid, "to_node_id": uuid, "conductance": q}),
        "job.submit": obj({"case_id": uuid, "snapshot": ref("artifact"), "semantic_hash": digest}),
        "job.cancel": obj({"job_id": uuid}),
        "result.query": obj({"result_id": uuid, "quantity": enum("temperature", "power", "residual"),
                             "entity_ids": arr(uuid, minItems=1, maxItems=1024, uniqueItems=True), "offset": integer,
                             "limit": {"type": "integer", "minimum": 1, "maximum": 4096}}),
    }
    envelope = {"oneOf": [obj({"contract_version": version, "project_id": uuid, "expected_revision": integer,
                "idempotency_key": uuid, "operation": {"const": name}, "arguments": schema,
                "dry_run": {"type": "boolean"}, "authorization_context_id": uuid},
                ("dry_run", "authorization_context_id")) for name, schema in args.items()]}
    caps = obj({"contract_version": version, "minimum_reader": version, "operations": arr(enum(*args), uniqueItems=True),
                "solver_available": {"const": False}, "execution_mode": {"const": "fcst_native"}})
    defs["capabilities"] = caps
    replies = {"model.validate": obj({"valid": {"const": True}}), "model.hash": obj({"semantic_hash": digest}),
               "capabilities.get": caps, "thermal.conductor.create": obj({"entity_id": uuid, "revision": integer}),
               "job.submit": obj({"job_id": uuid}), "job.cancel": obj({"job_id": uuid, "accepted": {"type": "boolean"}}),
               "result.query": obj({"artifact": ref("artifact"), "offset": integer, "count": integer})}
    response = {"oneOf": [obj({"contract_version": version, "operation": {"const": name}, "result": schema})
                          for name, schema in replies.items()] + [obj({"contract_version": version, "error": ref("diagnostic")})]}
    result = obj({"contract_version": version, "minimum_reader": version, "id": uuid, "project_id": uuid,
                  "case_id": uuid, "revision": integer, "semantic_hash": digest, "build_hash": digest,
                  "execution_mode": enum("fcst_native", "prototype_external", "reference_external", "fallback_external"),
                  "adapter": text, "outcome": enum("succeeded", "failed", "cancelled"), "data": ref("artifact"),
                  "node_ids": arr(uuid, minItems=1, uniqueItems=True), "time_count": {"type": "integer", "minimum": 1, "maximum": 9007199254740991},
                  "quantities": arr(enum("temperature", "power", "residual"), minItems=1, uniqueItems=True),
                  "diagnostics": arr(ref("diagnostic"))})
    manifest = obj({"contract_version": version, "minimum_reader": version, "project_id": uuid, "revision": integer,
                    "model_artifact_id": uuid, "artifacts": arr(obj({"id": uuid,
                        "role": enum("model", "geometry", "mesh", "source_original", "source_dependency", "result", "evidence", "audit", "freecad_document"),
                        "artifact": ref("artifact"), "dependencies": arr(uuid, uniqueItems=True)}), minItems=1)})
    messages = {
        "handshake": obj({"capabilities": caps}),
        "submit": obj({"case_id": uuid, "snapshot": ref("artifact"), "semantic_hash": digest}),
        "progress": obj({"fraction": {"type": "number", "minimum": 0, "maximum": 1}, "stage": enum("validate", "assemble", "solve", "write")}),
        "diagnostic": ref("diagnostic"), "cancel": obj({}),
        "terminal": obj({"outcome": enum("succeeded", "failed", "cancelled"), "result": ref("artifact")}, ("result",)),
        "checkpoint": obj({"snapshot_hash": digest, "build_hash": digest, "case_id": uuid,
                           "time": q, "state": ref("artifact"), "sequence": integer}),
    }
    worker = {"oneOf": [obj({"contract_version": version, "type": {"const": name}, "job_id": uuid,
                             "sequence": integer, "payload": schema}) for name, schema in messages.items()]}
    hdf = {"contract_version": "1.0.0", "byte_order": "little", "index_base": 0, "compression": "none", "chunking": "time-major; max 256 time samples and 1024 entities per chunk",
           "root_attributes": {"contract_version": "UTF-8 scalar 1.0.0", "semantic_hash": "ASCII lowercase SHA-256", "artifact_role": "result|radiation_mesh|conduction_mesh"},
           "datasets": {"/index/node_uuid": {"dtype": "uint8", "shape": ["N", 16], "unit": "1"},
                        "/time": {"dtype": "float64", "shape": ["T"], "unit": "s"},
                        "/temperature": {"dtype": "float64", "shape": ["T", "N"], "unit": "K"},
                        "/power": {"dtype": "float64", "shape": ["T", "N"], "unit": "W"},
                        "/residual": {"dtype": "float64", "shape": ["T", "N"], "unit": "W"}},
           "mesh_datasets": {"/index/entity_uuid": {"dtype": "uint8", "shape": ["E", 16], "unit": "1"},
                             "/vertices": {"dtype": "float64", "shape": ["V", 3], "unit": "m"},
                             "/connectivity/offsets": {"dtype": "uint64", "shape": ["E+1"], "unit": "1"},
                             "/connectivity/vertex_index": {"dtype": "uint64", "shape": ["L"], "unit": "1"},
                             "/normals": {"dtype": "float64", "shape": ["E", 3], "unit": "1"}},
           "role_datasets": {"result": ["/index/node_uuid", "/time"],
                             "radiation_mesh": ["/index/entity_uuid", "/vertices", "/connectivity/offsets", "/connectivity/vertex_index", "/normals"],
                             "conduction_mesh": ["/index/entity_uuid", "/vertices", "/connectivity/offsets", "/connectivity/vertex_index"]}}
    schemas = {}
    for name, body in {"model": model, "manifest": manifest, "operation": envelope, "response": response, "result": result, "worker": worker}.items():
        schemas[name] = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:fcst:contract:" + name + ":1.0.0",
                         **body, "$defs": defs}
    from spatial_schema import schema as spatial_schema
    schemas["spatial"] = spatial_schema(obj, arr, enum)
    from copy import deepcopy
    schemas["manifest2"] = deepcopy(schemas["manifest"])
    m2 = schemas["manifest2"]
    m2["$id"] = "urn:fcst:contract:manifest:2.0.0"
    for key in ("contract_version", "minimum_reader"):
        m2["properties"][key] = {"const": "2.0.0"}
    m2["properties"]["artifacts"]["items"]["properties"]["role"]["enum"].append("spatial")
    return {"version": "1.0.0", "units": units, "si": si, "dimensions": dims,
            "schemas": schemas, "hdf5": hdf, "operations": list(args), "entity_kinds": list(entities)}


def outputs():
    bundle = build()
    encoded = json.dumps(bundle, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    yield "python/fcst_contracts/bundle.json", encoded + "\n"
    chunks = [encoded[i:i+12000] for i in range(0, len(encoded), 12000)]
    yield "engine/include/fcst/contract_bundle.hpp", ('// SPDX-License-Identifier: MIT OR Apache-2.0\n'
          '// Generated by tools/generate_contracts.py; do not edit.\n#pragma once\n#include <string_view>\n'
          'namespace fcst { inline constexpr std::string_view contract_bundle_parts[] = {\n' +
          ',\n'.join('R"FCST(' + chunk + ')FCST"' for chunk in chunks) + '\n}; }\n')
    for name, schema in bundle["schemas"].items():
        yield "spec/schemas/" + ("manifest-v2" if name == "manifest2" else name + ("-v2" if name == "spatial" else "-v1")) + ".schema.json", json.dumps(schema, indent=2) + "\n"
    yield "spec/contracts/hdf5-v1.json", json.dumps(bundle["hdf5"], indent=2) + "\n"
    groups = {"EntityKind": bundle["entity_kinds"], "Operation": bundle["operations"],
              "WorkerMessage": [s["properties"]["type"]["const"] for s in bundle["schemas"]["worker"]["oneOf"]]}
    py = '# SPDX-License-Identifier: MIT OR Apache-2.0\n# Generated by tools/generate_contracts.py.\nfrom enum import Enum\n'
    cpp = '// SPDX-License-Identifier: MIT OR Apache-2.0\n// Generated by tools/generate_contracts.py.\n#pragma once\nnamespace fcst {\n'
    for group, names in groups.items():
        py += '\nclass ' + group + '(str, Enum):\n' + ''.join('    ' + n.replace('.', '_') + ' = "' + n + '"\n' for n in names)
        cpp += 'enum class ' + group + ' { ' + ', '.join(n.replace('.', '_') + '_value' for n in names) + ' };\n'
    yield "python/fcst_contracts/types.py", py
    yield "engine/include/fcst/contract_types.hpp", cpp + '}\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--validate", action="store_true", help="Run the independent standard schema reader (locked tooling environment)")
    args = parser.parse_args()
    for name, content in outputs():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit("contract_generation_drift: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if args.validate:
        from jsonschema import Draft202012Validator
        bundle = build()
        for schema in bundle["schemas"].values():
            Draft202012Validator.check_schema(schema)
        fixtures = ROOT / "tests/fixtures/contracts"
        cases = json.loads((fixtures / "cases.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            if case["status"] == "passed":
                Draft202012Validator(bundle["schemas"][case["kind"]]).validate(
                    json.loads((fixtures / case["path"]).read_text(encoding="utf-8")))
    print("contract_generation: passed")


if __name__ == "__main__":
    main()
