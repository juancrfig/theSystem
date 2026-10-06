import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_memory_requests.py"
SPEC = importlib.util.spec_from_file_location("memory_request_review", SCRIPT)
review = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review
SPEC.loader.exec_module(review)


class MemoryRequestReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / ".hermes"
        self.home.mkdir()
        self.catalog = Path(self.tmp.name) / "criteria.json"
        self.catalog.write_text('{"catalog_version": 1, "criteria": []}\n', encoding="utf-8")
        # Native decisions execute in a separate interpreter. Supply a minimal
        # isolated Hermes runtime so these tests exercise that boundary without
        # relying on a developer's checkout-local review environment.
        self.runtime = Path(self.tmp.name) / "runtime"
        (self.runtime / "tools").mkdir(parents=True)
        (self.runtime / "hermes_cli").mkdir()
        (self.runtime / "tools" / "__init__.py").write_text("")
        (self.runtime / "hermes_cli" / "__init__.py").write_text("")
        (self.runtime / "tools" / "write_approval.py").write_text(
            "import os\nfrom pathlib import Path\nMEMORY = 'memory'\n"
            "def discard_pending(subsystem, pending_id):\n"
            " p = Path(os.environ['HERMES_HOME']) / 'pending' / subsystem / f'{pending_id}.json'\n"
            " if not p.exists(): return False\n"
            " p.unlink(); return True\n"
        )
        (self.runtime / "tools" / "memory_tool.py").write_text("def load_on_disk_store(): return object()\n")
        (self.runtime / "hermes_cli" / "write_approval_commands.py").write_text(
            "import os\nfrom pathlib import Path\n"
            "def _apply_one(subsystem, record, _store):\n"
            " payload = record['payload']; root = Path(os.environ['HERMES_HOME'])\n"
            " if subsystem == 'memory':\n"
            "  name = 'USER.md' if payload.get('target') == 'user' else 'MEMORY.md'\n"
            "  path = root / 'memories' / name; path.parent.mkdir(parents=True, exist_ok=True)\n"
            "  path.write_text(payload.get('content', ''), encoding='utf-8')\n"
            " return True, '', {'applied': True}\n"
        )
        sys.path.insert(0, str(self.runtime))

    def tearDown(self):
        sys.path.remove(str(self.runtime))
        self.tmp.cleanup()

    def _pending(self, subsystem, ident, payload, *, home=None, created_at=10):
        target_home = home or self.home
        path = target_home / "pending" / subsystem
        path.mkdir(parents=True, exist_ok=True)
        record = {
            "id": ident,
            "subsystem": subsystem,
            "action": payload.get("action", ""),
            "summary": "test request",
            "origin": "foreground",
            "created_at": created_at,
            "payload": payload,
        }
        (path / f"{ident}.json").write_text(json.dumps(record), encoding="utf-8")

    def test_inventory_collects_all_authorized_profiles_and_subsystems(self):
        worker = self.home / "profiles" / "worker"
        reviewer = self.home / "profiles" / "reviewer"
        worker.mkdir(parents=True)
        reviewer.mkdir(parents=True)
        self._pending("memory", "same", {"action": "add", "target": "memory", "content": "a"})
        self._pending("skills", "same", {"action": "create", "name": "alpha", "content": "x"}, home=worker)
        self._pending("memory", "other", {"action": "add", "target": "user", "content": "b"}, home=reviewer)

        inventory = review.inventory_pending(self.home)

        self.assertEqual(inventory.counts, {"memory": 2, "skills": 1, "unreadable": 0})
        self.assertEqual(
            [(item.profile, item.subsystem, item.pending_id) for item in inventory.requests],
            [("default", "memory", "same"), ("reviewer", "memory", "other"), ("worker", "skills", "same")],
        )

    def test_inventory_ignores_profiles_outside_thesystem(self):
        self._pending("memory", "other", {"action": "add", "target": "memory", "content": "x"},
                      home=self.home / "profiles" / "personal")
        self.assertFalse(review.inventory_pending(self.home).requests)

    def test_headless_evaluator_uses_the_main_profile_without_tools(self):
        self._pending("memory", "one", {"action": "add", "target": "memory", "content": "keep this"})
        request = review.inventory_pending(self.home).requests[0]
        criteria = review.load_catalog(SCRIPT.parents[1] / "criteria.json").criteria[:1]
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, '{"concerns": []}', "")

        with mock.patch("shutil.which", return_value="/bin/hermes"), mock.patch.object(review.subprocess, "run", fake_run):
            result = review.evaluate_with_headless(request, criteria)

        self.assertEqual(result.status, "CONCERNS")
        long = review.Evaluation("CONCERNS", "hermes", {}, concerns=("unclear-proposal: " + "word " * 40 + "END",))
        panel = review.render_panel(request, long, 1, 1)
        self.assertIn("END", panel, "concern reasons are wrapped, not cut")
        self.assertNotIn("-p", calls[0])
        self.assertEqual(calls[0][calls[0].index("-t") + 1], "none")

    def _skill(self, name, text, *, mtime=None):
        skill = self.home / "skills" / "category" / name
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(text, encoding="utf-8")
        if mtime is not None:
            os.utime(skill / "SKILL.md", (mtime, mtime))
        return skill

    def _skill_patch(self, old):
        return {"action": "batch", "operations": [
            {"action": "patch", "name": "alpha", "old_string": old, "new_string": "new text"}]}

    def test_staleness_flags_old_text_missing_from_the_current_skill(self):
        self._skill("alpha", "# Alpha\n\nKeep   this line.\n", mtime=5)
        self._pending("skills", "present", self._skill_patch("Keep this\nline."))
        self._pending("skills", "gone", self._skill_patch("A line someone rewrote."))
        requests = {item.pending_id: item for item in review.inventory_pending(self.home).requests}
        self.assertEqual(review.staleness(requests["present"]), ())
        self.assertEqual(review.staleness(requests["gone"]), ("old-text-missing",))

    def test_staleness_flags_a_target_edited_after_the_request(self):
        self._skill("alpha", "Keep this line.\n", mtime=50)
        self._pending("skills", "older", self._skill_patch("Keep this line."), created_at=20)
        request = review.inventory_pending(self.home).requests[0]
        self.assertEqual(review.staleness(request), ("target-changed",))

    def test_staleness_reads_old_text_from_the_target_memory_file(self):
        memories = self.home / "memories"
        memories.mkdir()
        (memories / "USER.md").write_text("User likes tea.\n", encoding="utf-8")
        os.utime(memories / "USER.md", (5, 5))
        self._pending("memory", "m", {"action": "replace", "target": "user", "old_text": "likes coffee",
                                      "content": "User likes water."})
        request = review.inventory_pending(self.home).requests[0]
        self.assertEqual(review.staleness(request), ("old-text-missing",))

    def test_staleness_accepts_old_text_written_by_an_earlier_operation_in_the_batch(self):
        self._skill("alpha", "Base.\n", mtime=5)
        self._pending("skills", "s", {"action": "batch", "operations": [
            {"action": "patch", "name": "alpha", "old_string": "Base.", "new_string": "Base. Added."},
            {"action": "patch", "name": "alpha", "old_string": "Added.", "new_string": "Changed."},
        ]})
        self.assertEqual(review.staleness(review.inventory_pending(self.home).requests[0]), ())

    def test_panel_shows_staleness(self):
        self._skill("alpha", "Current text.\n", mtime=5)
        self._pending("skills", "s", self._skill_patch("Old text."))
        request = review.inventory_pending(self.home).requests[0]
        evaluation = review.Evaluation("NO CRITERIA", "", {})
        panel = review.render_panel(request, evaluation, 1, 1, staleness=review.staleness(request))
        self.assertIn("Old text no longer present", panel)

    def test_sweep_auto_rejects_only_requests_whose_old_text_is_gone(self):
        self._skill("alpha", "Current text.\n", mtime=50)
        self._pending("skills", "gone", self._skill_patch("Old text."), created_at=20)
        self._pending("skills", "changed", self._skill_patch("Current text."), created_at=20)
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = review.main(["sweep", "--home-root", str(self.home)])

        self.assertEqual(exit_code, 0)
        swept = json.loads(output.getvalue())["auto_rejected"]
        self.assertEqual([row["id"] for row in swept], ["gone"])
        self.assertTrue(swept[0]["success"])
        self.assertEqual(swept[0]["target"], "skill:alpha")
        self.assertFalse((self.home / "pending" / "skills" / "gone.json").exists())
        self.assertTrue((self.home / "pending" / "skills" / "changed.json").exists(), "target-changed alone is kept")
        self.assertEqual((self.home / "skills" / "category" / "alpha" / "SKILL.md").read_text(), "Current text.\n")
        decision = review.load_review_state(self.home)["decisions"][0]
        self.assertEqual((decision["decided_by"], decision["reason"]), ("auto", "old-text-missing"))

    def test_empty_catalog_never_calls_evaluator_and_panel_marks_no_criteria(self):
        self._pending("memory", "one", {"action": "add", "target": "memory", "content": "keep this"})
        request = review.inventory_pending(self.home).requests[0]
        calls = []

        result = review.evaluate_request(request, review.load_catalog(self.catalog), lambda *_: calls.append(True))
        panel = review.render_panel(request, result, 1, 1)

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "NO CRITERIA")
        self.assertIn("no criteria in the catalog", panel)
        self.assertIn("Target: memory", panel)
        self.assertIn("+ keep this", panel)

    def test_secret_like_payload_is_retained_without_exposing_value_or_calling_evaluator(self):
        secret = "sk-" + "a" * 24
        self._pending("memory", "secret", {"action": "add", "target": "memory", "content": f"key={secret}"})
        request = review.inventory_pending(self.home).requests[0]
        calls = []
        catalog = review.Catalog(1, (
            review.Criterion("retention", 1, "Is this unsafe?", {}, {"yes": "yes", "no": "no"}, [], []),
        ))

        result = review.evaluate_request(request, catalog, lambda *_: calls.append(True))
        panel = review.render_panel(request, result, 1, 1)

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "RETAINED LOCALLY")
        self.assertNotIn(secret, panel)
        self.assertIn("possible API key", panel)

    def test_new_or_changed_payload_invalidates_cached_result(self):
        self._pending("memory", "one", {"action": "add", "target": "memory", "content": "first"})
        request = review.inventory_pending(self.home).requests[0]
        catalog = review.Catalog(1, (review.Criterion("bad", 1, "Is it bad?", {}, {}, [], []),))
        cache = {review.cache_key(request, catalog.criteria[0], "jev-1"): {"probability": 0.8}}
        self.assertEqual(review.reusable_results(request, catalog, "jev-1", cache)["bad"], 0.8)

        self._pending("memory", "one", {"action": "add", "target": "memory", "content": "changed"})
        changed = review.inventory_pending(self.home).requests[0]
        self.assertEqual(review.reusable_results(changed, catalog, "jev-1", cache), {})

    def test_shipped_criteria_catalog_is_valid(self):
        self.assertEqual(review._default_catalog_path().name, "criteria.json")
        review.load_catalog(review._default_catalog_path())

    def test_catalog_rejects_criteria_without_complete_semantics(self):
        self.catalog.write_text(
            '{"catalog_version": 1, "criteria": [{"id": "bad", "version": 1, "question": "q"}]}\n',
            encoding="utf-8",
        )
        with self.assertRaises(review.ReviewError):
            review.load_catalog(self.catalog)

    def test_card_shows_target_questions_scores_and_full_literal_text(self):
        content = " ".join(f"word{index}" for index in range(400))
        self._pending("memory", "long", {"action": "add", "target": "user", "content": content})
        request = review.inventory_pending(self.home).requests[0]
        catalog = review.Catalog(1, (
            review.Criterion("vague", 1, "Is it vague?", {}, {"yes": "y", "no": "n"}, [], []),
        ))
        panel = review.render_panel(request, review.Evaluation("EVALUATED", "jev-test", {"vague": 0.27}), 1, 1, catalog)
        flattened = " ".join(panel.replace("│", " ").split())
        self.assertIn("Target: user", panel)
        self.assertIn("Is it vague?", panel)
        self.assertIn("0.27", panel)
        self.assertIn("ADD", flattened)
        self.assertIn("+ word0 ", flattened)
        self.assertIn("word399", flattened)
        self.assertTrue(all(len(line) <= review._WIDTH for line in panel.splitlines()))

    def test_unscored_questions_still_show_what_jev_was_asked(self):
        self._pending("memory", "one", {"action": "add", "target": "memory", "content": "x"})
        request = review.inventory_pending(self.home).requests[0]
        catalog = review.Catalog(1, (
            review.Criterion("vague", 1, "Is it vague?", {}, {"yes": "y", "no": "n"}, [], []),
        ))
        failed = review.Evaluation("EVALUATION ERROR", "", {}, "boom")
        panel = review.render_panel(request, failed, 1, 1, catalog)
        self.assertIn("Is it vague?", panel)
        self.assertIn("Jev failed: boom", panel)

    def test_skill_target_names_skills_from_batch_operations(self):
        self._pending("skills", "s", {"action": "batch", "operations": [
            {"action": "patch", "name": "alpha", "old_string": "a", "new_string": "b"},
            {"action": "write_file", "name": "beta", "file_path": "refs/x.md", "file_content": "body"},
        ]})
        request = review.inventory_pending(self.home).requests[0]
        self.assertEqual(review.target_label(request), "skill:alpha, skill:beta")
        operations = review.describe_operations(request)
        self.assertEqual([(op.verb, op.old, op.new) for op in operations], [("REPLACE", "a", "b"), ("ADD", "", "body")])

    def test_replace_that_keeps_its_old_text_is_shown_as_a_plain_add(self):
        self._pending("memory", "m", {"action": "batch", "target": "memory", "operations": [
            {"action": "replace", "old_text": "Anchor:", "content": "New fact. Anchor:"},
            {"action": "replace", "old_text": "Anchor:", "content": "Anchor: more"},
            {"action": "replace", "old_text": "Anchor:", "content": "Other", "extra": 1},
            {"action": "remove", "old_text": "Gone"},
        ]})
        request = review.inventory_pending(self.home).requests[0]
        operations = review.describe_operations(request)
        self.assertEqual([(op.verb, op.old, op.new) for op in operations[:2]],
                         [("ADD", "", "New fact."), ("ADD", "", "more")])
        self.assertEqual(operations[2].verb, "REPLACE")
        self.assertIn('"extra":1', operations[2].new)
        self.assertEqual((operations[3].verb, operations[3].old), ("DELETE", "Gone"))
        self.assertNotIn("Anchor", review.render_panel(request, review.Evaluation("NO CRITERIA", "", {}), 1, 1)
                         .split("REPLACE")[0])

    def test_show_evaluates_only_the_displayed_request(self):
        self.catalog.write_text(
            '{"catalog_version": 1, "criteria": [{"id": "q", "version": 1, "question": "Q?", '
            '"context": {}, "definition": {"yes": "y", "no": "n"}}]}\n',
            encoding="utf-8",
        )
        self._pending("memory", "first", {"action": "add", "target": "memory", "content": "a"})
        self._pending("memory", "second", {"action": "add", "target": "memory", "content": "b"})
        seen = []
        original = review.evaluate_with_jev
        review.evaluate_with_jev = lambda request, *_: (
            seen.append(request.pending_id) or review.Evaluation("EVALUATED", "jev-test", {"q": 0.5}))
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                review.main(["show", "--home-root", str(self.home), "--catalog", str(self.catalog), "--position", "2"])
        finally:
            review.evaluate_with_jev = original
        self.assertEqual(seen, ["second"])
        self.assertIn("0.50", output.getvalue())

    def test_reject_verifies_the_destination_was_not_applied(self):
        self._pending("memory", "reject", {"action": "add", "target": "memory", "content": "do not save"})
        request = review.inventory_pending(self.home).requests[0]
        result = review.apply_native_decision(request, "reject", request.record_sha256)
        self.assertTrue(result["success"])
        self.assertTrue(result["pending_removed"])
        self.assertTrue(result["destination_unchanged"])
        self.assertFalse((self.home / "memories" / "MEMORY.md").exists())

    def test_decide_binds_the_native_action_to_the_reviewed_request_identity(self):
        self._pending("memory", "reviewed", {"action": "add", "target": "memory", "content": "apply only this"})
        self._pending("memory", "other", {"action": "add", "target": "memory", "content": "do not apply"})
        reviewed = next(item for item in review.inventory_pending(self.home).requests if item.pending_id == "reviewed")

        with redirect_stdout(io.StringIO()):
            exit_code = review.main([
                "decide", "--home-root", str(self.home), "--profile", "default", "--subsystem", "memory",
                "--pending-id", "reviewed", "--decision", "approve", "--human-decision",
                "--expected-record-sha256", reviewed.record_sha256,
            ])

        self.assertEqual(exit_code, 0)
        self.assertFalse((self.home / "pending" / "memory" / "reviewed.json").exists())
        self.assertTrue((self.home / "pending" / "memory" / "other.json").exists())
        self.assertIn("apply only this", (self.home / "memories" / "MEMORY.md").read_text(encoding="utf-8"))
        self.assertNotIn("do not apply", (self.home / "memories" / "MEMORY.md").read_text(encoding="utf-8"))

    def test_native_decision_isolated_to_the_reviewed_named_profile(self):
        worker = self.home / "profiles" / "worker"
        worker.mkdir(parents=True)
        self._pending("memory", "same", {"action": "add", "target": "memory", "content": "default remains pending"})
        self._pending(
            "memory", "same", {"action": "add", "target": "memory", "content": "worker only"}, home=worker,
        )
        request = next(
            item for item in review.inventory_pending(self.home).requests
            if item.profile == "worker" and item.pending_id == "same"
        )

        result = review.apply_native_decision(request, "approve", request.record_sha256)

        self.assertTrue(result["success"])
        self.assertTrue((self.home / "pending" / "memory" / "same.json").exists())
        self.assertFalse((worker / "pending" / "memory" / "same.json").exists())
        self.assertIn("worker only", (worker / "memories" / "MEMORY.md").read_text(encoding="utf-8"))
        self.assertFalse((self.home / "memories" / "MEMORY.md").exists())

    def test_apply_requires_matching_snapshot_and_uses_native_pending_flow(self):
        self._pending("memory", "one", {"action": "add", "target": "memory", "content": "native approved"})
        request = review.inventory_pending(self.home).requests[0]

        with self.assertRaises(review.StaleRequestError):
            review.apply_native_decision(request, "approve", "wrong")

        result = review.apply_native_decision(request, "approve", request.record_sha256)
        self.assertTrue(result["success"])
        self.assertFalse((self.home / "pending" / "memory" / "one.json").exists())
        self.assertIn("native approved", (self.home / "memories" / "MEMORY.md").read_text(encoding="utf-8"))


