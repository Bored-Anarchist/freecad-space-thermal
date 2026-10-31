# SPDX-License-Identifier: MIT OR Apache-2.0
"""Install the source workbench into an explicitly selected FreeCAD Mod directory."""
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def install(destination):
    destination=Path(destination).resolve()/'FCST'
    if destination.exists():
        raise ValueError('workbench_destination_exists')
    destination.mkdir(parents=True)
    for source in (ROOT/'freecad/FCST').glob('*.py'):
        shutil.copyfile(source,destination/source.name)
    # FreeCAD adds each Mod directory to sys.path; keep the adapter install offline.
    for name in ('fcst_host','fcst_app','fcst_contracts'):
        shutil.copytree(ROOT/'python'/name,destination/name,
                        ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo'))
    shutil.copyfile(ROOT/'LICENSE',destination/'LICENSE')
    shutil.copytree(ROOT/'LICENSES',destination/'LICENSES')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mod-directory',type=Path,required=True)
    args=parser.parse_args()
    install(args.mod_directory)
    print('FCST workbench installed; native worker selected separately in Solve.')
