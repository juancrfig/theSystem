"""Roles: named selections of rules, skills and tools, declared globally or per project.

Global roles live in `<workspace>/agents/roles.yaml`, project roles in
`<project>/agents/roles.yaml`. A project role replaces a global role with the
same name. Paths inside a role are relative to the `agents/` folder that declares it.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from thesystem import frontmatter
from thesystem.errors import CodedError


@dataclass
class Context:
    """What one agent receives for one run. Copied into the run folder so evidence shows exactly what it had."""
    rules: list[Path] = field(default_factory=list)
    skills: list[Path] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    def add(self, other: "Context") -> None:
        for name in ("rules", "skills", "tools"):
            mine = getattr(self, name)
            mine.extend(item for item in getattr(other, name) if item not in mine)


def _declared(agents_dir: Path) -> dict:
    path = agents_dir / "roles.yaml"
    if not path.is_file():
        return {}
    data = frontmatter.parse(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CodedError("ROLES_INVALID", f"{path} must map role names to entries")
    return {name: (entry or {}, agents_dir) for name, entry in data.items()}


def resolve(workspace: Path, project: Path, names: list[str]) -> Context:
    available = {**_declared(workspace / "agents"), **_declared(project / "agents")}
    context = Context()
    for name in names:
        if name not in available:
            raise CodedError("ROLE_NOT_FOUND", f"role {name!r} is not declared in agents/roles.yaml")
        entry, agents_dir = available[name]
        if not isinstance(entry, dict):
            raise CodedError("ROLES_INVALID", f"role {name!r} must be a map of rules/skills/tools")
        part = Context(
            rules=[_existing(agents_dir, item, name) for item in entry.get("rules") or []],
            skills=[_existing(agents_dir, item, name) for item in entry.get("skills") or []],
            tools=[str(item) for item in entry.get("tools") or []],
        )
        context.add(part)
    return context


def _existing(agents_dir: Path, item, role: str) -> Path:
    path = agents_dir / str(item)
    if not path.exists():
        raise CodedError("ROLE_ENTRY_MISSING", f"role {role!r} references missing {path}")
    return path


def materialize(context: Context, destination: Path) -> str:
    """Copy the context into the run folder and return the prompt section that points the agent at it."""
    sections = []
    if context.rules:
        sections.append("# Rules you must follow\n")
        for rule in context.rules:
            target = destination / "rules" / rule.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(rule, target)
            sections.append(f"## {rule.name}\n\n{rule.read_text(encoding='utf-8').strip()}\n")
    if context.skills:
        sections.append("# Skills\n\nRead a skill's SKILL.md before doing work it covers:\n")
        for skill in context.skills:
            source = skill if skill.is_dir() else skill.parent
            target = destination / "skills" / source.name
            shutil.copytree(source, target, dirs_exist_ok=True)
            sections.append(f"- {source.name}: {target / 'SKILL.md'}")
        sections.append("")
    if context.tools:
        sections.append("# Tools available\n")
        sections.extend(f"- {tool}" for tool in context.tools)
        sections.append("")
    return "\n".join(sections)
