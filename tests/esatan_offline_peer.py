# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fresh-process conversion guard; attempts fail before any external side effect."""
import importlib.abc
import json
from pathlib import Path
import socket
import subprocess
import sys
import os

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))


class NoVendor(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if any(word in fullname.lower() for word in ('esatan','esarad','opentd','crtech','autocad')) and not fullname.startswith('fcst_'):
            raise AssertionError('vendor_import_attempt')


def denied(*args,**kwargs): raise AssertionError('external_call_attempt')


def main():
    sys.meta_path.insert(0,NoVendor())
    subprocess.Popen=denied; os.system=denied; socket.socket=denied; os.startfile=denied
    from fcst_exchange.esatan import EsatanAdapter, EsatanUnits
    from fcst_exchange.esatan_writer import export_model
    from fcst_exchange import Patch
    adapter=EsatanAdapter(EsatanUnits('degC','J/K','W/K','W','s'),source_version='2018-sp1')
    source=Path(sys.argv[1]); target=Path(sys.argv[2]); target.mkdir()
    preview=adapter.preview(source,'main.d'); preview.require_native()
    record=next(r for r in preview.sources[0].records if r.value['text']=='GL(1,2)=BASE;')
    adapter.export(preview,target/'edited',[Patch(record.path,record.start,record.end,record.digest,record.content.replace(b'BASE',b'4D0'))])
    model=adapter.preview(target/'edited','main.d').require_native()
    export_model(model,adapter.units,target/'new',source_version='2018-sp1')
    adapter.preview(target/'new','network.d').require_native()
    print(json.dumps({'status':'passed','vendor_calls':0}))


if __name__=='__main__': main()
