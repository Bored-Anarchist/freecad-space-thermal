# SPDX-License-Identifier: MIT OR Apache-2.0
"""Closed HDF5 v2 spatial envelope; validate budgets before reading datasets."""
import io
from hashlib import sha256
from fcst_contracts import read, loads, canonical
from .persistence import encode, reject
from .arrays import libraries


def digest(value):
    return sha256(b"FCST-semantic-v1\0" + canonical(read("spatial", value))).hexdigest()


def datasets(value):
    # Explicit arrays and the JSON declaration are compared, never trusted independently.
    import uuid
    result = {"descriptor": (list(encode(value)), "u1", "1"),
              "vertex_uuid": ([list(uuid.UUID(i).bytes) for i in value["vertex_ids"]], "u1", "1"),
              "vertices": (value["vertices"], "<f8", "m"),
              "time": (value["times"], "<f8", "s"),
              "cell_uuid": ([list(uuid.UUID(c["id"]).bytes) for c in value["cells"]], "u1", "1"),
              "offsets": ([0], "<u8", "1"), "connectivity": ([], "<u8", "1")}
    for c in value["cells"]:
        result["connectivity"][0].extend(c["vertices"])
        result["offsets"][0].append(len(result["connectivity"][0]))
    for f in value["fields"]:
        result[f["quantity"]] = (f["values"], "<f8", f["unit"])
    return result


def write_spatial(value, max_bytes=64*1024*1024):
    value = read("spatial", loads(encode(value)))
    h5py, np = libraries()
    output = io.BytesIO()
    with h5py.File(output, "w") as file:
        file.attrs.update(contract_version=np.bytes_("2.0.0"), artifact_role=np.bytes_("spatial"), semantic_hash=np.bytes_(digest(value)))
        for name, (values, dtype, unit) in datasets(value).items():
            file.create_dataset(name, data=np.asarray(values, dtype=dtype)).attrs["unit"] = np.bytes_(unit)
    raw = output.getvalue()
    read_spatial(raw, max_bytes)
    return raw


def read_spatial(raw, max_bytes=64*1024*1024):
    if len(raw) > max_bytes:
        reject("hdf5_limit")
    h5py, np = libraries()
    try:
        with h5py.File(io.BytesIO(raw), "r") as file:
            if set(file.attrs) != {"contract_version", "artifact_role", "semantic_hash"}:
                reject("hdf5_contract")
            if any(file.attrs.get_id(k).shape != () or file.attrs.get_id(k).dtype.kind != "S" or file.attrs.get_id(k).dtype.itemsize > 128 for k in file.attrs):
                reject("hdf5_limit")
            if file.attrs["contract_version"] != b"2.0.0" or file.attrs["artifact_role"] != b"spatial":
                reject("hdf5_contract")
            names = {"descriptor", "vertex_uuid", "vertices", "time", "cell_uuid", "offsets", "connectivity", "temperature", "heat_flux"}
            if not {"descriptor", "vertex_uuid", "vertices", "time", "cell_uuid", "offsets", "connectivity"} <= set(file) <= names:
                reject("hdf5_contract")
            total, seen = 0, set()
            for name in file:
                if not isinstance(file.get(name, getlink=True), h5py.HardLink):
                    reject("hdf5_link")
                d = file[name]
                address = h5py.h5o.get_info(d.id).addr
                if address in seen:
                    reject("hdf5_link")
                seen.add(address)
                if not isinstance(d, h5py.Dataset) or d.is_virtual or d.external or d.id.get_create_plist().get_nfilters():
                    reject("hdf5_contract")
                expected_dtype = "u1" if name in {"descriptor", "vertex_uuid", "cell_uuid"} else "<u8" if name in {"offsets", "connectivity"} else "<f8"
                if d.dtype != np.dtype(expected_dtype) or d.ndim not in (1, 2, 3) or 0 in d.shape or d.chunks:
                    reject("hdf5_contract")
                total += d.size*d.dtype.itemsize
                if total > max_bytes:
                    reject("hdf5_limit")
                if (set(d.attrs) != {"unit"} or d.attrs.get_id("unit").shape != ()
                        or d.attrs.get_id("unit").dtype.kind != "S" or d.attrs.get_id("unit").dtype.itemsize > 32):
                    reject("hdf5_contract")
            if file["descriptor"].ndim != 1 or file["descriptor"].size > 1048576:
                reject("hdf5_limit")
            value = read("spatial", loads(file["descriptor"][...].tobytes()))
            expected = datasets(value)
            if set(file) != set(expected) or file.attrs["semantic_hash"] != digest(value).encode("ascii"):
                reject("hdf5_identity")
            # Check every shape before materializing any bulk array.
            for name, (values, dtype, unit) in expected.items():
                target = np.asarray(values, dtype=dtype)
                if file[name].shape != target.shape or file[name].attrs["unit"] != unit.encode("ascii"):
                    reject("hdf5_shape")
            for name, (values, dtype, _) in expected.items():
                if not np.array_equal(file[name][...], np.asarray(values, dtype=dtype)):
                    reject("hdf5_identity")
            return value
    except (OSError, RuntimeError, TypeError, KeyError):
        reject("hdf5_contract")
