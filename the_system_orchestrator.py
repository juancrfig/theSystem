"""Safety-first deterministic task execution.

The orchestrator owns admission and lifecycle.  Agent CLIs are deliberately
small adapters and are always invoked in a fresh Docker container.  A task's
``command`` is an agent prompt, never a host shell command.
"""
from __future__ import annotations
import argparse, hashlib, json, os, signal, subprocess, sys, time, uuid, shutil, fcntl, re, secrets, threading, socketserver, tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

TERMINAL={"passed","changes-requested","execution-failed","review-failed","cancelled","timeout","aborted"}
ACTIVE={"starting","running","reviewing"}
RUNTIMES={"hermes","copilot"}
class OrchestratorError(Exception):
    def __init__(self,code,message): super().__init__(message); self.code=code

class _NoCredentialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

_provider_opener=build_opener(_NoCredentialRedirect())

class HostCredentialBroker:
    """Host-owned provider credential and short-lived, model-scoped agent capability."""
    def __init__(self, upstream_url, provider_key, model, lifetime=3600, max_requests=100):
        parsed=urlsplit(upstream_url)
        if parsed.scheme not in ("http","https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise OrchestratorError("CREDENTIAL_BROKER_INVALID","broker upstream must be an absolute HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise OrchestratorError("CREDENTIAL_BROKER_INVALID","remote broker upstream must use HTTPS")
        if not provider_key or not model or not re.fullmatch(r"[A-Za-z0-9._/-]+",model):
            raise OrchestratorError("CREDENTIAL_BROKER_INVALID","provider key and model are required")
        self.upstream_url=upstream_url.rstrip("/"); self.provider_key=provider_key; self.model=model
        self.capability=secrets.token_urlsafe(32); self.expires_at=time.monotonic()+lifetime
        self.max_requests=max(1,int(max_requests)); self.request_count=0; self.request_lock=threading.Lock()
        self.server=None; self.thread=None; self.socket_path=None

    @classmethod
    def from_environment(cls,runtime,env=None,lifetime=3600):
        env=os.environ if env is None else env
        upstream=env.get("THESYSTEM_BROKER_UPSTREAM_URL")
        key=env.get("THESYSTEM_BROKER_PROVIDER_KEY")
        if bool(upstream) != bool(key):
            raise OrchestratorError("CREDENTIAL_BROKER_INVALID","custom broker upstream and provider key must be configured together")
        if not (upstream and key):
            if env.get("OPENROUTER_API_KEY"):
                upstream="https://openrouter.ai/api/v1"; key=env["OPENROUTER_API_KEY"]
            elif env.get("OPENAI_API_KEY"):
                upstream="https://api.openai.com/v1"; key=env["OPENAI_API_KEY"]
        if not (upstream and key):
            raise OrchestratorError("CREDENTIAL_BROKER_REQUIRED","contained %s requires THESYSTEM_BROKER_UPSTREAM_URL and a host-held broker/provider key" % runtime)
        default_model="gpt-4.1-mini" if upstream == "https://api.openai.com/v1" else "openai/gpt-4.1-mini"
        model=env.get("THESYSTEM_BROKER_MODEL") or env.get("COPILOT_MODEL") or default_model
        return cls(upstream,key,model,lifetime=lifetime)

    def serve(self, socket_path):
        socket_path=Path(socket_path)
        if self.server: raise RuntimeError("broker is already running")
        if socket_path.exists(): raise OrchestratorError("CREDENTIAL_BROKER_INVALID","broker socket path already exists")
        socket_path.parent.mkdir(parents=True,exist_ok=True)
        broker=self
        class UnixHTTPServer(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
            daemon_threads=True
        class Handler(BaseHTTPRequestHandler):
            server_version="theSystemCredentialBroker"
            def log_message(self,*args): pass
            def do_POST(self): broker._proxy(self)
            def do_GET(self): broker._proxy(self)
        try:
            self.server=UnixHTTPServer(str(socket_path),Handler)
            os.chmod(socket_path,0o600)
        except OSError as error:
            raise OrchestratorError("CREDENTIAL_BROKER_UNAVAILABLE","cannot bind the host credential broker: "+str(error)) from error
        self.socket_path=socket_path
        self.thread=threading.Thread(target=self.server.serve_forever,name="thesystem-credential-broker",daemon=True)
        self.thread.start()
        return self

    def close(self):
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        if self.socket_path: self.socket_path.unlink(missing_ok=True)
        self.server=None; self.thread=None; self.socket_path=None

    def _reject(self, handler, code):
        handler.send_response(code); handler.send_header("Content-Length","0"); handler.end_headers()

    def _proxy(self, handler):
        authorization=handler.headers.get("Authorization","")
        if not secrets.compare_digest(authorization,"Bearer "+self.capability): return self._reject(handler,401)
        with self.request_lock:
            if time.monotonic()>self.expires_at or self.request_count>=self.max_requests: return self._reject(handler,403)
            self.request_count+=1
        if handler.command not in ("GET","POST") or handler.path not in ("/v1/models","/v1/chat/completions","/v1/responses"):
            return self._reject(handler,404)
        try:
            length=int(handler.headers.get("Content-Length","0"))
            if length<0 or length>10*1024*1024: return self._reject(handler,413)
            body=handler.rfile.read(length) if length else None
            if handler.command=="POST":
                try: requested_model=json.loads(body or b"{}") ["model"]
                except (KeyError,TypeError,json.JSONDecodeError): return self._reject(handler,400)
                if requested_model != self.model: return self._reject(handler,403)
            headers={k:v for k,v in handler.headers.items() if k.lower() in ("content-type","accept")}
            headers["Authorization"]="Bearer "+self.provider_key
            request=Request(self.upstream_url+handler.path[3:],data=body,headers=headers,method=handler.command)
            try: response=_provider_opener.open(request,timeout=120)
            except HTTPError as error: response=error
            payload=response.read()
            handler.send_response(response.status)
            content_type=response.headers.get("Content-Type")
            if content_type: handler.send_header("Content-Type",content_type)
            handler.send_header("Content-Length",str(len(payload))); handler.end_headers(); handler.wfile.write(payload)
        except (OSError,ValueError,URLError):
            self._reject(handler,502)

SOCKET_RELAY = r'''#!/usr/bin/env python3
"""Container-local HTTP to Unix-socket relay; it never receives a provider key."""
import http.client, socket, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

socket_path, capability, port_file = sys.argv[1:]
class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(socket_path)
class Relay(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self): self.forward()
    def do_POST(self): self.forward()
    def forward(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {key:value for key,value in self.headers.items()
                   if key.lower() in ("content-type", "accept")}
        headers["Authorization"] = "Bearer " + capability
        try:
            upstream = UnixConnection("localhost")
            upstream.request(self.command, self.path, body=body, headers=headers)
            response = upstream.getresponse(); payload = response.read()
            self.send_response(response.status)
            for key,value in response.getheaders():
                if key.lower() not in ("connection", "content-length", "date", "server"):
                    self.send_header(key,value)
            self.send_header("Content-Length",str(len(payload))); self.end_headers()
            self.wfile.write(payload)
        except (OSError, ValueError, http.client.HTTPException):
            self.send_response(502); self.send_header("Content-Length","0"); self.end_headers()
server = ThreadingHTTPServer(("127.0.0.1",18080),Relay)
with open(port_file,"w") as output:
    output.write(str(server.server_port))
server.serve_forever()
'''

def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def read(p,default):
    try: return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError): return default
def atomic(p,v):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+".tmp"); t.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n"); os.replace(t,p)
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()
def git(c,*a):
    p=subprocess.run(["git",*a],cwd=c,text=True,capture_output=True)
    if p.returncode: raise OrchestratorError("GIT_FAILED",p.stderr.strip() or "git failed")
    return p.stdout.strip()

