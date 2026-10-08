"""F11: offline fixtures; no real agents, model calls or application tasks."""
import fcntl
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from thesystem import run_awareness as awareness
from test_tasks import WorkspaceCase

ROOT = Path(__file__).resolve().parents[1]


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ws = self.root / "ws"
        self.ws.mkdir()
        self.home = self.root / "profile"
        self.monitor = awareness.Monitor(self.ws, self.home)

    def run_record(self, task="first", run="run-1", status="running", stage="worker", linked=True):
        path = self.ws / f"project/tickets/T/tasks/{task}/runs/{run}/run.json"
        value = {"task": task, "run": run, "status": status, "stage": stage,
                 "origin": {"home": str(self.home), "session_key": "origin"} if linked else None}
        awareness.atomic_json(path, value)
        return path

    def state(self, event_id):
        with self.monitor.connect() as db:
            return db.execute("SELECT state FROM events WHERE id=?", (event_id,)).fetchone()[0]

    def test_worker_reviewer_parallel_retained_results_and_dismissal(self):
        path = self.run_record()
        self.run_record(task="second", stage="reviewer")
        self.assertEqual({r["stage"] for r in self.monitor.snapshot()["runs"]}, {"worker", "reviewer"})
        for outcome in awareness.TERMINAL:
            self.run_record(task=outcome, status=outcome)
        rows = self.monitor.snapshot()["runs"]
        self.assertEqual(len(rows), 5)
        result = next(r for r in rows if r["status"] == "pre-done")
        before = path.read_bytes()
        self.assertTrue(self.monitor.dismiss(result["id"]))
        self.assertFalse(self.monitor.dismiss(rows[0]["id"]))
        self.assertEqual(path.read_bytes(), before)
        again = awareness.Monitor(self.ws, self.home)
        self.assertEqual(len(again.snapshot()["runs"]), 4)
        self.assertFalse((self.ws / ".thesystem/dispatcher.lock").exists())

    def test_lock_uncertain_is_not_a_final_status(self):
        self.run_record()
        self.assertTrue(self.monitor.snapshot()["runs"][0]["possibly_stale"])
        lock = self.ws / ".thesystem/dispatcher.lock"
        lock.parent.mkdir()
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertFalse(self.monitor.snapshot()["runs"][0]["possibly_stale"])
            self.assertEqual(self.monitor.snapshot()["runs"][0]["status"], "running")

    def test_malformed_truncated_and_old_metadata_are_safe(self):
        old = self.run_record()
        record = json.loads(old.read_text())
        del record["stage"]
        awareness.atomic_json(old, record)
        (old.parent / "reviewer-prompt.md").write_text("fixture")
        bad = self.run_record(task="bad")
        bad.write_text('{"status":')
        self.run_record(task="wrong").write_text(json.dumps({"task": "different", "run": "run-1", "status": "running"}))
        rows = self.monitor.snapshot()
        self.assertEqual(rows["skipped"], 2)
        self.assertEqual(rows["runs"][0]["stage"], "reviewer")
        with patch.object(awareness, "MAX_RUNS", 0):
            self.assertTrue(self.monitor.snapshot()["truncated"])
        bad.write_text("x" * (awareness.MAX_BYTES + 1))
        self.assertEqual(self.monitor.snapshot()["skipped"], 2)

    def test_originless_and_other_profile_never_deliver(self):
        self.run_record(status="failed", linked=False)
        foreign = self.run_record(task="foreign", status="failed")
        record = json.loads(foreign.read_text())
        record["origin"]["home"] = str(self.root / "other")
        awareness.atomic_json(foreign, record)
        calls = []
        self.monitor.deliver(lambda *a, **kw: calls.append((a, kw)))
        self.assertEqual(calls, [])
        self.assertEqual(len(self.monitor.snapshot()["runs"]), 2)

    def test_rejected_pending_admitted_not_acknowledged_then_processed_once(self):
        self.run_record(status="pre-done")
        event_id = awareness.identity(self.ws, "first", "run-1")
        calls = []
        self.assertEqual(self.monitor.deliver(lambda *a, **k: False), 0)
        self.assertEqual(self.state(event_id), "pending")
        def inject(message, **kw):
            calls.append((message, kw))
            return True
        self.assertEqual(self.monitor.deliver(inject), 1)
        self.assertEqual(calls[0][1], {"session_key": "origin"})
        self.assertEqual(self.state(event_id), "admitted")
        again = awareness.Monitor(self.ws, self.home)
        self.assertEqual(again.deliver(inject), 0)
        self.assertFalse(again.processing(event_id, "another-chat"))
        self.assertTrue(again.processing(event_id, "origin"))
        again.acknowledge(event_id, True)
        self.assertEqual(self.state(event_id), "processed")
        self.assertEqual(again.deliver(inject), 0)
        self.assertEqual(len(calls), 1)

    def test_interrupted_and_crashed_consumers_remain_deliverable(self):
        self.run_record(status="failed")
        event_id = awareness.identity(self.ws, "first", "run-1")
        self.monitor.deliver(lambda *a, **kw: True)
        self.monitor.processing(event_id, "origin")
        self.monitor.acknowledge(event_id, False)
        self.assertEqual(self.state(event_id), "pending")
        self.assertEqual(self.monitor.deliver(lambda *a, **kw: True), 1)
        with self.monitor.connect() as db:
            db.execute("UPDATE events SET owner='99999999:0' WHERE id=?", (event_id,))
        self.assertEqual(awareness.Monitor(self.ws, self.home).deliver(lambda *a, **kw: True), 1)

    def test_reentrant_ack_not_overwritten_and_dismiss_not_delivery_ack(self):
        self.run_record(status="failed")
        event_id = awareness.identity(self.ws, "first", "run-1")
        self.assertTrue(self.monitor.dismiss(event_id))
        def inject(*args, **kwargs):
            self.monitor.processing(event_id, "origin")
            self.monitor.acknowledge(event_id, True)
            return True
        self.monitor.deliver(inject)
        self.assertEqual(self.state(event_id), "processed")
        self.assertEqual(self.monitor.snapshot()["runs"], [])

    def test_publication_follows_evidence_and_recovers_without_event_file(self):
        path = self.run_record(status="changes-requested")
        awareness.publish_completion(self.ws, json.loads(path.read_text()), path.parent)
        files = list((self.ws / ".thesystem/notifications").glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text())["evidence"], str(path.parent))
        files[0].unlink()
        self.assertEqual(self.monitor.deliver(lambda *a, **k: True), 1)

    def test_safe_read_and_identical_run_names_across_workspaces(self):
        path = self.run_record()
        outside = self.root / "outside.json"
        outside.write_text(json.dumps({"secret": "fixture"}))
        path.unlink()
        path.symlink_to(outside)
        self.assertIsNone(awareness.read_json(path, self.ws))
        self.assertNotEqual(awareness.identity(self.ws, "first", "run-1"),
                            awareness.identity(self.root / "second", "first", "run-1"))

    def test_new_unlinked_launch_does_not_inherit_old_origin(self):
        with patch.dict(os.environ, {"THESYSTEM_SESSION_KEY": "origin", "THESYSTEM_ORIGIN_HOME": str(self.home)}):
            awareness.capture_origin(self.ws, ["first"])
        origin = awareness.task_origin(self.ws, "first")
        assert origin is not None
        self.assertEqual(origin["session_key"], "origin")
        with patch.dict(os.environ, {"THESYSTEM_SESSION_KEY": "", "THESYSTEM_ORIGIN_HOME": ""}):
            awareness.capture_origin(self.ws, ["first"])
        self.assertIsNone(awareness.task_origin(self.ws, "first"))

    def test_install_preserves_state_and_changes_only_selected_home(self):
        self.run_record(status="pre-done")
        self.monitor.deliver(lambda *a, **k: False)
        before = self.monitor.database.read_bytes()
        awareness.install_files(ROOT, self.home, self.ws, "applus")
        awareness.install_files(ROOT, self.home, self.ws, "applus")
        self.assertEqual(before, self.monitor.database.read_bytes())
        self.assertTrue((self.home / "tui-widgets/thesystem-runs.mjs").is_file())
        self.assertFalse((self.root / "other").exists())

    def test_plugin_real_hook_shapes_origin_and_ack(self):
        awareness.install_files(ROOT, self.home, self.ws, "applus")
        folder = self.home / "plugins/thesystem-runs"
        spec = importlib.util.spec_from_file_location("fixture_runs_plugin", folder / "__init__.py",
                                                    submodule_search_locations=[str(folder)])
        assert spec is not None and spec.loader is not None
        plugin = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = plugin
        self.addCleanup(lambda: sys.modules.pop(spec.name, None))
        spec.loader.exec_module(plugin)
        class Context:
            logger = __import__('logging').getLogger("test")
            def __init__(self): self.hooks, self.unload = {}, lambda: None
            def get_config(self, key, default=None): return default
            def register_hook(self, name, callback): self.hooks[name] = callback
            def register_command(self, *a, **kw): pass
            def on_unload(self, callback): self.unload = callback
            def inject_message(self, *a, **kw): return False
        ctx = Context()
        from types import SimpleNamespace
        public_api = SimpleNamespace(get_plugin_manager=lambda: SimpleNamespace(has_tui_message_injector=False))
        with patch.dict(sys.modules, {"hermes_cli.plugins": public_api}):
            plugin.register(ctx)
        self.addCleanup(ctx.unload)
        hook = ctx.hooks["pre_tool_call"]
        rewritten = hook("terminal", {"command": "applus retry first"}, session_id="ses_origin")
        self.assertIn("THESYSTEM_SESSION_KEY=ses_origin", rewritten["args"]["command"])
        self.assertIsNone(hook("terminal", {"command": "applus run; anything"}, session_id="ses_origin"))
        self.assertIsNone(hook("terminal", {"command": "other run"}, session_id="ses_origin"))
        self.run_record(status="pre-done")
        self.monitor.ingest()
        event_id = awareness.identity(self.ws, "first", "run-1")
        ctx.hooks["pre_llm_call"](user_message=f"[theSystem completion {event_id}]", session_id="origin")
        self.assertEqual(self.state(event_id), "processing")
        ctx.hooks["on_session_end"](session_id="origin", completed=True, failed=False, interrupted=False)
        self.assertEqual(self.state(event_id), "processed")


class OrchestratorOriginTests(WorkspaceCase):
    def test_real_dispatcher_with_offline_agents_preserves_origin_and_publishes_final(self):
        self.add_task("notice", "status: ready\nsource_clone: backend")
        self.env.update(THESYSTEM_SESSION_KEY="origin", THESYSTEM_ORIGIN_HOME=str(self.ws / "profile"))
        self.assertEqual(self.command("run")["status"], "ok")
        self.wait_idle()
        path = self.latest_run("notice")
        record = json.loads((path / "run.json").read_text())
        self.assertEqual(record["status"], "pre-done")
        self.assertEqual(record["stage"], "reviewer")
        self.assertEqual(record["origin"]["session_key"], "origin")
        events = list((self.ws / ".thesystem/notifications").glob("*.json"))
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(events[0].read_text())["status"], "pre-done")
        monitor = awareness.Monitor(self.ws, self.ws / "profile")
        self.assertEqual(monitor.deliver(lambda *a, **k: True), 1)


if __name__ == "__main__":
    unittest.main()
