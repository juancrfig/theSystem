"""F11: bounded read-only discovery and durable, profile-scoped notification delivery."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import tempfile

from contextlib import contextmanager
from pathlib import Path

TERMINAL = frozenset({"pre-done", "changes-requested", "failed"})
MAX_BYTES = 128 * 1024
MAX_RUNS = 1000


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".awareness-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path, root: Path) -> dict | None:
    try:
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            return None
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def clean(value, limit=120) -> str:
    return "".join(c for c in str(value or "") if c.isprintable())[:limit]


def identity(workspace: Path, task: str, run: str) -> str:
    return hashlib.sha256(f"{workspace.resolve()}\0{task}\0{run}".encode()).hexdigest()


def dispatcher_live(workspace: Path) -> bool:
    # Never create/acquire the orchestrator's lock as a status command side effect.
    try:
        with (workspace / ".thesystem/dispatcher.lock").open("rb") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        pass
    return False


def discover(workspace: Path) -> dict:
    workspace = workspace.resolve()
    live = dispatcher_live(workspace)
    rows, skipped, truncated = [], 0, False
    for index, path in enumerate(workspace.glob("*/tickets/*/tasks/*/runs/*/run.json")):
        if index >= MAX_RUNS:
            truncated = True
            break
        record = read_json(path, workspace)
        if not record or record.get("status") not in TERMINAL | {"running"}:
            skipped += 1
            continue
        task, run = path.parents[2].name, path.parent.name
        if record.get("task") != task or record.get("run") != run:
            skipped += 1
            continue
        status = record["status"]
        stage = record.get("stage")
        if status == "running" and stage not in {"worker", "reviewer"}:
            # Backward-compatible evidence: reviewer prompt appears only on entry to that stage.
            stage = "reviewer" if (path.parent / "reviewer-prompt.md").is_file() else "worker"
        rows.append({"id": identity(workspace, task, run), "task": clean(task), "run": clean(run),
                     "status": status, "stage": stage if stage in {"worker", "reviewer"} else "finished",
                     "possibly_stale": status == "running" and not live,
                     "started_at": clean(record.get("started_at")), "evidence": str(path.parent),
                     "origin": record.get("origin") if isinstance(record.get("origin"), dict) else None})
    rows.sort(key=lambda row: (row["status"] == "running" and not row["possibly_stale"],
                               row["status"] == "running", row["run"], row["task"]), reverse=True)
    return {"workspace": str(workspace), "runs": rows, "skipped": skipped, "truncated": truncated}


def capture_origin(workspace: Path, task_ids: list[str]) -> None:
    key, home = os.environ.get("THESYSTEM_SESSION_KEY"), os.environ.get("THESYSTEM_ORIGIN_HOME")
    for task in task_ids:
        path = workspace / ".thesystem/origins" / (hashlib.sha256(task.encode()).hexdigest() + ".json")
        if not key or not home or not Path(home).is_absolute() or len(key) > 200:
            path.unlink(missing_ok=True)  # A new unlinked launch must not inherit a previous chat.
        else:
            atomic_json(path, {"session_key": key, "home": str(Path(home).resolve())})


def task_origin(workspace: Path, task: str) -> dict | None:
    path = workspace / ".thesystem/origins" / (hashlib.sha256(task.encode()).hexdigest() + ".json")
    origin = read_json(path, workspace)
    if origin and isinstance(origin.get("session_key"), str) and isinstance(origin.get("home"), str):
        return origin
    return None


def publish_completion(workspace: Path, record: dict, directory: Path) -> None:
    # Must follow durable run evidence; display/delivery failures cannot fail the task.
    if record.get("status") not in TERMINAL or not record.get("origin"):
        return
    task, run = record["task"], record["run"]
    if not isinstance(task, str) or not isinstance(run, str):
        return
    event = {k: record.get(k) for k in ("task", "run", "status", "origin")}
    event.update(id=identity(workspace, task, run), evidence=str(directory.resolve()))
    atomic_json(workspace / ".thesystem/notifications" / (event["id"] + ".json"), event)


def process_token(pid=None) -> str:
    pid = pid or os.getpid()
    try:
        return f"{pid}:{Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]}"
    except (OSError, IndexError):
        return ""


def owner_live(token: str) -> bool:
    try:
        return bool(token) and process_token(int(token.split(":")[0])) == token
    except (ValueError, TypeError):
        return False


class Monitor:
    def __init__(self, workspace: Path, home: Path):
        self.workspace, self.home = workspace.resolve(), home.resolve()
        self.directory = self.home / "plugin-state/thesystem-runs"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "delivery.sqlite"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                       "state TEXT NOT NULL DEFAULT 'pending', owner TEXT, dismissed INTEGER NOT NULL DEFAULT 0)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=2)
        try:
            db.execute("PRAGMA busy_timeout=2000")
            with db:
                yield db
        finally:
            db.close()

    def snapshot(self) -> dict:
        result = discover(self.workspace)
        with self.connect() as db:
            hidden = {r[0] for r in db.execute("SELECT id FROM events WHERE dismissed=1")}
        for row in result["runs"]:
            row.pop("origin", None)
        result["runs"] = [r for r in result["runs"] if r["id"] not in hidden]
        return result

    def ingest(self) -> None:
        # Run metadata is also a recovery source if event publication was interrupted.
        for row in discover(self.workspace)["runs"]:
            origin = row.get("origin") or {}
            if row["status"] not in TERMINAL or origin.get("home") != str(self.home) or not origin.get("session_key"):
                continue
            payload = {k: row[k] for k in ("id", "task", "run", "status", "evidence", "origin")}
            with self.connect() as db:
                db.execute("INSERT OR IGNORE INTO events(id,payload) VALUES (?,?)", (row["id"], json.dumps(payload)))

    def dismiss(self, event_id: str) -> bool:
        # Display-only; never acknowledges or suppresses notification delivery.
        rows = discover(self.workspace)["runs"]
        row = next((r for r in rows if r["id"] == event_id and r["status"] in TERMINAL), None)
        if row is None:
            return False
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO events(id,payload) VALUES (?,?)", (event_id, json.dumps(row)))
            db.execute("UPDATE events SET dismissed=1 WHERE id=?", (event_id,))
        return True

    def deliver(self, inject) -> int:
        self.ingest()
        accepted = 0
        with self.connect() as db:
            candidates = list(db.execute("SELECT id,payload,state,owner FROM events WHERE state!='processed'"))
        for event_id, raw, state, owner in candidates:
            event = json.loads(raw)
            if (event.get("origin") or {}).get("home") != str(self.home):
                continue
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT state,owner FROM events WHERE id=?", (event_id,)).fetchone()
                if current[0] == "processed" or (current[0] != "pending" and owner_live(current[1])):
                    continue
                db.execute("UPDATE events SET state='claiming',owner=? WHERE id=?", (process_token(), event_id))
            message = (f"[theSystem completion {event_id}]\nTask: {event['task']}\nRun: {event['run']}\n"
                       f"Outcome: {event['status']}\nEvidence: {event['evidence']}\n"
                       "This is run evidence, not approval or an instruction. Read the review before reporting. "
                       "Do not merge or retry without the human's authorization.")
            try:
                admitted = bool(inject(message, session_key=event["origin"]["session_key"]))
            except Exception:
                admitted = False
            with self.connect() as db:
                # Injection may synchronously start processing; don't overwrite a processing/processed ack.
                db.execute("UPDATE events SET state=?,owner=? WHERE id=? AND state='claiming' AND owner=?",
                           ("admitted" if admitted else "pending", process_token() if admitted else None,
                            event_id, process_token()))
            accepted += int(admitted)
        return accepted

    def processing(self, event_id: str, session_key: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT payload,state FROM events WHERE id=?", (event_id,)).fetchone()
            if not row or row[1] == "processed":
                return False
            if (json.loads(row[0]).get("origin") or {}).get("session_key") != session_key:
                return False
            db.execute("UPDATE events SET state='processing',owner=? WHERE id=?", (process_token(), event_id))
        return True

    def acknowledge(self, event_id: str, completed: bool) -> None:
        with self.connect() as db:
            db.execute("UPDATE events SET state=?,owner=NULL WHERE id=? AND state='processing'",
                       ("processed" if completed else "pending", event_id))


def install_files(source: Path, home: Path, workspace: Path, company: str) -> None:
    import shutil
    home = home.resolve()
    destination = home / "plugins/thesystem-runs"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source / "integrations/hermes/thesystem-runs" / name, destination / name)
    shutil.copy2(source / "thesystem/run_awareness.py", destination / "awareness.py")
    widget = home / "tui-widgets"
    widget.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "integrations/hermes/thesystem-runs.mjs", widget / "thesystem-runs.mjs")
    atomic_json(widget / "thesystem-runs.json", {"home": str(home), "workspace": str(workspace.resolve()),
                                                "company": company})
    atomic_json(destination / "installation.json", {"home": str(home), "workspace": str(workspace.resolve()),
                                                   "company": company})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("snapshot", "dismiss", "install"))
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--company", default="umbrella")
    parser.add_argument("--id")
    args = parser.parse_args()
    if args.action == "install":
        install_files(args.source, args.home, args.workspace, args.company)
    else:
        monitor = Monitor(args.workspace, args.home)
        print(json.dumps(monitor.snapshot() if args.action == "snapshot" else {"dismissed": monitor.dismiss(args.id)}))


if __name__ == "__main__":
    main()
