# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned analytic filer envelopes. No acquired thermal payload bytes."""
import json
from fcst_exchange.dwg_native import snapshot

PATCH='a'*64
NAMES={1:('RCNODE','RcNode'),2:('RCCONDUCTOR','RcConductor'),3:('RCHEATLOAD','RcHeatLoad')}


def envelope(payload,handle=101,targets=(101,102,103,104)):
    # The common prefix is deliberately omitted from this synthetic envelope.
    bits=''.join(f'{byte:08b}' for byte in payload.data)[:payload.data_bits]
    bits+=''.join(f'{byte:08b}' for byte in payload.strings)[:payload.string_bits]
    if payload.string_bits:bits+=''.join(f'{byte:08b}' for byte in payload.string_bits.to_bytes(2,'little'))
    bits+=str(int(bool(payload.string_bits)));data_bits=len(bits)
    bits+='01010000' # common null layer
    for index in payload.references:
        target=targets[index-1] if index else 0;size=(target.bit_length()+7)//8
        bits+='0100'+f'{size:04b}'+(''.join(f'{v:08b}' for v in target.to_bytes(size,'big')) if size else '')
    bits+='1'*(-len(bits)%8)
    raw=int(bits,2).to_bytes(len(bits)//8,'big')
    row=dict(handle=handle,type=499+payload.kind,kind='UNKNOWN_ENT',bits=len(bits),data=raw.hex(),rest_bits=0,rest='',
             object_bits=len(bits),common_bits=0,data_bits=data_bits,string_bits=payload.string_bits,handle_bits=len(bits)-data_bits)
    common={'handle':[0,1,handle],'entmode':2,'is_xdic_missing':1,'layer':[5,0,0],
            'unknown_bits':raw.hex(),'num_unknown_bits':len(bits),'type':row['type']}
    return row,common


def drawing(records):
    rows=[];standards=[]
    for index,record in enumerate(records):
        row,standard=envelope(record,101+index);rows.append(row);standards.append(standard)
    classes=[dict(number=499+kind,proxyflag=0,appname='FCST owned fixture',cppname=cpp,dxfname=dxf,is_zombie=0,
                  item_class_id=498,num_instances=sum(p.kind==kind for p in records),dwg_version=21,
                  maint_version=0,unknown_1=0,unknown_2=0) for kind,(dxf,cpp) in NAMES.items()]
    native={'protocol':'fcst-dwg-native/2','patch_sha256':PATCH,'version':'AC1032','opaque_encoding':'msb-first-final-byte/1',
            'read_errors':4,'classes':classes,'objects':rows,'opaque_sections':[]}
    standard={'FILEHEADER':{'version':'AC1032'},'HEADER':{'INSUNITS':6},'CLASSES':classes,'OBJECTS':standards}
    return snapshot(json.dumps(native).encode(),json.dumps(standard).encode(),PATCH)
