#!/usr/bin/env python3
"""Review Hermes pending memory and skill writes without creating another queue.

The script is deliberately an adapter around Hermes's native pending-write store.
It inventories approved profiles, asks TypeSafe Jev only about the literal
staged payload of the one request being shown, renders a single ASCII panel, and delegates a human
approve/reject decision back to Hermes's native applier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

PROFILES = ("default", "implementer", "reviewer")
SUBSYSTEMS = ("memory", "skills")


class ReviewError(RuntimeError):
    pass


class StaleRequestError(ReviewError):
    pass


@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    version: int
    question: str
    context: dict[str, Any]
    definition: dict[str, Any]
    exclusions: list[str]
    examples: list[str]


@dataclass(frozen=True)
class Catalog:
    catalog_version: int
    criteria: tuple[Criterion, ...]


@dataclass(frozen=True)
class PendingRequest:
    profile: str
    home: Path
    subsystem: str
    pending_id: str
    record: dict[str, Any]
    record_sha256: str
    payload_sha256: str

    @property
    def payload(self) -> dict[str, Any]:
        payload = self.record.get("payload")
        if not isinstance(payload, dict):
            raise ReviewError(f"Pending {self.profile}/{self.subsystem}/{self.pending_id} has no object payload.")
        return payload


@dataclass(frozen=True)
class Inventory:
    requests: tuple[PendingRequest, ...]
    counts: dict[str, int]
    unreadable: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    status: str
    model: str
    results: dict[str, float]
    error: str = ""
    retention_categories: tuple[str, ...] = ()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _profile_homes(root: Path) -> Iterable[tuple[str, Path]]:
    yield "default", root
    for profile in PROFILES[1:]:
        home = root / "profiles" / profile
        if home.exists():
            yield profile, home


def _parse_pending_file(path: Path, profile: str, subsystem: str, home: Path) -> PendingRequest:
    raw = path.read_text(encoding="utf-8")
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ReviewError("record is not an object")
    pending_id = path.stem
    if not isinstance(record.get("payload"), dict):
        raise ReviewError("record payload is not an object")
    return PendingRequest(
        profile=profile,
        home=home,
        subsystem=subsystem,
        pending_id=pending_id,
        record=record,
        record_sha256=sha256_text(raw),
        payload_sha256=sha256_text(canonical_json(record["payload"])),
    )


def inventory_pending(root: Path) -> Inventory:
    requests: list[PendingRequest] = []
    unreadable: list[str] = []
    counts = {"memory": 0, "skills": 0, "unreadable": 0}
    for profile, home in _profile_homes(root):
        for subsystem in SUBSYSTEMS:
            directory = home / "pending" / subsystem
            for path in sorted(directory.glob("*.json")) if directory.exists() else ():
                try:
                    request = _parse_pending_file(path, profile, subsystem, home)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ReviewError) as exc:
                    counts["unreadable"] += 1
                    unreadable.append(f"{profile}/{subsystem}/{path.name}: {exc}")
                    continue
                requests.append(request)
                counts[subsystem] += 1
    requests.sort(key=lambda item: (
        float(item.record.get("created_at", 0) or 0), item.profile, item.subsystem, item.pending_id))
    return Inventory(tuple(requests), counts, tuple(unreadable))


def load_catalog(catalog_path: Path) -> Catalog:
    try:
        document = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewError(f"Cannot read criteria catalog {catalog_path}: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("criteria", []), list):
        raise ReviewError("Catalog must be a JSON object with a criteria list.")
    criteria: list[Criterion] = []
    seen: set[str] = set()
    for row in document["criteria"]:
        if not isinstance(row, dict):
            raise ReviewError("Every catalog criterion must be an object.")
        ident, version, question = row.get("id"), row.get("version"), row.get("question")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ReviewError("Criterion ids must be unique, non-empty strings.")
        if not isinstance(version, int) or version < 1 or not isinstance(question, str) or not question:
            raise ReviewError(f"Criterion {ident!r} requires positive version and question.")
        context, definition = row.get("context"), row.get("definition")
        if not isinstance(context, dict):
            raise ReviewError(f"Criterion {ident!r} requires an object context.")
        if (not isinstance(definition, dict)
                or not isinstance(definition.get("yes"), str) or not definition["yes"].strip()
                or not isinstance(definition.get("no"), str) or not definition["no"].strip()):
            raise ReviewError(f"Criterion {ident!r} requires non-empty definition.yes and definition.no strings.")
        exclusions, examples = row.get("exclusions", []), row.get("examples", [])
        if not isinstance(exclusions, list) or not all(isinstance(item, str) for item in exclusions):
            raise ReviewError(f"Criterion {ident!r} exclusions must be a list of strings.")
        if not isinstance(examples, list) or not all(isinstance(item, str) for item in examples):
            raise ReviewError(f"Criterion {ident!r} examples must be a list of strings.")
        seen.add(ident)
        criteria.append(Criterion(ident, version, question, context, definition, exclusions, examples))
    catalog_version = document.get("catalog_version", 1)
    if not isinstance(catalog_version, int) or catalog_version < 1:
        raise ReviewError("catalog_version must be a positive integer.")
    return Catalog(catalog_version, tuple(criteria))


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("possible API key", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b")),
    ("secret assignment", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}")),
)


def detect_possible_secrets(payload: dict[str, Any]) -> tuple[str, ...]:
    text = canonical_json(payload)
    return tuple(label for label, pattern in _SECRET_PATTERNS if pattern.search(text))


def _criterion_instructions(criterion: Criterion) -> dict[str, Any]:
    return {
        "question": criterion.question,
        "context": criterion.context,
        "yes_definition": criterion.definition.get("yes", "Yes means the stated problem exists."),
        "no_definition": criterion.definition.get("no", "No means the stated problem does not exist."),
        "exclusions": criterion.exclusions,
        "examples": criterion.examples,
        "direction": "A higher probability means the stated problem is more likely.",
    }


def evaluate_with_jev(request: PendingRequest, criteria: tuple[Criterion, ...], model: str | None = None) -> Evaluation:
    try:
        from typesafe_sdk import Noul, TypeSafeClient
    except ImportError as exc:
        return Evaluation("ERROR DE EVALUACION", "", {}, f"TypeSafe SDK unavailable: {exc}")
    questions = {criterion.criterion_id: Noul(instructions=_criterion_instructions(criterion)) for criterion in criteria}
    try:
        with TypeSafeClient(model=model) as client:
            response = client.system_one(state={"proposal": request.payload}, questions=questions, model=model)
        results = {criterion.criterion_id: float(response.nouls[criterion.criterion_id].noul) for criterion in criteria}
        effective_model = str(getattr(response, "model", None) or model or "jev")
        return Evaluation("EVALUADA", effective_model, results)
    except Exception as exc:  # provider failure must remain visible and non-authorizing
        return Evaluation("ERROR DE EVALUACION", model or "", {}, f"{type(exc).__name__}: {exc}")


def evaluate_request(
    request: PendingRequest,
    catalog: Catalog,
    evaluator: Callable[[PendingRequest, tuple[Criterion, ...]], Evaluation] | None = None,
    model: str | None = None,
) -> Evaluation:
    retained = detect_possible_secrets(request.payload)
    if retained:
        return Evaluation("RETENIDA LOCALMENTE", "", {}, retention_categories=retained)
    if not catalog.criteria:
        return Evaluation("SIN CRITERIOS", "", {})
    if evaluator is not None:
        return evaluator(request, catalog.criteria)
    return evaluate_with_jev(request, catalog.criteria, model)


def _review_state_path(root: Path) -> Path:
    return root / "memory-request-review" / "state.json"


def load_review_state(root: Path) -> dict[str, Any]:
    path = _review_state_path(root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"results": {}, "decisions": []}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"results": {}, "decisions": []}
    if not isinstance(state, dict):
        return {"results": {}, "decisions": []}
    results = state.get("results") if isinstance(state.get("results"), dict) else {}
    decisions = state.get("decisions") if isinstance(state.get("decisions"), list) else []
    return {"results": results, "decisions": decisions}


def save_review_state(root: Path, state: dict[str, Any]) -> None:
    path = _review_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _store_evaluation(state: dict[str, Any], request: PendingRequest, catalog: Catalog, evaluation: Evaluation) -> None:
    if evaluation.status != "EVALUADA" or not evaluation.model:
        return
    results = state.setdefault("results", {})
    for criterion in catalog.criteria:
        probability = evaluation.results.get(criterion.criterion_id)
        if probability is not None:
            results[cache_key(request, criterion, evaluation.model)] = {"probability": probability}


def evaluate_one(
    request: PendingRequest, catalog: Catalog, model: str | None = None, state: dict[str, Any] | None = None,
) -> Evaluation:
    """Evaluate only the request about to be shown; later pendings wait their turn.

    A result is reusable only when the caller supplies the same effective model
    identity and its payload/criterion-version cache key matches exactly.
    """
    state = state if state is not None else {"results": {}}
    retained = detect_possible_secrets(request.payload)
    if retained:
        return Evaluation("RETENIDA LOCALMENTE", "", {}, retention_categories=retained)
    if not catalog.criteria:
        return Evaluation("SIN CRITERIOS", "", {})
    cached = reusable_results(request, catalog, model, state.get("results", {})) if model else {}
    if len(cached) == len(catalog.criteria):
        return Evaluation("EVALUADA", model, cached)
    evaluation = evaluate_with_jev(request, catalog.criteria, model)
    _store_evaluation(state, request, catalog, evaluation)
    return evaluation


def cache_key(request: PendingRequest, criterion: Criterion, model: str) -> str:
    return ":".join((request.profile, request.subsystem, request.pending_id, request.payload_sha256,
                     criterion.criterion_id, str(criterion.version), model))


def reusable_results(request: PendingRequest, catalog: Catalog, model: str, cache: dict[str, Any]) -> dict[str, float]:
    reusable: dict[str, float] = {}
    for criterion in catalog.criteria:
        row = cache.get(cache_key(request, criterion, model))
        if isinstance(row, dict) and isinstance(row.get("probability"), (float, int)):
            reusable[criterion.criterion_id] = float(row["probability"])
    return reusable


_WIDTH = 72
_DECISIONS = "approve · reject · pending · discuss"
# Location fields (skill file paths) are deliberately not rendered: the reviewer
# judges what is added, deleted, or replaced, not where it lands in the file.
_KNOWN_OPERATION_KEYS = {
    "action", "name", "target", "file_path", "old_text", "old_string", "content", "new_string", "file_content",
}
_VERBS = {
    "add": "ADD", "create": "ADD", "write_file": "ADD",
    "remove": "DELETE", "delete": "DELETE", "remove_file": "DELETE",
    "replace": "REPLACE", "patch": "REPLACE", "edit": "REPLACE",
}


@dataclass(frozen=True)
class Operation:
    verb: str
    old: str = ""
    new: str = ""


def _payload_operations(payload: dict[str, Any]) -> list[Any]:
    operations = payload.get("operations")
    return list(operations) if isinstance(operations, list) else [payload]


def describe_operations(request: PendingRequest) -> list[Operation]:
    """Reduce a native payload to ADD/DELETE/REPLACE rows without hiding any content."""
    described: list[Operation] = []
    for raw in _payload_operations(request.payload):
        if not isinstance(raw, dict):
            described.append(Operation("UNKNOWN", new=canonical_json(raw)))
            continue
        action = str(raw.get("action", "unknown"))
        old = str(raw.get("old_text", raw.get("old_string", "")) or "")
        new = str(raw.get("content", raw.get("new_string", raw.get("file_content", ""))) or "")
        extra = {key: value for key, value in raw.items() if key not in _KNOWN_OPERATION_KEYS}
        if extra:
            new = (new + "\n" if new else "") + canonical_json(extra)
        # A replace that keeps its old text intact only adds text next to it.
        if old and new != old and new.endswith(old):
            described.append(Operation("ADD", new=new[:-len(old)].rstrip()))
        elif old and new != old and new.startswith(old):
            described.append(Operation("ADD", new=new[len(old):].lstrip()))
        else:
            described.append(Operation(_VERBS.get(action, action.upper()), old, new))
    return described


def target_label(request: PendingRequest) -> str:
    payload = request.payload
    if request.subsystem == "memory":
        return str(payload.get("target", "memory"))
    names: list[str] = []
    for raw in _payload_operations(payload):
        name = (raw.get("name") if isinstance(raw, dict) else None) or payload.get("name")
        if name and str(name) not in names:
            names.append(str(name))
    return ", ".join(f"skill:{name}" for name in names) or "skill:<unknown>"


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, width, break_on_hyphens=False, replace_whitespace=False) or [""])
    return lines


def _hang(prefix: str, text: str, width: int) -> list[str]:
    """Wrap text under a prefix; continuation lines align after the prefix."""
    body = _wrap(text, width - len(prefix))
    return [prefix + body[0]] + [" " * len(prefix) + line for line in body[1:]]


def _band(probability: float) -> str:
    return "likely" if probability >= 0.7 else "unlikely" if probability <= 0.3 else "uncertain"


def _bar(probability: float, cells: int = 10) -> str:
    filled = max(0, min(cells, round(probability * cells)))
    return "█" * filled + "░" * (cells - filled)


def _verdict_note(evaluation: Evaluation) -> str:
    if evaluation.status == "RETENIDA LOCALMENTE":
        return "possible secret (" + ", ".join(evaluation.retention_categories) + "): kept local, Jev not called"
    if evaluation.status == "SIN CRITERIOS":
        return "no criteria in the catalog: Jev not called"
    if evaluation.error:
        return "Jev failed: " + evaluation.error
    return ""


def _questions(evaluation: Evaluation, catalog: Catalog) -> list[tuple[str, float | None]]:
    """Every catalog question, scored or not, so the reviewer always sees what Jev was asked."""
    return [(criterion.question, evaluation.results.get(criterion.criterion_id)) for criterion in catalog.criteria]


def render_panel(
    request: PendingRequest, evaluation: Evaluation, position: int, total: int, catalog: Catalog | None = None,
) -> str:
    catalog = catalog or Catalog(1, ())
    inner = _WIDTH - 4
    rule = lambda left, right: left + "─" * (_WIDTH - 2) + right  # noqa: E731

    def rule_with_junction(left: str, right: str, content_col: int, junction: str) -> str:
        """Draw a horizontal border with one vertical junction aligned to content column."""
        span = ["─"] * (_WIDTH - 2)
        index = content_col + 1  # content starts after leading "│ " in boxed rows
        if 0 <= index < len(span):
            span[index] = junction
        return left + "".join(span) + right
    def _fit(text: str) -> str:
        if len(text) <= inner:
            return text
        if inner <= 1:
            return text[:inner]
        return text[:inner - 1] + "…"

    box = lambda text: f"│ {_fit(text):<{inner}} │"  # noqa: E731

    def _compose_with_right(left: str, right: str, width: int) -> str:
        """Keep right-aligned metadata visible; shrink the left side first."""
        if len(left) + 1 + len(right) <= width:
            return left + " " * (width - len(left) - len(right)) + right
        if width <= len(right):
            return right[:width]
        room_for_left = width - len(right) - 1
        if room_for_left <= 0:
            return right[:width]
        if len(left) > room_for_left:
            left = left[:max(1, room_for_left - 1)] + ("…" if room_for_left > 1 else "")
        return left + " " * (width - len(left) - len(right)) + right

    head = f"REQUEST {position}/{total}"
    ident = request.profile
    left = f"{head} │   Target: {target_label(request)}"
    header = _compose_with_right(left, ident, inner)
    divider_col = header.find("│")
    if divider_col >= 0:
        rows = [rule_with_junction("╭", "╮", divider_col, "┬"), box(header)]
    else:
        rows = [rule("╭", "╮"), box(header)]
    # Jev comes first: long operations must never push the verdict out of a collapsed view.
    if divider_col >= 0:
        rows.append(rule_with_junction("├", "┤", divider_col, "┴"))
    else:
        rows.append(rule("├", "┤"))
    note = _verdict_note(evaluation)
    question_blocks: list[str] = []
    questions = _questions(evaluation, catalog)
    for index, (question, probability) in enumerate(questions):
        if index > 0:
            question_blocks.append("")
        question_blocks.extend(_wrap(question, inner))
        question_blocks.append("·  no score" if probability is None
                               else f"{_bar(probability)}  {probability:.2f}")
    if note and evaluation.status != "RETENIDA LOCALMENTE":
        if question_blocks:
            question_blocks.append("")
        question_blocks.extend(_wrap(note, inner))
    if question_blocks:
        rows.append(box(""))
        rows += [box(line) for line in question_blocks]
        rows.append(box(""))
    rows.append(rule("├", "┤"))
    if evaluation.status == "RETENIDA LOCALMENTE":
        rows += [box(line) for line in _wrap("Content withheld: " + note, inner)]
    else:
        def _verb_badge(verb: str) -> list[str]:
            label = f" {verb} "
            top = "╭" + "─" * len(label) + "╮"
            mid = "│" + label + "│"
            bot = "╰" + "─" * len(label) + "╯"
            return [top.center(inner), mid.center(inner), bot.center(inner)]

        operations = describe_operations(request)
        if operations:
            rows.append(box(""))
        for index, op in enumerate(operations, 1):
            if index > 1:
                rows.append(box(""))
            rows += [box(line) for line in _verb_badge(op.verb)]
            if op.old:
                rows += [box(line) for line in _hang("   − ", op.old, inner)]
            if op.new:
                rows += [box(line) for line in _hang("   + ", op.new, inner)]
        if operations:
            rows.append(box(""))
    rows += [rule("╰", "╯")]
    return "\n".join(rows)


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        digest.update(b"missing")
        return digest.hexdigest()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(str(child.relative_to(path)).encode("utf-8"))
        digest.update(child.read_bytes())
    return digest.hexdigest()


def _destination_digest(request: PendingRequest) -> str:
    if request.subsystem == "memory":
        filename = "USER.md" if request.payload.get("target") == "user" else "MEMORY.md"
        return _tree_digest(request.home / "memories" / filename)
    return _tree_digest(request.home / "skills")


def _apply_native_decision_at_home(
    home: Path, subsystem: str, pending_id: str, decision: str, expected_record_sha256: str,
) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise ReviewError("Only approve or reject can invoke Hermes's native flow.")
    path = home / "pending" / subsystem / f"{pending_id}.json"
    try:
        current_raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise StaleRequestError("The pending request was already resolved.") from exc
    if sha256_text(current_raw) != expected_record_sha256:
        raise StaleRequestError("The pending request changed after review; inspect it again before acting.")
    request = _parse_pending_file(path, "native", subsystem, home)
    destination_before = _destination_digest(request)
    from tools import write_approval as wa
    if decision == "reject":
        removed = wa.discard_pending(request.subsystem, request.pending_id)
        destination_unchanged = destination_before == _destination_digest(request)
        return {"success": bool(removed and not path.exists() and destination_unchanged), "decision": decision,
                "pending_removed": not path.exists(), "destination": target_label(request),
                "destination_unchanged": destination_unchanged}
    from hermes_cli.write_approval_commands import _apply_one
    if request.subsystem == wa.MEMORY:
        from tools.memory_tool import load_on_disk_store
        store = load_on_disk_store()
    else:
        store = None
    ok, error, result = _apply_one(request.subsystem, request.record, store)
    if not ok:
        return {"success": False, "decision": decision, "error": error, "native_result": result,
                "pending_removed": False}
    discarded = wa.discard_pending(request.subsystem, request.pending_id)
    return {"success": bool(discarded and not path.exists()), "decision": decision, "native_result": result,
            "destination": target_label(request), "destination_changed": destination_before != _destination_digest(request),
            "pending_removed": not path.exists()}


def apply_native_decision(request: PendingRequest, decision: str, expected_record_sha256: str) -> dict[str, Any]:
    path = request.home / "pending" / request.subsystem / f"{request.pending_id}.json"
    try:
        current_raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise StaleRequestError("The pending request was already resolved.") from exc
    if sha256_text(current_raw) != expected_record_sha256:
        raise StaleRequestError("The pending request changed after review; inspect it again before acting.")
    command = [
        sys.executable, str(Path(__file__).resolve()), "native-apply", "--subsystem", request.subsystem,
        "--pending-id", request.pending_id, "--decision", decision,
        "--expected-record-sha256", expected_record_sha256,
    ]
    runtime_path = os.pathsep.join(path for path in sys.path if path)
    process = subprocess.run(
        command,
        env={"HERMES_HOME": str(request.home), "PYTHONPATH": runtime_path},
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip() or "native Hermes decision failed"
        raise ReviewError(detail)
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ReviewError("Native Hermes decision returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise ReviewError("Native Hermes decision returned a non-object result.")
    return result


def load_checkout_env() -> None:
    """Read KEY=VALUE lines from the checkout's gitignored .env; real env vars win."""
    path = Path(__file__).resolve().parents[4] / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def ensure_review_runtime() -> None:
    # Resolve the checkout, not the caller's cwd or a project-skill symlink.
    default = Path(__file__).resolve().parents[4] / ".agents" / "memory-review" / "bin" / "python"
    selected = os.environ.get("HERMES_MEMORY_REVIEW_PYTHON") or str(default)
    interpreter = os.path.abspath(os.path.expanduser(selected))
    if not Path(interpreter).is_file() or not os.access(interpreter, os.X_OK):
        raise ReviewError(
            f"Review interpreter is unavailable: {interpreter}. "
            "Run ./bootstrap from the checkout, or set HERMES_MEMORY_REVIEW_PYTHON "
            "to a prepared interpreter. Review never installs dependencies."
        )
    # Do not resolve the executable symlink: virtualenvs share a base Python.
    if os.path.abspath(sys.executable) != interpreter:
        os.execv(interpreter, [interpreter, str(Path(__file__).resolve()), *sys.argv[1:]])


