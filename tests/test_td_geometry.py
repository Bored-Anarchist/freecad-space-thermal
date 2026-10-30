# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from dataclasses import replace
import unittest
from fcst_exchange import ExchangeError
from fcst_exchange.dwg_native import NativeSnapshot,Fields,_one
from fcst_exchange.td_geometry import decode_rectangle,SENTINEL
from fcst_exchange.td_writer import FilerWriter
from fcst_exchange.td_decode import decode_drawing
from fcst_exchange.td_model import convert_network
from fcst_exchange.sinda import SindaUnits
from td_fixture import drawing,envelope


def rectangle():
    f=FilerWriter();b=f.data;b.bd(SENTINEL);b.bl(7)
    for value in (0,1,0,2,0,0):b.bd(value)
    for point in ((1,2,3),(1,0,0),(0,1,0),(0,0,1)):b.point(point)
    # Independently authored opaque attributes. They are never treated as TD
    # surface/mesh/material semantics or made eligible for thermal edits.
    b.bl(99);f.text('owned opaque attributes');return f.result(1)


class TdGeometryTests(unittest.TestCase):
    def test_rectangle_prefix_preserves_unknown_attributes_and_never_claims_thermal_mapping(self):
        row,common=envelope(rectangle());payload=decode_rectangle(row,Fields(common.items()))
        self.assertEqual(payload.fields['serialized_parameters'],(0,1,0,2,0,0));self.assertEqual(payload.fields['origin'],(1,2,3))
        self.assertEqual(payload.record,row);self.assertFalse(payload.report['payload_decoded']);self.assertFalse(payload.report['native_ready'])
        self.assertTrue(payload.report['geometric_envelope_decoded']);self.assertNotIn('owned',str(payload.report))
        self.assertLess(*payload.fields['opaque_data_range']);self.assertLess(*payload.fields['opaque_text_range'])
        with self.assertRaises(ExchangeError):payload.edited_record({'serialized_parameters':(0,2,0,2,0,0)})

    def test_future_version_bad_marker_and_truncated_streams_refuse_geometry_decoding(self):
        record=rectangle();row,common=envelope(record)
        from fcst_exchange.dwg_bits import replace_bits
        raw=bytes.fromhex(row['data'])
        for data in [bytes([raw[0]^64])+raw[1:],replace_bits(raw,66,10,264),raw[:-8]]:
            with self.assertRaises(ExchangeError):decode_rectangle(dict(row,data=data.hex()),Fields(common.items()))

    def test_partial_geometry_inventory_cannot_be_promoted_to_a_native_constant_network(self):
        snap=drawing([rectangle()]);native=deepcopy(snap.native);native['classes'][0].update(cppname='RcRectangle',dxfname='RCRECTANGLE')
        snapshot=NativeSnapshot(native,snap.standard,'');inventory=decode_drawing(snapshot)
        self.assertEqual(inventory.report['decoded_objects'],0);self.assertEqual(inventory.report['partial_objects'],1)
        self.assertEqual(inventory.report['retained_objects'],1)
        result=convert_network(snapshot,SindaUnits('K','J/K','W/K','W','s'),'a'*64)
        self.assertIsNone(result.model);self.assertFalse(result.report['native_ready'])
