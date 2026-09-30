"""Project operations own retry eligibility and immutable evidence reads."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from thesystem.errors import CodedError
from thesystem.project_operations import ProjectOperationError, read_evidence, retry_task


class ProjectOperationTests(unittest.TestCase):
    def test_retry_operation_checks_eligibility_and_starts_without_cli_dispatch(self):
        class OrchestratorFixture:
            def __init__(self, _project):
                self.state = {
                    "tasks": {"job": {"approval": "approved"}},
                    "runs": {"old": {"task_id": "job", "status": "execution-failed", "finished_at": "2026-01-01"}},
                }

            def task(self, task_id):
                if task_id not in self.state["tasks"]:
                    raise CodedError("TASK_NOT_FOUND", task_id)
                return self.state["tasks"][task_id]

            def start(self, task_id, detach=False):
                return {"id": "new", "task_id": task_id, "detach": detach}

        with patch("the_system_orchestrator.Orchestrator", OrchestratorFixture):
            self.assertEqual(retry_task("/fixture/project", "job"),
                             {"id": "new", "task_id": "job", "detach": True})

    def test_retry_operation_rejects_non_retryable_or_unapproved_work(self):
        class OrchestratorFixture:
            def __init__(self, _project):
                self.state = {"tasks": {"job": {"approval": "proposed"}},
                              "runs": {"old": {"task_id": "job", "status": "passed"}}}

            def task(self, task_id):
                return self.state["tasks"][task_id]

            def start(self, *_args, **_kwargs):
                raise AssertionError("non-retryable task must not start")

        with patch("the_system_orchestrator.Orchestrator", OrchestratorFixture):
            with self.assertRaises(ProjectOperationError) as failure:
                retry_task("/fixture/project", "job")
        self.assertEqual(failure.exception.code, "RETRY_NOT_ALLOWED")

    def test_retry_operation_preserves_unknown_task_domain_error(self):
        class OrchestratorFixture:
            def __init__(self, _project):
                self.state = {"tasks": {}, "runs": {}}

            def task(self, task_id):
                raise CodedError("TASK_NOT_FOUND", task_id)

        with patch("the_system_orchestrator.Orchestrator", OrchestratorFixture):
            with self.assertRaises(CodedError) as failure:
                retry_task("/fixture/project", "missing")
        self.assertEqual(failure.exception.code, "TASK_NOT_FOUND")

    def test_evidence_operation_reads_matching_record_and_refuses_symlinks_and_malformed_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_dir = project / ".thesystem/orchestrator/runs"
            run_dir.mkdir(parents=True)
            record_path = run_dir / "run-1.json"
            record_path.write_text(json.dumps({"id": "run-1", "status": "passed"}))
            self.assertEqual(read_evidence(project, "run-1")["status"], "passed")

            (run_dir / "wrong.json").write_text(json.dumps({"id": "other"}))
            with self.assertRaises(ProjectOperationError) as failure:
                read_evidence(project, "wrong")
            self.assertEqual(failure.exception.code, "EVIDENCE_INVALID")

            (run_dir / "link.json").symlink_to(record_path)
            with self.assertRaises(ProjectOperationError) as failure:
                read_evidence(project, "link")
            self.assertEqual(failure.exception.code, "EVIDENCE_INVALID")

    def test_evidence_operation_reports_missing_and_invalid_run_ids(self):
        with self.assertRaises(ProjectOperationError) as failure:
            read_evidence("/fixture/project", "../outside")
        self.assertEqual(failure.exception.code, "EVIDENCE_USAGE")
        with self.assertRaises(ProjectOperationError) as failure:
            read_evidence("/fixture/project", "missing")
        self.assertEqual(failure.exception.code, "EVIDENCE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
