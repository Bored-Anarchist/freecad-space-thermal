# SPDX-License-Identifier: MIT OR Apache-2.0
"""Strict HDF5 v1 bulk arrays. Optional dependency; never imported for JSON-only work."""
from __future__ import annotations

import io
import os
import re
import uuid

from .persistence import reject

LAYOUT = {
    "index/node_uuid": ("u1", "1"), "time": ("<f8", "s"),
    "temperature": ("<f8", "K"), "power": ("<f8", "W"), "residual": ("<f8", "W"),
    "index/entity_uuid": ("u1", "1"), "vertices": ("<f8", "m"),
    "connectivity/offsets": ("<u8", "1"), "connectivity/vertex_index": ("<u8", "1"),
    "normals": ("<f8", "1"),
}


def libraries():
    # HDF5 documents :: as disabling all dynamic plugins. Set before library load.
    os.environ["HDF5_PLUGIN_PRELOAD"] = "::"
    try:
        import h5py
        import numpy as np
    except ImportError:
        reject("hdf5_unavailable")
    return h5py, np


def _validate(file, max_bytes):
    h5py, np = libraries()
    if set(file.attrs) != {"contract_version", "semantic_hash", "artifact_role"}:
        reject("hdf5_contract")
    for key in file.attrs:
        if file.attrs.get_id(key).get_storage_size() > 256:
            reject("hdf5_limit")
    version, role, digest = (file.attrs[k] for k in ("contract_version", "artifact_role", "semantic_hash"))
    if (not all(isinstance(v, str) for v in (version, role, digest)) or version != "1.0.0"
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or role not in {"result", "radiation_mesh", "conduction_mesh"}):
        reject("hdf5_contract")
    allowed = ({"index/node_uuid", "time", "temperature", "power", "residual"} if role == "result" else
               {"index/entity_uuid", "vertices", "connectivity/offsets", "connectivity/vertex_index", "normals"})
    required = {"index/node_uuid", "time"} if role == "result" else allowed - ({"normals"} if role == "conduction_mesh" else set())
    datasets, visited, total = {}, set(), 0
    def walk(group, prefix=""):
        nonlocal total
        if len(group) > 16:
            reject("hdf5_limit")
        for key in group:
            name = prefix + key
            if not isinstance(group.get(key, getlink=True), h5py.HardLink):
                reject("hdf5_link")
            if name not in allowed and name not in {"index", "connectivity"}:
                reject("hdf5_contract")
            obj = group[key]
            address = h5py.h5o.get_info(obj.id).addr
            if address in visited:
                reject("hdf5_link")
            visited.add(address)
            if isinstance(obj, h5py.Group):
                if name not in {"index", "connectivity"} or obj.attrs:
                    reject("hdf5_contract")
                walk(obj, name + "/")
                continue
            if not isinstance(obj, h5py.Dataset) or name not in allowed:
                reject("hdf5_contract")
            if (obj.is_virtual or obj.external or obj.id.get_create_plist().get_nfilters()
                    or obj.dtype != np.dtype(LAYOUT[name][0]) or obj.dtype.kind not in "uf"
                    or obj.ndim not in (1, 2) or 0 in obj.shape):
                reject("hdf5_contract")
            total += obj.size * obj.dtype.itemsize
            if total > max_bytes:
                reject("hdf5_limit")
            if (set(obj.attrs) != {"unit"} or obj.attrs.get_id("unit").get_storage_size() > 64
                    or obj.attrs["unit"] != LAYOUT[name][1]):
                reject("hdf5_contract")
            if obj.chunks and (obj.chunks[0] > 256 or obj.ndim == 2 and obj.chunks[1] > 1024):
                reject("hdf5_contract")
            datasets[name] = obj
    walk(file)
    if not required <= datasets.keys():
        reject("hdf5_contract")
    # Shapes and logical budgets are verified before materializing any dataset.
    id_name = "index/node_uuid" if role == "result" else "index/entity_uuid"
    identity = datasets[id_name]
    if identity.ndim != 2 or identity.shape[1] != 16:
        reject("hdf5_shape")
    count = identity.shape[0]
    if role == "result":
        times = datasets["time"]
        if times.ndim != 1:
            reject("hdf5_shape")
        for name in datasets.keys() - {id_name, "time"}:
            if datasets[name].shape != (times.shape[0], count):
                reject("hdf5_shape")
    else:
        if datasets["vertices"].ndim != 2 or datasets["vertices"].shape[1] != 3:
            reject("hdf5_shape")
        if datasets["connectivity/offsets"].shape != (count + 1,) or datasets["connectivity/vertex_index"].ndim != 1:
            reject("hdf5_shape")
        if "normals" in datasets and datasets["normals"].shape != (count, 3):
            reject("hdf5_shape")
    arrays = {name: dataset[...] for name, dataset in datasets.items()}
    if any(not np.isfinite(array).all() for array in arrays.values()):
        reject("hdf5_nonfinite")
    identities = [bytes(row) for row in arrays[id_name]]
    if len(set(identities)) != count or any(uuid.UUID(bytes=b).variant != uuid.RFC_4122 or uuid.UUID(bytes=b).version not in range(1, 6) for b in identities):
        reject("hdf5_identity")
    if role == "result":
        if np.any(np.diff(arrays["time"]) <= 0) or arrays["time"][0] < 0:
            reject("hdf5_time")
        if "temperature" in arrays and np.any(arrays["temperature"] < 0):
            reject("hdf5_range")
    else:
        offsets, indices = arrays["connectivity/offsets"], arrays["connectivity/vertex_index"]
        if (offsets[0] != 0 or offsets[-1] != len(indices) or np.any(offsets[1:] <= offsets[:-1])
                or np.any(indices >= len(arrays["vertices"]))):
            reject("hdf5_connectivity")
        if "normals" in arrays and not np.allclose(np.linalg.norm(arrays["normals"], axis=1), 1, atol=1e-12, rtol=0):
            reject("hdf5_range")
    return {"role": role, "semantic_hash": digest, "arrays": arrays}


