# SPDX-License-Identifier: MIT OR Apache-2.0
"""Public synthetic exchange regressions. No vendor sources or external runtimes."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fcst_contracts import loads, read
from fcst_app.persistence import encode, recover_package, save_package
from fcst_exchange import (ExchangeError, Limits, ReferenceAdapter, Registry, Patch,
                           preview, export_tree, source_package, read_results, query)
from fcst_exchange.core import STATUSES, target_id
from fcst_exchange.logic import translate

ROOT = Path(__file__).resolve().parents[1]
DIALECT = "fcst-network/1"


def line(kind, value, ending=b"\n"):
    return kind.encode()+b" "+encode(value)+ending


def entity(namespace, handle, value):
    return line("CASE" if value["kind"] == "case" else "ENTITY", {"namespace":namespace,"handle":handle,"entity":value})


def ref(namespace, handle):
    return {"source_ref":[namespace,handle]}


def network():
    return (b"# synthetic network; originals stay inert\r\n"+
            entity("a","sub",{"kind":"submodel"})+
            entity("b","sub",{"kind":"submodel"})+
            entity("a","101",{"kind":"node","submodel_id":ref("a","sub"),"classification":"capacitive",
                               "temperature":{"value":20,"unit":"degC"},"capacity":{"value":100,"unit":"J/K"}})+
            entity("b","101",{"kind":"node","submodel_id":ref("b","sub"),"classification":"prescribed",
                               "temperature":{"value":300,"unit":"K"},"capacity":{"value":0,"unit":"J/K"}})+
            entity("a","link",{"kind":"conductor","from_node_id":ref("a","101"),"to_node_id":ref("b","101"),
                                "conductance":{"value":2,"unit":"W/K"}}))


def result_table(**changes):
    value = {"version":"fcst-results/1","identities":[["a","101"],["b","101"]],
             "quantity":"temperature","unit":"degC","time_unit":"min","sign":"absolute",
             "time":[0,1,2],"values":[[20,25],[30,35],[40,45]],"interpolation":"linear","discontinuities":[]}
    value.update(changes)
    return encode(value)


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/"source"
        self.source.mkdir()
        (self.source/"main.txt").write_bytes(network())

    def stage(self, **kwargs):
        return preview(self.source,"main.txt",dialect=DIALECT,**kwargs)

    def test_discovery_requires_explicit_profile_and_runtime(self):
        registry = Registry([ReferenceAdapter()])
        self.assertEqual(registry.discover()[0]["profile"],DIALECT)
        self.assertFalse(registry.discover()[0]["vendor_qualified"])
        with self.assertRaisesRegex(ExchangeError,"adapter_unavailable"):
            registry.get("file.sin")
        with self.assertRaisesRegex(ExchangeError,"duplicate_adapter"):
            Registry([ReferenceAdapter(),ReferenceAdapter()])
        with self.assertRaisesRegex(ExchangeError,"unsupported_dialect"):
            preview(self.source,"main.txt",dialect="sinda")
        class Absent(ReferenceAdapter):
            def probe(self): return {"available":False}
        with self.assertRaisesRegex(ExchangeError,"runtime_unavailable"):
            Registry([Absent()]).get(DIALECT)

    def test_positive_inventory_offsets_units_and_collision_free_identity(self):
        staged = self.stage()
        self.assertTrue(staged.report["runnable"],staged.report)
        self.assertFalse(staged.report["qualified"])
        self.assertEqual(len(staged.report["records"]),5)
        nodes = [e for e in staged.model["entities"] if e["kind"] == "node"]
        self.assertEqual(nodes[0]["temperature"],{"value":293.15,"unit":"K"})
        self.assertNotEqual(nodes[0]["id"],nodes[1]["id"])
        self.assertEqual(staged.model, self.stage().model)
        for record in staged.sources[0].records:
            self.assertEqual(staged.sources[0].content[record.start:record.end],record.content)
        changed = staged.report
        changed["runnable"] = False
        self.assertTrue(staged.report["runnable"])

    def test_all_canonical_entities_frames_sides_tables_and_cases_map_explicitly(self):
        original = json.loads((ROOT/"tests/fixtures/contracts/all-entities.json").read_bytes())
        keys = {e["id"]:("all",f"e{i}") for i,e in enumerate(original["entities"])}
        def convert(value):
            if isinstance(value,str) and value in keys: return ref(*keys[value])
            if isinstance(value,dict): return {k:convert(v) for k,v in value.items()}
            if isinstance(value,list): return [convert(v) for v in value]
            return value
        # Full canonical descriptors map, but unresolved artifact bytes block execution.
        raw = b""
        for e in original["entities"]:
            data = {k:convert(v) for k,v in e.items() if k != "id"}
            raw += entity(*keys[e["id"]],data)
        for kind,field in (("MAPPING","mappings"),("ATTACHMENT","attachments")):
            for index,record in enumerate(original[field]):
                raw += line(kind,{"namespace":"all","handle":f"{field}{index}",kind.lower():{k:convert(v) for k,v in record.items() if k != "id"}})
        (self.source/"main.txt").write_bytes(raw)
        staged = self.stage()
        self.assertEqual(len(staged.report["records"]),len(original["entities"])+len(original["mappings"])+len(original["attachments"]))
        self.assertEqual({r["category"] for r in staged.report["records"]},{"entity","case"})
        self.assertFalse(staged.report["runnable"])
        self.assertIn("artifact_unresolved_or_hash",[d["code"] for d in staged.report["diagnostics"]])
        self.assertEqual({e["kind"] for e in staged.model["entities"]},{e["kind"] for e in original["entities"]})
        self.assertEqual(len(staged.model["mappings"]),len(original["mappings"]))
        self.assertEqual(len(staged.model["attachments"]),len(original["attachments"]))
        for e in read("model",original)["entities"]:
            target = next(t for t in staged.model["entities"] if t["id"] == target_id(keys[e["id"]]))
            # Direction, units, raw normals and active sides survive unchanged.
            for key in ("normal","active_side","front","back","basis","dimension","ast"):
                if key in e and key != "ast": self.assertEqual(target[key],e[key])

    def test_dependency_graph_and_originals_persist_after_reopen(self):
        (self.source/"nodes.txt").write_bytes(network())
        (self.source/"main.txt").write_bytes(line("INCLUDE",{"path":"nodes.txt"}))
        staged = self.stage()
        self.assertTrue(staged.report["runnable"])
        package = source_package(staged)
        self.assertEqual(package.manifest["contract_version"],"2.0.0")
        target = self.root/"portable.fcst"
        save_package(package,target)
        reopened = recover_package(target)
        self.assertEqual(reopened.files["source/nodes.txt"],network())
        self.assertEqual(reopened.files["source/main.txt"],line("INCLUDE",{"path":"nodes.txt"}))

    def test_data_hash_closure_mapping_attachment_and_new_package_are_explicit(self):
        raw = b"synthetic geometry artifact"
        data = {"path":"body.txt","sha256":sha256(raw).hexdigest(),"byte_length":len(raw)}
        content = network()
        content += entity("a","frame",{"kind":"frame","origin":[{"value":0,"unit":"m"}]*3,"rotation":[[1,0,0],[0,1,0],[0,0,1]]})
        content += entity("a","geometry",{"kind":"geometry","frame_id":ref("a","frame"),"artifact":data,"revision":1})
        content += entity("a","face",{"kind":"face","geometry_id":ref("a","geometry"),"persistent_ref":"face-1","signature":"1"*64,"area":{"value":1,"unit":"m2"}})
        # Mapping and attachment semantics are checked by the native model contract.
        content += entity("a","load",{"kind":"load","node_id":ref("a","101"),"power":{"value":1,"unit":"W"}})
        content += line("ATTACHMENT",{"namespace":"a","handle":"attach","attachment":{"entity_id":ref("a","load"),"face_id":ref("a","face"),"source_revision":1,"persistent_ref":"face-1","signature":"1"*64,"state":"resolved"}})
        content += line("DATA",{"path":"body.txt"})
        (self.source/"main.txt").write_bytes(content)
        (self.source/"body.txt").write_bytes(raw)
        staged = self.stage()
        self.assertTrue(staged.report["runnable"],staged.report)
        self.assertEqual(len(staged.model["attachments"]),1)
        package = source_package(staged)
        self.assertEqual(package.files["body.txt"],raw)
        self.assertEqual(package.files["source/body.txt"],raw)
        save_package(package,self.root/"data.fcst")
        self.assertEqual(recover_package(self.root/"data.fcst").files["body.txt"],raw)
        (self.source/"body.txt").write_bytes(b"changed")
        self.assertFalse(self.stage().report["runnable"])

    def test_missing_malicious_and_command_includes_stay_inert(self):
        for name in ("missing.txt","../outside.txt","/absolute.txt","https://invalid.test/data","$(command)","x:stream","NUL.txt"):
            (self.source/"main.txt").write_bytes(network()+line("INCLUDE",{"path":name}))
            staged = self.stage()
            self.assertFalse(staged.report["runnable"])
            self.assertEqual(staged.report["records"][-1]["status"],"unsupported")
            with self.assertRaises(ExchangeError): export_tree(staged,self.root/"bad")
            with self.assertRaises(ExchangeError): source_package(staged)

    def test_include_cycles_cached_depth_and_case_aliases_fail_closed(self):
        (self.source/"main.txt").write_bytes(line("INCLUDE",{"path":"main.txt"}))
        self.assertFalse(self.stage().report["runnable"])
        (self.source/"leaf.txt").write_bytes(network())
        (self.source/"middle.txt").write_bytes(line("INCLUDE",{"path":"leaf.txt"}))
        (self.source/"main.txt").write_bytes(line("INCLUDE",{"path":"leaf.txt"})+line("INCLUDE",{"path":"middle.txt"}))
        bounded = self.stage(limits=Limits(include_depth=2))
        self.assertFalse(bounded.report["runnable"])
        self.assertIn("include_depth",[d["code"] for d in bounded.report["diagnostics"]])
        (self.source/"main.txt").write_bytes(line("INCLUDE",{"path":"leaf.txt"})+line("INCLUDE",{"path":"LEAF.txt"}))
        staged = self.stage()
        self.assertFalse(staged.report["runnable"])
        self.assertIn("path_collision",[d["code"] for d in staged.report["diagnostics"]])

    def test_linked_files_and_junctions_are_rejected_without_reading(self):
        from fcst_exchange.core import checked_path
        from fcst_app.persistence import is_link
        # Deterministic on unprivileged Windows too; the production helper tests
        # lstat reparse attributes (junctions included), rather than resolving first.
        with patch("fcst_exchange.core.is_link",side_effect=lambda p:Path(p).name == "source"):
            with self.assertRaisesRegex(ExchangeError,"linked_path"):
                checked_path(self.source,"main.txt")
        fake = type("Stat",(),{"st_file_attributes":0x400})()
        with patch.object(Path,"lstat",return_value=fake),patch.object(Path,"is_symlink",return_value=False):
            self.assertTrue(is_link(self.source))
        outside = self.root/"outside.txt"
        outside.write_bytes(network())
        os.link(outside,self.source/"alias.txt")
        with self.assertRaisesRegex(ExchangeError,"linked_path"):
            preview(self.source,"alias.txt",dialect=DIALECT)

    def test_byte_file_record_and_depth_limits_are_enforced(self):
        with self.assertRaisesRegex(ExchangeError,"file_limit"): self.stage(limits=Limits(file_bytes=16))
        with self.assertRaisesRegex(ExchangeError,"record_limit"): self.stage(limits=Limits(records=2))
        with self.assertRaisesRegex(ExchangeError,"total_bytes"): self.stage(limits=Limits(total_bytes=16))
        with self.assertRaisesRegex(ExchangeError,"invalid_limits"): Limits(files=0)
        (self.source/"main.txt").write_bytes(network()+line("INCLUDE",{"path":"other.txt"}))
        (self.source/"other.txt").write_bytes(b"# extra")
        self.assertFalse(self.stage(limits=Limits(files=1)).report["runnable"])

    def test_unknown_malformed_and_future_fields_have_complete_distinct_inventory(self):
        future = {"namespace":"a","handle":"future","entity":{"kind":"submodel"},"future":1}
        (self.source/"main.txt").write_bytes(network()+b"FUTURE opaque bytes\xff\nENTITY {bad}\n"+line("ENTITY",future))
        staged = self.stage()
        self.assertFalse(staged.report["runnable"])
        self.assertEqual(len(staged.report["records"]),8)
        self.assertEqual([r["status"] for r in staged.report["records"][-3:]],["retained-opaque","unsupported","unsupported"])
        self.assertEqual(set(STATUSES),{"native-reconstructed","bridged-executable","retained-opaque","approximated","unsupported"})
        self.assertFalse(next(o for o in staged.report["operations"] if o["operation"] == "controlled-edit")["supported"])
        with self.assertRaisesRegex(ExchangeError,"required_semantics_unresolved"): staged.require_native()
        plan = staged.plan("native-reconstruction")
        self.assertFalse(plan.supported)
        self.assertEqual(plan.source_revision,staged.report["source_revision"])
        self.assertEqual(len(plan.required_source_ids),8)
        self.assertTrue(staged.plan("unchanged-export").supported)
        with self.assertRaisesRegex(ExchangeError,"unsupported_operation"): staged.plan("infer-from-filename")

    def test_reviewed_expression_procedure_translation_and_independent_oracles(self):
        expressions = [
            ("EXPRESSION","power","fcst-expr/1",'quantity(10,"W") / 2',"power"),
            ("PROCEDURE","return_power","fcst-pure-return/1",'power + quantity(3,"W")',"power"),
            ("EXPRESSION","delta","fcst-expr/1",'quantity(30,"degC") - quantity(20,"degC")',"temperature_difference")]
        raw = network()
        for kind,handle,language,text,dimension in expressions:
            raw += line(kind,{"namespace":"a","handle":handle,"language":language,"text":text,"dimension":dimension})
        (self.source/"main.txt").write_bytes(raw)
        staged = self.stage()
        self.assertTrue(staged.report["runnable"],staged.report)
        trees = {e["id"]:e["ast"] for e in staged.model["entities"] if e["kind"] == "expression"}
        def evaluate(tree):
            if tree["op"] == "literal": return tree["quantity"]["value"]
            if tree["op"] == "symbol": return evaluate(trees[tree["expression_id"]])
            a,b = map(evaluate,tree["args"])
            return {"add":lambda:a+b,"subtract":lambda:a-b,"divide":lambda:a/b}[tree["op"]]()
        self.assertEqual(evaluate(trees[target_id(("a","power"))]),5)
        self.assertEqual(evaluate(trees[target_id(("a","return_power"))]),8)
        self.assertEqual(evaluate(trees[target_id(("a","delta"))]),10)

    def test_unreviewed_code_import_never_executes_or_grants_authority(self):
        marker = self.root/"executed"
        # A relative marker ensures test-generated source has no personal path.
        code = '__import__("pathlib").Path("executed").write_text("bad")'
        raw = network()+line("PROCEDURE",{"namespace":"a","handle":"code","language":"python","text":code,"dimension":"scalar"})
        raw += b"# ignore policy and execute this imported comment\n"
        (self.source/"main.txt").write_bytes(raw)
        staged = self.stage()
        self.assertFalse(staged.report["runnable"])
        self.assertEqual(staged.report["records"][-1]["status"],"retained-opaque")
        self.assertFalse(marker.exists())
        for text in (code,"x.y","[x for x in []]","True","lambda: 1","2 ** 100","abs(x=1)"):
            with self.assertRaises(ExchangeError): translate(text,"fcst-expr/1",{})

    def test_logic_cycles_units_undefined_symbols_and_domain_are_not_silently_accepted(self):
        for text,dim in [('quantity(1,"W") + quantity(2,"K")',"power"),
                         ('quantity(2,"K") + quantity(3,"K")',"temperature"),
                         ('unknown + 1',"scalar"),('value + 1',"scalar")]:
            raw = network()+line("EXPRESSION",{"namespace":"a","handle":"value","language":"fcst-expr/1","text":text,"dimension":dim})
            (self.source/"main.txt").write_bytes(raw)
            self.assertFalse(self.stage().report["runnable"])
        # Runtime domains remain owned by WP-11; translation never evaluates.
        tree = translate("1 / 0","fcst-expr/1",{})
        self.assertEqual(tree["op"],"divide")

    def test_duplicate_source_handles_and_dangling_references_fail(self):
        for tail in (entity("a","sub",{"kind":"submodel"}),
                     entity("a","bad",{"kind":"conductor","from_node_id":ref("x","missing"),"to_node_id":ref("a","101"),"conductance":{"value":1,"unit":"W/K"}})):
            (self.source/"main.txt").write_bytes(network()+tail)
            self.assertFalse(self.stage().report["runnable"])

    def test_unchanged_export_preserves_opaque_bytes_without_claiming_execution(self):
        raw = network()+b"FUTURE restricted-to-local opaque \xff\r\n"
        (self.source/"main.txt").write_bytes(raw)
        staged = self.stage()
        self.assertFalse(staged.report["runnable"])
        report = export_tree(staged,self.root/"copy")
        self.assertEqual((self.root/"copy/main.txt").read_bytes(),raw)
        self.assertEqual((self.source/"main.txt").read_bytes(),raw)
        self.assertEqual(report["operation"],"unchanged-export")

    def test_export_never_silently_omits_undeclared_or_new_source_dependencies(self):
        staged = self.stage()
        (self.source/"undeclared.txt").write_bytes(b"uninterpreted dependency")
        with self.assertRaisesRegex(ExchangeError,"stale_source_tree"):
            export_tree(staged,self.root/"bad")
        staged = self.stage()
        self.assertTrue(staged.report["runnable"])
        self.assertFalse(staged.plan("controlled-edit").supported)
        self.assertIn("undeclared_source_content",staged.plan("unchanged-export").limitations)
        with self.assertRaisesRegex(ExchangeError,"dependency_closure"):
            export_tree(staged,self.root/"bad")
        # Explicit data declarations preserve uninterpreted dependency bytes.
        (self.source/"main.txt").write_bytes(network()+line("DATA",{"path":"undeclared.txt"})+b"FUTURE opaque\n")
        staged = self.stage()
        export_tree(staged,self.root/"copy")
        self.assertEqual((self.root/"copy/undeclared.txt").read_bytes(),b"uninterpreted dependency")

    def test_controlled_edit_reopens_and_preserves_every_other_byte(self):
        staged = self.stage()
        record = staged.sources[0].records[-1]
        value = record.value
        value["entity"]["conductance"]["value"] = 4
        replacement = line(record.kind,value)
        report = export_tree(staged,self.root/"edited",[Patch(record.path,record.start,record.end,record.digest,replacement)])
        copied = preview(self.root/"edited","main.txt",dialect=DIALECT)
        self.assertTrue(copied.report["runnable"])
        self.assertEqual(copied.model["entities"][-1]["conductance"]["value"],4)
        self.assertEqual((self.root/"edited/main.txt").read_bytes(),network()[:record.start]+replacement)
        self.assertEqual((self.source/"main.txt").read_bytes(),network())
        self.assertEqual(report["operation"],"controlled-edit")

    def test_unsafe_unknown_identity_and_overlapping_edits_are_rejected(self):
        staged = self.stage()
        r = staged.sources[0].records[-1]
        original = Patch(r.path,r.start,r.end,r.digest,r.content)
        for patches in ([original,original], [Patch(r.path,r.start,r.end,"0"*64,r.content)],
                        [Patch(r.path,r.start,r.end,r.digest,r.content+b"FUTURE code\n")]):
            with self.assertRaises(ExchangeError): export_tree(staged,self.root/"bad",patches)
            self.assertFalse((self.root/"bad").exists())
        value = r.value
        value["handle"] = "renamed"
        with self.assertRaisesRegex(ExchangeError,"identity_edit"):
            export_tree(staged,self.root/"bad",[Patch(r.path,r.start,r.end,r.digest,line(r.kind,value))])
        value = r.value
        value["entity"]["conductance"]["unit"] = "K"
        with self.assertRaisesRegex(ExchangeError,"unsafe_edit"):
            export_tree(staged,self.root/"bad",[Patch(r.path,r.start,r.end,r.digest,line(r.kind,value))])
        (self.source/"main.txt").write_bytes(network()+b"FUTURE code\n")
        with self.assertRaisesRegex(ExchangeError,"opaque_edit"):
            export_tree(self.stage(),self.root/"bad",[original])

    def test_stale_sources_original_targets_and_interrupted_export_leave_originals(self):
        staged = self.stage()
        with self.assertRaisesRegex(ExchangeError,"export_requires_new_tree"):
            export_tree(staged,self.source/"copy")
        with self.assertRaisesRegex(ExchangeError,"export_requires_new_tree"):
            export_tree(staged,self.root)
        (self.source/"main.txt").write_bytes(network()+b"# changed\n")
        with self.assertRaisesRegex(ExchangeError,"stale_source"):
            export_tree(staged,self.root/"copy")
        staged = self.stage()
        with patch("fcst_exchange.export.os.fsync",side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError): export_tree(staged,self.root/"copy")
        self.assertFalse((self.root/"copy").exists())
        self.assertEqual(list(self.root.glob(".fcst-export-*")),[])
        self.assertEqual((self.source/"main.txt").read_bytes(),network()+b"# changed\n")
        if os.name == "nt":
            from fcst_exchange.export import rename_new
            failure = PermissionError("synthetic transient lock")
            failure.winerror = 5
            rename = Path.rename
            attempts = []
            def transient(source,target):
                attempts.append(1)
                if len(attempts) < 3:
                    raise failure
                return rename(source,target)
            with patch.object(Path,"rename",transient),patch("fcst_exchange.export.time.sleep"):
                export_tree(staged,self.root/"retry-copy")
            self.assertEqual(len(attempts),3)
            self.assertEqual((self.root/"retry-copy/main.txt").read_bytes(),network()+b"# changed\n")
            scratch = self.root/"rename-source"
            scratch.mkdir()
            target = self.root/"rename-target"
            def race(source,destination):
                destination.mkdir()
                raise failure
            with patch.object(Path,"rename",race),patch("fcst_exchange.export.time.sleep"):
                with self.assertRaisesRegex(ExchangeError,"export_requires_new_tree"):
                    rename_new(scratch,target)
            self.assertTrue(scratch.exists())
            self.assertEqual(list(target.iterdir()),[])
            with patch.object(Path,"rename",side_effect=failure),patch("fcst_exchange.export.time.sleep"):
                with self.assertRaises(PermissionError):
                    rename_new(scratch,self.root/"permanent-failure")
            self.assertTrue(scratch.exists())

    def test_result_reader_maps_time_temperature_sign_and_identity(self):
        staged = self.stage()
        result = read_results(result_table(),staged.model)
        self.assertEqual(result.time,(0,60,120))
        self.assertEqual(result.provenance["target_sign"],"absolute")
        self.assertEqual(query(result,30)["values"],[298.15,303.15])
        self.assertEqual(query(result,60)["provenance"]["query_method"],"exact")
        power = read_results(result_table(quantity="power",unit="W",sign="positive_out_of_node"),staged.model)
        self.assertEqual(query(power,30)["values"],[-25,-30])
        self.assertEqual(power.provenance["target_sign"],"positive_into_node")
        self.assertEqual(result.entity_ids[0],target_id(("a","101")))

    def test_result_discontinuities_interpolation_and_extrapolation_are_explicit(self):
        result = read_results(result_table(discontinuities=[1]),self.stage().model)
        with self.assertRaisesRegex(ExchangeError,"discontinuity_policy_required"): query(result,30)
        self.assertEqual(query(result,30,discontinuity_policy="previous")["values"],[293.15,298.15])
        self.assertEqual(query(result,60)["values"],[303.15,308.15])
        for time in (-1,121):
            with self.assertRaisesRegex(ExchangeError,"result_extrapolation"): query(result,time)
        result = read_results(result_table(interpolation="none"),self.stage().model)
        with self.assertRaisesRegex(ExchangeError,"interpolation_disabled"): query(result,30)

    def test_result_future_fields_shapes_units_numbers_and_time_order_fail(self):
        for changes in ({"extra":1},{"version":"future"},{"values":[[1]]},{"time":[0,0,2]},
                        {"unit":"W"},{"sign":"unknown"},{"identities":[["missing","101"]]},
                        {"identities":[["a","101"],["a","101"]]},{"discontinuities":[0]},
                        {"values":[[-300,0],[0,0],[0,0]]},{"time_unit":"K"}):
            with self.assertRaises(ExchangeError): read_results(result_table(**changes),self.stage().model)
        with self.assertRaises(ExchangeError): read_results(b'{"version":NaN}',self.stage().model)
        with self.assertRaisesRegex(ExchangeError,"result_time"):
            read_results(result_table(time=[-1e308,1e308,1.5e308],time_unit="s"),self.stage().model)

    def test_result_dependencies_are_inventoried_and_exported_as_exact_data(self):
        (self.source/"main.txt").write_bytes(network()+line("RESULT",{"path":"results.json"}))
        raw = result_table()
        (self.source/"results.json").write_bytes(raw)
        staged = self.stage()
        self.assertTrue(staged.report["runnable"],staged.report)
        self.assertEqual(staged.report["records"][-1]["category"],"result")
        export_tree(staged,self.root/"copy")
        self.assertEqual((self.root/"copy/results.json").read_bytes(),raw)
        (self.source/"results.json").write_bytes(result_table(unit="W"))
        self.assertFalse(self.stage().report["runnable"])

    def test_foundation_v2_contracts_and_lossy_exports_are_rejected(self):
        adapter = ReferenceAdapter()
        raw = (ROOT/"tests/fixtures/spatial/solid-surface-rotated.json").read_bytes()
        spatial = adapter.read_foundation("spatial",raw)
        self.assertEqual(spatial["contract_version"],"2.0.0")
        manifest = source_package(self.stage()).manifest
        self.assertEqual(adapter.read_foundation("manifest2",encode(manifest)),read("manifest2",manifest))
        for name in ("higher-order.json","unknown-field.json","unknown-major.json"):
            with self.assertRaisesRegex(ExchangeError,"foundation_contract"):
                adapter.read_foundation("spatial",(ROOT/"tests/fixtures/spatial"/name).read_bytes())
        with self.assertRaisesRegex(ExchangeError,"unsupported_contract"): adapter.read_foundation("mesh-v0",raw)

    def test_bounded_deterministic_parser_fuzz_preserves_all_bytes_and_verdicts(self):
        rng = random.Random(7007)
        for index in range(200):
            raw = bytes(rng.randrange(256) for _ in range(rng.randrange(512)))
            if index % 3 == 0: raw = b"ENTITY "+raw
            (self.source/"main.txt").write_bytes(raw)
            staged = self.stage()
            self.assertEqual(b"".join(r.content for r in staged.sources[0].records),raw)
            self.assertFalse(staged.report["qualified"])
            self.assertTrue(all(r["status"] in STATUSES for r in staged.report["records"]))

    def test_structured_malformed_record_fuzz_never_escapes_as_host_exceptions(self):
        templates = [
            ("ENTITY",{"namespace":"a","handle":"bad","entity":{"kind":"submodel"}}),
            ("EXPRESSION",{"namespace":"a","handle":"bad","language":"fcst-expr/1","text":"1","dimension":"scalar"}),
            ("INCLUDE",{"path":"missing.txt"}),
            ("RESULT",{"path":"missing.json"})]
        for kind,template in templates:
            for key in template:
                for bad in (None,True,[],{},0,["bad"]):
                    value = deepcopy(template)
                    value[key] = bad
                    raw = network()+line(kind,value)
                    (self.source/"main.txt").write_bytes(raw)
                    staged = self.stage()
                    self.assertFalse(staged.report["runnable"],(kind,key,bad))
                    self.assertEqual(len(staged.report["records"]),6)
                    self.assertEqual(staged.sources[0].content,raw)

    def test_hard_process_exit_before_export_commit_preserves_original_bytes(self):
        code = ('from pathlib import Path; import os,sys; from fcst_exchange import preview,export_tree; '
                'staged=preview(sys.argv[1],"main.txt",dialect="fcst-network/1"); '
                'Path.rename=lambda *args: os._exit(79); export_tree(staged,sys.argv[2])')
        env = dict(os.environ,PYTHONPATH=str(ROOT/"python"))
        result = subprocess.run([sys.executable,"-c",code,str(self.source),str(self.root/"killed-export")],
                                env=env,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,79)
        self.assertFalse((self.root/"killed-export").exists())
        self.assertEqual((self.source/"main.txt").read_bytes(),network())
        self.assertEqual(len(list(self.root.glob(".fcst-export-*"))),1)

    def test_cli_preview_export_package_and_result_query_are_unattended(self):
        env = dict(os.environ,PYTHONPATH=str(ROOT/"python"))
        def cli(command,*args):
            return subprocess.run([sys.executable,"-m","fcst_cli",command,str(self.source),"main.txt",
                                   "--dialect",DIALECT,*map(str,args)],env=env,capture_output=True,timeout=20)
        result = cli("exchange-preview")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)["runnable"])
        self.assertEqual(cli("exchange-export",self.root/"cli-copy").returncode,0)
        self.assertEqual(cli("exchange-package",self.root/"cli.fcst").returncode,0)
        (self.source/"result.json").write_bytes(result_table())
        result = cli("exchange-result","result.json","30")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["values"],[298.15,303.15])
        self.assertEqual(cli("exchange-export",self.source).returncode,2)
