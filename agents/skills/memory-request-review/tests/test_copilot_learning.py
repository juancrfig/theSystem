import importlib.util
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_memory_requests.py"
SPEC = importlib.util.spec_from_file_location("copilot_learning_review", SCRIPT)
review = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review
SPEC.loader.exec_module(review)


class CopilotLearningFallbackTests(unittest.TestCase):
    def test_explicit_copilot_lane_uses_fresh_copilot_when_remote_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            pending = home / "pending" / "memory" / "proposal.json"
            pending.parent.mkdir(parents=True)
            pending.write_text('{"payload":{"action":"add","content":"procedure"}}')
            request = review.inventory_pending(home).requests[0]
            catalog = review.Catalog(1, (review.Criterion(
                "clear", 1, "Is it unclear?", {}, {"yes":"yes","no":"no"}, [], []),))
            with patch.dict(os.environ, {"SYSTEM_ONE_API":"", "MEMORY_REVIEW_RUNTIME":"hermes"}), \
                 patch("shutil.which", return_value="/usr/bin/copilot"), \
                 patch.object(review.subprocess, "run", return_value=subprocess.CompletedProcess(
                     [], 0, '{"concerns":[]}', "")) as run:
                result = review.evaluate_one_for_runtime(request, catalog, "copilot")
            self.assertEqual(result.status, "CONCERNS")
            self.assertEqual(result.model, "copilot")
            self.assertEqual(result.results, {})
            command = run.call_args.args[0]
            self.assertEqual(command[0], "/usr/bin/copilot")
            self.assertNotIn("hermes", " ".join(command).lower())
            self.assertIn("--no-custom-instructions", command)
            self.assertIn("--disable-builtin-mcps", command)
            self.assertEqual(run.call_args.kwargs["env"]["MEMORY_REVIEW_RUNTIME"], "copilot")

    def test_remote_failure_reports_unavailable_if_native_evaluator_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            pending = home / "pending" / "memory" / "proposal.json"
            pending.parent.mkdir(parents=True)
            pending.write_text('{"payload":{"action":"add","content":"procedure"}}')
            request = review.inventory_pending(home).requests[0]
            catalog = review.Catalog(1, (review.Criterion(
                "clear", 1, "Is it unclear?", {}, {"yes":"yes","no":"no"}, [], []),))
            with patch.dict(os.environ, {"SYSTEM_ONE_API":"configured"}), \
                 patch.object(review, "evaluate_with_jev", return_value=review.Evaluation("EVALUATION ERROR", "", {}, "offline")), \
                 patch("shutil.which", return_value=None):
                result = review.evaluate_one_for_runtime(request, catalog, "copilot")
            self.assertEqual(result.status, "EVALUATION UNAVAILABLE")
            self.assertIn("copilot CLI unavailable", result.error)

    def test_secret_like_proposal_is_retained_without_remote_or_copilot_call(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            pending = home / "pending" / "memory" / "proposal.json"
            pending.parent.mkdir(parents=True)
            pending.write_text('{"payload":{"action":"add","content":"sk-aaaaaaaaaaaaaaaaaaaaaaaa"}}')
            request = review.inventory_pending(home).requests[0]
            catalog = review.Catalog(1, (review.Criterion(
                "clear", 1, "Is it unclear?", {}, {"yes":"yes","no":"no"}, [], []),))
            with patch.object(review, "evaluate_with_jev", side_effect=AssertionError("remote evaluator called")), \
                 patch.object(review, "evaluate_with_headless", side_effect=AssertionError("Copilot evaluator called")):
                result = review.evaluate_one_for_runtime(request, catalog, "copilot")
            self.assertEqual(result.status, "RETAINED LOCALLY")
            self.assertEqual(result.results, {})


if __name__ == "__main__":
    unittest.main()
