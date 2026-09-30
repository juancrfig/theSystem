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

TERMINAL={"passed","changes-requested","execution-failed","review-failed","cancelled","timeout","aborted","infra_blocked","isolation_violated"}
ACTIVE={"starting","running","reviewing"}
RUNTIMES={"hermes","copilot"}
ROLE_SECTIONS=("rules","skills","tools","utils","clis","mcp_servers")
class OrchestratorError(Exception):
    def __init__(self,code,message): super().__init__(message); self.code=code

class _NoCredentialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

_provider_opener=build_opener(_NoCredentialRedirect())

class HostCredentialBroker:
    """Host-owned provider credential and short-lived, model-scoped agent capability."""
    def __init__(self, upstream_url, provider_key, model, lifetime=3600, max_requests=2000):
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
    def from_environment(cls,runtime,env=None,lifetime=3600,max_requests=2000):
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
        return cls(upstream,key,model,lifetime=lifetime,max_requests=max_requests)

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
            filtered={"host","authorization","content-length","connection","transfer-encoding"}
            headers={k:v for k,v in handler.headers.items() if k.lower() not in filtered}
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
                   if key.lower() not in ("host", "authorization", "content-length", "connection", "transfer-encoding")}
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

def _tree_digest(root):
    root=Path(root)
    entries=[]
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if ".git" in path.relative_to(root).parts: continue
        relative=path.relative_to(root).as_posix()
        entries.append(relative+":"+hashlib.sha256(path.read_bytes()).hexdigest())
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()