class Orchestrator:
    def __init__(self,project):
        self.project=Path(project).expanduser().resolve()
        if not self.project.is_dir(): raise OrchestratorError("PROJECT_NOT_FOUND",str(self.project))
        self.root=self.project/".thesystem"/"orchestrator"; self.state_path=self.root/"state.json"; self.evidence=self.root/"runs"
        self.state=read(self.state_path,{"version":2,"tasks":{},"runs":{}})
        self.reconcile()
    def save(self):
        self.root.mkdir(parents=True,exist_ok=True)
        with open(self.root/"state.lock","a+") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            current=read(self.state_path,{"version":2,"tasks":{},"runs":{}})
            rank={"starting":0,"running":1,"reviewing":2,"passed":3,"changes-requested":3,"execution-failed":3,"review-failed":3,"cancelled":3,"timeout":3,"aborted":3}
            for rid,old in current["runs"].items():
                new=self.state["runs"].get(rid)
                if old.get("status") in TERMINAL:
                    preserved=dict(old)
                    if new and old.get("status")=="passed" and not old.get("integration_commit") and new.get("integration_commit"):
                        preserved.update(integration_commit=new["integration_commit"],integrated_at=new["integrated_at"])
                    self.state["runs"][rid]=preserved
                elif new is None or rank.get(old.get("status"),0)>rank.get(new.get("status"),0): self.state["runs"][rid]=old
            for tid,old in current["tasks"].items():
                new=self.state["tasks"].get(tid)
                if new is None or (old.get("status")=="done" and new.get("status")!="done"): self.state["tasks"][tid]=old
                elif old.get("approval")=="approved" and new.get("approval")=="proposed" and all(new.get(k)==old.get(k) for k in ("source_clone","prompt","runtime","acceptance","roles")):
                    self.state["tasks"][tid]=old
            atomic(self.state_path,self.state)
            fcntl.flock(lock,fcntl.LOCK_UN)
    def task(self,i):
        if i not in self.state["tasks"]: raise OrchestratorError("TASK_NOT_FOUND",i)
        return self.state["tasks"][i]
    def create_task(self,task_id,source_clone,command,runtime="hermes",ticket="local",acceptance=None,dependencies=None,roles=None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",task_id) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",ticket): raise OrchestratorError("IDENTIFIER_INVALID","task and ticket must be safe slugs")
        if task_id in self.state["tasks"]: raise OrchestratorError("TASK_EXISTS",task_id)
        clone=Path(source_clone).expanduser().resolve()
        if not clone.is_dir() or not (clone/".git").exists(): raise OrchestratorError("SOURCE_CLONE_INVALID",str(clone))
        if runtime not in RUNTIMES: raise OrchestratorError("RUNTIME_INVALID",runtime)
        if not isinstance(command,str) or not command.strip(): raise OrchestratorError("PROMPT_REQUIRED","agent prompt is required")
        self.state["tasks"][task_id]={"id":task_id,"ticket":ticket,"source_clone":str(clone),"prompt":command,"command":command,"runtime":runtime,"acceptance":acceptance or [],"dependencies":dependencies or [],"roles":roles or ["base","worker"],"approval":"proposed","created_at":now()}; self.save(); self._materialize_task(self.task(task_id)); return self.task(task_id)
    def approve(self,task_id,dispatch=True,timeout=3600):
        if not 1 <= int(timeout) <= 3600: raise OrchestratorError("TIMEOUT_INVALID","attempt timeout must be 1..3600 seconds")
        t=self.task(task_id)
        if t["approval"]!="proposed":
            if t["approval"]=="approved": return t
            raise OrchestratorError("APPROVAL_INVALID",t["approval"])
        t["approval"]="approved"; t["approval_digest"]=digest({k:t[k] for k in ("source_clone","prompt","runtime","acceptance","roles")}); t["approved_at"]=now(); self.save(); self._materialize_task(t)
        try: return self.start(task_id,timeout=timeout,detach=True)
        except OrchestratorError as e:
            if e.code == "BLOCKED": return t
            raise
    def _task_directory(self,t): return self.project/"tickets"/t["ticket"]/"tasks"/t["id"]
    def _materialize_task(self,t):
        d=self._task_directory(t); d.mkdir(parents=True,exist_ok=True)
        ticket=d.parent.parent
        f=ticket/"ticket.md"
        if not f.exists(): f.write_text(f"# {t['ticket']}\n\nLocal acceptance ticket.\n")
        spec=ticket/"spec.md"
        if not spec.exists(): spec.write_text("# Specification\n\nSee the individual approved tasks for scope.\n")
        (d/"task.md").write_text("---\nstatus: "+("done" if t.get("status")=="done" else "ready-for-agent" if t["approval"]=="approved" else "proposed")+"\nsource_clone: "+str(t["source_clone"])+"\nroles:\n  - worker\n---\n\n"+t["prompt"]+"\n\n## Acceptance criteria\n"+"\n".join("- "+x for x in t.get("acceptance",[]))+"\n")
    def _admission(self,t):
        for dep in t.get("dependencies",[]):
            if dep not in self.state["tasks"] or self.state["tasks"][dep].get("status")!="done": raise OrchestratorError("BLOCKED",dep)
        if not t.get("roles") or "worker" not in t["roles"]: raise OrchestratorError("ROLE_INVALID","worker role required")
        if t.get("approval_digest") != digest({k:t[k] for k in ("source_clone","prompt","runtime","acceptance","roles")}): raise OrchestratorError("APPROVAL_STALE","task scope changed after approval")
    def active(self,i): return [r for r in self.state["runs"].values() if r["task_id"]==i and r["status"] in ACTIVE]
    def start(self,task_id,timeout=3600,detach=False):
        self.root.mkdir(parents=True,exist_ok=True)
        with open(self.root/"dispatch.lock","a+") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self.state=read(self.state_path,{"version":2,"tasks":{},"runs":{}})
            try: return self._start_locked(task_id,timeout,detach)
            finally: fcntl.flock(lock,fcntl.LOCK_UN)
    def _start_locked(self,task_id,timeout,detach):
        t=self.task(task_id)
        if not 1 <= int(timeout) <= 3600: raise OrchestratorError("TIMEOUT_INVALID","attempt timeout must be 1..3600 seconds")
        if t["approval"]!="approved": raise OrchestratorError("TASK_NOT_APPROVED",task_id)
        self._admission(t)
        if self.active(task_id): raise OrchestratorError("RUN_ALREADY_ACTIVE",task_id)
        if sum(r["task_id"]==task_id for r in self.state["runs"].values()) >= 3:
            raise OrchestratorError("ATTEMPTS_EXHAUSTED","three implementation attempts exhausted")
        if sum(r["status"] in ACTIVE for r in self.state["runs"].values()) >= 2:
            raise OrchestratorError("BLOCKED","two workers/reviewers already active")
        if not shutil.which("docker"):
            raise OrchestratorError("DOCKER_UNAVAILABLE","Docker is required for contained execution")
        image=os.environ.get("THESYSTEM_"+t["runtime"].upper()+"_IMAGE") or os.environ.get("THESYSTEM_AGENT_IMAGE")
        if not image:
            raise OrchestratorError("AGENT_IMAGE_REQUIRED","configure the selected agent image before dispatch")
        inspected=subprocess.run(["docker","image","inspect",image],capture_output=True,text=True)
        if inspected.returncode:
            raise OrchestratorError("AGENT_IMAGE_UNAVAILABLE","selected agent image is not available locally")
        # Fail before allocating a branch or a run. Native Copilot authentication
        # is not a fallback: a real token must never enter the container.
        HostCredentialBroker.from_environment(t["runtime"],lifetime=int(timeout)+30)
        review_runtime=os.environ.get("THESYSTEM_REVIEW_RUNTIME",t["runtime"])
        if review_runtime not in RUNTIMES: raise OrchestratorError("REVIEW_RUNTIME_INVALID",review_runtime)
        HostCredentialBroker.from_environment(review_runtime,lifetime=int(timeout)+30)
        clone=Path(t["source_clone"]); base=git(clone,"rev-parse","HEAD"); branch=f"thesystem/{task_id.replace('/','-')}/{uuid.uuid4().hex[:8]}"; git(clone,"branch",branch,base)
        rid=uuid.uuid4().hex; r={"id":rid,"task_id":task_id,"status":"starting","runtime":t["runtime"],"ticket":t["ticket"],"source_clone":t["source_clone"],"models":{"worker":"openai/gpt-4.1-mini" if t["runtime"]=="hermes" else "copilot/default"},"base_commit":base,"branch":branch,"started_at":now(),"started_epoch":time.time(),"timeout_seconds":int(timeout),"evidence":[],"worker":{"prompt":t["prompt"],"roles":t["roles"]}}
        self.state["runs"][rid]=r; self.save()
        if detach:
            p=subprocess.Popen([sys.executable,__file__,"_run","--project",str(self.project),"--run",rid],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            r["pid"]=p.pid; r["pid_start_ticks"]=self._pid_info(p.pid)[1]; r["detached"]=True; self.save(); return r
        self._execute(r,t); self.save(); return r
    def _execute(self,r,t):
        try:
            r["status"]="running"; self.save(); result=self._worker(r,t); r["worker_result"]=result
            if result.get("timed_out"): r["status"]="timeout"
            elif result.get("returncode")!=0 or result.get("commit")==r["base_commit"]: r["status"]="execution-failed"
            else:
                r["status"]="reviewing"; self.save(); review=self._review(r,t); r["review_result"]=review; r["status"]="passed" if review["passed"] else ("timeout" if review.get("timed_out") else "review-failed" if review.get("returncode",1)!=0 else "changes-requested")
        except Exception as e: r.update(status="review-failed" if r["status"]=="reviewing" else "execution-failed",error={"code":type(e).__name__,"message":str(e)})
        r["finished_at"]=now()
        self._write_evidence(r); self.save(); self.dispatch_ready()
    def _docker(self,image,work,cmd,timeout,prompt,readonly=False,layer=None,runtime="copilot",container_name=None):
        if not shutil.which("docker"): raise OrchestratorError("DOCKER_UNAVAILABLE","docker is required")
        if not image: raise OrchestratorError("AGENT_IMAGE_REQUIRED","configure an image with the selected CLI")
        broker=HostCredentialBroker.from_environment(runtime,lifetime=max(1,int(timeout))+30)
        args=["docker","run","--rm",*(["--name",container_name] if container_name else []),"--network","none","--init","--cap-drop=ALL","--security-opt","no-new-privileges","--pids-limit","256","--memory","2g","--cpus","2","--user",f"{os.getuid()}:{os.getgid()}","-v",f"{work}:/workspace"+(':ro' if readonly else ''),"-v",f"{prompt}:/run/prompt:ro","-w","/workspace"]
        if layer: args += ["-v",f"{layer}:/review"]
        env=os.environ.copy()
        for name in ("COPILOT_GITHUB_TOKEN","GH_TOKEN","GITHUB_TOKEN","OPENROUTER_API_KEY","OPENAI_API_KEY","ANTHROPIC_API_KEY","CLAUDE_CODE_OAUTH_TOKEN","COPILOT_PROVIDER_API_KEY","COPILOT_PROVIDER_BEARER_TOKEN","THESYSTEM_BROKER_PROVIDER_KEY"):
            env.pop(name,None)
        # AF_UNIX path length is bounded independently of an arbitrary project
        # depth. Mount only this per-run directory into the container.
        agent_home=Path(tempfile.mkdtemp(prefix="tsb-")); agent_home.chmod(0o700)
        socket_path=agent_home/"broker.sock"; relay_path=agent_home/"socket-relay.py"
        relay_path.write_text(SOCKET_RELAY); relay_path.chmod(0o500)
        try:
            broker.serve(socket_path)
            try:
                args += ["-v",f"{agent_home}:/run/thesystem","-v",f"{relay_path}:/run/thesystem-relay.py:ro","-e","THESYSTEM_BROKER_CAPABILITY="+broker.capability]
                if runtime=="copilot":
                    args += ["-v",f"{agent_home}:/run/copilot-home","-e","COPILOT_HOME=/run/copilot-home","-e","COPILOT_PROVIDER_TYPE=openai","-e","COPILOT_PROVIDER_BASE_URL=http://127.0.0.1:18080/v1","-e","COPILOT_PROVIDER_API_KEY="+broker.capability,"-e","COPILOT_MODEL="+broker.model]
                elif runtime=="hermes":
                    (agent_home/"config.yaml").write_text("model:\n  default: %s\n  provider: custom\n  base_url: http://127.0.0.1:18080/v1\n  api_key: ${THESYSTEM_BROKER_CAPABILITY}\n" % broker.model)
                    # Hermes initializes a disposable home at startup; only
                    # the opaque capability is stored there, never a real key.
                    args += ["-v",f"{agent_home}:/home/agent/.hermes","-e","HERMES_HOME=/home/agent/.hermes"]
                else: raise OrchestratorError("RUNTIME_INVALID",runtime)
                wrapper="""python3 /run/thesystem-relay.py /run/thesystem/broker.sock \"$THESYSTEM_BROKER_CAPABILITY\" /run/thesystem/relay.port &
relay_pid=$!
cleanup() { kill \"$relay_pid\" 2>/dev/null || true; wait \"$relay_pid\" 2>/dev/null || true; }
trap cleanup EXIT HUP INT TERM
for attempt in $(seq 1 50); do [ -s /run/thesystem/relay.port ] && break; sleep 0.1; done
[ -s /run/thesystem/relay.port ] || exit 125
\"$@\"
"""
                args += [image,"sh","-ceu",wrapper,"thesystem-agent",*cmd]
                result=subprocess.run(args,text=True,capture_output=True,timeout=timeout,env=env)
            finally:
                broker.close()
            # Defense in depth: agent stdout/stderr are durable evidence.
            for secret in (broker.provider_key,broker.capability):
                result.stdout=result.stdout.replace(secret,"[REDACTED]")
                result.stderr=result.stderr.replace(secret,"[REDACTED]")
            return result
        except subprocess.TimeoutExpired:
            if container_name: subprocess.run(["docker","stop","--time","1",container_name],capture_output=True,timeout=10)
            return None
        finally:
            shutil.rmtree(agent_home,ignore_errors=True)
    def _agent_command(self,runtime,review=False,prompt=""):
        if runtime=="copilot":
            return ["copilot","-p",(prompt+"\nInspect application files in /workspace read-only. This is a git worktree whose .git pointer targets host metadata not accessible in the container; do not try to resolve it. Run tests only in /review. End your response with exactly VERDICT: PASS or VERDICT: FAIL and a reason. Do not change /workspace." if review else prompt+"\nImplement in /workspace. This is an intentionally empty initial clone; the .git worktree pointer targets host metadata not mounted in the container. Do not attempt to resolve that pointer; create the requested files. The host orchestrator owns commits. Do not access paths outside /workspace."),"--allow-all-tools","--disallow-temp-dir","--disable-builtin-mcps",*(["--allow-all-paths"] if review else []),"--no-auto-update","--no-remote","--no-remote-export","--no-ask-user"]
        return ["hermes","chat","--oneshot","--yolo","--ignore-rules","--provider","custom","--query-file","/run/prompt","--in","/workspace","--run-budget","600","--max-turns","40"]
    def _worker(self,r,t):
        clone=Path(t["source_clone"]); work=self.root/"worktrees"/r["id"]; work.parent.mkdir(parents=True,exist_ok=True); git(clone,"worktree","add",str(work),r["branch"])
        previous=[x for x in self.state["runs"].values() if x["task_id"]==r["task_id"] and x["id"]!=r["id"] and x.get("worker_result",{}).get("commit") not in (None,x["base_commit"]) and x["status"] in ("changes-requested","review-failed")]
        if previous:
            seed=previous[-1]; git(work,"-c","user.email=theSystem@localhost","-c","user.name=theSystem","cherry-pick",seed["worker_result"]["commit"]); r["seeded_from_run"]=seed["id"]; self.save()
        image=os.environ.get("THESYSTEM_"+t["runtime"].upper()+"_IMAGE") or os.environ.get("THESYSTEM_AGENT_IMAGE")
        prompt=t["prompt"]+"\nAcceptance criteria:\n"+"\n".join(t.get("acceptance",[]))+"\nYou are the worker. Edit only /workspace; do not push or publish."
        pf=self.root/"prompts"/(r["id"]+"-worker.txt"); pf.parent.mkdir(parents=True,exist_ok=True); pf.write_text(prompt)
        try:
            p=self._docker(image,work,self._agent_command(t["runtime"],prompt=prompt),max(1,int(r["started_epoch"]+r["timeout_seconds"]-time.time())),pf,runtime=t["runtime"],container_name="thesystem-"+r["id"]+"-worker")
            if p is None: return {"returncode":-1,"timed_out":True,"contained":True}
            changed=git(work,"status","--porcelain")
            streams=self._stream(r,"worker",p)
            if p.returncode==0 and changed:
                git(work,"add","-A"); git(work,"-c","user.email=theSystem@localhost","-c","user.name=theSystem","commit","-m",f"worker delivery {r['id']}")
            return {"returncode":p.returncode,"stdout":p.stdout[-8000:],"stderr":p.stderr[-4000:],"timed_out":False,"contained":True,"streams":streams,"delivery_status":changed,"commit":git(work,"rev-parse","HEAD")}
        finally: self._remove_worktree(clone,work); pf.unlink(missing_ok=True)
    def _review(self,r,t):
        clone=Path(t["source_clone"]); work=self.root/"review"/r["id"]; work.parent.mkdir(parents=True,exist_ok=True); git(clone,"worktree","add",str(work),r["branch"])
        review_runtime=os.environ.get("THESYSTEM_REVIEW_RUNTIME",t["runtime"])
        if review_runtime not in RUNTIMES: raise OrchestratorError("REVIEW_RUNTIME_INVALID",review_runtime)
        image=os.environ.get("THESYSTEM_"+review_runtime.upper()+"_IMAGE") or os.environ.get("THESYSTEM_REVIEW_IMAGE") or os.environ.get("THESYSTEM_AGENT_IMAGE")
        pf=self.root/"prompts"/(r["id"]+"-review.txt"); pf.write_text("Independent review. Criteria:\n"+"\n".join(t.get("acceptance",[]))+"\nInspect /workspace and use /review for writable tests. End exactly VERDICT: PASS or VERDICT: FAIL with reasons.")
        layer=self.root/"layers"/r["id"]; shutil.copytree(work,layer,ignore=shutil.ignore_patterns('.git'))
        before=git(work,"status","--porcelain"); commit=git(work,"rev-parse","HEAD")
        try:
            test_cmd=["python3","-m","unittest","discover","-s","tests","-q"] if (layer/"tests").exists() else (["npm","test"] if (layer/"package.json").exists() else None)
            test_args=["docker","run","--rm","--network","none","--cap-drop=ALL","--security-opt","no-new-privileges","--user",f"{os.getuid()}:{os.getgid()}","-v",f"{layer}:/review","-v",f"{work}:/workspace:ro","-w","/review",image,*(test_cmd or ["false"])]
            before_test=subprocess.run(test_args,capture_output=True,text=True,timeout=120)
            p=self._docker(image,work,self._agent_command(review_runtime,True,pf.read_text()),max(1,min(900,int(r["started_epoch"]+r["timeout_seconds"]-time.time()))),pf,readonly=True,layer=layer,runtime=review_runtime,container_name="thesystem-"+r["id"]+"-review")
            streams=self._stream(r,"review",p) if p is not None else {}
            after=git(work,"status","--porcelain"); unchanged=before==after and commit==git(work,"rev-parse","HEAD")
            if p is None: return {"review_runtime":review_runtime,"passed":False,"returncode":-1,"timed_out":True,"worker_tree_unchanged":unchanged}
            test=subprocess.run(test_args,capture_output=True,text=True,timeout=120)
            verdicts=re.findall(r"(?im)^VERDICT: (PASS|FAIL)\b",p.stdout)
            diff=git(work,"diff","--stat",r["base_commit"])
            return {"review_runtime":review_runtime,"model":"openai/gpt-4.1-mini" if review_runtime=="hermes" else "copilot/default","streams":streams,"passed":p.returncode==0 and before_test.returncode==0 and test.returncode==0 and unchanged and bool(diff) and verdicts[-1:]==["PASS"],"returncode":p.returncode,"stdout":p.stdout[-8000:],"stderr":p.stderr[-4000:],"diff_stat":diff,"independent":True,"worker_tree_unchanged":unchanged,"verdict":verdicts[-1] if verdicts else None,"pre_review_test_result":{"returncode":before_test.returncode,"stdout":before_test.stdout[-2000:],"stderr":before_test.stderr[-2000:]},"test_result":{"returncode":test.returncode,"stdout":test.stdout[-2000:],"stderr":test.stderr[-2000:]},"review_layer_changed":sorted(str(x.relative_to(layer)) for x in layer.rglob('*') if x.is_file() and (not (work/x.relative_to(layer)).exists() or x.read_bytes()!=(work/x.relative_to(layer)).read_bytes()))}
        finally: self._remove_worktree(clone,work); pf.unlink(missing_ok=True); shutil.rmtree(layer,ignore_errors=True)
    def _remove_worktree(self,clone,work): subprocess.run(["git","worktree","remove","--force",str(work)],cwd=clone,capture_output=True,text=True)
    def _stream(self,r,stage,process):
        directory=self._task_directory(self.task(r["task_id"]))/"runs"/r["id"]
        directory.mkdir(parents=True,exist_ok=True)
        records={}
        for kind in ("stdout","stderr"):
            content=getattr(process,kind)
            target=directory/(stage+"."+kind+".log")
            if not target.exists(): target.write_text(content)
            records[kind]={"path":str(target),"sha256":hashlib.sha256(content.encode()).hexdigest(),"bytes":len(content.encode())}
        return records
    def _write_evidence(self,r):
        self.evidence.mkdir(parents=True,exist_ok=True); p=self.evidence/(r["id"]+".json")
        if not p.exists():
            q=dict(r); q["evidence_digest"]=digest(q); atomic(p,q)
            t=self.task(r["task_id"]); target=self._task_directory(t)/"runs"/r["id"]/"run.json"
            if not target.exists(): atomic(target,q)
            report=target.parent/"report.md"
            if not report.exists():
                with report.open("x") as f:
                    f.write(f"# Run {r['id']}\n\nStatus: {r['status']}\nTicket: {r.get('ticket','')}\nClone: {r.get('source_clone','')}\nBase: {r.get('base_commit','')}\nHead: {r.get('worker_result',{}).get('commit','')}\nWorker: {r.get('runtime','')}\nReviewer: {r.get('review_result',{}).get('review_runtime','not run')}\nVerdict: {r.get('review_result',{}).get('verdict','not run')}\nStarted: {r.get('started_at','')}\nFinished: {r.get('finished_at','')}\n")
            r["evidence_path"]=str(p); r["evidence_digest"]=q["evidence_digest"]
    @staticmethod
    def _pid_info(pid):
        try:
            # Field 22 is process start ticks; a reused PID is not the same run.
            fields=Path(f"/proc/{pid}/stat").read_text().rsplit(") ",1)[1].split()
            return fields[0],fields[19]
        except (FileNotFoundError,ProcessLookupError,IndexError): return None,None
    def reconcile(self):
        changed=False
        for r in self.state.get("runs",{}).values():
            if r.get("status") not in ACTIVE or not r.get("detached") or not r.get("pid"): continue
            pid_state,pid_start=self._pid_info(r["pid"])
            if pid_state and pid_state!="Z" and (not r.get("pid_start_ticks") or r["pid_start_ticks"]==pid_start): continue
            previous=read(self.evidence/(r["id"]+".json"),{})
            if previous.get("status") in TERMINAL:
                r.update(previous)
            else:
                r.update(status="aborted",finished_at=now(),error={"code":"PROCESS_MISSING","message":"detached runner disappeared without terminal evidence"})
                self._write_evidence(r)
            changed=True
        if changed: self.save(); self.dispatch_ready()
    def dispatch_ready(self):
        for t in list(self.state["tasks"].values()):
            if t["approval"]=="approved" and not t.get("status") and not any(r["task_id"]==t["id"] for r in self.state["runs"].values()):
                try: self.start(t["id"],detach=True)
                except OrchestratorError: pass
    def status(self,task_id=None): return {"task":self.task(task_id),"runs":[r for r in self.state["runs"].values() if r["task_id"]==task_id]} if task_id else {"tasks":list(self.state["tasks"].values()),"runs":list(self.state["runs"].values())}
    def cancel(self,run_id):
        r=self.state["runs"].get(run_id)
        if not r: raise OrchestratorError("RUN_NOT_FOUND",run_id)
        if r["status"] not in ACTIVE: raise OrchestratorError("RUN_NOT_ACTIVE",r["status"])
        for stage in ("worker","review"):
            subprocess.run(["docker","stop","--time","1","thesystem-"+run_id+"-"+stage],capture_output=True,timeout=10)
        if r.get("pid"):
            try: os.killpg(r["pid"],signal.SIGTERM)
            except ProcessLookupError: pass
        r.update(status="cancelled",finished_at=now(),cancelled_at=now()); self._write_evidence(r); self.save(); self.dispatch_ready(); return r
    def integrate(self,run_id):
        r=self.state["runs"].get(run_id)
        if not r: raise OrchestratorError("RUN_NOT_FOUND",run_id)
        if r["status"]!="passed": raise OrchestratorError("INTEGRATION_NOT_ALLOWED",r["status"])
        c=Path(self.task(r["task_id"])["source_clone"])
        if git(c,"rev-parse","HEAD")!=r["base_commit"]: raise OrchestratorError("INTEGRATION_BASE_MOVED",git(c,"rev-parse","HEAD"))
        git(c,"merge","--no-ff",r["branch"],"-m",f"Integrate theSystem run {run_id}")
        r["integrated_at"]=now(); r["integration_commit"]=git(c,"rev-parse","HEAD")
        self.task(r["task_id"])["status"]="done"; self.save(); self._materialize_task(self.task(r["task_id"]))
        event=self._task_directory(self.task(r["task_id"]))/"runs"/run_id/"integration.json"; atomic(event,{"run_id":run_id,"base_commit":r["base_commit"],"integration_commit":r["integration_commit"],"integrated_at":r["integrated_at"]})
        self.dispatch_ready(); return r

def shutil_which(x):
    import shutil; return shutil.which(x)
def main(argv=None):
    p=argparse.ArgumentParser(prog="orchestrator"); p.add_argument("action",choices=["create-task","approve","start","status","cancel","integrate","_run"]); p.add_argument("--project",required=True); p.add_argument("--task",dest="task_id"); p.add_argument("--run"); p.add_argument("--source-clone"); p.add_argument("--command",default=""); p.add_argument("--runtime",default="hermes"); p.add_argument("--ticket",default="local"); p.add_argument("--timeout",type=int,default=3600); p.add_argument("--dispatch",action="store_true"); a=p.parse_args(argv); o=Orchestrator(a.project)
    if a.action=="create-task": out=o.create_task(a.task_id,a.source_clone,a.command,a.runtime,a.ticket)
    elif a.action=="approve": out=o.approve(a.task_id,True,a.timeout)
    elif a.action=="start": out=o.start(a.task_id,a.timeout,True)
    elif a.action=="_run": o._execute(o.state["runs"][a.run],o.task(o.state["runs"][a.run]["task_id"])); o.save(); return 0
    elif a.action=="status": out=o.status(a.task_id)
    elif a.action=="cancel": out=o.cancel(a.run)
    else: out=o.integrate(a.run)
    print(json.dumps(out,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
