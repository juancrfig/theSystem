#!/usr/bin/env python3
"""Review Hermes pending memory and skill writes without creating another queue.

The script is deliberately an adapter around Hermes's native pending-write store.
It inventories approved profiles, optionally asks TypeSafe Jev only about the
literal staged payload, renders a single ASCII panel, and delegates a human
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
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

PROFILES = ("default", "implementer", "reviewer")
SUBSYSTEMS = ("memory", "skills")
CATALOG_OPEN = "<!-- MEMORY-REQUEST-REVIEW-CATALOG"
CATALOG_CLOSE = "MEMORY-REQUEST-REVIEW-CATALOG -->"


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


def load_catalog(rule_path: Path) -> Catalog:
    text = rule_path.read_text(encoding="utf-8")
    start, end = text.find(CATALOG_OPEN), text.find(CATALOG_CLOSE)
    if start < 0 or end < 0 or end <= start:
        raise ReviewError(f"Catalog markers are missing in {rule_path}.")
    raw = text[start + len(CATALOG_OPEN):end].strip()
    document = json.loads(raw)
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


def evaluate_inventory(
    inventory: Inventory, catalog: Catalog, model: str | None = None, state: dict[str, Any] | None = None,
) -> dict[tuple[str, str, str], Evaluation]:
    """Evaluate every eligible request before any individual panel is rendered.

    A result is reusable only when the caller supplies the same effective model
    identity and its payload/criterion-version cache key matches exactly.
    """
    state = state if state is not None else {"results": {}}
    evaluations: dict[tuple[str, str, str], Evaluation] = {}
    for request in inventory.requests:
        retained = detect_possible_secrets(request.payload)
        identity = (request.profile, request.subsystem, request.pending_id)
        if retained:
            evaluations[identity] = Evaluation("RETENIDA LOCALMENTE", "", {}, retention_categories=retained)
            continue
        if not catalog.criteria:
            evaluations[identity] = Evaluation("SIN CRITERIOS", "", {})
            continue
        cached = reusable_results(request, catalog, model, state.get("results", {})) if model else {}
        if len(cached) == len(catalog.criteria):
            evaluations[identity] = Evaluation("EVALUADA", model, cached)
            continue
        evaluation = evaluate_with_jev(request, catalog.criteria, model)
        _store_evaluation(state, request, catalog, evaluation)
        evaluations[identity] = evaluation
    return evaluations


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


def _wrap(value: str, width: int = 76) -> list[str]:
    if not value:
        return [""]
    lines: list[str] = []
    for paragraph in value.splitlines() or [""]:
        while len(paragraph) > width:
            lines.append(paragraph[:width])
            paragraph = paragraph[width:]
        lines.append(paragraph)
    return lines


def _panel_line(value: str) -> str:
    if len(value) > 78:
        raise ReviewError("Panel value must be wrapped before rendering.")
    return f"| {value:<78} |"


def _panel_lines(value: str) -> list[str]:
    return [_panel_line(line) for line in _wrap(value)]


def render_panel(request: PendingRequest, evaluation: Evaluation, position: int, total: int, catalog_version: int = 1) -> str:
    lines = ["+" + "-" * 80 + "+"]
    for value in (
        f"SOLICITUD {position}/{total}",
        f"PERFIL: {request.profile}   SUBSISTEMA: {request.subsystem}   DESTINO: {_destination_label(request)}",
        f"ID: {request.pending_id}",
        f"ESTADO: {evaluation.status}",
        f"MODELO: {evaluation.model or 'N/A'}   CATALOGO: v{catalog_version}",
    ):
        lines.extend(_panel_lines(value))
    lines.extend(_panel_lines("OPERACIONES PROPUESTAS:"))
    if evaluation.status == "RETENIDA LOCALMENTE":
        lines.extend(_panel_lines("CONTENIDO NO MOSTRADO: " + ", ".join(evaluation.retention_categories)))
    else:
        literal_lines = _wrap(json.dumps(request.payload, ensure_ascii=False, indent=2))
        block_size = 18
        block_count = max(1, (len(literal_lines) + block_size - 1) // block_size)
        for block_index in range(block_count):
            lines.extend(_panel_lines(f"OPERACIONES PROPUESTAS (BLOQUE {block_index + 1}/{block_count}):"))
            start = block_index * block_size
            for line in literal_lines[start:start + block_size]:
                lines.append(_panel_line(line))
    if evaluation.results:
        lines.extend(_panel_lines("RESULTADOS JEV (probabilidad de que exista el problema):"))
        for ident, probability in evaluation.results.items():
            lines.extend(_panel_lines(f"- {ident}: {probability:.6f}"))
    if evaluation.error:
        lines.extend(_panel_lines("ERROR: " + evaluation.error))
    lines.extend(_panel_lines("DECISION HUMANA: aprobar | rechazar | pendiente | discutir criterio"))
    lines.append("+" + "-" * 80 + "+")
    return "\n".join(lines)


def _destination_label(request: PendingRequest) -> str:
    payload = request.payload
    if request.subsystem == "memory":
        return str(payload.get("target", "memory"))
    return f"skill:{payload.get('name', '<unknown>')}"


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
                "pending_removed": not path.exists(), "destination": _destination_label(request),
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
            "destination": _destination_label(request), "destination_changed": destination_before != _destination_digest(request),
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


def _default_rule_path() -> Path:
    return Path(__file__).resolve().parents[3] / "rules" / "memory-request-review-catalog.md"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "show", "decide", "native-apply"))
    parser.add_argument("--home-root", type=Path, default=Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")))
    parser.add_argument("--rule", type=Path, default=_default_rule_path())
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
        catalog = load_catalog(args.rule)
        state = load_review_state(args.home_root)
        evaluations = evaluate_inventory(inventory, catalog, args.model, state)
        save_review_state(args.home_root, state)
        evaluation = evaluations[(request.profile, request.subsystem, request.pending_id)]
        print(render_panel(request, evaluation, args.position, len(inventory.requests), catalog.catalog_version))
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
        raise SystemExit(main())
    except ReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
