"""Native Hermes plugin. Observes runs; never approves, merges or retries them."""
from __future__ import annotations

import json
import re
import shlex
import threading
from pathlib import Path

from importlib import import_module

Monitor = import_module(str(__package__) + ".awareness").Monitor

_MARKER = re.compile(r"\[theSystem completion ([a-f0-9]{64})\]")


def register(ctx):
    from hermes_cli.plugins import get_plugin_manager

    manager = get_plugin_manager()  # Capture the registering profile, not a polling thread's ambient home.
    installation = json.loads((Path(__file__).parent / "installation.json").read_text())
    home = Path(installation["home"])
    workspace = Path(ctx.get_config("workspace", installation["workspace"]) or installation["workspace"])
    monitor = Monitor(workspace, home)
    stopped = threading.Event()
    active = {}
    guard = threading.Lock()

    def pre_tool(tool_name, args, session_id="", **kwargs):
        if tool_name != "terminal" or not session_id:
            return None
        command = args.get("command", "")
        try:
            tokens = shlex.split(command)
        except ValueError:
            return None
        # Only a simple, direct launcher invocation; never parse/rewrite arbitrary shell scripts.
        if len(tokens) < 2 or Path(tokens[0]).name != installation["company"]:
            return None
        if tokens[1] not in {"run", "retry"} or any(c in command for c in "\n;&|`$<>()"):
            return None
        prefix = ("THESYSTEM_SESSION_KEY=" + shlex.quote(session_id) + " THESYSTEM_ORIGIN_HOME=" +
                  shlex.quote(str(home)) + " ")
        return {"action": "modify", "args": {"command": prefix + command}}

    def pre_llm(user_message="", session_id="", **kwargs):
        # Acknowledge consumption, not admission; never inspect replayed conversation history.
        if not isinstance(user_message, str):
            return
        for event_id in _MARKER.findall(user_message):
            if monitor.processing(event_id, session_id):
                with guard:
                    active.setdefault(session_id, set()).add(event_id)

    def end(session_id="", completed=False, interrupted=False, failed=False, **kwargs):
        with guard:
            events = active.pop(session_id, set())
        for event_id in events:
            monitor.acknowledge(event_id, bool(completed) and not interrupted and not failed)

    def poll():
        while not stopped.is_set():
            try:
                # Classic CLI injection ignores session_key. Only use the session-routing TUI host.
                if manager.has_tui_message_injector and ctx.get_config("allow_gateway_injection", False):
                    # Use the public, profile-bound TUI host entrypoint. ctx.inject_message falls
                    # back to other surfaces after a TUI refusal, which must not reroute an origin.
                    monitor.deliver(manager.inject_tui_message)
            except Exception as exc:
                ctx.logger.warning("Run awareness poll failed (%s); will retry", type(exc).__name__)
            stopped.wait(2)

    def command(args="", **kwargs):
        words = shlex.split(args)
        if not words or words == ["status"]:
            snapshot = monitor.snapshot()
            lines = [f"{r['task']} / {r['run']}: {r['status']} ({r['stage']})" +
                     (" — possibly stale" if r['possibly_stale'] else "") for r in snapshot["runs"]]
            return "\n".join(lines) or "No orchestrator runs."
        if len(words) == 2 and words[0] == "dismiss":
            return "Result dismissed." if monitor.dismiss(words[1]) else "No matching finished result."
        return "Usage: /runs [status | dismiss <event-id>]. Dismissal does not acknowledge notification delivery."

    ctx.register_hook("pre_tool_call", pre_tool)
    ctx.register_hook("pre_llm_call", pre_llm)
    ctx.register_hook("on_session_end", end)
    ctx.register_command("runs", command, description="Show runs or dismiss a retained finished result")
    thread = threading.Thread(target=poll, name="thesystem-runs", daemon=True)
    ctx.on_unload(lambda: (stopped.set(), thread.join(timeout=3)))
    thread.start()
