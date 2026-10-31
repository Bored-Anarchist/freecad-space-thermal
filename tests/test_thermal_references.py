# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from fcst_tools.thermal_references import assess, expected_comparisons, validate_run, compare, analytic, analytic_error

ROOT=Path(__file__).resolve().parents[1]


class ThermalReferenceTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((ROOT/"ci/thermal-reference-v1.json").read_bytes())
        self.candidate="a"*40

    def report(self):
        p=self.policy;runs=[]
        keys=[(c,b,l) for c in p["cases"] for b in p["required_backends"] for l in ("coarse","fine")]+[(c,"native","native") for c in p["cases"]]+[(c,"pycanha_core",l) for c in p["pycanha"]["required_cases"] for l in ("coarse","fine")]
        for c,b,l in keys:runs.append(dict(case=c,backend=b,level=l,execution_mode="fcst_native" if b=="native" else "reference_external",version="owned" if b=="native" else p["pycanha"]["version"] if b=="pycanha_core" else p["required_backends"][b],result_sha256=sha256((c+b+l).encode()).hexdigest()))
        source=next(x for x in json.loads((ROOT/"ci/probe-sources.json").read_bytes())["sources"] if x["id"]=="sundials")
        return dict(schema_version=1,candidate=self.candidate,input_sha256={},profile=p["profile"],scope="engine_numerical_qualification",vendor_compatibility_qualified=False,q1_qualified=False,status="passed",runs=runs,comparisons=[dict(id=k,status="passed",limits=v,maximum_errors={f:0 for f in v}) for k,v in expected_comparisons(p).items()],provenance=dict(native_subject_sha256="1"*64,scipy_runtime_sha256="2"*64,pycanha_runtime_sha256="3"*64,ida_source=dict(archive_sha256=source["sha256"],revision=source["revision"],license_sha256=source["license_sha256"],runtime_sha256={"fcst-ida-reference.exe":"4"*64})),pycanha_excluded_cases=p["pycanha"]["excluded_cases"])

    def test_gate_rejects_missing_failed_stale_or_substituted_reference_evidence(self):
        report=self.report();self.assertTrue(assess(report,self.policy,{},self.candidate))
        for change in ("missing-case","duplicate","failed","nan","limit","version","mode","replay","candidate","inputs","source","pycanha-missing","vendor","q1"):
            r=deepcopy(report)
            if change=="missing-case":r["comparisons"].pop()
            if change=="duplicate":r["comparisons"][-1]=r["comparisons"][0]
            if change=="failed":r["comparisons"][0]["status"]="failed"
            if change=="nan":r["comparisons"][0]["maximum_errors"]["temperature"]=float("nan")
            if change=="limit":r["comparisons"][0]["limits"]["temperature"]=100
            if change=="version":r["runs"][0]["version"]="unknown"
            if change=="mode":r["runs"][0]["execution_mode"]="fcst_native"
            if change=="replay":r["runs"][1]["result_sha256"]=r["runs"][0]["result_sha256"]
            if change=="candidate":r["candidate"]="b"*40
            if change=="inputs":r["input_sha256"]={"changed":"5"*64}
            if change=="source":r["provenance"]["ida_source"]["revision"]="b"*40
            if change=="pycanha-missing":r["runs"].pop()
            if change=="vendor":r["vendor_compatibility_qualified"]=True
            if change=="q1":r["q1_qualified"]=True
            with self.subTest(change=change),self.assertRaises(ValueError):assess(r,self.policy,{},self.candidate)

    def cooling(self):
        return dict(status="passed",execution_mode="reference_external",backend="scipy_radau",version="1.15.2",case="cooling",level="fine",tolerance=1e-11,samples=[dict(time=t,temperature=analytic("cooling",t),links=[10],boundary_power=-10,storage_change=0,external_energy=0,boundary_energy=0,energy_defect=0,duty=0) for t in (0,.5,1,2,4)],events=[],steady=dict(temperature=[300,300],boundary_power=0))

    def test_raw_runs_require_exact_grids_modes_dimensions_versions_and_finite_values(self):
        value=self.cooling();validate_run(value,"scipy_radau","cooling","fine",self.policy,self.candidate)
        for change in ("mode","case","version","level","tolerance","missing-time","duplicate-time","node","nan","steady"):
            r=deepcopy(value)
            if change=="mode":r["execution_mode"]="fcst_native"
            if change=="case":r["case"]="dae"
            if change=="version":r["version"]="0"
            if change=="level":r["level"]="coarse"
            if change=="tolerance":r["tolerance"]=1e-3
            if change=="missing-time":r["samples"].pop()
            if change=="duplicate-time":r["samples"][1]=r["samples"][0]
            if change=="node":r["samples"][1]["temperature"].pop()
            if change=="nan":r["samples"][1]["external_energy"]=float("nan")
            if change=="steady":r["steady"]["temperature"][0]+=1
            with self.subTest(change=change),self.assertRaises(ValueError):validate_run(r,"scipy_radau","cooling","fine",self.policy,self.candidate)

    def test_comparison_observes_energy_flows_duty_events_and_every_requested_time(self):
        a=self.cooling()
        for field in ("temperature","links","boundary_power","storage_change","external_energy","boundary_energy","energy_defect","duty"):
            b=deepcopy(a)
            if isinstance(b["samples"][2][field],list):b["samples"][2][field][0]+=1
            else:b["samples"][2][field]+=1
            self.assertAlmostEqual(compare(a,b,"cooling")[field],1)
        b=deepcopy(a);b["samples"].pop(2)
        with self.assertRaises(ValueError):compare(a,b,"cooling")
        b=deepcopy(a);b["events"]=[dict(time=1,kind="heater",before=1,after=0)]
        with self.assertRaises(ValueError):compare(a,b,"cooling")
        a["events"]=deepcopy(b["events"]);b["events"][0]["time"]+=.1
        self.assertAlmostEqual(compare(a,b,"cooling")["event_time"],.1)
        b["events"][0]["after"]=1
        with self.assertRaises(ValueError):compare(a,b,"cooling")

    def test_independent_analytic_oracles_cover_conservation_enthalpy_and_fast_mode(self):
        self.assertEqual(analytic("dae",0),[310,305,300])
        self.assertEqual(analytic("stiff",0),[310,300,290])
        self.assertAlmostEqual(2*analytic("closed",1)[0]+3*analytic("closed",1)[1],1490)
        self.assertAlmostEqual(.01*(analytic("enthalpy",10)[0]**2-90000),50)
        self.assertEqual(analytic("schedule",4),analytic("schedule",2))
        a=self.cooling();self.assertEqual(analytic_error(a,"cooling"),0)
        a["samples"][1]["temperature"][0]+=1;self.assertAlmostEqual(analytic_error(a,"cooling"),1)


if __name__=="__main__":unittest.main()
