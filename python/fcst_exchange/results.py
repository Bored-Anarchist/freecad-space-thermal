# SPDX-License-Identifier: MIT OR Apache-2.0
"""Strict source-result tables and explicit, discontinuity-aware SI queries."""
from dataclasses import dataclass
from hashlib import sha256
import bisect
import math

from fcst_contracts import BUNDLE, ContractError, loads, read
from .core import ExchangeError, reject, identity


@dataclass(frozen=True)
class Results:
    entity_ids: tuple
    time: tuple
    values: tuple
    quantity: str
    unit: str
    interpolation: str
    discontinuities: tuple
    source_sha256: str
    source_unit: str
    source_time_unit: str
    source_sign: str

    @property
    def provenance(self):
        return {"source_sha256":self.source_sha256, "source_unit":self.source_unit,
                "source_time_unit":self.source_time_unit, "source_sign":self.source_sign,
                "target_sign":{"power":"positive_into_node","temperature":"absolute","flux":"source_positive"}[self.quantity],
                "interpolation":self.interpolation, "discontinuities":list(self.discontinuities)}


def read_results(raw, model):
    try:
        value = loads(raw)
        model = read("model", model)
    except (ContractError, TypeError, ValueError, RecursionError):
        reject("result_contract")
    fields = {"version","identities","quantity","unit","time_unit","sign","time","values","interpolation","discontinuities"}
    if not isinstance(value, dict) or set(value) != fields or value["version"] != "fcst-results/1":
        reject("result_version_or_fields")
    quantity = value["quantity"]
    if not isinstance(quantity,str) or quantity not in {"temperature","power","flux"}:
        reject("result_quantity")
    unit, time_unit = value["unit"], value["time_unit"]
    if not isinstance(unit, str) or not isinstance(time_unit, str) or unit not in BUNDLE["units"] or time_unit not in BUNDLE["units"]:
        reject("result_unit")
    dimension, scale, offset = BUNDLE["units"][unit]
    if dimension != quantity or BUNDLE["units"][time_unit][0] != "time":
        reject("result_dimension")
    sign = value["sign"]
    allowed = {"power":{"positive_into_node", "positive_out_of_node"},
               "temperature":{"absolute"}, "flux":{"source_positive"}}
    if not isinstance(sign, str) or sign not in allowed[quantity]:
        reject("result_sign")
    if not isinstance(value["interpolation"], str) or value["interpolation"] not in {"linear","previous","none"}:
        reject("result_interpolation")
    source_map = {}
    for source in model["source_maps"]:
        for entry in source["entries"]:
            key = (entry["namespace"],entry["handle"])
            if key in source_map:
                reject("result_ambiguous_identity")
            source_map[key] = entry["entity_id"]
    entities = {e["id"]:e["kind"] for e in model["entities"]}
    refs = value["identities"]
    if not isinstance(refs, list) or not 0 < len(refs) <= 10000:
        reject("result_identity")
    ids = []
    for ref in refs:
        if not isinstance(ref, list) or len(ref) != 2:
            reject("result_identity")
        key = identity(*ref)
        if key not in source_map:
            reject("result_identity")
        target = source_map[key]
        if entities[target] not in ({"node"} if quantity in {"temperature","power"} else {"face","facet","element"}):
            reject("result_identity_kind")
        ids.append(target)
    if len(set(ids)) != len(ids):
        reject("result_identity")
    def number(v):
        if type(v) not in (int,float) or not math.isfinite(v):
            reject("result_number")
        return float(v)
    if not isinstance(value["time"],list) or not 0 < len(value["time"]) <= 10000:
        reject("result_time")
    times = tuple(number(t)*BUNDLE["units"][time_unit][1] for t in value["time"])
    if any(not math.isfinite(t) for t in times) or any(a >= b or not math.isfinite(b-a) for a,b in zip(times,times[1:])):
        reject("result_time")
    values = value["values"]
    if not isinstance(values,list) or len(values) != len(times):
        reject("result_shape")
    samples = []
    for row in values:
        if not isinstance(row,list) or len(row) != len(ids):
            reject("result_shape")
        converted = tuple((number(v)*scale+offset)*(-1 if sign == "positive_out_of_node" else 1) for v in row)
        if any(not math.isfinite(v) or quantity == "temperature" and v < 0 for v in converted):
            reject("result_range")
        samples.append(converted)
    breaks = value["discontinuities"]
    if (not isinstance(breaks,list) or any(type(i) not in (int,float) or not float(i).is_integer() or i < 1 or i >= len(times) for i in breaks)
            or len(set(breaks)) != len(breaks)):
        reject("result_discontinuity")
    return Results(tuple(ids), times, tuple(samples), quantity, BUNDLE["si"][quantity], value["interpolation"],
                   tuple(sorted(int(i) for i in breaks)), sha256(raw.encode() if isinstance(raw,str) else raw).hexdigest(), unit, time_unit, sign)


def query(result, time, *, discontinuity_policy="error"):
    if type(time) not in (int,float) or not math.isfinite(time) or not isinstance(discontinuity_policy,str) or discontinuity_policy not in {"error","previous"}:
        reject("query_policy")
    index = bisect.bisect_left(result.time, time)
    if index < len(result.time) and result.time[index] == time:
        values, method = result.values[index], "exact"
    else:
        if index == 0 or index == len(result.time):
            reject("result_extrapolation")
        method = result.interpolation
        if method == "none":
            reject("interpolation_disabled")
        if index in result.discontinuities:
            if discontinuity_policy != "previous":
                reject("discontinuity_policy_required")
            method = "previous"
        values = result.values[index-1]
        if method == "linear":
            fraction = (time-result.time[index-1])/(result.time[index]-result.time[index-1])
            values = tuple((1-fraction)*a+fraction*b for a,b in zip(values,result.values[index]))
    return {"time":time, "unit":result.unit, "quantity":result.quantity, "entity_ids":list(result.entity_ids),
            "values":list(values), "provenance":{**result.provenance, "query_method":method, "discontinuity_policy":discontinuity_policy}}
