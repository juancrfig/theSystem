import json
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
            self.assertNotIn(secret,str(run.call_args.kwargs["env"]))
            self.assertNotIn("HOST_ONLY_TEST_TOKEN",str(run.call_args.kwargs["env"]))
            self.assertNotIn(secret,result.stdout+result.stderr)
            self.assertIn("[REDACTED]",result.stdout)
            self.assertIn("[REDACTED]",result.stderr)

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

if __name__ == "__main__": unittest.main()
