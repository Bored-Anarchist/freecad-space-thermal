# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private corrected-native container experiment; never TD thermal qualification."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from fcst_app.persistence import is_link
from fcst_exchange.core import ExchangeError,reject
from fcst_exchange.dwg_native import NativeRuntime
from fcst_exchange.independent_td import IndependentTdAdapter


def bounded_preview(staged):
    """Publication evidence excludes source object identities and field data."""
    report=staged.report
    thermal=report['thermal_payloads']
    counts={}
    for row in thermal['records']:
        if row['status']=='payload-decoded':counts[row['profile']]=counts.get(row['profile'],0)+1
    return {**staged.snapshot.report,'source_revision':staged.original.source_hash,
            'files':report['files'],'directories':report['directories'],
            'decoded_profile_counts':counts,'retained_thermal_objects':thermal['retained_objects'],
            'property_databases':report['property_databases']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drawing',type=Path,required=True)
    parser.add_argument('--backend',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    try:
        drawing=args.drawing.absolute();work=args.work.absolute()
        if (work.exists() or not work.parent.is_dir() or args.report.exists()
                or any(is_link(p) for p in (work,*work.parents))
                or work.resolve().is_relative_to(drawing.parent.resolve())
                or drawing.parent.resolve().is_relative_to(work.resolve())):reject('dwg_probe_new_private_tree')
        runtime=NativeRuntime.from_receipt(args.backend);adapter=IndependentTdAdapter(runtime)
        work.mkdir();staged=adapter.preview(drawing.parent,drawing.name,work/'inspect')
        result={'schema_version':1,'operation':'independent-dwg-native-research',
                'candidate':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'input':bounded_preview(staged),'roundtrip':adapter.audit_rewrite(staged,work/'roundtrip'),
                'vendor_runtime_required':False,'original_unchanged':True,'native_ready':False,'qualified':False}
        with args.report.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':'completed','qualified':False,'native_ready':False}));return 0
    except (ExchangeError,OSError,ValueError):
        print(json.dumps({'status':'blocked','code':'independent_dwg_probe_failed'}));return 1


if __name__=='__main__':raise SystemExit(main())
