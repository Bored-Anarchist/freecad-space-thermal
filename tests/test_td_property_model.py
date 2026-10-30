# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fcst_app.persistence import encode,Package
from fcst_exchange import ExchangeError
from fcst_exchange.td_properties import parse_properties
from fcst_exchange.td_property_model import material_entity,optics_entity,dependency_catalog,export_library,read_library,render_library,read_library_files,import_document,export_document_package
from fcst_exchange.td_writer import node_payload
from fcst_exchange.td_decode import decode_drawing
from fcst_exchange.dwg_native import NativeSnapshot
from td_fixture import drawing
from test_td_properties import TDP,RCO
from test_sinda_writer import model


def properties_model():
    m=model();m['entities']=[material_entity(parse_properties(TDP,'tdp').entries[0],(100,500)),
                            optics_entity(parse_properties(RCO.replace(b'[USEVSA]',b'[SOLSPEC]\n0.1\n[IRSPEC]\n0.1\n[SOLTRANS]\n0\n[IRTRANS]\n0\n[USEVSA]'),'rco').entries[0])]
    return m


def document_package(raw,model,names):
    source='source/owned.original';name='materials (owned).tdp';files={'model.json':encode(model),source:raw,
        'exchange/property-source-map.json':encode({'profile':'td-property-document/1','source_paths':{name:source},'entries':names,'report':{'kind':'tdp'}})}
    records=[];model_id='00000000-0000-4000-8000-000000000091'
    for index,(path,data) in enumerate(files.items()):
        records.append({'id':model_id if path=='model.json' else '00000000-0000-4000-8000-'+str(92+index).zfill(12),
            'role':'model' if path=='model.json' else 'source_original' if path==source else 'evidence',
            'artifact':{'path':path,'sha256':sha256(data).hexdigest(),'byte_length':len(data)},'dependencies':[]})
    return Package({'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':model['project_id'],'revision':0,'model_artifact_id':model_id,'artifacts':records},files)


class TdPropertyModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_constant_material_mapping_uses_stored_si_and_explicit_validity_interval(self):
        entry=parse_properties(TDP,'tdp').entries[0]
        actual=material_entity(entry,[150,450]);self.assertEqual(actual['density'],{'value':2500,'unit':'kg/m3'})
        self.assertEqual(actual['conductivity']['value'],12.5);self.assertEqual(actual['specific_heat']['value'],800)
        self.assertEqual([q['value'] for q in actual['valid_temperature']],[150,450])
        raw=TDP.replace(b'[END]\r\n',b'[DENSITYMULT]\r\n2\r\n[KUMULT]\r\n3\r\n[END]\r\n')
        scaled=material_entity(parse_properties(raw,'tdp').entries[0],[150,450])
        self.assertEqual(scaled['density']['value'],5000);self.assertEqual(scaled['conductivity']['value'],37.5)

    def test_missing_bounds_unknown_modes_or_fields_and_invalid_scalars_block_material_mapping(self):
        entry=parse_properties(TDP,'tdp').entries[0]
        for bounds in (None,[],[100,100],[0,300],[float('nan'),300],['100',300]):
            with self.assertRaises(ExchangeError):material_entity(entry,bounds)
        for raw in (TDP.replace(b'[TYPE]\r\n0',b'[TYPE]\r\n2'),
                    TDP.replace(b'[END]\r\n',b'[FUTURE]\r\n1\r\n[END]\r\n'),
                    TDP.replace(b'[END]\r\n',b'[USEANISO]\r\n1\r\n[END]\r\n'),
                    TDP.replace(b'2500',b'0'),TDP.replace(b'2500',b'1E-999')):
            with self.assertRaises(ExchangeError):material_entity(parse_properties(raw,'tdp').entries[0],[100,500])

    def test_optics_require_equivalent_bands_and_physical_energy_bounds(self):
        files,_,_=render_library(properties_model());entry=parse_properties(files['optics.rco'],'rco').entries[0]
        actual=optics_entity(entry);self.assertEqual(actual['solar_absorptivity'],.2);self.assertEqual(actual['ir_emissivity'],.8)
        raw=files['optics.rco']
        for bad in (raw.replace(b'[IRSPEC]\r\n0.10000000000000001',b'[IRSPEC]\r\n0.5'),
                    raw.replace(b'[USEVSA]\r\n0',b'[USEVSA]\r\n1'),
                    raw.replace(b'[SOLREFRAC]\r\n1',b'[SOLREFRAC]\r\n2'),
                    raw.replace(b'[IRTRANS]\r\n0',b'[IRTRANS]\r\n0.5').replace(b'[SOLTRANS]\r\n0',b'[SOLTRANS]\r\n0.5')):
            with self.assertRaises(ExchangeError):optics_entity(parse_properties(bad,'rco').entries[0])

    def test_source_free_property_library_roundtrips_every_quantity_label_and_id_without_processes(self):
        original=properties_model();before=deepcopy(original)
        with patch('subprocess.Popen',side_effect=AssertionError('vendor execution forbidden')):
            receipt=export_library(original,self.root/'library');actual,files=read_library(self.root/'library')
        self.assertEqual(actual['entities'],sorted(before['entities'],key=lambda e:e['id']));self.assertEqual(original,before)
        self.assertEqual(set(files),{'materials.tdp','optics.rco','canonical.json','property-map.json'})
        self.assertTrue(receipt['independent_reopen_verified']);self.assertFalse(receipt['qualified'])

    def test_library_tampering_with_updated_hash_still_fails_semantic_verification(self):
        export_library(properties_model(),self.root/'library');_,files=read_library(self.root/'library')
        files['materials.tdp']=files['materials.tdp'].replace(b'[DENSITY]\r\n2500',b'[DENSITY]\r\n2501')
        metadata=json.loads(files['property-map.json']);metadata['files']['materials.tdp']=sha256(files['materials.tdp']).hexdigest();files['property-map.json']=encode(metadata)
        with self.assertRaisesRegex(ExchangeError,'semantic_mismatch'):read_library_files(files)

    def test_library_unknown_files_aliases_existing_targets_and_unmapped_models_fail(self):
        export_library(properties_model(),self.root/'library');(self.root/'library/unexpected.dat').write_bytes(b'keep')
        with self.assertRaises(ExchangeError):read_library(self.root/'library')
        with self.assertRaises(ExchangeError):export_library(properties_model(),self.root/'library')
        invalid=properties_model();invalid['entities'].append(model()['entities'][0])
        with self.assertRaises(ExchangeError):export_library(invalid,self.root/'invalid')
        self.assertFalse((self.root/'invalid').exists())

    def test_dependency_catalog_resolves_missing_and_ambiguous_material_names_without_echoing_them(self):
        snap=drawing([node_payload('MAIN',1,300,10,'capacitive')]);inventory=decode_drawing(snap);payload=inventory.payloads[0]
        fields=deepcopy(payload.fields);fields.update(use_material=True,material='OWNED MATERIAL')
        from dataclasses import replace
        with patch('fcst_exchange.td_decode.decode_drawing',return_value=replace(inventory,payloads=(replace(payload,fields=fields),))):
            one=dependency_catalog(snap,[('one.tdp',TDP)]);missing=dependency_catalog(snap,[]);duplicate=dependency_catalog(snap,[('one.tdp',TDP),('two.tdp',TDP)])
        self.assertEqual(one['references'][0]['status'],'resolved');self.assertEqual(missing['references'][0]['status'],'missing')
        self.assertEqual(duplicate['references'][0]['status'],'ambiguous');self.assertNotIn('OWNED MATERIAL',json.dumps(one))
        self.assertFalse(one['full_drawing_dependency_closure'])

    def test_original_property_import_has_explicit_selection_validity_and_source_identity(self):
        extra=TDP[TDP.index(b'[START]'):].replace(b'OWNED MATERIAL',b'UNSUPPORTED MATERIAL').replace(b'[TYPE]\r\n0',b'[TYPE]\r\n2')
        raw=TDP+extra
        with self.assertRaises(ExchangeError):import_document(raw,'tdp',[100,500])
        model,report=import_document(raw,'tdp',[100,500],names=['OWNED MATERIAL'])
        self.assertEqual(len(model['entities']),1);self.assertEqual(report['retained_unselected_entries'],1)
        self.assertEqual(model['source_maps'][0]['source_revision'],sha256(raw).hexdigest())
        for names in (['missing'],['OWNED MATERIAL','owned material'],[]):
            with self.assertRaises(ExchangeError):import_document(raw,'tdp',[100,500],names=names)

    def test_documented_defaults_and_inactive_tables_map_without_enabling_variable_physics(self):
        raw=b'[UNICODE]\n[START]\n[NAME]\nOWNED DEFAULT\n[VARSPECHEAT]\n2\n100\n700\n500\n900\n[END]\n'
        model,_=import_document(raw,'tdp',[100,500]);material=model['entities'][0]
        self.assertEqual(material['conductivity']['value'],1);self.assertEqual(material['density']['value'],1)
        self.assertEqual(material['specific_heat']['value'],1)
        active=raw.replace(b'[VARSPECHEAT]',b'[USEVARSPECHEAT]\n1\n[VARSPECHEAT]')
        with self.assertRaises(ExchangeError):import_document(active,'tdp',[100,500])
        optics,_=import_document(b'[UNICODE]\n[START]\n[NAME]\nOWNED OPTICS\n[END]\n','rco')
        self.assertEqual(optics['entities'][0]['solar_absorptivity'],1);self.assertEqual(optics['entities'][0]['transmissivity'],0)

    def test_native_property_source_export_preserves_unselected_entries_comments_and_original_bytes(self):
        extra=TDP[TDP.index(b'[START]'):].replace(b'OWNED MATERIAL',b'UNSUPPORTED MATERIAL').replace(b'[TYPE]\r\n0',b'[TYPE]\r\n2');raw=TDP+extra
        model,_=import_document(raw,'tdp',[100,500],names=['OWNED MATERIAL']);model['entities'][0]['specific_heat']['value']=850
        package=document_package(raw,model,['OWNED MATERIAL']);before=dict(package.files)
        receipt=export_document_package(package,self.root/'edited')
        self.assertTrue(receipt['canonical_roundtrip_verified']);self.assertEqual(package.files,before)
        self.assertEqual((self.root/'edited/materials (owned).tdp').read_bytes(),raw.replace(b'800',b'850',1))
        self.assertTrue((self.root/'edited/canonical.json').is_file())

    def test_native_property_source_export_inserts_optional_defaults_and_rejects_identity_changes(self):
        raw=b'[UNICODE]\n[START]\n[NAME]\nOWNED DEFAULT\n[END]\n';model,_=import_document(raw,'tdp',[100,500])
        model['entities'][0]['specific_heat']['value']=800;package=document_package(raw,model,['OWNED DEFAULT'])
        export_document_package(package,self.root/'defaults')
        self.assertEqual((self.root/'defaults/materials (owned).tdp').read_bytes(),raw.replace(b'[END]',b'[SPECHEAT]\n800\n[END]'))
        model['entities'][0]['label']='renamed'
        with self.assertRaises(ExchangeError):export_document_package(document_package(raw,model,['OWNED DEFAULT']),self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
