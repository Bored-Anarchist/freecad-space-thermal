# SPDX-License-Identifier: MIT OR Apache-2.0
"""FCST v1 contracts. Pure Python reader; never imports or calls the C++ reader."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import struct

BUNDLE = json.loads(Path(__file__).with_name("bundle.json").read_text(encoding="utf-8"))
VERSION = BUNDLE["version"]
MAX_BYTES = 1048576


@dataclass(frozen=True)
class Diagnostic:
    code: str
    pointer: str = ""
    entity_id: str | None = None
    source_map_id: str | None = None


class ContractError(ValueError):
    def __init__(self, code, pointer="", entity_id=None, source_map_id=None):
        self.diagnostic = Diagnostic(code, pointer, entity_id, source_map_id)
        super().__init__(code)


def fail(code, pointer=""):
    raise ContractError(code, pointer)


def loads(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_BYTES:
        fail("invalid_json")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail("invalid_json")
            result[key] = value
        return result
    try:
        def floating(token):
            result = float(token)
            if not math.isfinite(result) or result == 0 and any(c in "123456789" for c in token.lower().split("e")[0]):
                fail("invalid_json")
            return result
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_float=floating, parse_int=floating,
                           parse_constant=lambda _: fail("invalid_json"))
        def bounded(v, depth=0):
            if depth > 64:
                fail("invalid_json")
            if isinstance(v, float) and not math.isfinite(v):
                fail("invalid_json")
            if isinstance(v, str):
                v.encode("utf-8")
            if isinstance(v, dict):
                for key in v:
                    key.encode("utf-8")
            for x in (v.values() if isinstance(v, dict) else v if isinstance(v, list) else []):
                bounded(x, depth + 1)
        bounded(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ContractError):
            raise
        fail("invalid_json")


def validate(schema, value, root=None, depth=0, schema_hops=0):
    """The frozen schema vocabulary; unknown keywords are never accepted in bundles."""
    if depth > 64 or schema_hops > 64:
        fail("schema")
    root = root or schema
    if "$ref" in schema:
        return validate(root["$defs"][schema["$ref"].split("/")[-1]], value, root, depth, schema_hops + 1)
    if "oneOf" in schema:
        count = 0
        for choice in schema["oneOf"]:
            try:
                validate(choice, value, root, depth, schema_hops + 1)
                count += 1
            except ContractError:
                pass
        if count != 1:
            fail("schema")
        return
    def same(a, b):
        return type(a) is type(b) and a == b or (type(a) in (int, float) and type(b) in (int, float) and a == b)
    if "const" in schema and not same(value, schema["const"]):
        fail("schema")
    if "enum" in schema and not any(same(value, choice) for choice in schema["enum"]):
        fail("schema")
    kind = schema.get("type")
    matches = {"object": isinstance(value, dict), "array": isinstance(value, list),
               "string": isinstance(value, str), "number": type(value) in (int, float),
               "integer": type(value) in (int, float) and math.isfinite(value) and int(value) == value,
               "boolean": isinstance(value, bool)}
    if kind and not matches[kind]:
        fail("schema")
    if kind == "object":
        if any(key not in value for key in schema["required"]) or set(value) - set(schema["properties"]):
            fail("schema")
        for key, item in value.items():
            validate(schema["properties"][key], item, root, depth + 1)
    elif kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", MAX_BYTES):
            fail("schema")
        if schema.get("uniqueItems") and len({canonical(x) for x in value}) != len(value):
            fail("schema")
        for item in value:
            validate(schema["items"], item, root, depth + 1)
    elif kind == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", MAX_BYTES):
            fail("schema")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            fail("schema")
    elif kind in ("number", "integer"):
        if not math.isfinite(value):
            fail("schema")
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            fail("schema")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            fail("schema")


def canonical(value):
    """Prefix coded semantic bytes. Numbers are normalized binary64, big endian hex."""
    if value is None:
        return b"n"
    if isinstance(value, bool):
        return b"t" if value else b"f"
    if type(value) in (int, float):
        if not math.isfinite(value):
            fail("schema")
        return b"d" + struct.pack(">d", float(value) if value else 0.0).hex().encode("ascii")
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return b"s" + str(len(raw)).encode() + b":" + raw
    if isinstance(value, list):
        return b"a" + str(len(value)).encode() + b":" + b"".join(canonical(x) for x in value)
    return b"o" + str(len(value)).encode() + b":" + b"".join(canonical(k) + canonical(value[k]) for k in sorted(value))


def normalize(value):
    if isinstance(value, list):
        return [normalize(x) for x in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"value", "unit"}:
        dimension, scale, offset = BUNDLE["units"][value["unit"]]
        amount = float(value["value"]) * scale + offset
        if not math.isfinite(amount):
            fail("range")
        if dimension == "temperature" and amount < 0:
            fail("range")
        return {"value": amount if amount else 0.0, "unit": BUNDLE["si"][dimension]}
    try:
        return {key: normalize(item) for key, item in value.items()}
    except ContractError as error:
        if "id" in value and "kind" in value:
            error.diagnostic = Diagnostic(error.diagnostic.code, "/entities", value["id"])
        raise


def quantity(value, dimension, minimum=None, strict=False):
    if BUNDLE["units"][value["unit"]][0] != dimension:
        fail("dimension")
    number = value["value"]
    if minimum is not None and (number < minimum or strict and number == minimum):
        fail("range")
    return number


def dependency_order(graph, limit_code, entity_context=False):
    """Children first, with longest-path limits independent of input/cache order."""
    import heapq
    parents = {key: [] for key in graph}
    remaining = {key: len(children) for key, children in graph.items()}
    heights = dict.fromkeys(graph, 1)
    def reject(code, key):
        raise ContractError(code, "/entities" if entity_context else "", key if entity_context else None)
    for key in sorted(graph):
        for child in sorted(graph[key]):
            if child not in graph:
                reject("reference", key)
            parents[child].append(key)
    ready = [key for key in graph if not remaining[key]]
    heapq.heapify(ready)
    order = []
    while ready:
        child = heapq.heappop(ready)
        order.append(child)
        for parent in parents[child]:
            heights[parent] = max(heights[parent], heights[child] + 1)
            remaining[parent] -= 1
            if not remaining[parent]:
                heapq.heappush(ready, parent)
    if len(order) != len(graph):
        reject("cycle", min(key for key in graph if remaining[key]))
    for key in sorted(graph):
        if heights[key] > 64:
            reject(limit_code, key)
    return order


def expression_types(entities):
    expressions = {key: value for key, value in entities.items() if value["kind"] == "expression"}
    def symbols(ast):
        if ast["op"] == "symbol":
            return {ast["expression_id"]}
        children = [ast["input"]] if ast["op"] == "table" else ast.get("args", [])
        return set().union(*(symbols(child) for child in children))
    order = dependency_order({key: symbols(e["ast"]) for key, e in expressions.items()}, "expression", True)
    visited = {}
    dims = BUNDLE["dimensions"]
    def infer_id(key):
        return visited[key]
    def infer(ast):
        op = ast["op"]
        if op == "literal":
            return BUNDLE["units"][ast["quantity"]["unit"]][0]
        if op == "symbol":
            return infer_id(ast["expression_id"])
        if op == "table":
            x, y = ast["x"], ast["y"]
            xd, yd = BUNDLE["units"][x[0]["unit"]][0], BUNDLE["units"][y[0]["unit"]][0]
            if len(x) != len(y) or any(x[i]["value"] >= x[i+1]["value"] for i in range(len(x)-1)):
                fail("expression")
            if any(quantity(v, xd) is None for v in x) or any(quantity(v, yd) is None for v in y) or infer(ast["input"]) != xd:
                fail("dimension")
            if any(i < 1 or i >= len(x) for i in ast["discontinuities"]) or ast["discontinuities"] and ast["interpolation"] != "previous":
                fail("expression")
            return yd
        args = [infer(a) for a in ast["args"]]
        if len(args) != (1 if op in ("negate", "abs", "sqrt", "exp", "log", "sin", "cos") else 2):
            fail("expression")
        if op in ("add", "subtract", "min", "max"):
            a, b = args
            if op == "subtract" and a == b == "temperature":
                return "temperature_difference"
            if op == "add" and {a, b} == {"temperature", "temperature_difference"}:
                return "temperature"
            if op == "subtract" and a == "temperature" and b == "temperature_difference":
                return "temperature"
            if a != b or a == "temperature" and op in ("add", "subtract"):
                fail("dimension")
            return a
        if "temperature" in args:
            fail("dimension")
        if op in ("negate", "abs"):
            return args[0]
        if op in ("exp", "log", "sin", "cos"):
            if args[0] not in (("scalar", "angle") if op in ("sin", "cos") else ("scalar",)):
                fail("dimension")
            return "scalar"
        target = [a / 2 for a in dims[args[0]]] if op == "sqrt" else [a + (b if op == "multiply" else -b) for a, b in zip(dims[args[0]], dims[args[1]])]
        for name, dimensions in dims.items():
            if name not in ("temperature", "angle") and dimensions == target:
                return name
        fail("dimension")
    for key in order:
        try:
            inferred = infer(expressions[key]["ast"])
            if inferred != expressions[key]["dimension"]:
                fail("dimension")
            visited[key] = inferred
        except ContractError as error:
            error.diagnostic = Diagnostic(error.diagnostic.code, "/entities", key)
            raise


def check_model(model):
    entities = {}
    ids = set()
    for record in model["entities"] + model["source_maps"] + model["mappings"] + model["attachments"]:
        if record["id"] in ids or record["id"] == model["project_id"]:
            fail("duplicate_id")
        ids.add(record["id"])
    entities = {item["id"]: item for item in model["entities"]}
    def target(key, kinds):
        if key not in entities or entities[key]["kind"] not in kinds.split():
            fail("reference")
        return entities[key]
    refs = {"submodel_id": "submodel", "frame_id": "frame", "geometry_id": "geometry", "mesh_id": "mesh",
            "material_id": "material", "optics_id": "optics", "from_node_id": "node", "to_node_id": "node",
            "node_id": "node", "sensor_node_id": "node", "load_id": "load", "environment_id": "environment", "expression_id": "expression"}
    fields = {"temperature": ("temperature", 0), "capacity": ("capacity", 0), "conductance": ("conductance", 0),
              "power": ("power", None), "density": ("density", 0), "specific_heat": ("specific_heat", 0),
              "conductivity": ("conductivity", 0), "area": ("area", 0), "background_temperature": ("temperature", 0),
              "solar_flux": ("flux", 0), "start": ("time", None), "end": ("time", None), "time_origin": ("time", None),
              "on_below": ("temperature", 0), "off_above": ("temperature", 0)}
    for e in entities.values():
        try:
            kind = e["kind"]
            for key, item in e.items():
                if key in refs:
                    target(item, refs[key])
                if key in fields:
                    quantity(item, *fields[key])
            for key, kinds in (("facet_ids", "facet"), ("excluded_facet_ids", "facet"), ("load_ids", "load"), ("control_ids", "control")):
                for item in e.get(key, []):
                    target(item, kinds)
            if "parent_id" in e:
                target(e["parent_id"], kind)
                seen = {e["id"]}
                cursor = e
                while "parent_id" in cursor:
                    if cursor["parent_id"] in seen:
                        fail("cycle")
                    seen.add(cursor["parent_id"])
                    cursor = target(cursor["parent_id"], kind)
            if kind == "node":
                capacity = e["capacity"]["value"]
                if (e["classification"] == "capacitive") != (capacity > 0):
                    fail("range")
            if kind == "conductor" and e["from_node_id"] == e["to_node_id"]:
                fail("reference")
            if kind in ("face", "facet") and e["area"]["value"] <= 0:
                fail("range")
            if kind == "frame":
                for q in e["origin"]:
                    quantity(q, "length")
                r = e["rotation"]
                if any(abs(sum(r[i][k]*r[j][k] for k in range(3)) - (1 if i == j else 0)) > 1e-12 for i in range(3) for j in range(3)):
                    fail("frame")
                determinant = sum(r[0][i] * (r[1][(i+1)%3]*r[2][(i+2)%3]-r[1][(i+2)%3]*r[2][(i+1)%3]) for i in range(3))
                if abs(determinant - 1) > 1e-12:
                    fail("frame")
            if kind in ("facet", "element") and target(e["mesh_id"], "mesh")["role"] != ("radiation" if kind == "facet" else "conduction"):
                fail("reference")
            if kind == "material":
                lo, hi = [quantity(q, "temperature", 0) for q in e["valid_temperature"]]
                if lo >= hi or e["density"]["value"] <= 0 or e["specific_heat"]["value"] <= 0 or e["conductivity"]["value"] <= 0:
                    fail("range")
                if ("conductivity_tensor" in e) != ("frame_id" in e):
                    fail("frame")
                if "conductivity_tensor" in e:
                    t = e["conductivity_tensor"]
                    if any(t[i][j] != t[j][i] for i in range(3) for j in range(3)):
                        fail("range")
                    det = sum(t[0][i]*(t[1][(i+1)%3]*t[2][(i+2)%3]-t[1][(i+2)%3]*t[2][(i+1)%3]) for i in range(3))
                    minor = t[0][0]*t[1][1]-t[0][1]*t[0][1]
                    if t[0][0] <= 0 or not math.isfinite(minor) or minor <= 0 or not math.isfinite(det) or det <= 0:
                        fail("range")
            if kind == "optics" and (any(e[k] > 1 for k in ("solar_absorptivity", "ir_emissivity", "specular_fraction", "transmissivity")) or e["specular_fraction"] + e["transmissivity"] > 1):
                fail("range")
            if kind == "case":
                if e["start"]["value"] > e["end"]["value"]:
                    fail("range")
                for overlay in e["overlays"]:
                    o = target(overlay["entity_id"], "node load conductor")
                    field = overlay["field"]
                    if field not in o:
                        fail("reference")
                    quantity(overlay["value"], *fields[field])
            if kind == "control" and e["on_below"]["value"] >= e["off_above"]["value"]:
                fail("range")
            if kind == "load" and "expression_id" in e and target(e["expression_id"], "expression")["dimension"] != "power":
                fail("dimension")
        except ContractError as error:
            error.diagnostic = Diagnostic(error.diagnostic.code, "/entities", e["id"], next((s["id"] for s in model["source_maps"] if any(x["entity_id"] == e["id"] for x in s["entries"])), None))
            raise
    for source in model["source_maps"]:
        keys = set()
        for entry in source["entries"]:
            target(entry["entity_id"], " ".join(BUNDLE["entity_kinds"]))
            key = (entry["namespace"], entry["handle"])
            if key in keys:
                fail("duplicate_id")
            keys.add(key)
    pairs, weights = set(), {}
    for mapping in sorted(model["mappings"], key=lambda item: item["id"]):
        a, b = (target(mapping[key], "face facet element node") for key in ("from_id", "to_id"))
        if (a["kind"], b["kind"]) not in (("face", "facet"), ("face", "element"), ("facet", "node"), ("element", "node")):
            fail("reference")
        pair = (a["id"], b["id"])
        if pair in pairs:
            fail("duplicate_id")
        pairs.add(pair)
        quantity(mapping["area"], "area", 0, True)
        domain = (a["id"], b["kind"])
        weights[domain] = weights.get(domain, 0) + mapping["weight"]
    if any(abs(weight-1) > 1e-12 for weight in weights.values()):
        fail("range")
    for attachment in model["attachments"]:
        target(attachment["entity_id"], "facet element load")
        face = target(attachment["face_id"], "face")
        geometry = target(face["geometry_id"], "geometry")
        if (attachment["state"] != "resolved" or attachment["source_revision"] != geometry["revision"] or attachment["persistent_ref"] != face["persistent_ref"] or attachment["signature"] != face["signature"]):
            fail("attachment")
    try:
        expression_types(entities)
    except ContractError as error:
        d = error.diagnostic
        error.diagnostic = Diagnostic(d.code, d.pointer, d.entity_id, next((s["id"] for s in model["source_maps"] if any(x["entity_id"] == d.entity_id for x in s["entries"])), None))
        raise


def read(kind, document):
    value = deepcopy(document)
    if not isinstance(value, dict):
        fail("schema")
    expected_version = "2.0.0" if kind in {"spatial", "manifest2"} else VERSION
    if value.get("contract_version") != expected_version or "minimum_reader" in value and value["minimum_reader"] != expected_version:
        fail("version")
    if kind == "operation" and value.get("operation") not in BUNDLE["operations"]:
        fail("unsupported_operation")
    if kind not in BUNDLE["schemas"]:
        fail("schema")
    validate(BUNDLE["schemas"][kind], value)
    try:
        value = normalize(value)
    except ContractError as error:
        if kind == "model" and error.diagnostic.entity_id:
            d = error.diagnostic
            error.diagnostic = Diagnostic(d.code, d.pointer, d.entity_id, next((s["id"] for s in value["source_maps"] if any(x["entity_id"] == d.entity_id for x in s["entries"])), None))
        raise
    def artifacts(v):
        if isinstance(v, dict):
            if set(v) == {"path", "sha256", "byte_length"}:
                parts = v["path"].split("/")
                if any(p in ("", ".", "..") or p.endswith((".", " ")) or p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]} for p in parts):
                    fail("artifact")
            for item in v.values():
                artifacts(item)
        elif isinstance(v, list):
            for item in v:
                artifacts(item)
    artifacts(value)
    if kind == "model":
        check_model(value)
    if kind == "spatial":
        from .spatial import check
        check(value)
    if kind in {"manifest", "manifest2"}:
        records = value["artifacts"]
        by_id = {r["id"]: r for r in records}
        if len(by_id) != len(records) or len({r["artifact"]["path"].lower() for r in records}) != len(records):
            fail("duplicate_id")
        if value["model_artifact_id"] not in by_id or by_id[value["model_artifact_id"]]["role"] != "model":
            fail("reference")
        dependency_order({key: set(r["dependencies"]) for key, r in by_id.items()}, "artifact")
    if kind == "operation":
        op, args = value["operation"], value["arguments"]
        if op in ("model.hash", "model.validate"):
            value["arguments"]["snapshot"] = read("model", args["snapshot"])
        if op == "thermal.conductor.create":
            quantity(args["conductance"], "conductance", 0)
            if len({args[k] for k in ("id", "from_node_id", "to_node_id")}) != 3:
                fail("reference")
    if kind == "worker" and value["type"] == "terminal":
        if (value["payload"]["outcome"] == "succeeded") != ("result" in value["payload"]):
            fail("artifact")
    if kind == "worker" and value["type"] == "checkpoint":
        quantity(value["payload"]["time"], "time")
    return value


def snapshot(model):
    value = read("model", model)
    for key in ("audit", "gui", "revision"):
        value.pop(key, None)
    for key in ("entities", "source_maps", "mappings", "attachments"):
        value[key].sort(key=lambda x: x["id"])
    for source in value["source_maps"]:
        source["entries"].sort(key=lambda x: (x["namespace"], x["handle"], x["entity_id"]))
    for e in value["entities"]:
        for key in ("facet_ids", "excluded_facet_ids", "load_ids", "control_ids"):
            if key in e:
                e[key].sort()
    return value


def inspect(kind, raw):
    try:
        value = unframe(raw) if kind == "worker-frame" else read(kind, loads(raw))
        semantic = snapshot(value) if kind == "model" else value
        return {"status": "passed", "normalized": value, "canonical": canonical(semantic).hex(),
                "semantic_hash": sha256(b"FCST-semantic-v1\0" + canonical(semantic)).hexdigest()}
    except ContractError as error:
        result = {"status": "failed", "code": error.diagnostic.code}
        if error.diagnostic.entity_id:
            result["entity_id"] = error.diagnostic.entity_id
            result["pointer"] = error.diagnostic.pointer
            if error.diagnostic.source_map_id:
                result["source_map_id"] = error.diagnostic.source_map_id
        return result


def verify_artifact(reference, data):
    if len(data) != reference["byte_length"] or sha256(data).hexdigest() != reference["sha256"]:
        fail("artifact")


def frame(message):
    read("worker", message)
    raw = json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    if len(raw) > 65536:
        fail("schema")
    return struct.pack("<I", len(raw)) + raw


def unframe(data):
    if len(data) < 4 or not 1 <= struct.unpack("<I", data[:4])[0] <= 65536 or len(data) != 4 + struct.unpack("<I", data[:4])[0]:
        fail("invalid_json")
    return read("worker", loads(data[4:]))