def read_arrays(data, max_bytes=64 * 1024 * 1024):
    h5py, _ = libraries()
    if len(data) > max_bytes:
        reject("hdf5_limit")
    try:
        with h5py.File(io.BytesIO(data), "r") as file:
            return _validate(file, max_bytes)
    except (OSError, TypeError, RuntimeError, KeyError):
        reject("hdf5_contract")


def validate_arrays(data, max_bytes=64 * 1024 * 1024):
    result = read_arrays(data, max_bytes)
    metadata = {"role": result["role"], "semantic_hash": result["semantic_hash"]}
    if result["role"] == "result":
        metadata.update(node_ids=[str(uuid.UUID(bytes=bytes(row))) for row in result["arrays"]["index/node_uuid"]],
                        time_count=len(result["arrays"]["time"]),
                        quantities=sorted(set(result["arrays"]) - {"index/node_uuid", "time"}))
    return metadata


def write_arrays(role, semantic_hash, arrays):
    h5py, np = libraries()
    output = io.BytesIO()
    with h5py.File(output, "w") as file:
        file.attrs.update(contract_version="1.0.0", semantic_hash=semantic_hash, artifact_role=role)
        for name, values in arrays.items():
            if name not in LAYOUT:
                reject("hdf5_contract")
            source = np.asarray(values)
            if source.dtype.kind not in "uif" or source.ndim not in (1, 2) or source.size > 8 * 1024 * 1024 or 0 in source.shape:
                reject("hdf5_limit")
            target = source.astype(LAYOUT[name][0])
            if not np.array_equal(source, target):
                reject("hdf5_range")
            chunks = tuple(min(n, 256 if i == 0 else 1024) for i, n in enumerate(target.shape))
            file.create_dataset(name, data=target, chunks=chunks).attrs["unit"] = LAYOUT[name][1]
    data = output.getvalue()
    validate_arrays(data)
    return data
