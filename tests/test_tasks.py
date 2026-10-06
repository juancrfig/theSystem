"""F2 · Projects, F3 · Roles, F4 · Tasks, F6 · Run evidence, F7 · The command.

`hermes` is replaced by a stub on PATH: it edits a file as the worker and answers
with the verdict in $FAKE_VERDICT as the reviewer. A real Hermes run is a manual check.
"""
import json
import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FAKE_HERMES = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
prompt = open(args[args.index("--query-file") + 1]).read()
cwd = args[args.index("--in") + 1]
profile = args[args.index("-p") + 1]
if profile != ("worker" if prompt.startswith("You are the worker") else "reviewer"):
    sys.exit(9)  # each agent must run in its own Hermes profile
print(json.dumps({"type": "system", "subtype": "init", "session_id": "fake",
                  "safe_root": os.environ.get("HERMES_WRITE_SAFE_ROOT"),
                  "toolsets": args[args.index("-t") + 1] if "-t" in args else None}))
if prompt.startswith("You are the worker"):
    mode = os.environ.get("FAKE_WORKER", "edit")
    if mode == "crash":
        sys.exit(3)
    if mode == "switch-branch":
        import subprocess
        subprocess.run(["git", "checkout", "-q", "-b", "elsewhere"], cwd=cwd, check=True)
    if mode == "edit":
        with open(os.path.join(cwd, "feature.txt"), "a") as f:
            f.write("done\n")
    text = "finished"
else:
    text = "Looks fine.\nVERDICT: " + os.environ.get("FAKE_VERDICT", "PASS")
