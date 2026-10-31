# SPDX-License-Identifier: MIT OR Apache-2.0
"""Versioned owned-engine preparation envelope; the existing model stays frozen."""
from copy import deepcopy


def schema(model, obj, arr, enum):
    definitions = deepcopy(model['$defs'])
    quantity = {'$ref': '#/$defs/quantity'}
    uuid = {'$ref': '#/$defs/uuid'}
    definitions['property_law'] = obj({
        'temperature': arr(quantity, minItems=2, maxItems=16384),
        'values': arr(quantity, minItems=2, maxItems=16384),
        'interpolation': enum('linear', 'previous'),
        'extrapolation': enum('error', 'clamp'),
        'discontinuities': arr({'type': 'integer', 'minimum': 1, 'maximum': 16383}, uniqueItems=True),
    })
    body = obj({
        'contract_version': {'const': '1.0.0'},
        'model': {k: deepcopy(v) for k, v in model.items() if k not in ('$defs', '$id', '$schema')},
        'case_id': uuid,
        'material_laws': arr(obj({
            'material_id': uuid,
            **{name: {'$ref': '#/$defs/property_law'} for name in ('density', 'specific_heat', 'conductivity')},
        }, ('density', 'specific_heat', 'conductivity')), maxItems=16384),
        'node_storage': arr(obj({'node_id': uuid, 'material_id': uuid, 'mass': quantity}), maxItems=16384),
    }, ('case_id',))
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            '$id': 'urn:fcst:thermal-input:1.0.0', **body, '$defs': definitions}
