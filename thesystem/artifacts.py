"""Artifact library (F9): serves the workspace's HTML artifacts on localhost so the human can browse and review them.

Artifacts live in three places, newest first in the index:
  <project>/tickets/<ticket>/artifacts/   work on a ticket
  <project>/artifacts/                    other work on a project
  docs/artifacts/                         workspace-wide work
Run: THESYSTEM_WORKSPACE=<workspace> python3 -m thesystem.artifacts  (the installer runs it as a user service).
"""
from __future__ import annotations

import html
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

PORT = int(os.environ.get("THESYSTEM_ARTIFACTS_PORT", "8765"))
NOT_PROJECTS = {"agents", "docs"}
TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass
class Artifact:
    project: str  # "" for workspace-wide artifacts
    ticket: str   # "" when not tied to a ticket
    path: Path
    rel: str
    title: str
    modified: float


def _title(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            match = TITLE.search(handle.read(8192))
    except OSError:
        match = None
    text = match.group(1).decode("utf-8", "replace").strip() if match else ""
    return html.unescape(" ".join(text.split())) or path.stem


def _artifact_dirs(workspace: Path):
    yield "", "", workspace / "docs" / "artifacts"
    for project in sorted(p for p in workspace.iterdir() if p.is_dir()):
        if project.name.startswith(".") or project.name in NOT_PROJECTS:
            continue
        yield project.name, "", project / "artifacts"
        tickets = project / "tickets"
        if tickets.is_dir():
            for ticket in sorted(t for t in tickets.iterdir() if t.is_dir()):
                yield project.name, ticket.name, ticket / "artifacts"


def find_all(workspace: Path) -> list[Artifact]:
    found = []
    for project, ticket, directory in _artifact_dirs(workspace):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.html"):
            if path.is_file():
                found.append(Artifact(project, ticket, path, path.relative_to(workspace).as_posix(),
                                      _title(path), path.stat().st_mtime))
    return sorted(found, key=lambda a: a.modified, reverse=True)


def is_servable(workspace: Path, rel: str) -> Path | None:
    """The file for *rel* if it sits inside an artifacts folder of the workspace, else None."""
    parts = Path(rel).parts
    if not parts or any(p in ("..", "") or p.startswith(".") for p in parts):
        return None
    allowed = ((len(parts) >= 3 and parts[:2] == ("docs", "artifacts"))
               or (len(parts) >= 3 and parts[0] not in NOT_PROJECTS and parts[1] == "artifacts")
               or (len(parts) >= 5 and parts[0] not in NOT_PROJECTS and parts[1] == "tickets" and parts[3] == "artifacts"))
    if not allowed:
        return None
    path = (workspace / rel).resolve()
    root = workspace.resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def _when(timestamp: float) -> str:
    moment = datetime.fromtimestamp(timestamp)
    return moment.strftime("%b %d, %H:%M") if moment.year == datetime.now().year else moment.strftime("%b %d %Y")


def _row(artifact: Artifact, show_place: bool) -> str:
    place = " · ".join(x for x in (artifact.project or "workspace", artifact.ticket) if x)
    search = html.escape(f"{artifact.title} {artifact.project} {artifact.ticket} {artifact.path.name}".lower())
    meta = f'<span class="place">{html.escape(place)}</span>' if show_place else ""
    return (f'<a class="row" href="/{quote(artifact.rel)}" data-s="{search}">'
            f'<span class="title">{html.escape(artifact.title)}</span>'
            f'<span class="meta">{meta}<time>{_when(artifact.modified)}</time></span></a>')


def render_index(workspace: Path) -> str:
    artifacts = find_all(workspace)
    groups: dict[str, dict[str, list[Artifact]]] = {}
    for artifact in artifacts:
        groups.setdefault(artifact.project, {}).setdefault(artifact.ticket, []).append(artifact)
    sections = []
    if artifacts:
        sections.append('<section><h2>Recent</h2>' + "".join(_row(a, True) for a in artifacts[:5]) + "</section>")
    for project in sorted(groups, key=lambda p: (p == "", p)):
        body = []
        for ticket in sorted(groups[project], key=lambda t: (t != "", t)):
            label = f'<h3>{html.escape(ticket)}</h3>' if ticket else ""
            body.append(label + "".join(_row(a, False) for a in groups[project][ticket]))
        count = sum(len(v) for v in groups[project].values())
        sections.append(f'<section><h2>{html.escape(project or "Workspace")}<small>{count}</small></h2>'
                        + "".join(body) + "</section>")
    empty = ('<p class="empty">No artifacts yet. They appear here when the agent saves HTML files in an '
             '<code>artifacts/</code> folder of a project or ticket.</p>')
    return PAGE.format(count=len(artifacts), workspace=html.escape(workspace.name),
                       content="".join(sections) if artifacts else empty)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Artifacts</title>
<style>
:root{{--bg:#fafaf9;--fg:#1c1917;--mute:#78716c;--line:#e7e5e4;--hover:#f5f5f4;--accent:#2563eb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0c0a09;--fg:#e7e5e4;--mute:#a8a29e;--line:#292524;--hover:#1c1917;--accent:#60a5fa}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}}
main{{max-width:720px;margin:0 auto;padding:56px 20px 96px}}
header{{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:28px}}
h1{{font-size:22px;font-weight:600;letter-spacing:-.02em;margin:0}}
header span{{color:var(--mute);font-size:13px}}
input{{width:100%;padding:10px 14px;margin-bottom:40px;border:1px solid var(--line);border-radius:10px;background:transparent;color:var(--fg);font:inherit;outline:none}}
input:focus{{border-color:var(--accent)}}
section{{margin-bottom:40px}}
h2{{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin:0 0 8px;display:flex;gap:8px}}
h2 small{{font-weight:400;opacity:.7}}
h3{{font-size:13px;font-weight:500;color:var(--mute);margin:18px 0 4px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
.row{{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding:10px 12px;margin:0 -12px;border-radius:8px;color:inherit;text-decoration:none;border-bottom:1px solid var(--line)}}
.row:hover{{background:var(--hover)}}
.row:hover .title{{color:var(--accent)}}
.title{{font-weight:450;overflow:hidden;text-overflow:ellipsis}}
.meta{{display:flex;gap:12px;flex-shrink:0;color:var(--mute);font-size:13px;font-variant-numeric:tabular-nums}}
.place{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}}
.empty{{color:var(--mute)}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.9em}}
@media (max-width:520px){{.row{{flex-direction:column;gap:2px}}}}
</style></head>
<body><main>
<header><h1>Artifacts</h1><span>{workspace} · {count}</span></header>
<input id="q" type="search" placeholder="Filter" autocomplete="off">
{content}
</main>
<script>
const q=document.getElementById('q');
q.addEventListener('input',()=>{{const v=q.value.trim().toLowerCase();
document.querySelectorAll('.row').forEach(r=>r.style.display=!v||r.dataset.s.includes(v)?'':'none');
document.querySelectorAll('section').forEach(s=>s.style.display=[...s.querySelectorAll('.row')].some(r=>r.style.display!=='none')?'':'none');}});
</script>
</body></html>
"""


def make_handler(workspace: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            rel = unquote(urlparse(self.path).path).lstrip("/")
            if rel in ("", "index.html"):
                return self._send(200, render_index(workspace).encode(), "text/html; charset=utf-8")
            path = is_servable(workspace, rel)
            if path is None:
                return self._send(404, b"Not found", "text/plain; charset=utf-8")
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if kind.startswith("text/"):
                kind += "; charset=utf-8"
            return self._send(200, path.read_bytes(), kind)

        def _send(self, status: int, body: bytes, kind: str):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 - quiet service, matches the base signature
            pass

    return Handler


def serve(workspace: Path, port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(workspace))


def main() -> None:
    workspace = Path(os.environ["THESYSTEM_WORKSPACE"]).expanduser()
    serve(workspace).serve_forever()


if __name__ == "__main__":
    main()
