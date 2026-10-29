# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned protocol vectors; these do not model proprietary thermal classes."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fcst_exchange import ExchangeError
from fcst_exchange.dwg_native import NativeRuntime,snapshot,compare
from fcst_exchange.dwg_container import DwgAuditLimits
from fcst_exchange.independent_td import IndependentTdAdapter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from dwg_build_support import apply_patch,safe_name,prepare_source

PATCH='a'*64


def packet():
    return {'protocol':'fcst-dwg-native/1','patch_sha256':PATCH,'version':'AC1032','read_errors':4,
            'classes':[dict(number=500,proxyflag=0,appname='owned',cppname='FcstOwnedFixture',
                            dxfname='OWNED',is_zombie=0,item_class_id=499,num_instances=1,
                            dwg_version=0,maint_version=0,unknown_1=0,unknown_2=0)],
            'objects':[dict(handle=1,type=500,kind='UNKNOWN_OBJ',bits=9,data='aa80',rest_bits=1,rest='80')],
            'opaque_sections':[dict(name='AcDsPrototype_1b',byte_length=2,data='0102')]}


def standard(first=1):
    return ('{"FILEHEADER":{"version":"AC1032"},"HEADER":{"INSUNITS":6},'
            '"CLASSES":[{"number":500}],"OBJECTS":[{"handle":[0,1,1],"index":0,"size":20,"bitsize":100,'
            '"type":500,"_subclass":"A","value":'+str(first)+',"_subclass":"B","value":2}]}').encode()


def snap(data=None,raw=None):
    return snapshot(json.dumps(data or packet()).encode(),raw or standard(),PATCH)


class NativeDwgTests(unittest.TestCase):
    def test_ordered_duplicate_occurrences_are_preserved_and_compared(self):
        a=snap();b=snap(raw=standard(9))
        self.assertTrue(compare(a,a)['structural_roundtrip_verified'])
        self.assertFalse(compare(a,b)['standard_fields_preserved'])
        self.assertFalse(a.report['native_ready']);self.assertFalse(a.report['qualified'])
        self.assertEqual(a.report['thermal_mapping'],'unmapped')

    def test_full_partial_bytes_sections_classes_and_warning_bits_are_checked(self):
        a=snap()
        for part,key,value in [('objects','data','aa'),('objects','rest',''),('opaque_sections','data','01')]:
            b=packet();b[part][0][key]=value
            with self.assertRaisesRegex(ExchangeError,'payload_length'):snap(b)
        for part,key,value in [('objects','data','ab80'),('objects','rest','00'),
                               ('opaque_sections','data','0103'),('classes','dwg_version',1)]:
            b=packet();b[part][0][key]=value
            self.assertFalse(compare(a,snap(b))['native_records_preserved'])
        b=packet();b['read_errors']=0
        self.assertFalse(compare(a,snap(b))['structural_roundtrip_verified'])

    def test_protocol_inventory_limits_and_private_errors_fail_closed(self):
        for field,value in [('patch_sha256','b'*64),('version','AC1027'),('read_errors',True)]:
            b=packet();b[field]=value
            with self.assertRaises(ExchangeError):snap(b)
        for field in ('classes','objects'):
            b=packet();b[field].append(deepcopy(b[field][0]))
            with self.assertRaises(ExchangeError):snap(b)
        for limits in (DwgAuditLimits(bytes=1),DwgAuditLimits(values=3),DwgAuditLimits(depth=1)):
            with self.assertRaises(ExchangeError):snapshot(json.dumps(packet()).encode(),standard(),PATCH,limits=limits)
        for raw in (b'{"private-marker":1,"private-marker":2}',b'{"x":NaN}',b'\xff'):
            with self.assertRaises(ExchangeError) as error:snapshot(raw,standard(),PATCH)
            self.assertNotIn('private-marker',str(error.exception))
        self.assertNotIn('owned',json.dumps(snap().report))

    def test_container_preview_copies_entire_source_tree_and_blocks_thermal_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'project';source.mkdir()
            (source/'main.dwg').write_bytes(b'AC1032-owned')
            (source/'extra.bin').write_bytes(b'\x00\xff-preserved');(source/'empty').mkdir()
            runtime=NativeRuntime(root/'backend.exe','c'*64,PATCH)
            adapter=IndependentTdAdapter(runtime)
            with patch.object(NativeRuntime,'run',return_value=(snap(),None,{})):
                preview=adapter.preview(source,'main.dwg',root/'work')
            self.assertFalse(preview.report['operations']['thermal-native-reconstruction'])
            with self.assertRaisesRegex(ExchangeError,'semantics_unmapped'):preview.require_native()
            with self.assertRaisesRegex(ExchangeError,'semantics_unmapped'):adapter.export_source(preview,root/'edited',[{}])
            result=adapter.export_source(preview,root/'export')
            self.assertTrue(result['exact_source_bytes_preserved']);self.assertFalse(result['qualified'])
            self.assertEqual((root/'export/extra.bin').read_bytes(),b'\x00\xff-preserved')
            self.assertTrue((root/'export/empty').is_dir())
            (source/'extra.bin').write_bytes(b'changed')
            with self.assertRaises(ExchangeError):adapter.export_source(preview,root/'stale')
            self.assertFalse((root/'stale').exists())

    def test_source_cannot_supply_backend_or_execution_work_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'project';source.mkdir();(source/'main.dwg').write_bytes(b'AC1032')
            for executable,work in ((source/'backend.exe',root/'work'),(root/'backend.exe',source/'work')):
                with patch.object(NativeRuntime,'run') as run:
                    with self.assertRaisesRegex(ExchangeError,'overlap'):
                        IndependentTdAdapter(NativeRuntime(executable,'c'*64,PATCH)).preview(source,'main.dwg',work)
                    run.assert_not_called()
            with self.assertRaisesRegex(ExchangeError,'operation'):
                NativeRuntime(root/'backend.exe','c'*64,PATCH).run('arbitrary',b'',root/'work')

    def test_source_patch_requires_exact_preimage_postimage_and_safe_paths(self):
        before=b'a\nb\n';after=b'a\nc\n'
        images={'file.c':{'before':sha256(before).hexdigest(),'after':sha256(after).hexdigest()}}
        raw=b'--- a/file.c\n+++ b/file.c\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'file.c';path.write_bytes(before)
            apply_patch(root,raw,images);self.assertEqual(path.read_bytes(),after)
            with self.assertRaisesRegex(ValueError,'preimage'):apply_patch(root,raw,images)
            path.write_bytes(before)
            with self.assertRaisesRegex(ValueError,'postimage'):apply_patch(root,raw.replace(b'+c',b'+d'),images)
            self.assertEqual(path.read_bytes(),before)
        for name in ('../file','C:/file','a\\b','/root','a/./b','CON.txt','a/trailing.'):
            with self.assertRaises(ValueError):safe_name(name)

    def test_cached_source_modification_and_extra_files_are_rejected_before_build(self):
        import io,tarfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'source.tar';patchfile=root/'empty.patch';patchfile.write_bytes(b'')
            with tarfile.open(archive,'w') as stream:
                info=tarfile.TarInfo('libredwg-0.14/owned.c');info.size=5;stream.addfile(info,io.BytesIO(b'owned'))
            target=root/'source';original=prepare_source(archive,target,patchfile,{})
            self.assertEqual(prepare_source(archive,target,patchfile,{}),original)
            (target/'extra.c').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'cached_source_changed'):prepare_source(archive,target,patchfile,{})
            (target/'extra.c').unlink();(target/'owned.c').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'cached_source_changed'):prepare_source(archive,target,patchfile,{})

