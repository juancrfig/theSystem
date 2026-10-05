"""The YAML subset used by task front matter and roles files.

The standard library has no YAML parser, and a fresh Ubuntu server cannot be
assumed to have PyYAML. Supported: block maps, block lists, list items that
are maps, quoted or plain scalars, `true`/`false`, and inline `[a, b]`, `[]`, `{}`.
"""
from __future__ import annotations

import re
from pathlib import Path


class FormatError(ValueError):
    pass


def parse(text: str):
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise FormatError(f"tabs are not allowed for indentation: {raw!r}")
        lines.append([len(raw) - len(raw.lstrip(" ")), re.sub(r"""\s+#[^"']*$""", "", raw.strip())])
    if not lines:
        return {}
    value, end = _block(lines, 0, lines[0][0])
    if end != len(lines):
        raise FormatError(f"unexpected indentation at: {lines[end][1]!r}")
    return value


def _block(lines, i, indent):
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        return _list(lines, i, indent)
    return _map(lines, i, indent)


def _list(lines, i, indent):
    items = []
    while i < len(lines) and lines[i][0] == indent and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
        content = lines[i][1][1:].strip()
        if _is_key(content):
            lines[i] = [indent + 2, content]
            value, i = _map(lines, i, indent + 2)
        elif content:
            value, i = _scalar(content), i + 1
        else:
            value, i = _child(lines, i + 1, indent)
        items.append(value)
    return items, i


def _map(lines, i, indent):
    result = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        key, sep, rest = lines[i][1].partition(":")
        if not sep:
            raise FormatError(f"expected 'key: value', got {lines[i][1]!r}")
        key, rest = _scalar(key.strip()), rest.strip()
        if rest:
            result[key], i = _scalar(rest), i + 1
        else:
            result[key], i = _child(lines, i + 1, indent)
    return result, i


def _child(lines, i, parent_indent):
    if i < len(lines) and (lines[i][0] > parent_indent or
                           (lines[i][0] == parent_indent and lines[i][1].startswith("- "))):
        return _block(lines, i, lines[i][0])
    return None, i


def _is_key(content: str) -> bool:
    return bool(re.match(r"""^(?:"[^"]*"|'[^']*'|[^"'\[{][^:]*):(?:\s|$)""", content))


def _scalar(text: str):
    if text in ("[]", "{}"):
        return [] if text == "[]" else {}
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(part.strip()) for part in text[1:-1].split(",") if part.strip()]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    return text


FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def read_front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if not match:
        raise FormatError(f"{path}: missing '---' front matter")
    data = parse(match.group(1))
    if not isinstance(data, dict):
        raise FormatError(f"{path}: front matter must be a map")
    return data, text[match.end():]


def write_field(path: Path, key: str, value: str) -> None:
    """Rewrite one top-level scalar field in place, keeping the rest of the file as written."""
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if not match:
        raise FormatError(f"{path}: missing '---' front matter")
    body = match.group(1)
    line = f"{key}: {value}"
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    body = pattern.sub(line, body, count=1) if pattern.search(body) else f"{line}\n{body}"
    path.write_text(f"---\n{body}\n---\n{text[match.end():]}", encoding="utf-8")
