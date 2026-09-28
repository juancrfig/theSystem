import json
import hashlib
import http.client
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from the_system_orchestrator import HostCredentialBroker, Orchestrator, OrchestratorError

ROOT = Path(__file__).resolve().parents[1]

class OrchestratorTests(unittest.TestCase):
    def repo(self, root):
        repo = root / "src"; repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        (repo / "README").write_text("base\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        return repo

    def fake_docker(self, root):
        docker = root / "docker"
        docker.write_text("""#!/usr/bin/env python3
import os, subprocess, sys
mount = next(x.split(':', 1)[0] for x in sys.argv if x.startswith('/') and ':' in x)
command = sys.argv[-1]
p = subprocess.run(['sh', '-lc', command], cwd=mount, text=True)
raise SystemExit(p.returncode)
""")
        docker.chmod(0o755)
        return docker

    def read_contract(self, task_file: Path) -> tuple[dict, str]:
        text = task_file.read_text()
        self.assertTrue(text.startswith("---\n"))
        end = text.find("\n---\n", 4)
        self.assertNotEqual(end, -1)
        return json.loads(text[4:end]), text[end + 5 :]

    def write_contract(self, task_file: Path, contract: dict, body: str):
        task_file.write_text("---\n" + json.dumps(contract, indent=2, sort_keys=True) + "\n---\n" + body)

    def fixture_agents(self, root: Path) -> tuple[Path, Path]:
        global_agents = root / "global-agents"
        project_agents = root / "project" / "agents"
        (global_agents / "rules").mkdir(parents=True)
        (global_agents / "skills" / "kit").mkdir(parents=True)
        (project_agents / "rules").mkdir(parents=True)
        (project_agents / "skills" / "kit").mkdir(parents=True)
        (global_agents / "rules" / "base.md").write_text("global-base\n")
        (global_agents / "rules" / "worker.md").write_text("global-worker\n")
        (global_agents / "rules" / "reviewer.md").write_text("global-reviewer\n")
        (global_agents / "skills" / "kit" / "SKILL.md").write_text("global skill\n")
        (global_agents / "skills" / "kit" / "guide.md").write_text("global guide\n")
        (project_agents / "rules" / "worker.md").write_text("project-worker-override\n")
        (project_agents / "skills" / "kit" / "SKILL.md").write_text("project skill override\n")
        (project_agents / "roles.yaml").write_text(json.dumps({
            "custom": {
                "rules": ["rules/worker.md"],
                "skills": ["skills/kit"]
            }
        }, indent=2) + "\n")
        (global_agents / "roles.yaml").write_text(json.dumps({
            "base": {"rules": ["rules/base.md"]},
            "worker": {"rules": ["rules/worker.md"], "skills": ["skills/kit"]},
            "reviewer": {"rules": ["rules/reviewer.md"]}
        }, indent=2) + "\n")
        return global_agents, project_agents

    def test_provider_secret_is_redacted_before_worker_output_becomes_evidence(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);o=Orchestrator(root);prompt=root/"prompt";prompt.write_text("task")
            secret="TEST_SECRET_DO_NOT_USE"
            completed=subprocess.CompletedProcess(["docker"],0,stdout="debug "+secret,stderr="warning "+secret)
            env={"THESYSTEM_BROKER_UPSTREAM_URL":"http://127.0.0.1:9/v1","THESYSTEM_BROKER_PROVIDER_KEY":secret,"THESYSTEM_BROKER_MODEL":"model-a","COPILOT_GITHUB_TOKEN":"HOST_ONLY_TEST_TOKEN"}
            with patch.dict(os.environ,env),patch("the_system_orchestrator.subprocess.run",return_value=completed) as run:
                result=o._docker("test-image",root,["copilot"],10,prompt,runtime="copilot")
            args=run.call_args.args[0]
            self.assertNotIn(secret," ".join(args))
            self.assertNotIn("HOST_ONLY_TEST_TOKEN"," ".join(args))
            self.assertEqual(args[args.index("--network")+1],"none")
            self.assertIn("HOME=/run/copilot-home", args)
            self.assertIn("XDG_CACHE_HOME=/run/copilot-home/.cache", args)
            self.assertNotIn(secret,str(run.call_args.kwargs["env"]))
            self.assertNotIn("HOST_ONLY_TEST_TOKEN",str(run.call_args.kwargs["env"]))
            self.assertNotIn(secret,result.stdout+result.stderr)
            self.assertIn("[REDACTED]",result.stdout)
            self.assertIn("[REDACTED]",result.stderr)

    def test_container_network_mode_override_and_validation(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);o=Orchestrator(root);prompt=root/"prompt";prompt.write_text("task")
            completed=subprocess.CompletedProcess(["docker"],0,stdout="ok",stderr="")
            env={
                "THESYSTEM_BROKER_UPSTREAM_URL":"http://127.0.0.1:9/v1",
                "THESYSTEM_BROKER_PROVIDER_KEY":"TEST_SECRET",
                "THESYSTEM_BROKER_MODEL":"model-a",
                "THESYSTEM_CONTAINER_NETWORK":"bridge",
            }
            with patch.dict(os.environ,env),patch("the_system_orchestrator.subprocess.run",return_value=completed) as run:
                o._docker("test-image",root,["copilot"],10,prompt,runtime="copilot")
            args=run.call_args.args[0]
            self.assertEqual(args[args.index("--network")+1],"bridge")
            with patch.dict(os.environ,{**env,"THESYSTEM_CONTAINER_NETWORK":"invalid"}):
                with self.assertRaises(OrchestratorError) as failure:
                    o._docker("test-image",root,["copilot"],10,prompt,runtime="copilot")
            self.assertEqual(failure.exception.code,"CONTAINER_NETWORK_INVALID")

    def test_broker_configuration_fails_closed_before_branch_allocation(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("broker-absent",repo,"Build app",runtime="copilot")
            environment={"THESYSTEM_COPILOT_IMAGE":"thesystem-copilot:local","THESYSTEM_BROKER_PROVIDER_KEY":"","THESYSTEM_BROKER_UPSTREAM_URL":"","OPENROUTER_API_KEY":"","OPENAI_API_KEY":""}
            with patch.dict(os.environ,environment),patch("the_system_orchestrator.subprocess.run",return_value=subprocess.CompletedProcess([],0,"","")):
                with self.assertRaises(OrchestratorError) as failure: o.approve("broker-absent")
            self.assertEqual(failure.exception.code,"CREDENTIAL_BROKER_REQUIRED")
            self.assertEqual(o.state["runs"],{})
            self.assertFalse(subprocess.run(["git","-C",str(repo),"branch","--list","thesystem/*"],capture_output=True,text=True,check=True).stdout.strip())
        with self.assertRaises(OrchestratorError) as failure:
            HostCredentialBroker.from_environment("copilot",{"THESYSTEM_BROKER_UPSTREAM_URL":"https://unrelated.invalid/v1","OPENROUTER_API_KEY":"marker"})
        self.assertEqual(failure.exception.code,"CREDENTIAL_BROKER_INVALID")

    def test_actual_container_forwards_only_a_scoped_capability(self):
        from unittest.mock import patch
        if subprocess.run(["docker","image","inspect","thesystem-copilot:local"],capture_output=True).returncode:
            self.skipTest("disposable Copilot image or Docker daemon is unavailable")
        marker="DISPOSABLE_PROVIDER_SECRET_NOT_REAL"
        seen=[]
        class Upstream(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(self.headers.get("Authorization"))
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{"ok":true}')
            def log_message(self, format, *args): pass
        upstream=ThreadingHTTPServer(("127.0.0.1",0),Upstream)
        threading.Thread(target=upstream.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td); prompt=root/"prompt"; prompt.write_text("probe")
                script=("import os,urllib.request,json,time; "
                        "assert not any(k in os.environ for k in ('THESYSTEM_BROKER_PROVIDER_KEY','OPENROUTER_API_KEY','OPENAI_API_KEY','COPILOT_GITHUB_TOKEN','GH_TOKEN','GITHUB_TOKEN')); "
                        "base=os.environ['COPILOT_PROVIDER_BASE_URL']; token=os.environ['COPILOT_PROVIDER_API_KEY']; "
                        "req=urllib.request.Request(base+'/chat/completions', "
                        "data=b'{\"model\":\"model-a\",\"messages\":[]}', "
                        "headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST'); "
                        "assert json.loads(urllib.request.urlopen(req,timeout=10).read())=={'ok':True}; "
                        "print('CONTAINED_REQUEST_OK'); time.sleep(4)")
                environment={"THESYSTEM_BROKER_UPSTREAM_URL":f"http://127.0.0.1:{upstream.server_port}/v1","THESYSTEM_BROKER_PROVIDER_KEY":marker,"THESYSTEM_BROKER_MODEL":"model-a"}
                container_name="thesystem-broker-probe-"+uuid.uuid4().hex[:8]
                outcome=[]
                def run_container():
                    try:
                        outcome.append(Orchestrator(root)._docker("thesystem-copilot:local",root,["python3","-c",script],30,prompt,runtime="copilot",container_name=container_name))
                    except Exception as exc:
                        outcome.append(exc)
                with patch.dict(os.environ,environment):
                    worker=threading.Thread(target=run_container,daemon=True); worker.start()
                    inspected=None
                    for _ in range(50):
                        candidate=subprocess.run(["docker","inspect",container_name],capture_output=True,text=True)
                        if candidate.returncode==0:
                            inspected=json.loads(candidate.stdout)[0]
                            break
                        time.sleep(0.1)
                    worker.join(timeout=40)
                self.assertFalse(worker.is_alive(),"contained Docker probe did not finish")
                self.assertIsNotNone(inspected,"container never became inspectable")
                assert inspected is not None
                self.assertNotIn(marker,json.dumps(inspected))
                self.assertEqual(inspected["HostConfig"]["NetworkMode"],"none")
                self.assertEqual(len(outcome),1)
                if isinstance(outcome[0],Exception): raise outcome[0]
                result=outcome[0]
                self.assertIsNotNone(result)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn("CONTAINED_REQUEST_OK",result.stdout)
                self.assertEqual(seen,["Bearer "+marker])
                self.assertNotIn(marker,result.stdout+result.stderr)
        finally:
            upstream.shutdown(); upstream.server_close()

    def test_unix_broker_rejects_wrong_capability_and_cleans_socket(self):
        with tempfile.TemporaryDirectory() as td:
            socket_path=Path(td)/"broker.sock"
            broker=HostCredentialBroker("http://127.0.0.1:9/v1","DISPOSABLE_KEY","model-a").serve(socket_path)
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(10); client.connect(str(socket_path))
                    client.sendall(b"POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}")
                    response=http.client.HTTPResponse(client); response.begin()
                    self.assertEqual(response.status,401)
            finally:
                broker.close()
            self.assertFalse(socket_path.exists())

    def test_host_provider_key_is_not_forwarded_to_redirect_target(self):
        received=[]
        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("Authorization"))
                self.send_response(200); self.end_headers()
            def log_message(self, format, *args): pass
        target=ThreadingHTTPServer(("127.0.0.1",0),Target)
        threading.Thread(target=target.serve_forever,daemon=True).start()
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location",f"http://127.0.0.1:{target.server_port}/capture")
                self.end_headers()
            def log_message(self, format, *args): pass
        upstream=ThreadingHTTPServer(("127.0.0.1",0),Redirect)
        threading.Thread(target=upstream.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as td:
                broker=HostCredentialBroker(f"http://127.0.0.1:{upstream.server_port}/v1","DISPOSABLE_HOST_MARKER","model-a").serve(Path(td)/"broker.sock")
                try:
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                        client.settimeout(10); client.connect(str(broker.socket_path))
                        request=f"GET /v1/models HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {broker.capability}\r\n\r\n"
                        client.sendall(request.encode())
                        response=http.client.HTTPResponse(client); response.begin()
                        self.assertEqual(response.status,302)
                finally:
                    broker.close()
            self.assertEqual(received,[])
        finally:
            upstream.shutdown(); upstream.server_close(); target.shutdown(); target.server_close()

    def test_broker_forwards_non_auth_headers(self):
        captured=[]
        class Upstream(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(dict(self.headers.items()))
                self.rfile.read(int(self.headers.get("Content-Length","0")))
                body=b'{"ok":true}'
                self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, format, *args): pass
        upstream=ThreadingHTTPServer(("127.0.0.1",0),Upstream)
        threading.Thread(target=upstream.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as td:
                broker=HostCredentialBroker(f"http://127.0.0.1:{upstream.server_port}/v1","PROVIDER_KEY","model-a").serve(Path(td)/"broker.sock")
                try:
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                        client.settimeout(10); client.connect(str(broker.socket_path))
                        body=b'{"model":"model-a","messages":[]}'
                        request=(f"POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {broker.capability}\r\nX-Copilot-Feature: enabled\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n").encode()+body
                        client.sendall(request)
                        response=http.client.HTTPResponse(client); response.begin(); response.read()
                        self.assertEqual(response.status,200)
                finally:
                    broker.close()
            self.assertEqual(captured[0].get("X-Copilot-Feature"),"enabled")
            self.assertEqual(captured[0].get("Authorization"),"Bearer PROVIDER_KEY")
        finally:
            upstream.shutdown(); upstream.server_close()

    def test_copilot_agent_command_uses_portable_reasoning_setting(self):
        with tempfile.TemporaryDirectory() as td:
            command = Orchestrator(Path(td))._agent_command("copilot", review=False, prompt="do work")
        self.assertIn("--reasoning-effort", command)
        self.assertIn("none", command)
        self.assertIn("--available-tools", command)
        self.assertIn("bash", command)

    def test_approval_dispatches_without_second_start(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root)
            o=Orchestrator(root)
            o.create_task("t1",repo,"Build an app",runtime="copilot")
            with self.assertRaises(OrchestratorError) as failure: o.start("t1")
            self.assertEqual(failure.exception.code,"TASK_NOT_APPROVED")
            with patch.object(o,"start",return_value={"id":"r1","status":"starting"}) as start:
                result=o.approve("t1")
                self.assertEqual(result["id"],"r1")
                start.assert_called_once_with("t1",timeout=3600,detach=True)
            o.task("t1")["prompt"]="changed scope"; o.save()
            with self.assertRaises(OrchestratorError) as failure: o.start("t1")
            self.assertEqual(failure.exception.code,"APPROVAL_STALE")

    def test_one_active_run_and_moved_base_block_integration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.repo(root)
            o = Orchestrator(root)
            o.create_task("t1", repo, "true")
            from unittest.mock import patch
            with patch.object(o,"start",return_value={}): o.approve("t1")
            o.state["runs"]["fake"] = {"id":"fake", "task_id":"t1", "status":"running"}
            o.save()
            with self.assertRaises(OrchestratorError) as failure: o.start("t1")
            self.assertEqual(failure.exception.code, "RUN_ALREADY_ACTIVE")

    def test_missing_agent_image_refuses_before_creating_run_or_branch(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.repo(root); o = Orchestrator(root)
            o.create_task("missing-image", repo, "Build a page", runtime="copilot")
            with patch.dict(os.environ, {"THESYSTEM_COPILOT_IMAGE": "", "THESYSTEM_AGENT_IMAGE": ""}):
                with self.assertRaises(OrchestratorError) as failure:
                    o.approve("missing-image")
            self.assertEqual(failure.exception.code, "AGENT_IMAGE_REQUIRED")
            self.assertEqual(o.task("missing-image")["approval"], "approved")
            self.assertEqual(o.state["runs"], {})
            branches = subprocess.run(["git", "-C", str(repo), "branch", "--list", "thesystem/*"], capture_output=True, text=True, check=True)
            self.assertEqual(branches.stdout.strip(), "")

    def test_stale_writer_cannot_revoke_approval_or_change_terminal_verdict(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); first=Orchestrator(root)
            first.create_task("one",repo,"Build a page",runtime="copilot")
            stale=Orchestrator(root)
            with patch.object(first,"start",return_value={}): first.approve("one")
            stale.create_task("two",repo,"Build a second page",runtime="copilot")
            self.assertEqual(Orchestrator(root).task("one")["approval"],"approved")
            terminal=Orchestrator(root)
            terminal.state["runs"]["r1"]={"id":"r1","task_id":"one","status":"changes-requested","review_result":{"verdict":"FAIL"}}
            terminal.save()
            stale.state["runs"]["r1"]={"id":"r1","task_id":"one","status":"passed","review_result":{"verdict":"PASS"}}
            stale.save()
            outcome=Orchestrator(root).state["runs"]["r1"]
            self.assertEqual(outcome["status"],"changes-requested")
            self.assertEqual(outcome["review_result"]["verdict"],"FAIL")
            stale.state["runs"]["r1"]["status"]="changes-requested"
            stale.save()
            self.assertEqual(Orchestrator(root).state["runs"]["r1"]["review_result"]["verdict"],"FAIL")

    def test_dependency_blocks_and_auto_dispatches_after_integration(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("first", repo, "Build first", runtime="copilot")
            o.create_task("second", repo, "Build second", runtime="copilot", dependencies=["first"])
            with patch.object(o, "start", return_value={"id":"first-run"}):
                o.approve("first")
            with patch.object(o, "start", wraps=o.start) as start:
                blocked=o.approve("second")
                self.assertEqual(blocked["approval"],"approved")
                self.assertEqual(len(o.state["runs"]),0)
                self.assertEqual(start.call_count,1)
            with self.assertRaises(OrchestratorError) as failure: o.start("second")
            self.assertEqual(failure.exception.code,"BLOCKED")

    def test_moved_integration_base_refuses_merge_and_completion(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=self.repo(root);o=Orchestrator(root)
            o.create_task("moved",repo,"Build something",runtime="copilot")
            base=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
            subprocess.run(["git","-C",str(repo),"branch","thesystem/moved-test"],check=True)
            (repo/"README").write_text("base changed\n")
            subprocess.run(["git","-C",str(repo),"commit","-qam","another integration"],check=True)
            current=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
            o.state["runs"]["passed-run"]={"id":"passed-run","task_id":"moved","status":"passed","base_commit":base,"branch":"thesystem/moved-test"}
            o.save()
            with self.assertRaises(OrchestratorError) as failure: o.integrate("passed-run")
            self.assertEqual(failure.exception.code,"INTEGRATION_BASE_MOVED")
            self.assertIn(current,str(failure.exception))
            self.assertEqual(subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip(),current)
            self.assertNotEqual(o.task("moved").get("status"),"done")

    def test_passing_run_only_becomes_done_after_real_local_merge(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("ready",repo,"Build a page",runtime="copilot")
            base=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
            integration_branch=subprocess.run(["git","-C",str(repo),"symbolic-ref","--short","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
            subprocess.run(["git","-C",str(repo),"checkout","-qb","thesystem/ready-test"],check=True)
            (repo/"index.html").write_text("<title>ready</title>\n")
            subprocess.run(["git","-C",str(repo),"add","index.html"],check=True)
            subprocess.run(["git","-C",str(repo),"commit","-qm","delivery"],check=True)
            subprocess.run(["git","-C",str(repo),"checkout","-q",integration_branch],check=True)
            o.state["runs"]["approved-run"]={"id":"approved-run","task_id":"ready","status":"passed","base_commit":base,"branch":"thesystem/ready-test"}
            o.save()
            self.assertNotEqual(Orchestrator(root).task("ready").get("status"),"done")
            o.integrate("approved-run")
            fresh=Orchestrator(root)
            self.assertEqual(fresh.task("ready")["status"],"done")
            self.assertEqual(fresh.state["runs"]["approved-run"]["integration_commit"],subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip())
            self.assertTrue((repo/"index.html").exists())

    def test_recovery_uses_immutable_terminal_record_instead_of_false_abortion(self):
        from the_system_orchestrator import atomic
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=self.repo(root);o=Orchestrator(root)
            o.create_task("recovery",repo,"Build one file",runtime="copilot")
            with __import__("unittest.mock",fromlist=["patch"]).patch.object(o,"start",return_value={}):
                o.approve("recovery")
            run={"id":"recovered","task_id":"recovery","status":"reviewing","detached":True,"pid":999999999,"base_commit":"base","branch":"branch","runtime":"copilot","started_at":"start"}
            o.state["runs"]["recovered"]=run;o.save()
            terminal=dict(run,status="changes-requested",finished_at="end",review_result={"verdict":"FAIL"})
            atomic(o.evidence/"recovered.json",terminal)
            fresh=Orchestrator(root)
            self.assertEqual(fresh.state["runs"]["recovered"]["status"],"changes-requested")
            self.assertEqual(Orchestrator(root).state["runs"]["recovered"]["review_result"]["verdict"],"FAIL")

    def test_capacity_and_attempt_caps_do_not_alter_approval_scope(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=self.repo(root);o=Orchestrator(root)
            o.create_task("capacity",repo,"Implement app",runtime="copilot")
            with __import__("unittest.mock",fromlist=["patch"]).patch.object(o,"start",return_value={}):
                o.approve("capacity")
            for index in range(3):
                o.state["runs"][str(index)]={"id":str(index),"task_id":"capacity","status":"changes-requested"}
            o.save()
            with self.assertRaises(OrchestratorError) as failure: o.start("capacity")
            self.assertEqual(failure.exception.code,"ATTEMPTS_EXHAUSTED")
            self.assertEqual(o.task("capacity")["approval"],"approved")

    def test_ticket_contract_validator_accepts_materialized_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("contract-ok", repo, "Build contract")
            task=o.task("contract-ok")
            contract, blockers = o._validate_task_contract(task)
            self.assertEqual(contract["task"], "contract-ok")
            self.assertEqual(blockers, [])

    def test_ticket_contract_validator_rejects_missing_clone_and_missing_verify(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("contract-invalid", repo, "Build contract")
            with patch.object(o, "start", return_value={}):
                o.approve("contract-invalid")
            task=o.task("contract-invalid")
            task_file = root / "tickets" / "local" / "tasks" / "contract-invalid" / "task.md"
            contract, body = self.read_contract(task_file)
            contract["source_clone"] = ""
            contract["acceptance_criteria"][0].pop("verify", None)
            self.write_contract(task_file, contract, body)
            with self.assertRaises(OrchestratorError) as failure:
                o._admission(task)
            self.assertEqual(failure.exception.code, "TICKET_INVALID")
            message = str(failure.exception)
            self.assertIn("source_clone must be a non-empty string", message)
            self.assertIn("acceptance_criteria[1].verify is required", message)

    def test_ticket_contract_validator_reports_multiple_missing_fields(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("contract-missing", repo, "Build contract")
            with patch.object(o, "start", return_value={}):
                o.approve("contract-missing")
            task=o.task("contract-missing")
            task_file = root / "tickets" / "local" / "tasks" / "contract-missing" / "task.md"
            contract, body = self.read_contract(task_file)
            contract.pop("project", None)
            contract.pop("runtime", None)
            contract["acceptance_criteria"] = []
            self.write_contract(task_file, contract, body)
            with self.assertRaises(OrchestratorError) as failure:
                o._admission(task)
            self.assertEqual(failure.exception.code, "TICKET_INVALID")
            message = str(failure.exception)
            self.assertIn("missing required field: project", message)
            self.assertIn("missing required field: runtime", message)
            self.assertIn("acceptance_criteria must be a non-empty list", message)

    def test_probe_failure_blocks_run_before_worker_and_records_probe_results(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("isolation-probe",repo,"Build app",runtime="copilot")
            task=o.task("isolation-probe")
            base=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
            branch="thesystem/isolation-probe"; subprocess.run(["git","-C",str(repo),"branch",branch,base],check=True)
            run={"id":"run-probe","task_id":"isolation-probe","status":"starting","runtime":"copilot","ticket":"local","source_clone":str(repo),"base_commit":base,"branch":branch,"started_at":"now","started_epoch":time.time(),"timeout_seconds":300,"worker":{"bundle":{"path":"/tmp/worker-bundle"}},"reviewer":{"bundle":{"path":"/tmp/reviewer-bundle"}}}
            o.state["runs"][run["id"]]=run
            with patch.object(o,"_run_isolation_probes",return_value=[{"name":"worker-worktree-and-bundle","ok":False,"message":"outside write succeeded"}]),patch.object(o,"_worker") as worker:
                o._execute(run,task)
            worker.assert_not_called()
            self.assertEqual(run["status"],"infra_blocked")
            self.assertEqual(run["error"]["code"],"ISOLATION_PROBE_FAILED")
            self.assertEqual(run["isolation_probes"][0]["ok"],False)

    def test_review_tree_change_sets_isolation_violated(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=self.repo(root); o=Orchestrator(root)
            o.create_task("isolation-hash",repo,"Build app",runtime="copilot")
            task=o.task("isolation-hash")
            base=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
            branch="thesystem/isolation-hash"; subprocess.run(["git","-C",str(repo),"branch",branch,base],check=True)
            subprocess.run(["git","-C",str(repo),"worktree","add",str(root/"work"),branch],check=True,capture_output=True,text=True)
            try:
                (root/"work"/"feature.txt").write_text("hello\n")
                subprocess.run(["git","-C",str(root/"work"),"add","feature.txt"],check=True)
                subprocess.run(["git","-C",str(root/"work"),"-c","user.email=test@example.invalid","-c","user.name=Test","commit","-qm","worker delivery"],check=True)
                worker_commit=subprocess.run(["git","-C",str(repo),"rev-parse",branch],capture_output=True,text=True,check=True).stdout.strip()
            finally:
                subprocess.run(["git","-C",str(repo),"worktree","remove","--force",str(root/"work")],check=True,capture_output=True,text=True)
            run={"id":"run-hash","task_id":"isolation-hash","status":"starting","runtime":"copilot","ticket":"local","source_clone":str(repo),"base_commit":base,"branch":branch,"started_at":"now","started_epoch":time.time(),"timeout_seconds":300,"worker":{"bundle":{"path":"/tmp/worker-bundle"}},"reviewer":{"bundle":{"path":"/tmp/reviewer-bundle"}},"worker_result":{"commit":worker_commit}}
            o.state["runs"][run["id"]]=run
            default_branch=subprocess.run(["git","-C",str(repo),"symbolic-ref","--short","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
            def mutate_branch(*_args,**_kwargs):
                subprocess.run(["git","-C",str(repo),"checkout","-qb","temp-isolation-edit",branch],check=True,capture_output=True,text=True)
                try:
                    (repo/"feature.txt").write_text("mutated during review\n")
                    subprocess.run(["git","-C",str(repo),"commit","-qam","mutate during review"],check=True)
                    subprocess.run(["git","-C",str(repo),"branch","-f",branch,"HEAD"],check=True)
                finally:
                    subprocess.run(["git","-C",str(repo),"checkout","-q",default_branch],check=True)
                    subprocess.run(["git","-C",str(repo),"branch","-D","temp-isolation-edit"],check=True,capture_output=True,text=True)
                return {"passed":True,"returncode":0,"timed_out":False,"worker_tree_unchanged":True}
            with patch.object(o,"_run_isolation_probes",return_value=[{"name":"worker-worktree-and-bundle","ok":True},{"name":"reviewer-worktree-and-bundle","ok":True}]),patch.object(o,"_worker",return_value={"timed_out":False,"returncode":0,"commit":worker_commit}),patch.object(o,"_review",side_effect=mutate_branch):
                o._execute(run,task)
            self.assertEqual(run["status"],"isolation_violated")
            self.assertEqual(run["error"]["code"],"ISOLATION_VIOLATED")
            self.assertNotEqual(run["worker_tree_hash"]["before_review"],run["worker_tree_hash"]["after_review"])

    def test_bundle_uses_project_role_overlay_and_skill_directory_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            global_agents, _ = self.fixture_agents(root)
            orchestrator = Orchestrator(project, global_agents=global_agents)
            effective = orchestrator._effective_roles()
            bundle = orchestrator._build_bundle("run-a", "worker", ["base", "worker", "custom"], effective)
            files = {entry["path"] for entry in bundle["manifest"]["entries"]}
            self.assertIn("rules/base.md", files)
            self.assertIn("rules/worker.md", files)
            self.assertIn("skills/kit/SKILL.md", files)
            self.assertNotIn("skills/kit/guide.md", files)
            worker_rule = Path(bundle["path"]) / "rules" / "worker.md"
            skill_doc = Path(bundle["path"]) / "skills" / "kit" / "SKILL.md"
            self.assertEqual(worker_rule.read_text(), "project-worker-override\n")
            self.assertEqual(skill_doc.read_text(), "project skill override\n")

    def test_reviewer_rule_coverage_failure_names_the_missing_rule(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            global_agents = root / "global-agents"
            (global_agents / "rules").mkdir(parents=True)
            (global_agents / "rules" / "base.md").write_text("base\n")
            (global_agents / "rules" / "worker-only.md").write_text("worker\n")
            (global_agents / "roles.yaml").write_text(json.dumps({
                "base": {"rules": ["rules/base.md"]},
                "worker": {"rules": ["rules/worker-only.md"]},
                "reviewer": {"rules": ["rules/base.md"]}
            }, indent=2) + "\n")
            orchestrator = Orchestrator(project, global_agents=global_agents)
            effective = orchestrator._effective_roles()
            worker_bundle = orchestrator._build_bundle("run-a", "worker", ["base", "worker"], effective)
            reviewer_bundle = orchestrator._build_bundle("run-a", "reviewer", ["base", "reviewer"], effective)
            with self.assertRaises(OrchestratorError) as failure:
                orchestrator._ensure_reviewer_covers_worker(worker_bundle, reviewer_bundle)
            self.assertEqual(failure.exception.code, "REVIEWER_RULES_MISSING")
            self.assertIn("rules/worker-only.md", str(failure.exception))

    def test_bundle_manifest_lists_path_and_hash_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            global_agents, _ = self.fixture_agents(root)
            orchestrator = Orchestrator(project, global_agents=global_agents)
            effective = orchestrator._effective_roles()
            first = orchestrator._build_bundle("run-a", "worker", ["base", "worker", "custom"], effective)
            second = orchestrator._build_bundle("run-b", "worker", ["base", "worker", "custom"], effective)
            self.assertEqual(first["manifest"], second["manifest"])
            for entry in first["manifest"]["entries"]:
                materialized = Path(first["path"]) / entry["path"]
                self.assertEqual(entry["sha256"], hashlib.sha256(materialized.read_bytes()).hexdigest())

    def test_worker_and_reviewer_mount_bundle_read_only_and_separate_from_workspace(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            global_agents, _ = self.fixture_agents(root)
            orchestrator = Orchestrator(project, global_agents=global_agents)
            prompt = project / "prompt.txt"
            prompt.write_text("task")
            workspace = project / "workspace"
            workspace.mkdir()
            bundle = project / "bundle"
            bundle.mkdir()
            completed = subprocess.CompletedProcess(["docker"], 0, stdout="ok", stderr="")
            env = {
                "THESYSTEM_BROKER_UPSTREAM_URL": "http://127.0.0.1:9/v1",
                "THESYSTEM_BROKER_PROVIDER_KEY": "TEST_SECRET",
                "THESYSTEM_BROKER_MODEL": "model-a",
            }
            with patch.dict(os.environ, env), patch("the_system_orchestrator.subprocess.run", return_value=completed) as run:
                orchestrator._docker("test-image", workspace, ["copilot"], 10, prompt, runtime="copilot", bundle=bundle)
            args = run.call_args.args[0]
            self.assertIn(f"{bundle}:/bundle:ro", args)
            self.assertIn("THESYSTEM_BUNDLE=/bundle", args)
            self.assertIn(f"{workspace}:/workspace", args)

    def test_start_records_worker_and_reviewer_bundle_manifests_in_run(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            repo = self.repo(project)
            global_agents, _ = self.fixture_agents(root)
            orchestrator = Orchestrator(project, global_agents=global_agents)
            orchestrator.create_task("bundle-run", repo, "Build", runtime="copilot", roles=["base", "worker", "custom"])
            task = orchestrator.task("bundle-run")
            task["approval"] = "approved"
            task["approval_digest"] = __import__("the_system_orchestrator", fromlist=["digest"]).digest({k: task[k] for k in ("source_clone", "prompt", "runtime", "acceptance", "roles")})
            orchestrator.save()
            env = {"THESYSTEM_COPILOT_IMAGE": "fake-image"}
            real_run = subprocess.run
            def fake_run(args, **kwargs):
                if args[:4] == ["docker", "image", "inspect", "fake-image"]:
                    return subprocess.CompletedProcess(args, 0, "[]", "")
                return real_run(args, **kwargs)
            with patch.dict(os.environ, env), \
                 patch("the_system_orchestrator.HostCredentialBroker.from_environment", return_value=object()), \
                 patch("the_system_orchestrator.subprocess.run", side_effect=fake_run), \
                 patch.object(orchestrator, "_execute", return_value=None):
                run = orchestrator.start("bundle-run", timeout=30, detach=False)
            self.assertIn("bundle", run["worker"])
            self.assertIn("bundle", run["reviewer"])
            worker_entries = run["worker"]["bundle"]["manifest"]["entries"]
            reviewer_entries = run["reviewer"]["bundle"]["manifest"]["entries"]
            self.assertTrue(worker_entries)
            self.assertTrue(reviewer_entries)
            self.assertTrue(any(entry["path"].startswith("rules/") for entry in worker_entries))

if __name__ == "__main__": unittest.main()