print(json.dumps({"type": "result", "session_id": "fake", "exit_code": 0, "text": text}))
'''


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        (self.ws / "agents" / "rules").mkdir(parents=True)
        (self.ws / "agents" / "rules" / "global.md").write_text("Rule: global rule text\n")
        (self.ws / "agents" / "roles.yaml").write_text(textwrap.dedent("""\
            worker:
              rules:
                - rules/global.md
            reviewer: {}
            """))
        self.project = self.ws / "app"
        self.clone = self.project / "backend"
        self.clone.mkdir(parents=True)
        git(self.clone, "init", "-q", "-b", "main")
        (self.clone / "README").write_text("app\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-q", "-m", "init")
        bin_dir = self.ws / "bin"
        bin_dir.mkdir()
        (bin_dir / "hermes").write_text(FAKE_HERMES)
        (bin_dir / "hermes").chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PYTHONPATH": str(REPO),
                    "THESYSTEM_WORKSPACE": str(self.ws), "FAKE_VERDICT": "PASS", "FAKE_WORKER": "edit"}

    def add_task(self, task_id, front_matter):
        path = self.project / "tickets" / "T1" / "tasks" / task_id / "task.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"---\n{textwrap.dedent(front_matter).strip()}\n---\n\nBuild {task_id}.\n")
        return path

    def command(self, *args):
        result = subprocess.run(["python3", "-m", "thesystem.cli", *args], env=self.env, capture_output=True,
                                text=True, cwd=REPO)
        return json.loads(result.stdout)

    def status(self, task_id):
        path = next(self.ws.glob(f"*/tickets/*/tasks/{task_id}/task.md"))
        for line in path.read_text().splitlines():
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip()

    def wait_idle(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with open(self.ws / ".thesystem" / "dispatcher.lock", "a+") as lock:
                import fcntl
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(lock, fcntl.LOCK_UN)
                    if not any(self.status(p.parent.name) in ("ready", "running")
                               for p in self.ws.glob("*/tickets/*/tasks/*/task.md")):
                        return
                except BlockingIOError:
                    pass
            time.sleep(0.3)
        self.fail("dispatcher did not finish")

    def latest_run(self, task_id):
        return sorted(next(self.ws.glob(f"*/tickets/*/tasks/{task_id}")).glob("runs/*"))[-1]


class TaskFlowTests(WorkspaceCase):
    def test_passed_review_goes_pre_done_and_merge_makes_it_done(self):
        self.add_task("a", "status: ready\nsource_clone: backend")
        self.assertEqual(self.command("run")["status"], "ok")
        self.wait_idle()
        self.assertEqual(self.status("a"), "pre-done")
        self.assertFalse((self.clone / "feature.txt").exists(), "not merged before the human says so")

        merged = self.command("merge", "a")
        self.assertEqual(merged["status"], "ok", merged)
        self.assertEqual(self.status("a"), "done")
        self.assertTrue((self.clone / "feature.txt").exists())

    def test_rejected_review_is_changes_requested_and_retry_runs_again(self):
        self.add_task("a", "status: ready\nsource_clone: backend")
        self.env["FAKE_VERDICT"] = "FAIL"
        self.command("run")
        self.wait_idle()
        self.assertEqual(self.status("a"), "changes-requested")

        self.env["FAKE_VERDICT"] = "PASS"
        self.assertEqual(self.command("retry", "a")["status"], "ok")
        self.wait_idle()
        self.assertEqual(self.status("a"), "pre-done")
        self.assertEqual(len(list(next(self.ws.glob("*/tickets/*/tasks/a")).glob("runs/*"))), 2)

    def test_worker_crash_is_failed(self):
        self.add_task("a", "status: ready\nsource_clone: backend")
        self.env["FAKE_WORKER"] = "crash"
        self.command("run")
        self.wait_idle()
        self.assertEqual(self.status("a"), "failed")
        record = json.loads((self.latest_run("a") / "run.json").read_text())
        self.assertEqual(record["error"]["code"], "WORKER_FAILED")

    def test_worker_leaving_its_branch_is_failed(self):
        self.add_task("a", "status: ready\nsource_clone: backend")
        self.env["FAKE_WORKER"] = "switch-branch"
        self.command("run")
        self.wait_idle()
        self.assertEqual(self.status("a"), "failed")
        run = self.latest_run("a")
        record = json.loads((run / "run.json").read_text())
        self.assertEqual(record["error"]["code"], "ISOLATION_BROKEN")
        self.assertIn(f'"safe_root": "{record["worktree"]}"', (run / "worker.jsonl").read_text(),
                      "Hermes' file tools are confined to the worktree")

    def test_blocked_task_waits_for_blocker_to_be_done(self):
        self.add_task("first", "status: ready\nsource_clone: backend")
        self.add_task("second", "status: ready\nsource_clone: backend\nblockers:\n  - task: first")
        self.command("run")
        self.wait_idle()
        self.assertEqual(self.status("first"), "pre-done")
        self.assertEqual(self.status("second"), "blocked")

        self.command("merge", "first")
        self.wait_idle()
        self.assertEqual(self.status("second"), "pre-done")

    def test_external_blocker_holds_task(self):
        self.add_task("a", 'status: ready\nsource_clone: backend\nblockers:\n  - external: "waiting for keys"')
        self.command("run")
        self.wait_idle()
        self.assertEqual(self.status("a"), "blocked")

    def test_merge_and_retry_refuse_wrong_states(self):
        self.add_task("a", "status: blocked\nsource_clone: backend\nblockers:\n  - external: x")
        self.assertEqual(self.command("merge", "a")["code"], "NOT_PRE_DONE")
        self.assertEqual(self.command("retry", "a")["code"], "NOT_RETRYABLE")
        self.assertEqual(self.command("merge", "missing")["code"], "TASK_NOT_FOUND")


class EvidenceAndRolesTests(WorkspaceCase):
    def test_run_keeps_all_evidence_and_exact_role_context(self):
        project_agents = self.project / "agents"
        (project_agents / "rules").mkdir(parents=True)
        (project_agents / "rules" / "project.md").write_text("Rule: project rule text\n")
        (project_agents / "roles.yaml").write_text("worker:\n  rules:\n    - rules/project.md\n")
        self.add_task("a", "status: ready\nsource_clone: backend\nroles: [worker]")
        self.command("run")
        self.wait_idle()
        run = self.latest_run("a")
        for name in ("run.json", "review.md", "worker.diff", "worker.jsonl", "reviewer.jsonl",
                     "worker-prompt.md", "reviewer-prompt.md", "orchestrator.log"):
            self.assertTrue((run / name).is_file(), name)
        self.assertIn("feature.txt", (run / "worker.diff").read_text())
        self.assertIn("VERDICT: PASS", (run / "review.md").read_text())
        worker_prompt = (run / "worker-prompt.md").read_text()
        self.assertIn("project rule text", worker_prompt, "project role replaces the global one")
        self.assertNotIn("global rule text", worker_prompt)
        self.assertTrue((run / "worker-context" / "rules" / "project.md").is_file())
        self.assertIn("project rule text", (run / "reviewer-prompt.md").read_text(),
                      "the reviewer gets the worker's rules")

    def test_roles_tools_are_the_hermes_toolsets_each_agent_gets(self):
        (self.ws / "agents" / "roles.yaml").write_text(textwrap.dedent("""\
            worker:
              tools: [terminal, file, web]
            reviewer: {}
            """))
        self.add_task("a", "status: ready\nsource_clone: backend\nroles: [worker]")
        self.command("run")
        self.wait_idle()
        run = self.latest_run("a")
        init = lambda name: json.loads((run / f"{name}.jsonl").read_text().splitlines()[0])
        self.assertEqual(init("worker")["toolsets"], "terminal,file,web")
        self.assertEqual(init("reviewer")["toolsets"], "none", "no tools listed: no tools")
        record = json.loads((run / "run.json").read_text())
        self.assertEqual(record["toolsets"], {"worker": ["terminal", "file", "web"], "reviewer": []})

    def test_base_role_comes_first_for_every_agent(self):
        (self.ws / "agents" / "roles.yaml").write_text(textwrap.dedent("""\
            base:
              tools: [terminal, delegation]
              rules:
                - rules/global.md
            frontend:
              tools: [browser]
            reviewer: {}
            """))
        self.add_task("a", "status: ready\nsource_clone: backend\nroles: [frontend]")
        self.command("run")
        self.wait_idle()
        run = self.latest_run("a")
        record = json.loads((run / "run.json").read_text())
        self.assertEqual(record["toolsets"], {"worker": ["terminal", "delegation", "browser"],
                                              "reviewer": ["terminal", "delegation"]})
        self.assertIn("global rule text", (run / "worker-prompt.md").read_text(), "base rules reach a specialist task")
        self.assertIn("global rule text", (run / "reviewer-prompt.md").read_text())

    def test_unknown_role_fails_the_run(self):
        self.add_task("a", "status: ready\nsource_clone: backend\nroles: [nobody]")
        self.command("run")
        self.wait_idle()
        self.assertEqual(self.status("a"), "failed")
        record = json.loads((self.latest_run("a") / "run.json").read_text())
        self.assertEqual(record["error"]["code"], "ROLE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
