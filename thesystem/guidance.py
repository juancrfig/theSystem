"""Role declaration validation and registered project role updates."""
from __future__ import annotations

import json
from pathlib import Path
import re

from thesystem.errors import CodedError
from thesystem.workspace import Workspace, WorkspaceError

ROLE_SECTIONS = ("rules", "skills", "tools", "utils", "clis", "mcp_servers")
ROLE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
GUIDANCE_PATH_SECTIONS = {"rules", "skills", "tools", "utils"}


class GuidanceError(CodedError):
    pass


def validate_role_document(document, source: Path | str = "role configuration") -> dict:
    if not isinstance(document, dict):
        raise GuidanceError("ROLE_CONFIG_INVALID", f"{source} must contain an object")
    validated = {}
    for role, spec in document.items():
        if not isinstance(role, str) or not role.strip() or not isinstance(spec, dict):
            raise GuidanceError("ROLE_CONFIG_INVALID", f"invalid role declaration in {source}: {role!r}")
        normalized = {}
        for section, entries in spec.items():
            if section not in ROLE_SECTIONS:
                raise GuidanceError("ROLE_CONFIG_INVALID", f"unknown role section {section!r} in {source}")
            if not isinstance(entries, list) or any(not isinstance(entry, str) or not entry.strip() for entry in entries):
                raise GuidanceError("ROLE_CONFIG_INVALID", f"role section {role}.{section} in {source} must be a list of non-empty strings")
            values = [entry.strip() for entry in entries]
            if section in GUIDANCE_PATH_SECTIONS:
                for value in values:
                    path = Path(value)
                    if path.is_absolute() or ".." in path.parts:
                        raise GuidanceError("ROLE_INVALID", f"{section} entries must be relative paths inside project guidance")
            normalized[section] = values
        validated[role] = normalized
    return validated


def read_role_file(path: Path) -> dict:
    if path.is_symlink():
        raise GuidanceError("ROLE_CONFIG_INVALID", f"roles file is not a regular file: {path}")
    if not path.exists():
        return {}
    if not path.is_file():
        raise GuidanceError("ROLE_CONFIG_INVALID", f"roles file is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GuidanceError("ROLE_CONFIG_UNSUPPORTED", f"existing roles.yaml is not JSON-compatible YAML; preserve it and edit it manually: {error}") from error
    return validate_role_document(payload, path)


def update_project_role(workspace: Workspace, project: str | Path, role: str, values: dict[str, list[str]]) -> dict:
    if not ROLE_NAME.fullmatch(role):
        raise GuidanceError("ROLE_INVALID", "role must use letters and numbers and start with a letter")
    selected = validate_role_document({role: values})[role]
    try:
        with workspace.locked_project(project) as registered:
            guidance = registered / "agents"
            if guidance.is_symlink() or not guidance.is_dir():
                raise GuidanceError("ROLE_CONFIG_INVALID", "project agents path is not a real directory")
            target = guidance / "roles.yaml"
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise GuidanceError("ROLE_CONFIG_INVALID", "project roles.yaml is not a regular file")
            document = read_role_file(target)
            document[role] = selected
            document = validate_role_document(document, target)
            worker_rules = set(document.get("worker", {}).get("rules", []))
            reviewer_rules = set(document.get("reviewer", {}).get("rules", []))
            if not worker_rules.issubset(reviewer_rules):
                raise GuidanceError("REVIEWER_RULES_MISSING", "reviewer roles must include every worker rule")
            Workspace.atomic_write(target, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    except WorkspaceError as error:
        raise GuidanceError(error.code, str(error)) from error
    return {"project": str(registered), "role": role, "role_config": str(target)}