def _slug(value):
    return isinstance(value,str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",value)

class Orchestrator:
    def __init__(self,project,global_agents=None):
        self.project=Path(project).expanduser().resolve()
        if not self.project.is_dir(): raise OrchestratorError("PROJECT_NOT_FOUND",str(self.project))
        self.global_agents=(Path(global_agents).expanduser().resolve() if global_agents else Path(__file__).resolve().parent/"agents")
        if not self.global_agents.is_dir(): raise OrchestratorError("ROLE_CONFIG_INVALID","global agents directory is missing")
        self.root=self.project/".thesystem"/"orchestrator"; self.state_path=self.root/"state.json"; self.evidence=self.root/"runs"
        self.state=read(self.state_path,{"version":2,"tasks":{},"runs":{}})
        self.reconcile()
    def save(self):
        self.root.mkdir(parents=True,exist_ok=True)
        with open(self.root/"state.lock","a+") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            current=read(self.state_path,{"version":2,"tasks":{},"runs":{}})
            rank={"starting":0,"running":1,"reviewing":2,"passed":3,"changes-requested":3,"execution-failed":3,"review-failed":3,"cancelled":3,"timeout":3,"aborted":3,"infra_blocked":3,"isolation_violated":3}
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
    def _normalize_acceptance(self, acceptance, fallback_prompt):
        if not acceptance:
            acceptance=[{"text":fallback_prompt.strip(),"verify":{"type":"human","instructions":"Validate manually against the stated behavior."}}]
        normalized=[]
        for index,item in enumerate(acceptance):
            if isinstance(item,str):
                normalized.append({"text":item,"verify":{"type":"human","instructions":"Validate manually against this criterion."}})
            elif isinstance(item,dict):
                normalized.append(item)
            else:
                raise OrchestratorError("ACCEPTANCE_INVALID",f"acceptance criterion {index+1} must be a string or object")
        return normalized
    def _acceptance_lines(self, t):
        lines=[]
        for criterion in t.get("acceptance",[]):
            if isinstance(criterion,str):
                lines.append(criterion)
                continue
            text=(criterion.get("text") or "").strip()
            verify=criterion.get("verify") if isinstance(criterion,dict) else None
            if isinstance(verify,dict):
                if verify.get("type")=="command":
                    lines.append(f"{text} (Verify: command `{verify.get('command','')}`)")
                elif verify.get("type")=="human":
                    lines.append(f"{text} (Verify: human — {verify.get('instructions','')})")
                else:
                    lines.append(text)
            else:
                lines.append(text)
        return [x for x in lines if x]
    def _load_roles_file(self,path):
        if not path.exists(): return {}
        if path.is_symlink() or not path.is_file(): raise OrchestratorError("ROLE_CONFIG_INVALID",f"roles file is not a regular file: {path}")
        try: payload=json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise OrchestratorError("ROLE_CONFIG_INVALID",f"roles file must be JSON-compatible YAML object: {path}: {error.msg}") from error
        if not isinstance(payload,dict): raise OrchestratorError("ROLE_CONFIG_INVALID",f"roles file must contain an object: {path}")
        normalized={}
        for role,spec in payload.items():
            if not isinstance(role,str) or not role.strip() or not isinstance(spec,dict):
                raise OrchestratorError("ROLE_CONFIG_INVALID",f"invalid role declaration in {path}: {role!r}")
            role_spec={}
            for section,entries in spec.items():
                if section not in ROLE_SECTIONS:
                    raise OrchestratorError("ROLE_CONFIG_INVALID",f"unknown role section {section!r} in {path}")
                if not isinstance(entries,list) or any((not isinstance(entry,str) or not entry.strip()) for entry in entries):
                    raise OrchestratorError("ROLE_CONFIG_INVALID",f"role section {role}.{section} in {path} must be a list of non-empty strings")
                role_spec[section]=[entry.strip() for entry in entries]
            normalized[role]=role_spec
        return normalized
    def _effective_roles(self):
        global_roles=self._load_roles_file(self.global_agents/"roles.yaml")
        project_roles=self._load_roles_file(self.project/"agents"/"roles.yaml")
        merged={name:{section:list(entries) for section,entries in spec.items()} for name,spec in global_roles.items()}
        for role,spec in project_roles.items():
            current=merged.setdefault(role,{})
            for section,entries in spec.items(): current[section]=list(entries)
        return merged
    def _review_roles(self,worker_roles):
        review=[]
        replaced=False
        for role in worker_roles:
            if role=="worker": review.append("reviewer"); replaced=True
            elif role!="reviewer": review.append(role)
        if not replaced and "reviewer" not in review: review.append("reviewer")
        return review
    def _role_entries(self,roles,section,effective):
        items=[]
        for role in roles:
            spec=effective.get(role)
            if spec is None: raise OrchestratorError("ROLE_INVALID",f"unknown role: {role}")
            items.extend(spec.get(section,[]))
        return items
    def _resolve_entry_source(self,section,entry):
        path=Path(entry)
        if path.is_absolute() or ".." in path.parts: raise OrchestratorError("ROLE_INVALID",f"{section} entry must stay inside agents/: {entry}")
        project_root=self.project/"agents"
        global_root=self.global_agents
        if section=="skills" and path.parts and path.parts[0]=="skills" and len(path.parts)>=2:
            skill_root=Path("skills")/path.parts[1]
            candidate=project_root/skill_root
            if candidate.exists():
                source=candidate
                remainder=Path(*path.parts[2:]) if len(path.parts)>2 else Path()
                if remainder and not (source/remainder).exists():
                    raise OrchestratorError("ROLE_INVALID",f"skill entry not found in project tier: {entry}")
                return source,skill_root
            candidate=global_root/skill_root
            if candidate.exists():
                source=candidate
                remainder=Path(*path.parts[2:]) if len(path.parts)>2 else Path()
                if remainder and not (source/remainder).exists():
                    raise OrchestratorError("ROLE_INVALID",f"skill entry not found in global tier: {entry}")
                return source,skill_root
            raise OrchestratorError("ROLE_INVALID",f"skill entry not found: {entry}")
        for tier in (project_root,global_root):
            source=tier/path
            if source.exists(): return source,path
        raise OrchestratorError("ROLE_INVALID",f"{section} entry not found: {entry}")
    def _copy_into_bundle(self,source,target):
        if source.is_symlink(): raise OrchestratorError("ROLE_INVALID",f"symlink entries are not allowed in bundle source: {source}")
        target.parent.mkdir(parents=True,exist_ok=True)
        if source.is_dir():
            shutil.copytree(source,target,dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source,target)
        else:
            raise OrchestratorError("ROLE_INVALID",f"bundle source must be a file or directory: {source}")
    def _bundle_manifest(self,bundle_root):
        entries=[]
        for file in sorted(p for p in bundle_root.rglob("*") if p.is_file()):
            relative=file.relative_to(bundle_root).as_posix()
            entries.append({"path":relative,"sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
        return {"entries":entries,"digest":digest(entries)}
    def _build_bundle(self,run_id,agent,roles,effective):
        bundle_root=self.root/"bundles"/run_id/agent
        if bundle_root.exists(): shutil.rmtree(bundle_root)
        bundle_root.mkdir(parents=True,exist_ok=True)
        selected={section:self._role_entries(roles,section,effective) for section in ROLE_SECTIONS}
        for section in ("rules","skills","tools","utils"):
            copied=set()
            for entry in selected[section]:
                source,relative=self._resolve_entry_source(section,entry)
                key=relative.as_posix()
                if key in copied: continue
                self._copy_into_bundle(source,bundle_root/relative)
                copied.add(key)
        manifest=self._bundle_manifest(bundle_root)
        manifest["roles"]=list(roles)
        manifest["clis"]=selected["clis"]
        manifest["mcp_servers"]=selected["mcp_servers"]
        (bundle_root/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
        return {"path":str(bundle_root),"manifest":manifest}
    def _ensure_reviewer_covers_worker(self,worker_manifest,review_manifest):
        worker_rules={entry["path"] for entry in worker_manifest["manifest"]["entries"] if entry["path"].startswith("rules/")}
        reviewer_rules={entry["path"] for entry in review_manifest["manifest"]["entries"] if entry["path"].startswith("rules/")}
        missing=sorted(worker_rules-reviewer_rules)
        if missing: raise OrchestratorError("REVIEWER_RULES_MISSING",f"reviewer bundle is missing worker rule: {missing[0]}")
    def create_task(self,task_id,source_clone,command,runtime="hermes",ticket="local",acceptance=None,dependencies=None,roles=None):
        if not _slug(task_id) or not _slug(ticket): raise OrchestratorError("IDENTIFIER_INVALID","task and ticket must be safe slugs")
        if task_id in self.state["tasks"]: raise OrchestratorError("TASK_EXISTS",task_id)
        clone=Path(source_clone).expanduser().resolve()
        if not clone.is_dir() or not (clone/".git").exists(): raise OrchestratorError("SOURCE_CLONE_INVALID",str(clone))
        if runtime not in RUNTIMES: raise OrchestratorError("RUNTIME_INVALID",runtime)
        if not isinstance(command,str) or not command.strip(): raise OrchestratorError("PROMPT_REQUIRED","agent prompt is required")
        criteria=self._normalize_acceptance(acceptance,command)
        self.state["tasks"][task_id]={"id":task_id,"ticket":ticket,"source_clone":str(clone),"prompt":command,"command":command,"runtime":runtime,"acceptance":criteria,"dependencies":dependencies or [],"roles":roles or ["base","worker"],"base_ref":"HEAD","approval":"proposed","created_at":now()}; self.save(); self._materialize_task(self.task(task_id)); return self.task(task_id)
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
    def _task_contract(self,t):
        return {
            "project":str(self.project),
            "ticket":t["ticket"],
            "task":t["id"],
            "source_clone":t["source_clone"],
            "base_ref":t.get("base_ref","HEAD"),
            "runtime":t["runtime"],
            "roles":t.get("roles",[]),
            "what_to_build":t.get("prompt",""),
            "acceptance_criteria":t.get("acceptance",[]),
            "blockers":[{"task":dep} for dep in t.get("dependencies",[])],
            "status":"done" if t.get("status")=="done" else "ready-for-agent" if t["approval"]=="approved" else "proposed",
        }
    def _read_task_contract(self,t):
        path=self._task_directory(t)/"task.md"
        errors=[]
        if not path.exists():
            return None,[f"missing contract file: {path}"]
        text=path.read_text()
        if not text.startswith("---\n"):
            return None,["task contract must begin with front matter delimiter ---"]
        end=text.find("\n---\n",4)
        if end==-1:
            return None,["task contract front matter is not closed with ---"]
        front=text[4:end].strip()
        try:
            contract=json.loads(front)
        except json.JSONDecodeError as error:
            return None,[f"task contract front matter must be JSON-compatible YAML object: {error.msg}"]
        if not isinstance(contract,dict):
            return None,["task contract front matter must decode to an object"]
        return contract,errors
    def _validate_task_contract(self,t):
        contract,errors=self._read_task_contract(t)
        if contract is None:
            raise OrchestratorError("TICKET_INVALID","; ".join(errors))
        required=("project","ticket","task","source_clone","base_ref","runtime","roles","what_to_build","acceptance_criteria","blockers","status")
        for field in required:
            if field not in contract: errors.append(f"missing required field: {field}")
        if isinstance(contract.get("project"),str):
            if contract["project"]!=str(self.project): errors.append("project must match the orchestrator project path")
        elif "project" in contract:
            errors.append("project must be a string")
        if "ticket" in contract and (not isinstance(contract["ticket"],str) or not _slug(contract["ticket"])):
            errors.append("ticket must be a safe slug")
        elif isinstance(contract.get("ticket"),str) and contract["ticket"]!=t["ticket"]:
            errors.append("ticket must match orchestrator task metadata")
        if "task" in contract and (not isinstance(contract["task"],str) or not _slug(contract["task"])):
            errors.append("task must be a safe slug")
        elif isinstance(contract.get("task"),str) and contract["task"]!=t["id"]:
            errors.append("task must match orchestrator task metadata")
        source=contract.get("source_clone")
        if "source_clone" in contract:
            if not isinstance(source,str) or not source.strip():
                errors.append("source_clone must be a non-empty string")
            elif source!=t["source_clone"]:
                errors.append("source_clone must match orchestrator task metadata")
        if "runtime" in contract and contract.get("runtime") not in RUNTIMES:
            errors.append("runtime must be one of: "+", ".join(sorted(RUNTIMES)))
        elif contract.get("runtime")!=t["runtime"]:
            errors.append("runtime must match orchestrator task metadata")
        roles=contract.get("roles")
        if "roles" in contract:
            if not isinstance(roles,list) or not all(isinstance(role,str) for role in roles):
                errors.append("roles must be a list of strings")
            elif "worker" not in roles:
                errors.append("roles must include worker")
        if "what_to_build" in contract and (not isinstance(contract["what_to_build"],str) or not contract["what_to_build"].strip()):
            errors.append("what_to_build must be a non-empty string")
        criteria=contract.get("acceptance_criteria")
        if "acceptance_criteria" in contract:
            if not isinstance(criteria,list) or not criteria:
                errors.append("acceptance_criteria must be a non-empty list")
            else:
                for index,criterion in enumerate(criteria,start=1):
                    if not isinstance(criterion,dict):
                        errors.append(f"acceptance_criteria[{index}] must be an object")
                        continue
                    text=(criterion.get("text") or "") if isinstance(criterion.get("text"),str) else ""
                    if not text.strip(): errors.append(f"acceptance_criteria[{index}].text is required")
                    verify=criterion.get("verify")
                    if not isinstance(verify,dict):
                        errors.append(f"acceptance_criteria[{index}].verify is required")
                        continue
                    verify_type=verify.get("type")
                    if verify_type=="command":
                        if not isinstance(verify.get("command"),str) or not verify["command"].strip():
                            errors.append(f"acceptance_criteria[{index}].verify.command is required")
                    elif verify_type=="human":
                        if not isinstance(verify.get("instructions"),str) or not verify["instructions"].strip():
                            errors.append(f"acceptance_criteria[{index}].verify.instructions is required")
                    else:
                        errors.append(f"acceptance_criteria[{index}].verify.type must be command or human")
        blockers=contract.get("blockers")
        blocker_tasks=[]
        if "blockers" in contract:
            if not isinstance(blockers,list):
                errors.append("blockers must be a list")
            else:
                for index,blocker in enumerate(blockers,start=1):
                    if isinstance(blocker,dict) and isinstance(blocker.get("task"),str) and blocker["task"].strip():
                        blocker_tasks.append(blocker["task"].strip())
                    elif isinstance(blocker,dict) and isinstance(blocker.get("external"),str) and blocker.get("state") in {"done","open"}:
                        pass
                    else:
                        errors.append(f"blockers[{index}] must be {{task:<id>}} or {{external:<id>,state:done|open}}")
        expected=sorted(str(dep) for dep in t.get("dependencies",[]))
        if sorted(blocker_tasks)!=expected:
            errors.append("blockers must match orchestrator dependency list")
        if "status" in contract and contract["status"] not in {"proposed","ready-for-agent","done"}:
            errors.append("status must be proposed, ready-for-agent, or done")
        if "base_ref" in contract and (not isinstance(contract["base_ref"],str) or not contract["base_ref"].strip()):
            errors.append("base_ref must be a non-empty string")
        if errors:
            raise OrchestratorError("TICKET_INVALID","; ".join(errors))
        return contract,blockers
    def _materialize_task(self,t):
        d=self._task_directory(t); d.mkdir(parents=True,exist_ok=True)
        ticket=d.parent.parent
        f=ticket/"ticket.md"
        if not f.exists(): f.write_text(f"# {t['ticket']}\n\nLocal acceptance ticket.\n")
        spec=ticket/"spec.md"
        if not spec.exists(): spec.write_text("# Specification\n\nSee the individual approved tasks for scope.\n")
        contract=self._task_contract(t)
        frontmatter=json.dumps(contract,indent=2,sort_keys=True)
        acceptance="\n".join(f"- {line}" for line in self._acceptance_lines(t))
        blockers="\n".join(f"- {item['task']}" for item in contract.get("blockers",[])) or "- None (can start immediately)"
        (d/"task.md").write_text("---\n"+frontmatter+"\n---\n\n# "+t["id"]+"\n\n## What to build\n\n"+contract["what_to_build"].strip()+"\n\n## Acceptance criteria\n"+acceptance+"\n\n## Blocked by\n"+blockers+"\n")
    def _admission(self,t):
        _,blockers=self._validate_task_contract(t)
        for blocker in blockers:
            if isinstance(blocker,dict) and isinstance(blocker.get("task"),str):
                dep=blocker["task"].strip()
                if dep not in self.state["tasks"] or self.state["tasks"][dep].get("status")!="done":
                    raise OrchestratorError("BLOCKED",dep)
            elif isinstance(blocker,dict) and isinstance(blocker.get("external"),str) and blocker.get("state")!="done":
                raise OrchestratorError("BLOCKED",blocker["external"])
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
        rid=uuid.uuid4().hex
        effective_roles=self._effective_roles()
        worker_roles=list(t.get("roles") or [])
        reviewer_roles=self._review_roles(worker_roles)
        worker_bundle=self._build_bundle(rid,"worker",worker_roles,effective_roles)
        reviewer_bundle=self._build_bundle(rid,"reviewer",reviewer_roles,effective_roles)
        self._ensure_reviewer_covers_worker(worker_bundle,reviewer_bundle)
        clone=Path(t["source_clone"]); base=git(clone,"rev-parse","HEAD"); branch=f"thesystem/{task_id.replace('/','-')}/{uuid.uuid4().hex[:8]}"; git(clone,"branch",branch,base)
        r={"id":rid,"task_id":task_id,"status":"starting","runtime":t["runtime"],"ticket":t["ticket"],"source_clone":t["source_clone"],"models":{"worker":"openai/gpt-4.1-mini" if t["runtime"]=="hermes" else "copilot/default"},"base_commit":base,"branch":branch,"started_at":now(),"started_epoch":time.time(),"timeout_seconds":int(timeout),"evidence":[],"worker":{"prompt":t["prompt"],"roles":worker_roles,"bundle":worker_bundle},"reviewer":{"roles":reviewer_roles,"bundle":reviewer_bundle}}
        self.state["runs"][rid]=r; self.save()
        if detach:
            p=subprocess.Popen([sys.executable,__file__,"_run","--project",str(self.project),"--run",rid],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            r["pid"]=p.pid; r["pid_start_ticks"]=self._pid_info(p.pid)[1]; r["detached"]=True; self.save(); return r
        self._execute(r,t); self.save(); return r
    def _execute(self,r,t):
        try:
            r["status"]="running"; self.save(); probes=self._run_isolation_probes(r,t); r["isolation_probes"]=probes
            failed_probe=next((probe for probe in probes if not probe.get("ok")),None)
            if failed_probe:
                r["status"]="infra_blocked"
                r["error"]={"code":"ISOLATION_PROBE_FAILED","message":failed_probe.get("message") or failed_probe.get("name","isolation probe failed")}
                return
            result=self._worker(r,t); r["worker_result"]=result
            if result.get("timed_out"): r["status"]="timeout"
            elif result.get("returncode")!=0 or result.get("commit")==r["base_commit"]: r["status"]="execution-failed"
            else:
                clone=Path(t["source_clone"])
                before_review_tree=git(clone,"rev-parse",r["branch"]+"^{tree}")
                r["status"]="reviewing"; self.save(); review=self._review(r,t); r["review_result"]=review
                after_review_tree=git(clone,"rev-parse",r["branch"]+"^{tree}")
                r["worker_tree_hash"]={"before_review":before_review_tree,"after_review":after_review_tree}
                if before_review_tree!=after_review_tree:
                    r["status"]="isolation_violated"
                    r["error"]={"code":"ISOLATION_VIOLATED","message":"implementer tree changed during review"}
                else:
                    r["status"]="passed" if review["passed"] else ("timeout" if review.get("timed_out") else "review-failed" if review.get("returncode",1)!=0 else "changes-requested")
        except Exception as e: r.update(status="review-failed" if r["status"]=="reviewing" else "execution-failed",error={"code":type(e).__name__,"message":str(e)})
        r["finished_at"]=now()
        self._write_evidence(r); self.save(); self.dispatch_ready()
    def _run_isolation_probe(self,image,work,bundle,name):
        args=["docker","run","--rm","--network","none","--cap-drop=ALL","--security-opt","no-new-privileges","--user",f"{os.getuid()}:{os.getgid()}","-v",f"{work}:/workspace"]
        if bundle: args += ["-v",f"{bundle}:/bundle:ro"]
        marker=".theSystem-isolation-probe"
        script="set -eu; printf ok > /workspace/%s; rm -f /workspace/%s; if sh -ceu 'printf blocked > /tmp/%s' 2>/dev/null; then rm -f /tmp/%s; echo outside-write-allowed; exit 41; fi" % (marker,marker,marker,marker)
        if bundle:
            script += "; if sh -ceu 'printf blocked > /bundle/%s' 2>/dev/null; then rm -f /bundle/%s; echo bundle-write-allowed; exit 42; fi" % (marker,marker)
        probe=subprocess.run([*args,image,"sh","-ceu",script],capture_output=True,text=True,timeout=30)
        return {"name":name,"ok":probe.returncode==0,"returncode":probe.returncode,"stdout":probe.stdout[-1000:],"stderr":probe.stderr[-1000:],"message":"" if probe.returncode==0 else "isolation probe failed"}
    def _run_isolation_probes(self,r,t):
        clone=Path(t["source_clone"])
        worker_image=os.environ.get("THESYSTEM_"+t["runtime"].upper()+"_IMAGE") or os.environ.get("THESYSTEM_AGENT_IMAGE")
        review_runtime=os.environ.get("THESYSTEM_REVIEW_RUNTIME",t["runtime"])
        if review_runtime not in RUNTIMES: raise OrchestratorError("REVIEW_RUNTIME_INVALID",review_runtime)
        reviewer_image=os.environ.get("THESYSTEM_"+review_runtime.upper()+"_IMAGE") or os.environ.get("THESYSTEM_REVIEW_IMAGE") or os.environ.get("THESYSTEM_AGENT_IMAGE")
        worker_probe_work=self.root/"probe-workspaces"/(r["id"]+"-worker")
        reviewer_probe_work=self.root/"probe-workspaces"/(r["id"]+"-reviewer")
        for path in (worker_probe_work,reviewer_probe_work):
            if path.exists(): shutil.rmtree(path)
            shutil.copytree(clone,path,ignore=shutil.ignore_patterns('.git'))
        probes=[]
        try:
            probes.append(self._run_isolation_probe(worker_image,worker_probe_work,r.get("worker",{}).get("bundle",{}).get("path"),"worker-worktree-and-bundle"))
            probes.append(self._run_isolation_probe(reviewer_image,reviewer_probe_work,r.get("reviewer",{}).get("bundle",{}).get("path"),"reviewer-worktree-and-bundle"))
            return probes
        finally:
            shutil.rmtree(worker_probe_work,ignore_errors=True)
            shutil.rmtree(reviewer_probe_work,ignore_errors=True)
    def _docker(self,image,work,cmd,timeout,prompt,readonly=False,layer=None,runtime="copilot",container_name=None,bundle=None):
        if not shutil.which("docker"): raise OrchestratorError("DOCKER_UNAVAILABLE","docker is required")
        if not image: raise OrchestratorError("AGENT_IMAGE_REQUIRED","configure an image with the selected CLI")
        broker=HostCredentialBroker.from_environment(runtime,lifetime=max(1,int(timeout))+30,max_requests=max(2000,int(timeout)*10))
        network_mode=(os.environ.get("THESYSTEM_CONTAINER_NETWORK") or "none").strip().lower()
        if network_mode not in {"none","bridge"}:
            raise OrchestratorError("CONTAINER_NETWORK_INVALID","THESYSTEM_CONTAINER_NETWORK must be none or bridge")
        args=["docker","run","--rm",*(["--name",container_name] if container_name else []),"--network",network_mode,"--init","--cap-drop=ALL","--security-opt","no-new-privileges","--pids-limit","256","--memory","2g","--cpus","2","--user",f"{os.getuid()}:{os.getgid()}","-v",f"{work}:/workspace"+(':ro' if readonly else ''),"-v",f"{prompt}:/run/prompt:ro","-w","/workspace"]
        if bundle: args += ["-v",f"{bundle}:/bundle:ro","-e","THESYSTEM_BUNDLE=/bundle"]
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
                    args += ["-v",f"{agent_home}:/run/copilot-home","-e","HOME=/run/copilot-home","-e","XDG_CACHE_HOME=/run/copilot-home/.cache","-e","COPILOT_HOME=/run/copilot-home","-e","COPILOT_PROVIDER_TYPE=openai","-e","COPILOT_PROVIDER_BASE_URL=http://127.0.0.1:18080/v1","-e","COPILOT_PROVIDER_API_KEY="+broker.capability,"-e","COPILOT_MODEL="+broker.model]
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
            return ["copilot","-p",(prompt+"\nInspect and test in /workspace. This is a disposable review copy of the implementer result; you may modify files for validation as needed. End your response with exactly VERDICT: PASS or VERDICT: FAIL and a reason. Do not access paths outside /workspace." if review else prompt+"\nImplement in /workspace. This is an intentionally empty initial clone; the .git worktree pointer targets host metadata not mounted in the container. Do not attempt to resolve that pointer; create the requested files. The host orchestrator owns commits. Do not access paths outside /workspace."),"--allow-all-tools","--disallow-temp-dir","--disable-builtin-mcps","--available-tools","bash","--reasoning-effort","none",*(["--allow-all-paths"] if review else []),"--no-auto-update","--no-remote","--no-remote-export","--no-ask-user"]
        return ["hermes","chat","--oneshot","--yolo","--ignore-rules","--provider","custom","--query-file","/run/prompt","--in","/workspace","--run-budget","600","--max-turns","40"]
    def _worker(self,r,t):
        clone=Path(t["source_clone"]); work=self.root/"worktrees"/r["id"]; work.parent.mkdir(parents=True,exist_ok=True); git(clone,"worktree","add",str(work),r["branch"])
        previous=[x for x in self.state["runs"].values() if x["task_id"]==r["task_id"] and x["id"]!=r["id"] and x.get("worker_result",{}).get("commit") not in (None,x["base_commit"]) and x["status"] in ("changes-requested","review-failed")]
        if previous:
            seed=previous[-1]; git(work,"-c","user.email=theSystem@localhost","-c","user.name=theSystem","cherry-pick",seed["worker_result"]["commit"]); r["seeded_from_run"]=seed["id"]; self.save()
        image=os.environ.get("THESYSTEM_"+t["runtime"].upper()+"_IMAGE") or os.environ.get("THESYSTEM_AGENT_IMAGE")
        prompt=t["prompt"]+"\nAcceptance criteria:\n"+"\n".join(self._acceptance_lines(t))+"\nYou are the worker. Edit only /workspace; do not push or publish. Use /bundle as read-only role context when needed."
        pf=self.root/"prompts"/(r["id"]+"-worker.txt"); pf.parent.mkdir(parents=True,exist_ok=True); pf.write_text(prompt)
        try:
            p=self._docker(image,work,self._agent_command(t["runtime"],prompt=prompt),max(1,int(r["started_epoch"]+r["timeout_seconds"]-time.time())),pf,runtime=t["runtime"],container_name="thesystem-"+r["id"]+"-worker",bundle=r.get("worker",{}).get("bundle",{}).get("path"))
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
        pf=self.root/"prompts"/(r["id"]+"-review.txt"); pf.parent.mkdir(parents=True,exist_ok=True); pf.write_text("Independent review. Criteria:\n"+"\n".join(self._acceptance_lines(t))+"\n/workspace is a disposable review copy. You may run tests/builds and make temporary edits there. End exactly VERDICT: PASS or VERDICT: FAIL with reasons.")
        layer=self.root/"layers"/r["id"]
        if layer.exists(): shutil.rmtree(layer)
        shutil.copytree(work,layer,ignore=shutil.ignore_patterns('.git'))
        before_layer_hash=_tree_digest(layer)
        try:
            test_cmd=["python3","-m","unittest","discover","-s","tests","-q"] if (layer/"tests").exists() else (["npm","test"] if (layer/"package.json").exists() else None)
            test_args=["docker","run","--rm","--network","none","--cap-drop=ALL","--security-opt","no-new-privileges","--user",f"{os.getuid()}:{os.getgid()}","-v",f"{layer}:/workspace","-w","/workspace",image,*(test_cmd or ["false"])]
            before_test=subprocess.run(test_args,capture_output=True,text=True,timeout=120)
            p=self._docker(image,layer,self._agent_command(review_runtime,True,pf.read_text()),max(1,min(900,int(r["started_epoch"]+r["timeout_seconds"]-time.time()))),pf,readonly=False,layer=None,runtime=review_runtime,container_name="thesystem-"+r["id"]+"-review",bundle=r.get("reviewer",{}).get("bundle",{}).get("path"))
            streams=self._stream(r,"review",p) if p is not None else {}
            unchanged=before_layer_hash==_tree_digest(work)
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
