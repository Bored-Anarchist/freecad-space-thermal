# SPDX-License-Identifier: MIT OR Apache-2.0
"""Optional-array acceptance, collected by check_esatan in the locked environment."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from fcst_app.persistence import encode
from fcst_exchange import ExchangeError
from fcst_exchange.esatan import EsatanAdapter
from fcst_exchange.esatan_results import TmdBinding, read_tmd
from fcst_exchange.results import query
from esatan_fixture import NETWORK, UNITS, tmd


class EsatanResultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); source=self.root/'source'; source.mkdir()
        (source/'main.d').write_bytes(NETWORK)
        self.model=EsatanAdapter(UNITS,source_version='2018-sp1').preview(source,'main.d').require_native()
        self.path=self.root/'result.tmd'; self.raw=tmd(self.path)

    def binding(self,raw=None):
        return TmdBinding(sha256(raw or self.raw).hexdigest(),sha256(encode(self.model)).hexdigest(),
                          'CASE',((1,'MAIN','/MAIN','ESA.MAIN'),))

    def load(self,raw=None,**kwargs):
        raw=raw or self.path.read_bytes()
        return read_tmd(raw,self.model,self.binding(raw),UNITS,**kwargs)

    def mutate(self,operation):
        with h5py.File(self.path,'r+') as f: operation(f)
        return self.path.read_bytes()

    def test_actual_dataset_profile_maps_source_identity_units_time_and_powers(self):
        result=self.load()
        self.assertEqual(result.unit,'K'); self.assertEqual(result.time,(0,10,20))
        self.assertEqual(result.values,((293.15,303.15),(294.15,303.15),(296.15,303.15)))
        self.assertEqual(result.source_sha256,sha256(self.raw).hexdigest())
        power=self.load(attribute='Total_Internal_Heat_Source')
        self.assertEqual(power.unit,'W'); self.assertEqual(power.values,((5,0),(5,0),(8,0)))
        self.assertEqual(power.provenance['source_sign'],'positive_into_node')

    def test_result_hash_model_case_model_path_and_producer_binding_are_required(self):
        base=self.binding()
        changes=[{'source_sha256':'0'*64},{'model_sha256':'0'*64},{'case':'OTHER'},
                 {'models':((1,'MAIN','/OTHER','ESA.MAIN'),)}, {'models':((1,'OTHER','/MAIN','ESA.MAIN'),)}]
        for fields in changes:
            with self.assertRaises(ExchangeError): read_tmd(self.raw,self.model,replace(base,**fields),UNITS)
        for kwargs in ({'models':((1,'MAIN','/MAIN','ESA.MAIN'),(1,'A','/A','ESA.A'))},{'producer':'2018-sp1'}):
            with self.assertRaises(ExchangeError): replace(base,**kwargs)
        self.mutate(lambda f:f['AnalysisSet1/DataGroup1'].attrs.modify('ESATAN_version',np.array([b'2024'])))
        with self.assertRaisesRegex(ExchangeError,'producer'): self.load()

    def test_interpolation_is_explicit_and_never_crosses_events_silently(self):
        result=self.load(interpolation='linear',discontinuities=(2,))
        self.assertAlmostEqual(query(result,5)['values'][0],293.65)
        with self.assertRaisesRegex(ExchangeError,'discontinuity'): query(result,15)
        self.assertEqual(query(result,15,discontinuity_policy='previous')['values'][0],294.15)
        with self.assertRaisesRegex(ExchangeError,'interpolation'): query(self.load(),5)
        with self.assertRaisesRegex(ExchangeError,'extrapolation'): query(result,30)

    def test_duplicate_missing_extra_or_unknown_nodes_and_types_are_rejected(self):
        for values in ([[1,1],[1,1]],[[1,1],[3,1]],[[1,1],[2,2]]):
            tmd(self.path)
            self.mutate(lambda f:f['AnalysisSet1/thermalNodes'].__setitem__(slice(None),values))
            with self.assertRaises(ExchangeError): self.load()
        tmd(self.path)
        self.mutate(lambda f:f['AnalysisSet1/DataGroup1/thermalNodesStringData'].__setitem__((0,0,0),b'B'))
        with self.assertRaisesRegex(ExchangeError,'node_type'): self.load()

    def test_nonfinite_nonmonotone_negative_kelvin_and_bad_shape_are_rejected(self):
        mutations=[lambda f:f['AnalysisSet1/DataGroup1/times'].__setitem__(1,0),
                   lambda f:f['AnalysisSet1/DataGroup1/thermalNodesRealData'].__setitem__((0,0,0),float('nan')),
                   lambda f:f['AnalysisSet1/DataGroup1/thermalNodesRealData'].__setitem__((0,0,0),-300),
                   lambda f:f['AnalysisSet1'].attrs.modify('TAbs',0.)]
        for mutation in mutations:
            tmd(self.path); self.mutate(mutation)
            with self.assertRaises(ExchangeError): self.load()
        tmd(self.path)
        def shape(f):
            d=f['AnalysisSet1/DataGroup1']; del d['thermalNodesRealData']; d.create_dataset('thermalNodesRealData',shape=(3,1,16))
        self.mutate(shape)
        with self.assertRaises(ExchangeError): self.load()

    def test_external_soft_alias_virtual_and_variable_storage_are_rejected(self):
        def soft(f): f['AnalysisSet1/alias']=h5py.SoftLink('/AnalysisSet1/thermalNodes')
        def hard(f): f['AnalysisSet1/alias']=f['AnalysisSet1/thermalNodes']
        def external(f): f['AnalysisSet1/alias']=h5py.ExternalLink('missing.tmd','/data')
        def variable(f): f['AnalysisSet1'].create_dataset('extra',(1,),dtype=h5py.string_dtype())
        def virtual(f):
            layout=h5py.VirtualLayout(shape=(3,),dtype='f8'); layout[:]=h5py.VirtualSource('missing.tmd','/x',shape=(3,))
            f['AnalysisSet1'].create_virtual_dataset('extra',layout)
        for mutation in (soft,hard,external,variable,virtual):
            tmd(self.path); self.mutate(mutation)
            with self.assertRaises(ExchangeError): self.load()

    def test_logical_allocation_and_unsafe_filters_are_checked_before_materialization(self):
        self.mutate(lambda f:f['AnalysisSet1'].create_dataset('bomb',shape=(1000000,1000000),dtype='f8',chunks=(1,1)))
        with self.assertRaisesRegex(ExchangeError,'allocation_limit'): self.load()
        tmd(self.path)
        self.mutate(lambda f:f['AnalysisSet1'].create_dataset('lossy',data=[1.25,2.5],scaleoffset=1))
        with self.assertRaisesRegex(ExchangeError,'filter'): self.load()

    def test_future_datasets_attribute_schema_and_model_hierarchy_are_held(self):
        mutations=[lambda f:f['AnalysisSet1'].create_group('FutureRequired'),
                   lambda f:f['AnalysisSet1/thermalNodesRealAttributes'].__setitem__(0,b'Unknown'),
                   lambda f:f['AnalysisSet1/models'].__setitem__(0,(b'MAIN',1,b'/MAIN'))]
        for mutation in mutations:
            tmd(self.path); self.mutate(mutation)
            with self.assertRaises(ExchangeError): self.load()

    def test_inactive_nodes_need_exact_binding_and_cannot_hide_active_or_missing_nodes(self):
        def extend(f):
            a=f['AnalysisSet1']; d=a['DataGroup1']
            del a['thermalNodes']; a.create_dataset('thermalNodes',data=np.array([[1,1],[2,1],[3,1]],dtype='<i4'))
            values=d['thermalNodesRealData'][:]; types=d['thermalNodesStringData'][:]
            del d['thermalNodesRealData']; del d['thermalNodesStringData']
            d.create_dataset('thermalNodesRealData',data=np.concatenate((values,np.zeros((3,1,16))),axis=1))
            d.create_dataset('thermalNodesStringData',data=np.concatenate((types,np.array([[[b'X',b'inactive']]]*3,dtype='S24')),axis=1))
        raw=self.mutate(extend)
        with self.assertRaises(ExchangeError): self.load()
        binding=replace(self.binding(raw),inactive_nodes=((1,3),))
        result=read_tmd(raw,self.model,binding,UNITS)
        self.assertEqual(len(result.entity_ids),2); self.assertEqual(result.provenance['inactive_count'],1)
        self.assertEqual(result.provenance['model_sha256'],sha256(encode(self.model)).hexdigest())
        with self.assertRaises(ExchangeError): read_tmd(raw,self.model,replace(binding,inactive_nodes=((1,2),(1,3))),UNITS)
        self.mutate(lambda f:f['AnalysisSet1/DataGroup1/thermalNodesStringData'].__setitem__((0,2,0),b'D'))
        raw=self.path.read_bytes()
        with self.assertRaisesRegex(ExchangeError,'inactive_type'):
            read_tmd(raw,self.model,replace(binding,source_sha256=sha256(raw).hexdigest()),UNITS)


if __name__=='__main__': unittest.main()