def _default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "criteria.json"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "show", "decide", "native-apply"))
    parser.add_argument("--home-root", type=Path, default=Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")))
    parser.add_argument("--catalog", type=Path, default=_default_catalog_path())
    parser.add_argument("--position", type=int, default=1)
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--subsystem", choices=SUBSYSTEMS)
    parser.add_argument("--pending-id")
    parser.add_argument("--model", default=None)
    parser.add_argument("--decision", choices=("approve", "reject", "pending"))
    parser.add_argument("--expected-record-sha256")
    parser.add_argument("--human-decision", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.command == "native-apply":
        if not args.subsystem or not args.pending_id or not args.expected_record_sha256 or args.decision not in {"approve", "reject"}:
            raise ReviewError("Native Hermes decision requires subsystem, pending id, decision, and reviewed record hash.")
        print(json.dumps(
            _apply_native_decision_at_home(
                args.home_root, args.subsystem, args.pending_id, args.decision, args.expected_record_sha256,
            ),
            ensure_ascii=False,
        ))
        return 0
    inventory = inventory_pending(args.home_root)
    if args.command == "inventory":
        output = {
            "counts": inventory.counts,
            "requests": [{"profile": item.profile, "subsystem": item.subsystem, "id": item.pending_id,
                          "record_sha256": item.record_sha256, "payload_sha256": item.payload_sha256}
                         for item in inventory.requests],
            "unreadable": list(inventory.unreadable),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if not inventory.requests:
        print("No hay solicitudes pendientes en los perfiles autorizados.")
        return 0
    if args.command == "show":
        if args.position < 1 or args.position > len(inventory.requests):
            raise ReviewError(f"position must be 1..{len(inventory.requests)}")
        request = inventory.requests[args.position - 1]
        catalog = load_catalog(args.catalog)
        state = load_review_state(args.home_root)
        evaluation = evaluate_one(request, catalog, args.model, state)
        save_review_state(args.home_root, state)
        print(render_panel(request, evaluation, args.position, len(inventory.requests), catalog))
        print(f"\nrecord_sha256: {request.record_sha256}")
        return 0
    if not args.human_decision or args.decision not in {"approve", "reject"}:
        raise ReviewError("A native decision requires --human-decision and --decision approve|reject.")
    if not args.expected_record_sha256:
        raise ReviewError("A native decision requires --expected-record-sha256 from the reviewed inventory.")
    if not args.profile or not args.subsystem or not args.pending_id:
        raise ReviewError("A native decision requires the reviewed profile, subsystem, and pending id.")
    request = next(
        (
            item for item in inventory.requests
            if (item.profile, item.subsystem, item.pending_id) == (args.profile, args.subsystem, args.pending_id)
        ),
        None,
    )
    if request is None:
        raise StaleRequestError("The reviewed pending request is no longer available; inspect the inventory again.")
    result = apply_native_decision(request, args.decision, args.expected_record_sha256)
    state = load_review_state(args.home_root)
    state.setdefault("decisions", []).append({
        "at": time.time(), "profile": request.profile, "subsystem": request.subsystem,
        "pending_id": request.pending_id, "record_sha256": request.record_sha256,
        "payload_sha256": request.payload_sha256, "decision": args.decision,
        "success": bool(result.get("success")),
    })
    save_review_state(args.home_root, state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    try:
        ensure_review_runtime()
        load_checkout_env()
        raise SystemExit(main())
    except ReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
