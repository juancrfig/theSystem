import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
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

    def tearDown(self):
        self.tmp.cleanup()

    def _pending(self, subsystem, ident, payload, *, home=None):
        target_home = home or self.home
        path = target_home / "pending" / subsystem
        path.mkdir(parents=True, exist_ok=True)
        record = {
            "id": ident,
            "subsystem": subsystem,
            "action": payload.get("action", ""),
            "summary": "test request",
            "origin": "foreground",
            "created_at": 10,
            "payload": payload,
        }
        (path / f"{ident}.json").write_text(json.dumps(record), encoding="utf-8")

    def test_inventory_collects_all_authorized_profiles_and_subsystems(self):
        implementer = self.home / "profiles" / "implementer"
        reviewer = self.home / "profiles" / "reviewer"
        implementer.mkdir(parents=True)
        reviewer.mkdir(parents=True)
        self._pending("memory", "same", {"action": "add", "target": "memory", "content": "a"})
        self._pending("skills", "same", {"action": "create", "name": "alpha", "content": "x"}, home=implementer)
        self._pending("memory", "other", {"action": "add", "target": "user", "content": "b"}, home=reviewer)

        inventory = review.inventory_pending(self.home)

        self.assertEqual(inventory.counts, {"memory": 2, "skills": 1, "unreadable": 0})
        self.assertEqual(
            [(item.profile, item.subsystem, item.pending_id) for item in inventory.requests],
            [("default", "memory", "same"), ("implementer", "skills", "same"), ("reviewer", "memory", "other")],
        )

    def test_empty_catalog_never_calls_evaluator_and_panel_marks_no_criteria(self):
        self._pending("memory", "one", {"action": "add", "target": "memory", "content": "keep this"})
        request = review.inventory_pending(self.home).requests[0]
        calls = []

        result = review.evaluate_request(request, review.load_catalog(self.catalog), lambda *_: calls.append(True))
        panel = review.render_panel(request, result, 1, 1)

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "SIN CRITERIOS")
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
        self.assertEqual(result.status, "RETENIDA LOCALMENTE")
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
        panel = review.render_panel(request, review.Evaluation("EVALUADA", "jev-test", {"vague": 0.27}), 1, 1, catalog)
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
        failed = review.Evaluation("ERROR DE EVALUACION", "", {}, "boom")
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
        self.assertNotIn("Anchor", review.render_panel(request, review.Evaluation("SIN CRITERIOS", "", {}), 1, 1)
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
            seen.append(request.pending_id) or review.Evaluation("EVALUADA", "jev-test", {"q": 0.5}))
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
        implementer = self.home / "profiles" / "implementer"
        implementer.mkdir(parents=True)
        self._pending("memory", "same", {"action": "add", "target": "memory", "content": "default remains pending"})
        self._pending(
            "memory", "same", {"action": "add", "target": "memory", "content": "implementer only"}, home=implementer,
        )
        request = next(
            item for item in review.inventory_pending(self.home).requests
            if item.profile == "implementer" and item.pending_id == "same"
        )

        result = review.apply_native_decision(request, "approve", request.record_sha256)

        self.assertTrue(result["success"])
        self.assertTrue((self.home / "pending" / "memory" / "same.json").exists())
        self.assertFalse((implementer / "pending" / "memory" / "same.json").exists())
        self.assertIn("implementer only", (implementer / "memories" / "MEMORY.md").read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
