# SPDX-License-Identifier: MIT OR Apache-2.0
"""CLI exchange commands; reports contain no raw imported text or host paths."""
import json
from pathlib import Path
from fcst_exchange import ReferenceAdapter, export_tree, source_package, read_results, query
from fcst_app.persistence import save_package


def parsers(commands):
    inspect = commands.add_parser("exchange-preview")
    export = commands.add_parser("exchange-export")
    package = commands.add_parser("exchange-package")
    result = commands.add_parser("exchange-result")
    for parser in (inspect,export,package,result):
        parser.add_argument("root")
        parser.add_argument("entry")
        parser.add_argument("--dialect", required=True, choices=["fcst-network/1"])
    for parser in (export,package):
        parser.add_argument("destination")
    result.add_argument("path")
    result.add_argument("time", type=float)
    result.add_argument("--discontinuity-policy", choices=["error","previous"], default="error")


def execute(args):
    staged = ReferenceAdapter().preview(args.root,args.entry)
    if args.command == "exchange-preview":
        return staged.report
    if args.command == "exchange-export":
        return export_tree(staged,args.destination)
    if args.command == "exchange-package":
        from fcst_exchange.core import reject
        if Path(args.destination).exists():
            reject("package_requires_new_target")
        package = source_package(staged)
        save_package(package,args.destination)
        return {"operation":"exchange-package", "source_revision":staged.report["source_revision"], "status":"saved"}
    from fcst_exchange.core import checked_path, Limits, reject
    with checked_path(Path(args.root),args.path).open("rb") as stream:
        raw = stream.read(Limits().file_bytes+1)
    if len(raw) > Limits().file_bytes:
        reject("file_limit")
    return query(read_results(raw,staged.require_native()),args.time,discontinuity_policy=args.discontinuity_policy)
