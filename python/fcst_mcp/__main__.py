# SPDX-License-Identifier: MIT OR Apache-2.0
"""Explicit local stdio entry point; no HTTP or arbitrary execution endpoint."""
import argparse
import sys
import sqlite3
from fcst_app.persistence import PersistenceError
from fcst_app.store import ProjectStore
from .gateway import Gateway
from .server import serve
from .service import configuration, wake, run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','service'])
    parser.add_argument('--config',required=True)
    args=parser.parse_args()
    try:
        if args.command=='service':run(args.config)
        else:
            _,database,policy,backend=configuration(args.config)
            with ProjectStore(database) as store:
                serve(Gateway(store,policy,backend=backend,wake=lambda:wake(args.config)),sys.stdin.buffer,sys.stdout.buffer)
    except (ValueError,OSError,TypeError,sqlite3.Error):
        print('FCST MCP configuration or storage unavailable',file=sys.stderr)
        return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
