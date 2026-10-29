# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from fcst_tools.privacy import POLICY_PATH, Scanner, inspect_git, main, sha

SCRATCH = POLICY_PATH.parents[1] / ".local" / "test-scratch"
SCRATCH.mkdir(parents=True, exist_ok=True)


def archive(name, payload):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr(name, payload)
    return buffer.getvalue()


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY_PATH.read_text())
        self.scanner = Scanner(copy.deepcopy(self.policy))

    def test_safe_synthetic_document(self):
        self.scanner.scan("fixtures/model.json", b'{"nodes":[{"id":"n1","temperature_K":300}]}')
        self.assertEqual(self.scanner.report()["status"], "passed")

    def test_native_header_and_patch_are_scanned_as_text_without_binary_exemptions(self):
        for name in ('config.h','preservation.patch'):
            scanner=Scanner(self.policy);scanner.scan(name,b'/* owned synthetic source */\n')
            self.assertEqual(scanner.report()['status'],'passed')
            secret='synthetic'+'@'+'example.invalid'
            scanner=Scanner(self.policy);scanner.scan(name,secret.encode())
            self.assertIn('contact',{row['category'] for row in scanner.findings})
            self.assertNotIn(secret,json.dumps(scanner.report()))
            scanner=Scanner(self.policy);scanner.scan(name,b'\x00\xffbinary')
            self.assertEqual(scanner.report()['status'],'failed')

    def test_public_project_url_is_distinct_from_real_home_paths(self):
        self.scanner.scan("project.json", b'{"url":"https://github.com/users/sample/projects/1"}')
        self.assertEqual(self.scanner.report()["status"], "passed")
        for value in ["/".join(["", "home", "synthetic-person", "model.txt"]),
                      "file://" + "/".join(["", "Users", "synthetic-person", "model.txt"])]:
            scanner = Scanner(self.policy)
            scanner.scan("data.txt", value.encode())
            self.assertIn("personal_path", {item["category"] for item in scanner.findings})

    def test_planted_categories_and_reports_never_echo_values(self):
        cases = {
            "personal_path": "C:" + chr(92) + "Users" + chr(92) + "synthetic-person" + chr(92) + "model.txt",
            "contact": "synthetic.person" + "@" + "example.invalid",
            "credential": "gh" + "p_" + "X" * 36,
            "private_key": "-----BEGIN " + "PRIVATE KEY-----",
            "internal_network": "10." + "21.22.23",
            "assigned_secret": "license_" + "key=" + "SYNTHETIC123456",
            "phone": "(" + "212) 555-0187",
        }
        for category, secret in cases.items():
            with self.subTest(category=category):
                scanner = Scanner(self.policy)
                scanner.scan("payload.txt", secret.encode())
                report = scanner.report()
                self.assertIn(category, {item["category"] for item in report["findings"]})
                self.assertNotIn(secret, json.dumps(report))

    def test_private_identifier_hash(self):
        value = "synthetic-" + "restricted-system"
        self.policy["private_term_hashes"] = [sha(value.casefold().encode())]
        scanner = Scanner(self.policy)
        scanner.scan("data.txt", value.upper().encode())
        self.assertEqual(scanner.report()["findings"][0]["category"], "private_identifier")

    def test_sensitive_filename_redacted(self):
        secret = "C:" + chr(92) + "Users" + chr(92) + "synthetic-person" + chr(92) + "notes.txt"
        self.scanner.scan(secret, b"safe")
        self.assertEqual(self.scanner.report()["status"], "failed")
        self.assertNotIn(secret, json.dumps(self.scanner.report()))

    def test_nested_archive(self):
        secret = "synthetic" + "@" + "example.invalid"
        self.scanner.scan("package.zip", archive("nested.zip", archive("generated.txt", secret)))
        self.assertIn("contact", {item["category"] for item in self.scanner.findings})

    def test_unknown_binary_and_fake_text_fail_closed(self):
        for name, value in [("screenshot.png", b"image"), ("model.txt", b"a\x00b"), ("doc.md", b"\xff")]:
            with self.subTest(name=name):
                scanner = Scanner(self.policy)
                scanner.scan(name, value)
                self.assertEqual(scanner.report()["status"], "failed")

    def test_archive_traversal(self):
        for name in ["../secret.txt", "/absolute.txt", "C:/absolute.txt"]:
            scanner = Scanner(self.policy)
            scanner.scan("data.zip", archive(name, b"safe"))
            self.assertIn("archive_traversal", {item["category"] for item in scanner.findings})

    def test_size_and_depth_limits(self):
        self.policy["max_item_bytes"] = 10
        with self.assertRaises(ValueError):
            Scanner(self.policy).scan("large.txt", b"x" * 11)
        self.policy["max_item_bytes"] = 100000
        self.policy["max_archive_depth"] = 0
        scanner = Scanner(self.policy)
        scanner.scan("package.zip", archive("safe.txt", b"safe"))
        self.assertIn("archive_depth", {item["category"] for item in scanner.findings})

    def test_clearance_binds_content_and_policy(self):
        first = Scanner(self.policy)
        first.scan("safe.txt", b"one")
        second = Scanner(self.policy)
        second.scan("safe.txt", b"two")
        self.assertNotEqual(first.report()["payload_sha256"], second.report()["payload_sha256"])
        changed_policy = copy.deepcopy(self.policy)
        changed_policy["version"] += 1
        self.assertNotEqual(first.report()["policy_sha256"], Scanner(changed_policy).report()["policy_sha256"])

    def test_empty_input_rejected(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 1)

    def test_git_deleted_history_and_author_are_inspected(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout
            git("init", "-q")
            git("config", "user.name", "Unapproved Synthetic")
            git("config", "user.email", "synthetic" + "@" + "example.invalid")
            secret = "gh" + "p_" + "S" * 36
            (root / "old.txt").write_text(secret)
            git("add", "old.txt")
            git("-c", "core.hooksPath=", "commit", "-qm", "Synthetic first commit")
            git("rm", "old.txt")
            identity = self.policy["approved_identities"][0]
            git("-c", "core.hooksPath=", "-c", "user.name=" + identity["name"],
                "-c", "user.email=" + identity["email"], "commit", "-qm", "Remove synthetic file")
            inspect_git(self.scanner, root, "HEAD", True)
            categories = {item["category"] for item in self.scanner.findings}
            self.assertIn("credential", categories)
            self.assertIn("unapproved_identity", categories)
            self.assertNotIn(secret, json.dumps(self.scanner.report()))

    def test_staged_bytes_are_not_worktree_bytes(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            target = root / "data.txt"
            target.write_text("gh" + "p_" + "S" * 36)
            subprocess.run(["git", "-C", str(root), "add", "data.txt"], check=True, capture_output=True)
            target.write_text("safe worktree")
            inspect_git(self.scanner, root, None, True)
            self.assertIn("credential", {item["category"] for item in self.scanner.findings})

    def test_annotated_tag_identity_is_inspected(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout
            git("init", "-q")
            identity = self.policy["approved_identities"][0]
            git("config", "user.name", identity["name"])
            git("config", "user.email", identity["email"])
            (root / "safe.txt").write_text("safe")
            git("add", "safe.txt")
            git("-c", "core.hooksPath=", "commit", "-qm", "Synthetic safe commit")
            git("-c", "user.name=Synthetic unapproved tagger", "tag", "-a", "test-tag", "-m", "Synthetic tag")
            inspect_git(self.scanner, root, "test-tag", False)
            self.assertIn("unapproved_identity", {item["category"] for item in self.scanner.findings})

    def test_staged_mode_changes_invalidate_clearance(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout
            git("init", "-q")
            (root / "safe.txt").write_text("safe")
            git("add", "safe.txt")
            inspect_git(self.scanner, root, None, True)
            first = self.scanner.report()
            git("update-index", "--chmod=+x", "safe.txt")
            changed = Scanner(self.policy)
            inspect_git(changed, root, None, True)
            self.assertNotEqual(first["payload_sha256"], changed.report()["payload_sha256"])

    def test_unchanged_history_versions_share_content_budget_but_all_commits_are_bound(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root=Path(temporary)
            def git(*args):
                return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout
            git('init','-q'); identity=self.policy['approved_identities'][0]
            git('config','user.name',identity['name']);git('config','user.email',identity['email'])
            payload=b'public synthetic content\n'*1024
            (root/'unchanged.txt').write_bytes(payload);git('add','unchanged.txt')
            for index in range(4):
                git('-c','core.hooksPath=','commit','--allow-empty','-qm','Synthetic history '+str(index))
            policy=copy.deepcopy(self.policy);policy['max_total_bytes']=len(payload)+4096
            scanner=Scanner(policy);inspect_git(scanner,root,'HEAD',False)
            self.assertEqual(scanner.report()['status'],'passed')
            self.assertEqual(sum(item['sha256']==sha(payload) for item in scanner.items),1)
            self.assertEqual(len(scanner.items),5)  # one content version plus every commit
            first=scanner.report()['payload_sha256']
            git('-c','core.hooksPath=','commit','--allow-empty','-qm','Additional bound metadata')
            scanner=Scanner(policy);inspect_git(scanner,root,'HEAD',False)
            self.assertNotEqual(first,scanner.report()['payload_sha256'])

    def test_history_reused_blob_is_rechecked_for_every_path_and_mode(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root=Path(temporary)
            def git(*args):
                return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout
            git('init','-q'); identity=self.policy['approved_identities'][0]
            git('config','user.name',identity['name']);git('config','user.email',identity['email'])
            (root/'safe.txt').write_text('synthetic reused bytes');git('add','safe.txt')
            git('-c','core.hooksPath=','commit','-qm','Synthetic text context')
            git('update-index','--chmod=+x','safe.txt')
            git('-c','core.hooksPath=','commit','-qm','Synthetic executable mode')
            (root/'restricted').mkdir()
            (root/'restricted/reused.txt').write_text('synthetic reused bytes')
            (root/'reused.png').write_text('synthetic reused bytes')
            git('add','restricted/reused.txt','reused.png')
            git('-c','core.hooksPath=','commit','-qm','Synthetic different path contexts')
            scanner=Scanner(self.policy);inspect_git(scanner,root,'HEAD',False)
            categories={item['category'] for item in scanner.findings}
            self.assertTrue({'restricted_or_unsafe_path','unchecked_type'}<=categories)
            self.assertEqual(sum(item['sha256']==sha(b'synthetic reused bytes') for item in scanner.items),4)
