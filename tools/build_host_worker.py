# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build only the candidate's native worker for early isolated GUI acceptance."""
from profile_support import ROOT, cmake_tools, revision, run


def main():
    output=ROOT/'.local/host-worker';output.mkdir(parents=True,exist_ok=True)
    cmake,_=cmake_tools()
    run([cmake,'--preset','windows-release','-DFCST_SOURCE_REVISION='+revision()],ROOT,output/'configure.log',timeout=180)
    run([cmake,'--build','--preset','windows-release','--target','fcst-worker','--parallel','2'],ROOT,output/'build.log',timeout=600)
    print('Candidate worker for isolated GUI acceptance: built')


if __name__=='__main__':
    try:main()
    except Exception:
        print('Host worker build failed; raw diagnostics retained locally')
        raise SystemExit(1)
