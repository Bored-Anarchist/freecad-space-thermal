# SPDX-License-Identifier: MIT OR Apache-2.0
import argparse
import json
from fcst_app import capabilities


def main() -> int:
    parser = argparse.ArgumentParser(description="FCST application and portable project tools")
    parser.add_argument("--capabilities", action="store_true")
    commands = parser.add_subparsers(dest="command")
    from .jobs import parsers as job_parsers
    job_parsers(commands)
    from .exchange import parsers as exchange_parsers
    exchange_parsers(commands)
    from .td import parsers as td_parsers
    td_parsers(commands)
    inspect = commands.add_parser("project-inspect")
    inspect.add_argument("path")
    inspect.add_argument("--previous", action="store_true")
    migrate = commands.add_parser("project-migrate")
    migrate.add_argument("source")
    migrate.add_argument("destination")
    recover = commands.add_parser("project-recover")
    recover.add_argument("source")
    recover.add_argument("destination")
    recover.add_argument("--previous", action="store_true")
    args = parser.parse_args()
    if args.capabilities and args.command:
        parser.error("Choose a command or --capabilities")
    if args.capabilities:
        result = capabilities()
    elif args.command:
        from fcst_contracts import ContractError
        from fcst_exchange import ExchangeError
        from pathlib import Path
        from fcst_app.persistence import PersistenceError, recover_package, migrate_project, semantic_hash, save_package
        try:
            if args.command=='td-probe' or args.command.startswith('sinda-'):
                from .td import execute
                result=execute(args)
            elif args.command.startswith("exchange-"):
                from .exchange import execute
                result = execute(args)
            elif args.command.startswith("job-"):
                from .jobs import execute
                result = execute(args)
            elif args.command == "project-inspect":
                package = recover_package(args.path, previous=args.previous)
                result = {"project_id": package.model["project_id"], "revision": package.model["revision"],
                          "semantic_hash": semantic_hash(package.model), "artifacts": len(package.manifest["artifacts"])}
            elif args.command == "project-migrate":
                result = migrate_project(args.source, args.destination)
            else:
                if Path(args.destination).exists() or Path(args.source).resolve() == Path(args.destination).resolve():
                    raise PersistenceError("recovery_requires_new_target")
                result = save_package(recover_package(args.source, previous=args.previous), args.destination)
        except (ContractError, PersistenceError, ExchangeError) as error:
            print(json.dumps({"code": str(error)}))
            return 2
        except OSError:
            print(json.dumps({"code": "storage_unavailable"}))
            return 2
    else:
        parser.error("Choose a command or --capabilities")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
