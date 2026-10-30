# SPDX-License-Identifier: MIT OR Apache-2.0
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import acquire_esatan_xml
from fcst_exchange import ExchangeError
from fcst_exchange.esatan_xml import inspect_postprocess_xml

XML=(b'<?xml version="1.0" encoding="UTF-8"?><postprocessdatafile version="1">'
     b'<dataseries><dataseriesvalues><dataseriesvalue domain="0" range="20"/>'
     b'<dataseriesvalue domain="1" range="21"/></dataseriesvalues></dataseries></postprocessdatafile>')


class EsatanXmlTests(unittest.TestCase):
    def test_streaming_postprocessing_family_is_not_mistaken_for_a_native_project(self):
        result=inspect_postprocess_xml(io.BytesIO(XML))
        self.assertEqual(result['points'],2); self.assertEqual(result['series'],1)
        self.assertEqual(result['source_sha256'],sha256(XML).hexdigest())
        self.assertFalse(result['runnable']); self.assertFalse(result['qualified'])
        self.assertNotIn('20',json.dumps(result['limitations']))
        with self.assertRaisesRegex(ExchangeError,'wrong_family'): inspect_postprocess_xml(io.BytesIO(b'<project/>'))

    def test_streaming_xml_rejects_dtd_entities_includes_and_processing_instructions(self):
        for raw in (b'<!DOCTYPE postprocessdatafile [<!ENTITY x "bad">]>'+XML,
                    XML.replace(b'<dataseries>',b'<dataseries><?execute bad?>'),
                    b'<postprocessdatafile xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="bad"/></postprocessdatafile>',
                    XML.replace(b'20',b'\x00')):
            with self.assertRaises(ExchangeError): inspect_postprocess_xml(io.BytesIO(raw))

    def test_streaming_xml_detects_entity_declarations_across_read_boundaries(self):
        for suffix in (b'<!DOC',b'<!ENT'):
            prefix=b' '*(65536-len(suffix))+suffix
            raw=prefix+(b'TYPE postprocessdatafile>' if suffix==b'<!DOC' else b'ITY x "bad">')+XML
            with self.assertRaises(ExchangeError): inspect_postprocess_xml(io.BytesIO(raw))

    def test_streaming_xml_byte_element_depth_and_attribute_limits_are_enforced(self):
        with self.assertRaises(ExchangeError): inspect_postprocess_xml(io.BytesIO(XML),max_bytes=10)
        with self.assertRaises(ExchangeError): inspect_postprocess_xml(io.BytesIO(XML),max_elements=2)
        with self.assertRaises(ExchangeError): inspect_postprocess_xml(io.BytesIO(b'<postprocessdatafile>'+b'<x>'*40+b'</x>'*40+b'</postprocessdatafile>'))
        with self.assertRaises(ExchangeError): inspect_postprocess_xml(io.BytesIO(b'<postprocessdatafile key="'+b'x'*20000+b'"/>'))
        with self.assertRaises(ExchangeError): inspect_postprocess_xml(io.BytesIO(XML[:-10]))

    def test_mirror_acquisition_verifies_pointer_length_hash_and_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'ci').mkdir(); (root/'baseline').mkdir()
            pointer=('version https://git-lfs.github.com/spec/v1\noid sha256:'+sha256(XML).hexdigest()+'\nsize '+str(len(XML))+'\n').encode()
            (root/'baseline/model.xml').write_bytes(pointer)
            profile={'pointer_path':'baseline/model.xml','pointer_sha256':sha256(pointer).hexdigest(),
                     'payload_sha256':sha256(XML).hexdigest(),'payload_bytes':len(XML),'source_url':'https://example.invalid/model.xml'}
            (root/'ci/esatan-acquisition.json').write_text(json.dumps(profile))
            with patch.object(acquire_esatan_xml,'ROOT',root),patch.object(acquire_esatan_xml.urllib.request,'urlopen',return_value=io.BytesIO(XML)):
                result=acquire_esatan_xml.acquire(root/'resolved.xml')
            self.assertEqual(result['status'],'acquired'); self.assertEqual((root/'resolved.xml').read_bytes(),XML)
            self.assertEqual((root/'baseline/model.xml').read_bytes(),pointer)
            for payload in (XML+b'excess',XML.replace(b'20',b'99')):
                with patch.object(acquire_esatan_xml,'ROOT',root),patch.object(acquire_esatan_xml.urllib.request,'urlopen',return_value=io.BytesIO(payload)):
                    with self.assertRaises(ExchangeError): acquire_esatan_xml.acquire(root/'bad.xml')
                self.assertFalse((root/'bad.xml').exists())
                self.assertFalse(list(root.glob('.esatan-acquire-*')))

    def test_raw_source_xml_and_planted_private_data_cannot_be_publication_assets(self):
        from fcst_tools.privacy import POLICY_PATH,Scanner
        policy=json.loads(POLICY_PATH.read_bytes())
        scanner=Scanner(policy); scanner.scan('source.xml',XML)
        self.assertEqual(scanner.report()['status'],'failed')
        # A bounded report is inspected as bytes too; its extension is no bypass.
        planted='analyst'+'@'+'example.invalid'
        scanner=Scanner(policy); scanner.scan('esatan.json',json.dumps({'contact':planted}).encode())
        report=scanner.report(); self.assertEqual(report['status'],'failed')
        self.assertNotIn(planted,json.dumps(report))


if __name__=='__main__': unittest.main()
