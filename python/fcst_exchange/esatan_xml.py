# SPDX-License-Identifier: MIT OR Apache-2.0
"""Streaming inspection of the acquired ESATAN postprocessing XML family.

The large XML is a chart/result companion, not a native project descriptor.
Charts are retained as source; chart rendering and campaign semantics are held.
"""
from hashlib import sha256
import re
import xml.etree.ElementTree as ET

from .core import reject


def inspect_postprocess_xml(stream, *, max_bytes=268435456, max_elements=3000000):
    if (type(max_bytes) is not int or not 0<max_bytes<=268435456 or
            type(max_elements) is not int or not 0<max_elements<=3000000): reject('esatan_xml_limits')
    parser=ET.XMLPullParser(events=('start','end')); digest=sha256(); total=0; count=0; depth=0
    tail=b''; stack=[]; root_seen=False; series=0; points=0
    try:
        while True:
            chunk=stream.read(65536)
            if not chunk: break
            if not isinstance(chunk,bytes): reject('esatan_xml_encoding')
            total+=len(chunk)
            if total>max_bytes: reject('esatan_xml_byte_limit')
            digest.update(chunk); text=tail+chunk
            # Scan before feeding. A declaration split across chunks cannot be
            # interpreted until its closing chunk, which is inspected first.
            if b'\x00' in chunk or re.search(rb'<!\s*(?:DOCTYPE|ENTITY)',text,re.I):
                reject('esatan_xml_external_construct')
            for m in re.finditer(rb'<\?',text):
                absolute=total-len(chunk)-len(tail)+m.start()
                if absolute not in {0,3} or not text[m.start():].startswith(b'<?xml '):
                    reject('esatan_xml_external_construct')
            parser.feed(chunk)
            for event,node in parser.read_events():
                if event=='start':
                    depth+=1; count+=1
                    if depth>32 or count>max_elements or len(node.attrib)>128: reject('esatan_xml_limit')
                    if any(len(v)>16384 for v in node.attrib.values()): reject('esatan_xml_attribute_limit')
                    if not root_seen:
                        if node.tag!='postprocessdatafile': reject('esatan_xml_wrong_family')
                        root_seen=True
                    if node.tag.startswith('{http://www.w3.org/2001/XInclude}'):
                        reject('esatan_xml_external_construct')
                    if node.tag=='dataseries': series+=1
                    if node.tag=='dataseriesvalue': points+=1
                    stack.append(node)
                else:
                    stack.pop(); depth-=1
                    if stack: stack[-1].remove(node)
                    node.clear()
            tail=text[-128:]
        parser.close()
        if not root_seen or stack: reject('esatan_xml_syntax')
    except (ET.ParseError,UnicodeError,RecursionError): reject('esatan_xml_syntax')
    return {'profile':'esatan-postprocess-xml-inspection/1','source_sha256':digest.hexdigest(),
            'bytes':total,'elements':count,'series':series,'points':points,'runnable':False,'qualified':False,
            'limitations':['Postprocessing chart data is not a native project or campaign schema']}
