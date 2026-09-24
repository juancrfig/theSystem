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
        self.rule = Path(self.tmp.name) / "memory-request-review.md"
        self.rule.write_text(
            "# Rule\n\nRule: test.\n\nPrevents: test.\n\nEnforce with: test.\n\n"
            "<!-- MEMORY-REQUEST-REVIEW-CATALOG\n"
            '{"catalog_version": 1, "criteria": []}\n'
            "MEMORY-REQUEST-REVIEW-CATALOG -->\n",
            encoding="utf-8",
        )

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

        result = review.evaluate_request(request, review.load_catalog(self.rule), lambda *_: calls.append(True))
        panel = review.render_panel(request, result, 1, 1)

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "SIN CRITERIOS")
        self.assertIn("| ESTADO: SIN CRITERIOS", panel)
        self.assertIn('"content": "keep this"', panel)

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

    def test_catalog_rejects_criteria_without_complete_semantics(self):
        self.rule.write_text(
            "<!-- MEMORY-REQUEST-REVIEW-CATALOG\n"
            '{"catalog_version": 1, "criteria": [{"id": "bad", "version": 1, "question": "q"}]}\n'
            "MEMORY-REQUEST-REVIEW-CATALOG -->\n",
            encoding="utf-8",
        )
        with self.assertRaises(review.ReviewError):
            review.load_catalog(self.rule)

    def test_long_panel_uses_numbered_continuation_blocks_without_losing_payload(self):
        content = "x" * 2000
        self._pending("memory", "long", {"action": "add", "target": "memory", "content": content})
        request = review.inventory_pending(self.home).requests[0]
        panel = review.render_panel(request, review.Evaluation("SIN CRITERIOS", "", {}), 1, 1)
        self.assertIn("BLOQUE 1/", panel)
        self.assertIn(content[:76], panel)
        self.assertIn(content[-76:], panel)

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
