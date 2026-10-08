"""F11 integration with the real Hermes plugin manager and TUI admission/queue.

Run with Hermes' dependency closure: hermes --run-module unittest discover -s tests
-p test_run_awareness_host.py -v. Agent/provider execution is deliberately stubbed;
these tests exercise the host and hooks, not a live model or application task.
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thesystem import run_awareness as awareness

try:
    from hermes_cli.plugins import get_plugin_manager
    from tui_gateway import server
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


def wait_for(predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.03)
    return False


@unittest.skipUnless(AVAILABLE, "run with Hermes runtime for native host integration")
class NativeHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home, self.ws = self.root / "home", self.root / "ws"
        self.ws.mkdir()
        awareness.install_files(Path(__file__).resolve().parents[1], self.home, self.ws, "applus")
        (self.home / "config.yaml").write_text("plugins:\n  enabled: [thesystem-runs]\n  entries:\n"
                                              "    thesystem-runs:\n      allow_gateway_injection: true\n")
        env = patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.manager = get_plugin_manager()
        self.manager.discover_and_load(force=True)
        self.addCleanup(self.manager.unload)
        details = next((p for p in self.manager.list_plugins() if p['name'] == 'thesystem-runs'), {})
        self.assertTrue(details.get('enabled'), details)
        self.assertFalse(details.get('error'), details)
        self.monitor = awareness.Monitor(self.ws, self.home)
        self.event_id = awareness.identity(self.ws, "first", "run1")
        self.record_path = self.ws / "p/tickets/T/tasks/first/runs/run1/run.json"
        self.notice = {"task": "first", "run": "run1", "status": "pre-done",
                       "origin": {"home": str(self.home), "session_key": "ses-origin"}}
        sessions = patch.object(server, "_sessions", {})
        sessions.start()
        self.addCleanup(sessions.stop)
        server.install_tui_message_injector(self.manager)
        self.addCleanup(server.clear_tui_message_injector, self.manager)

    def session(self, key, busy):
        return {"agent": SimpleNamespace(), "session_key": key, "history": [],
                "history_lock": threading.Lock(), "history_version": 0, "running": busy,
                "transport": None, "attached_images": [], "last_active": 1.0}

    def state(self):
        with self.monitor.connect() as db:
            row = db.execute("SELECT state FROM events WHERE id=?", (self.event_id,)).fetchone()
        return row[0] if row else None

    def test_real_manager_loads_plugin_busy_queue_and_hooks_ack(self):
        origin, other = self.session("ses-origin", True), self.session("ses-other", True)
        server._sessions.update({"ui-origin": origin, "ui-other": other})
        awareness.atomic_json(self.record_path, self.notice)
        self.assertTrue(wait_for(lambda: origin.get("queued_prompt") is not None))
        self.assertIsNone(other.get("queued_prompt"))
        self.assertTrue(wait_for(lambda: self.state() == "admitted"))
        text = origin["queued_prompt"]["text"]
        self.assertIn(self.event_id, text)
        self.manager.invoke_hook("pre_llm_call", user_message=text, conversation_history=[],
                                 session_id="ses-origin", is_first_turn=False)
        self.assertEqual(self.state(), "processing")
        self.manager.invoke_hook("on_session_end", session_id="ses-origin", completed=True,
                                 failed=False, interrupted=False)
        self.assertEqual(self.state(), "processed")
        before = json.dumps(origin["queued_prompt"])
        time.sleep(2.2)
        self.assertEqual(json.dumps(origin["queued_prompt"]), before)
        self.assertEqual(self.state(), "processed")
        directive = self.manager.invoke_hook("pre_tool_call", tool_name="terminal",
                                             args={"command": "applus run"}, session_id="ses-origin")
        self.assertTrue(any(r.get("action") == "modify" for r in directive if isinstance(r, dict)))

    def test_missing_origin_retained_then_real_idle_host_starts_correct_turn(self):
        other = self.session("ses-other", True)
        server._sessions["ui-other"] = other
        awareness.atomic_json(self.record_path, self.notice)
        self.assertTrue(wait_for(lambda: self.state() == "pending"))
        self.assertIsNone(other.get("queued_prompt"))
        entered = threading.Event()
        observed = {}
        def provider_boundary(rid, sid, session, text, **kwargs):
            observed.update(sid=sid, text=text)
            self.manager.invoke_hook("pre_llm_call", user_message=text, session_id="ses-origin")
            self.manager.invoke_hook("on_session_end", session_id="ses-origin", completed=True, failed=False)
            entered.set()
        with patch.object(server, "_run_prompt_submit", provider_boundary), \
             patch.object(server, "_session_uses_compute_host", return_value=False):
            server._sessions["ui-origin"] = self.session("ses-origin", False)
            self.assertTrue(entered.wait(6))
        self.assertEqual(observed["sid"], "ui-origin")
        self.assertEqual(self.state(), "processed")
        self.assertIsNone(other.get("queued_prompt"))


if __name__ == "__main__":
    unittest.main()
