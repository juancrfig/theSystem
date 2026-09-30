"""Headless memory-review bridge preserves decision and child failure boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from thesystem.learning import LearningError, review_memory


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.script = self.root / "agents/skills/memory-request-review/scripts/review_memory_requests.py"
        self.script.parent.mkdir(parents=True)
        self.script.write_text("pass\n")

    def test_decide_requires_explicit_human_decision_without_child_execution(self):
        with patch("thesystem.learning.subprocess.run") as run:
            with self.assertRaises(LearningError) as failure:
                review_memory(["decide"], self.root)
        self.assertEqual(failure.exception.code, "HUMAN_DECISION_REQUIRED")
        run.assert_not_called()

    def test_native_review_arguments_and_json_result_are_preserved(self):
        completed = subprocess.CompletedProcess([], 0, '{"count": 2}', "")
        with patch("thesystem.learning.subprocess.run", return_value=completed) as run:
            result = review_memory(["inventory", "--profile", "fixture"], self.root, python="/fixture/python")
        self.assertEqual(result, {"count": 2})
        self.assertEqual(run.call_args.args[0], ["/fixture/python", str(self.script), "inventory", "--profile", "fixture"])
        self.assertEqual(run.call_args.kwargs["timeout"], 90)

    def test_explicit_human_decision_is_forwarded_and_timeout_is_coded(self):
        completed = subprocess.CompletedProcess([], 0, "approved\n", "")
        with patch("thesystem.learning.subprocess.run", return_value=completed) as run:
            result = review_memory(["decide", "--human-decision", "--decision", "approve"], self.root)
        self.assertEqual(result, {"display": "approved"})
        self.assertEqual(run.call_args.args[0][2:], ["decide", "--human-decision", "--decision", "approve"])
        self.assertEqual(run.call_args.kwargs["timeout"], 90)

        with patch("thesystem.learning.subprocess.run", side_effect=subprocess.TimeoutExpired("review", 90)):
            with self.assertRaises(LearningError) as failure:
                review_memory(["inventory"], self.root)
        self.assertEqual(failure.exception.code, "MEMORY_REVIEW_UNAVAILABLE")

    def test_child_failure_is_reported_without_success_payload(self):
        completed = subprocess.CompletedProcess([], 7, "", "fixture refusal")
        with patch("thesystem.learning.subprocess.run", return_value=completed):
            with self.assertRaises(LearningError) as failure:
                review_memory(["inventory"], self.root)
        self.assertEqual(failure.exception.code, "MEMORY_REVIEW_FAILED")
        self.assertEqual(str(failure.exception), "fixture refusal")

    def test_unavailable_native_script_is_not_reported_as_working(self):
        with self.assertRaises(LearningError) as failure:
            review_memory(["inventory"], self.root / "missing")
        self.assertEqual(failure.exception.code, "MEMORY_REVIEW_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
