# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fcst_exchange import ExchangeError,Limits
from fcst_exchange.td_properties import parse_properties
from fcst_exchange.td_property_laws import read_laws,write_laws,material_laws,optical_laws,law_report,export_laws,PropertyLaw
from fcst_exchange.td_property_model import import_document,export_library,read_library,read_library_files,export_document_package
from fcst_app.persistence import encode,Package
from fcst_cli.__main__ import main
from test_td_properties import TDP
from test_td_property_model import document_package


def database(fields,kind='tdp'):
    lines=['[UNICODE]','[START]','[NAME]','OWNED LAW']
    for tag,value in fields.items():
        lines+=['['+tag+']',str(value)]
    return ('\n'.join(lines)+'\n[END]\n').encode()


def frame():
    return {'id':'00000000-0000-4000-8000-000000000101','kind':'frame','label':'Declared material axes',
        'origin':[{'value':0,'unit':'m'} for _ in range(3)],'rotation':[[0,-1,0],[1,0,0],[0,0,1]]}


def grid():
    return database({'USEVARCONDTEMPPRES':1,'KUMULT':2,'DENSITY':1000,'SPECHEAT':800,
        'BIVARTEMPERATURE':'2\n100\n300','BIVARPRESSURE':'3\n0\n100\n300',
        'BIVARCONDUCTIVITY':'6\n10\n20\n30\n40\n70\n80'})


POLICY={'interpolation':'linear','extrapolation':'error'}