PREPARE_SCRIPT = SCRIPT.with_name("prepare_environment.py")
PREPARE_SPEC = importlib.util.spec_from_file_location("memory_review_prepare", PREPARE_SCRIPT)
prepare = importlib.util.module_from_spec(PREPARE_SPEC)
PREPARE_SPEC.loader.exec_module(prepare)


class PrepareEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_published_runtime_command_becomes_a_path_probe(self):
        bootstrap = "import sys; sys.path.insert(0, '/src'); " + prepare.ENTRY_MARKER
        published = self.root / "runtime.json"
        published.write_text(json.dumps(["/py/bin/python3", "-I", "-c", bootstrap]))
        launcher = self.root / "hermes"
        launcher.write_text(f"#!/bin/sh\ncat '{published}'\n")
        launcher.chmod(0o755)
        python, probe = prepare.hermes_runtime(str(launcher))
        self.assertEqual(python, "/py/bin/python3")
        self.assertEqual(probe[:3], ["/py/bin/python3", "-I", "-c"])
        self.assertNotIn(prepare.ENTRY_MARKER, probe[3])
        self.assertIn("sys.path.insert(0, '/src')", probe[3])

    def test_bridge_adds_existing_unique_directories_only(self):
        site_dir = self.root / "site"
        site_dir.mkdir()
        target = prepare.write_bridge(str(self.root), [str(site_dir), str(site_dir), str(self.root / "missing")])
        self.assertEqual(target.read_text(), f"import site; site.addsitedir({str(site_dir)!r})\n")


if __name__ == "__main__":
    unittest.main()
