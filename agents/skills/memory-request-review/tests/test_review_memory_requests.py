import importlib.util
import json
import os
import sys
import tempfile
import unittest
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
        secret = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJK"
        self._pending("memory", "secret", {"action": "add", "target": "memory", "content": f"key={secret}"})
        request = review.inventory_pending(self.home).requests[0]
        calls = []

        result = review.evaluate_request(request, review.load_catalog(self.rule), lambda *_: calls.append(True))
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