class TdPropertyLawTests(unittest.TestCase):
    def test_temperature_pressure_grid_uses_temperature_first_storage_and_explicit_policies(self):
        raw=grid();library=read_laws(raw,'tdp');law=material_laws(library['entries'][0])['conductivity'][0]
        self.assertEqual(law.evaluate(temperature=100,pressure=0,**POLICY),20)
        self.assertEqual(law.evaluate(temperature=300,pressure=300,**POLICY),160)
        self.assertEqual(law.evaluate(temperature=200,pressure=50,**POLICY),50)
        self.assertEqual(law.evaluate(temperature=200,pressure=200,**POLICY),110)
        self.assertEqual(law.evaluate(temperature=300,pressure=100,interpolation='previous',extrapolation='error'),80)
        self.assertEqual(law.evaluate(temperature=1,pressure=999,interpolation='linear',extrapolation='clamp'),140)
        for kwargs in ({'temperature':1,'pressure':0}, {'temperature':100,'pressure':None}, {'temperature':float('nan'),'pressure':0}):
            with self.assertRaises(ExchangeError):law.evaluate(**kwargs,**POLICY)
        with self.assertRaises(ExchangeError):law.evaluate(temperature=100,pressure=0,interpolation='vendor-default',extrapolation='clamp')
        self.assertEqual(read_laws(write_laws(library),'tdp'),library)
        self.assertEqual(raw,grid())

    def test_active_temperature_specific_heat_and_each_conductivity_axis_are_independent(self):
        raw=database({'USEANISO':1,'USEVARSPECHEAT':1,'VARSPECHEAT':'2\n100 500\n300 900',
            'USEVARCONDUCT':1,'VARCONDUCT':'2\n100 10\n300 30','KUMULT':2,
            'USEVARCONDUCTY':1,'VARCONDUCTY':'2\n100 40\n300 80','KVMULT':3,'CONDUCTZ':4,'KWMULT':5})
        library=read_laws(raw,'tdp');law=material_laws(library['entries'][0])
        self.assertEqual(law['mode'],'orthotropic')
        self.assertEqual([axis.evaluate(temperature=200,**POLICY) for axis in law['conductivity']],[40,180,20])
        self.assertEqual(law['specific_heat'].evaluate(temperature=200,**POLICY),700)
        self.assertEqual(law['specific_heat'].evaluate(temperature=300,interpolation='previous',extrapolation='error'),900)
        with self.assertRaises(ExchangeError):import_document(raw,'tdp',[100,300],material_frame=frame())
        self.assertEqual(read_laws(write_laws(library),'tdp'),library)

    def test_grid_shapes_axes_modes_ranges_and_allocation_budgets_fail_closed(self):
        good=read_laws(grid(),'tdp')
        for tag,value in [('USEVARCONDUCT',1),('USEVARCONDTEMPPRES',2),('KUMULT',0),('TYPE',2),('USEANISO',.5)]:
            bad=deepcopy(good);bad['entries'][0]['scalars'][tag]=value
            with self.assertRaises(ExchangeError):write_laws(bad)
        for tag,values in [('BIVARTEMPERATURE',[300,100]),('BIVARTEMPERATURE',[0,300]),('BIVARPRESSURE',[-1,100,300]),
                           ('BIVARCONDUCTIVITY',[1,2]),('BIVARCONDUCTIVITY',[10,20,30,40,70,0])]:
            bad=deepcopy(good);bad['entries'][0]['vectors'][tag]=values
            with self.assertRaises(ExchangeError):write_laws(bad)
        for change in (lambda b:b.update(kind=[]),lambda b:b.update(profile='future'),
                lambda b:b['entries'][0]['scalars'].update(DENSITY=True),lambda b:b['entries'][0].update(name='[END]\n[START]'),
                lambda b:b['entries'][0]['vectors'].update(BIVARPRESSURE='0,1')):
            bad=deepcopy(good);change(bad)
            with self.assertRaises(ExchangeError):write_laws(bad)
        with self.assertRaises(ExchangeError):read_laws(grid(),'tdp',limits=Limits(records=10))
        with self.assertRaises(ExchangeError):read_laws(grid().replace(b'6\n10',b'99999999\n10'),'tdp')
        with self.assertRaises(ExchangeError):read_laws(database({'FUTURE':'unmapped'}),'tdp')
        with self.assertRaises(ExchangeError):PropertyLaw('temperature-table','W/(m*K)',(1,2),temperature=(200,100))

    def test_guarded_grid_edits_preserve_original_comments_modes_and_every_other_byte(self):
        raw=grid().replace(b'[END]',b'[COMMENT_MULTILINE]\nsource-marker\n[ENDCOMMENT]\n[END]')
        doc=parse_properties(raw,'tdp');change={'entry':'OWNED LAW','field':'BIVARCONDUCTIVITY','values':[11,22,33,44,77,88]}
        edited,receipt=doc.edited([change]);self.assertEqual(doc.raw,raw)
        self.assertEqual(edited,raw.replace(b'10\n20\n30\n40\n70\n80',b'11\n22\n33\n44\n77\n88'))
        self.assertTrue(receipt['reopen_verified']);self.assertEqual(read_laws(edited,'tdp')['entries'][0]['vectors'][change['field']],change['values'])
        for tag,values in [('BIVARCONDUCTIVITY',[1]),('BIVARPRESSURE',[0,100,99]),('BIVARTEMPERATURE',[0,300]),('BIVARCONDUCTIVITY',[True]*6)]:
            with self.assertRaises(ExchangeError):doc.edited([{**change,'field':tag,'values':values}])

    def test_optical_bands_transmissive_specularity_and_temperature_precedence_roundtrip(self):
        raw=database({'ALPHA':.1,'EMISS':.6,'SOLTRANS':.2,'IRTRANS':.3,'SOLSPEC':.4,'IRSPEC':.5,
            'SOLTSPEC':.7,'IRTSPEC':.8,'SOLREFRAC':1.2,'IRREFRAC':1.5,
            'USEVSA':1,'VARALPHA':'2\n0 .1\n90 .2','USEVST':1,'VARSOLT':'2\n0 .2\n90 .3',
            'USETEMPSOLABS':1,'TEMPALPHA':'2\n100 .2\n300 .6','USEWAVELENGTHDEPPROPS':1},'rco')
        library=read_laws(raw,'rco');laws=optical_laws(library['entries'][0])
        solar=laws['solar'];infrared=laws['infrared']
        self.assertEqual(solar['absorptivity'].evaluate(temperature=200,**POLICY),.4)
        self.assertEqual(solar['transmissivity'].evaluate(**POLICY),.2)
        self.assertEqual(infrared['transmissivity'].evaluate(**POLICY),.3)
        self.assertEqual(solar['transmissive_specular_fraction'].evaluate(**POLICY),.7)
        self.assertEqual(infrared['refractive_index_ratio'],1.5)
        self.assertTrue(laws['wavelength_dependent_radks'])
        self.assertEqual(read_laws(write_laws(library),'rco'),library)
        self.assertFalse(law_report(library)['native_ready'])

    def test_angle_laws_require_source_angle_coordinates_and_check_energy_at_all_knots(self):
        raw=database({'ALPHA':.1,'EMISS':.5,'USEVSA':1,'VARALPHA':'3\n0 .1\n40 .4\n80 .6',
            'USEVST':1,'VARSOLT':'2\n0 .2\n80 .4','USEVSZ':1,'VARSOLZ':'2\n0 .2\n80 .8'},'rco')
        library=read_laws(raw,'rco');laws=optical_laws(library['entries'][0])['solar']
        self.assertAlmostEqual(laws['absorptivity'].evaluate(angle=20,**POLICY),.25)
        self.assertAlmostEqual(laws['transmissive_specular_fraction'].evaluate(angle=40,**POLICY),.5)
        with self.assertRaises(ExchangeError):laws['absorptivity'].evaluate(**POLICY)
        with self.assertRaises(ExchangeError):read_laws(raw.replace(b'40 .4',b'40 .9'),'rco')
        with self.assertRaises(ExchangeError):read_laws(raw.replace(b'80 .8',b'80 1.1'),'rco')

    def test_transmissive_specularity_flags_do_not_alias_constant_refractive_indices(self):
        raw=database({'ALPHA':.2,'EMISS':.5,'SOLREFRAC':1.2,'SOLTSPEC':.3,'USEVSZ':1,'VARSOLZ':'2\n0 .2\n80 .8'},'rco')
        document=parse_properties(raw,'rco')
        with self.assertRaises(ExchangeError):document.edited([{'entry':'OWNED LAW','field':'SOLTSPEC','value':.4}])
        edited,_=document.edited([{'entry':'OWNED LAW','field':'SOLREFRAC','value':1.5}])
        self.assertEqual(edited,raw.replace(b'[SOLREFRAC]\n1.2',b'[SOLREFRAC]\n1.5'))

    def test_constant_orthotropic_material_requires_declared_frame_and_roundtrips_all_axes(self):
        raw=database({'USEANISO':1,'CONDUCT':10,'CONDUCTY':20,'CONDUCTZ':30,'KUMULT':2,'KVMULT':3,'KWMULT':4})
        with self.assertRaises(ExchangeError):import_document(raw,'tdp',[100,500])
        model,report=import_document(raw,'tdp',[100,500],material_frame=frame())
        material=next(e for e in model['entities'] if e['kind']=='material')
        self.assertEqual(material['conductivity_tensor'],[[20,0,0],[0,60,0],[0,0,120]])
        self.assertEqual(material['frame_id'],frame()['id']);self.assertEqual(report['selected_entries'],1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('subprocess.Popen',side_effect=AssertionError('vendor execution forbidden')):
                export_library(model,root/'library');reopened,files=read_library(root/'library')
            self.assertEqual(reopened['entities'],sorted(model['entities'],key=lambda e:e['id']))
            source=parse_properties(files['materials.tdp'],'tdp').entries[0]
            self.assertEqual([source.get(tag).scalar() for tag in ('CONDUCT','CONDUCTY','CONDUCTZ')],[20,60,120])
            bad=deepcopy(model);native=next(e for e in bad['entities'] if e['kind']=='material');native['conductivity_tensor'][0][1]=1;native['conductivity_tensor'][1][0]=1
            with self.assertRaises(ExchangeError):export_library(bad,root/'bad')
            bad=deepcopy(model);native=next(e for e in bad['entities'] if e['kind']=='material');native['conductivity']['value']=21
            with self.assertRaises(ExchangeError):export_library(bad,root/'bad')

    def test_orthotropic_source_export_keeps_scales_frame_and_inactive_source_bytes(self):
        raw=database({'USEANISO':1,'CONDUCT':10,'CONDUCTY':20,'CONDUCTZ':30,'KUMULT':2,'KVMULT':3,'KWMULT':4})
        model,_=import_document(raw,'tdp',[100,500],material_frame=frame());material=model['entities'][0]
        material['conductivity_tensor'][1][1]=90;material['conductivity_tensor'][2][2]=160
        package=document_package(raw,model,['OWNED LAW']);meta=json.loads(package.files['exchange/property-source-map.json']);meta['material_frames']=[frame()]
        files=dict(package.files);files['exchange/property-source-map.json']=encode(meta);manifest=package.manifest
        from hashlib import sha256
        r=next(r for r in manifest['artifacts'] if r['artifact']['path']=='exchange/property-source-map.json')
        r['artifact'].update(sha256=sha256(files[r['artifact']['path']]).hexdigest(),byte_length=len(files[r['artifact']['path']]))
        package=Package(manifest,files)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);receipt=export_document_package(package,root/'edited')
            self.assertTrue(receipt['canonical_roundtrip_verified'])
            self.assertEqual((root/'edited/materials (owned).tdp').read_bytes(),raw.replace(b'[CONDUCTY]\n20',b'[CONDUCTY]\n30').replace(b'[CONDUCTZ]\n30',b'[CONDUCTZ]\n40'))

    def test_law_cli_roundtrip_needs_no_backend_and_reports_counts_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'owned.tdp').write_bytes(grid())
            with patch('subprocess.Popen',side_effect=AssertionError('no vendor runtime')):
                for args in (['td-read-property-laws',str(root),'owned.tdp',str(root/'laws'),'--kind','tdp'],
                             ['td-write-property-laws',str(root/'laws'),'property-laws.json',str(root/'source')]):
                    out=io.StringIO()
                    with patch('sys.argv',['fcst',*args]),patch('sys.stdout',out):self.assertEqual(main(),0)
                    report=json.loads(out.getvalue());self.assertFalse(report['vendor_runtime_required']);self.assertFalse(report['qualified'])
                    self.assertNotIn('OWNED LAW',out.getvalue());self.assertNotIn(str(root),out.getvalue())
            self.assertEqual(read_laws((root/'source/materials.tdp').read_bytes(),'tdp'),read_laws(grid(),'tdp'))
            self.assertEqual((root/'owned.tdp').read_bytes(),grid())
            with self.assertRaises(ExchangeError):export_laws(read_laws(grid(),'tdp'),root/'source')
            with self.assertRaises(ExchangeError):export_laws(read_laws(grid(),'tdp'),root/'missing'/'output')

    def test_malformed_law_documents_and_inactive_tables_never_execute_or_gain_readiness(self):
        raw=database({'CONDUCT':2,'VARCONDUCT':'2\n100 5\n300 7'})
        with patch('subprocess.Popen',side_effect=AssertionError('source must be inert')):
            library=read_laws(raw,'tdp');laws=material_laws(library['entries'][0])
            self.assertEqual(laws['conductivity'][0].evaluate(**POLICY),2)
            self.assertEqual(read_laws(write_laws(library),'tdp'),library)
            for bad in (raw.replace(b'100 5',b'100 __import__(x)'),raw.replace(b'100 5',b'300 5'),
                    raw.replace(b'100 5',b'100 1E-999'),raw.replace(b'2\n100 5',b'10000000\n100 5'),
                    raw.replace(b'100 5',b'100 NaN'),raw.replace(b'[END]',b'[AGGREGATE]\n[COMPONENT]\n[MATERIALNAME]\nx\n[ENDCOMPONENT]\n[ENDAGGREGATE]\n[END]')):
                with self.assertRaises(ExchangeError):read_laws(bad,'tdp')
            for number in (True,float('inf'),float('nan'),10**400,'exec(source)'):
                bad=deepcopy(library);bad['entries'][0]['scalars']['DENSITY']=number
                with self.assertRaises(ExchangeError):write_laws(bad)
        self.assertFalse(law_report(library)['qualified']);self.assertFalse(law_report(library)['native_ready'])

    def test_laminate_and_aggregate_definitions_keep_component_order_settings_and_closed_references(self):
        library=read_laws(database({'CONDUCT':10,'DENSITY':1000,'SPECHEAT':800}),'tdp')
        for mode in (1,2):
            row={'name':'OWNED COMPOSITE','scalars':{'TYPE':mode},'tables':{},'vectors':{},
                'aggregate':{'scalars':{'WEIGHTTYPE':0,'AGGREGATE_OVERRIDE_CONDUCTIVITY':1},'components':[
                    {'material':'OWNED LAW','scalars':{'THICKNESS':.001,'ORIENTATIONANGLE':30,'MASSFRACTION':.4,'KXP':.3}},
                    {'material':'OWNED LAW','scalars':{'THICKNESS':.002,'ORIENTATIONANGLE':-45,'MASSFRACTION':.6,'KXP':.7}}]}}
            library['entries'].append(row)
            raw=write_laws(library);self.assertEqual(read_laws(raw,'tdp'),library)
            self.assertEqual(law_report(library)['composite_entries'],len(library['entries'])-1)
            with self.assertRaises(ExchangeError):material_laws(row)
            with self.assertRaises(ExchangeError):import_document(raw,'tdp',[100,500])
            for mutate in (lambda r:r['aggregate']['components'][0].update(material='missing'),
                    lambda r:r['aggregate']['components'][0].update(material='OWNED COMPOSITE'),
                    lambda r:r['aggregate']['components'][0]['scalars'].update(KXP=1.1),
                    lambda r:r['aggregate']['scalars'].update(WEIGHTTYPE=2)):
                bad=deepcopy(library);mutate(bad['entries'][-1])
                with self.assertRaises(ExchangeError):write_laws(bad)
            library['entries'][-1]['name']+=' '+str(mode)

    def test_component_source_edits_preserve_comments_repeated_materials_and_unselected_layers(self):
        raw=database({'CONDUCT':10})+b'[START]\n[NAME]\nOWNED LAYERS\n[TYPE]\n1\n[AGGREGATE]\n[COMPONENT]\n[MATERIALNAME]\nOWNED LAW\n[THICKNESS]\n 0.001 \n[ORIENTATIONANGLE]\n30\n[ENDCOMPONENT]\n[COMPONENT]\n[MATERIALNAME]\nOWNED LAW\n[THICKNESS]\n0.002\n[ORIENTATIONANGLE]\n-45\n[ENDCOMPONENT]\n[ENDAGGREGATE]\n[COMMENT_MULTILINE]\nkeep-marker\n[ENDCOMMENT]\n[END]\n'
        document=parse_properties(raw,'tdp');change={'entry':'OWNED LAYERS','component':1,'field':'THICKNESS','value':.004}
        edited,report=document.edited([change])
        self.assertEqual(edited,raw.replace(b'0.002',b'0.0040000000000000001'))
        self.assertEqual(document.raw,raw);self.assertTrue(report['reopen_verified']);self.assertFalse(report['native_ready'])
        for bad in ({**change,'component':2},{**change,'component':True},{**change,'value':0},{**change,'field':'MATERIALNAME','value':1}):
            with self.assertRaises(ExchangeError):document.edited([bad])
        with self.assertRaises(ExchangeError):document.edited([change,change])
        with self.assertRaises(ExchangeError):read_laws(raw.replace(b'[THICKNESS]\n0.002',b'[THICKNESS]\n0.002\n[THICKNESS]\n.003'),'tdp')
