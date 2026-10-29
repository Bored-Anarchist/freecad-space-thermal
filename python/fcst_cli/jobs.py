# SPDX-License-Identifier: MIT OR Apache-2.0
"""Local trusted CLI adapter for durable jobs; no credentials or commands in models."""
from pathlib import Path
from fcst_app.jobs import JobStore, Scheduler, native_backend
from fcst_app.store import ProjectStore

ACTOR = "local-client"
SCOPES = {"job.submit","job.query","job.cancel","result.query","result.attach"}


def parsers(commands):
    for name in ("job-submit","job-status","job-cancel","job-run","job-retry","job-result"):
        parser = commands.add_parser(name)
        parser.add_argument("database")
        if name in {"job-submit","job-run"}:
            parser.add_argument("--worker",required=True)
        if name == "job-submit":
            parser.add_argument("--case",required=True)
            parser.add_argument("--key",required=True)
            parser.add_argument("--expected-revision",type=int,required=True)
        if name in {"job-status","job-cancel","job-retry","job-result"}:
            parser.add_argument("--job",required=True)
        if name == "job-retry":
            parser.add_argument("--key",required=True)
            parser.add_argument("--resume",action="store_true")
        if name == "job-result":
            parser.add_argument("--historical",action="store_true")
        if name == "job-status":
            parser.add_argument("--offset",type=int,default=0)
            parser.add_argument("--limit",type=int,default=64)
        if name == "job-run":
            parser.add_argument("--root")


def execute(args):
    with ProjectStore(args.database) as project:
        jobs = JobStore(project)
        if args.command == "job-submit":
            backend = native_backend(args.worker)
            return jobs.submit(ACTOR,SCOPES,args.key,args.case,expected_revision=args.expected_revision,execution=backend["execution"])
        if args.command == "job-status":
            return jobs.query(ACTOR,SCOPES,args.job,offset=args.offset,limit=args.limit)
        if args.command == "job-cancel":
            return jobs.cancel(ACTOR,SCOPES,args.job)
        if args.command == "job-retry":
            return jobs.retry(ACTOR,SCOPES,args.job,args.key,resume=args.resume)
        if args.command == "job-result":
            return jobs.result(ACTOR,SCOPES,args.job,historical=args.historical)
        backend = native_backend(args.worker)
        root = args.root or Path(args.database).resolve().parent / "job-artifacts"
        with Scheduler(jobs,root,{"native":backend}) as scheduler:
            return scheduler.run_next() or {"state":"idle"}
