# SPDX-License-Identifier: MIT OR Apache-2.0
"""Local research probe: independent DWG container read/write, never TD fidelity.

No downloads, vendor discovery, registry access or vendor assembly loading.
All drawing/JSON derivatives stay in a fresh private work tree. No export is
promoted to a user project. Converter stdout/stderr is bounded and discarded.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from fcst_app.persistence import is_link
from fcst_exchange.core import Limits, ExchangeError, reject
from fcst_exchange.dwg_container import audit, compare
from fcst_exchange.tools import Tool, ToolRunner, Authorization


def probe(drawing, tools, work):
    profile = json.loads((ROOT/'ci/independent-dwg-probe.json').read_bytes())
    drawing, tools, work = (Path(p).absolute() for p in (drawing, tools, work))
    for path in (drawing, tools, work):
        if any(is_link(p) for p in (path, *path.parents)):
            reject('linked_probe_path')
    if not drawing.is_file() or drawing.suffix.lower() != '.dwg':
        reject('dwg_probe_source')
    if (work.exists() or not work.parent.is_dir() or not tools.is_dir()
            or work.resolve().is_relative_to(drawing.parent.resolve())
            or work.resolve().is_relative_to(tools.resolve())):
        reject('dwg_probe_new_private_tree')
    with drawing.open('rb') as stream:
        raw = stream.read(67108865)
    if len(raw) > 67108864 or raw[:6] != b'AC1032':
        reject('dwg_probe_size_or_version')
    if {p.name for p in tools.glob('*.dll')} != {n for n in profile['files'] if n.endswith('.dll')}:
        reject('dwg_probe_runtime_assets')
    assets = tuple((tools/n, digest) for n, digest in profile['files'].items() if n.endswith('.dll'))
    operations = (
        ('read', 'dwgread.exe', ('-O','JSON','-o','decoded.json','source.dwg'), 'source.dwg','decoded.json'),
        ('write', 'dwgwrite.exe', ('--as','r2018','-o','rewritten.dwg','decoded.json'), 'decoded.json','rewritten.dwg'),
        ('reopen', 'dwgread.exe', ('-O','JSON','-o','decoded.json','source.dwg'), 'source.dwg','decoded.json'))
    definitions = [Tool('libredwg-research-'+name, tools/exe, profile['files'][exe], args,
                        assets=assets, timeout_seconds=180, memory_mb=4096, output_bytes=1048576)
                   for name, exe, args, _, _ in operations]
    runner = ToolRunner(definitions)
    for definition in definitions:
        runner.probe(definition.profile)
    work.mkdir(); reports = []; decoded = None; current = raw
    limits = Limits(files=16, file_bytes=67108864, total_bytes=268435456)
    for definition, (name, _, _, source, target) in zip(definitions, operations):
        result, receipt = runner.run(definition.profile, work/name, {source: current}, (target,),
                                    Authorization(definition.profile, 'convert', 'independent-dwg-research-v1'), limits=limits)
        current = result[target]; reports.append(receipt)
        if name == 'read':
            decoded = current
        elif name == 'write' and current[:6] != raw[:6]:
            reject('dwg_probe_version_changed')
    if sha256(drawing.read_bytes()).digest() != sha256(raw).digest():
        reject('dwg_probe_original_changed')
    try:
        decoded_report = audit(decoded)
        roundtrip_report = compare(decoded, current)
    except ExchangeError as error:
        decoded_report = {'status':'blocked', 'code':error.code}
        roundtrip_report = {'status':'blocked', 'code':error.code,
                            'decoded_inventory_preserved':False, 'native_ready':False, 'qualified':False}
    result = {'schema_version':1, 'operation':'independent-dwg-research',
              'backend':profile['backend'], 'version':profile['version'],
              'vendor_runtime_required':False, 'original_unchanged':True,
              'input':decoded_report, 'roundtrip':roundtrip_report,
              'tool_receipts':reports, 'native_ready':False, 'qualified':False,
              'scope':'Drawing container experiment only; no thermal codec or project dependency closure',
              'base_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'input_sha256':{name:sha256((ROOT/name).read_bytes()).hexdigest() for name in
                              ('tools/probe_independent_dwg.py','python/fcst_exchange/dwg_container.py',
                               'python/fcst_exchange/tools.py','python/fcst_app/process_limits.py','ci/independent-dwg-probe.json')}}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drawing', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.report.exists():
            reject('dwg_probe_report_exists')
        result = probe(args.drawing, args.tools, args.work)
        # The explicit report is a local summary; raw drawings/JSON stay private.
        with args.report.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, indent=2)+'\n')
        print(json.dumps({k: result[k] for k in ('operation','vendor_runtime_required','original_unchanged','native_ready','qualified','roundtrip')}))
        return 0
    except ExchangeError as error:
        print(json.dumps({'status':'failed','code':error.code})); return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({'status':'failed','code':'dwg_probe_unavailable'})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
