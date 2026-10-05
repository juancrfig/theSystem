"""Installer helpers for the Hermes harness (F1). Standard library only: the installer can't rely on PyYAML.

  python3 -m thesystem.harness apply <canonical_config.yaml> [<hermes_root>]
      Applies canonical config directly to <hermes_root>/config.yaml (default $HERMES_HOME or ~/.hermes).
  python3 -m thesystem.harness settings <canonical_config.yaml>
      Prints one `<dot.key>\t<value>` line per setting, ready for `hermes config set`.
  python3 -m thesystem.harness keys <main .env> <profile .env>
      Writes the main agent's keys to a profile, without messaging-channel credentials.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Messaging channels own these env prefixes. Two profiles holding one bot token make the gateways fight over it.
CHANNEL_PREFIXES = (
    "TELEGRAM_", "DISCORD_", "SLACK_", "WHATSAPP_", "SIGNAL_", "MATRIX_", "MATTERMOST_", "EMAIL_", "SMS_",
    "TWILIO_", "GATEWAY_", "BLUEBUBBLES_", "IMESSAGE_", "WEIXIN_", "WECHAT_", "WECOM_", "QQ_", "QQBOT_",
    "DINGTALK_", "FEISHU_", "LARK_", "YUANBAO_", "HOMEASSISTANT_", "MSGRAPH_", "TEAMS_", "LINE_", "WEBHOOK_",
)
KEY = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _strip_comment(text: str) -> str:
    quote = None
    for i, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def _scalar(text: str):
    if text.startswith(('[', '{', '"')):
        try:
            return json.loads(text)
        except Exception:
            pass
    if text.startswith("'"):
        return text[1:-1].replace("''", "'")
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text


def load(text: str) -> dict:
    """Parse the plain YAML subset the harness uses: nested mappings, scalars and lists of scalars."""
    root: dict = {}
    stack = [(-1, root)]  # (indent, container)
    pending = None  # (indent, parent dict, key) for a key whose value is a nested block
    for number, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if pending:
            p_indent, parent, key = pending
            pending = None
            if indent > p_indent:
                parent[key] = [] if body.startswith("- ") or body == "-" else {}
                stack.append((p_indent, parent[key]))
        while stack[-1][0] >= indent and len(stack) > 1:
            stack.pop()
        container = stack[-1][1]
        if body.startswith("- "):
            if not isinstance(container, list):
                raise ValueError(f"line {number}: list item outside a list")
            container.append(_scalar(body[2:].strip()))
            continue
        if ":" not in body or not isinstance(container, dict):
            raise ValueError(f"line {number}: expected 'key: value'")
        key, _, value = body.partition(":")
        key, value = key.strip(), value.strip()
        if value:
            container[key] = _scalar(value)
        else:
            container[key] = {}
            pending = (indent, container, key)
    return root


def settings(config: dict, prefix: str = ""):
    """(dot.key, value text for `hermes config set`) for every leaf setting."""
    for key, value in config.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            yield from settings(value, path + ".")
        elif isinstance(value, str):
            yield path, value
        else:
            yield path, json.dumps(value)


def _format_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        if v.lower() in ("yes", "no", "on", "off", "true", "false", "null", "~"):
            return json.dumps(v)
        if "\n" in v:
            return "|\n" + "\n".join("  " + l for l in v.splitlines())
        if any(c in v for c in ":{}[]#&*!|>'\"%@`"):
            return json.dumps(v)
        return v
    return json.dumps(v)


def dump_yaml(data: dict, indent: int = 0) -> str:
    lines = []
    prefix = " " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{prefix}{k}: {{}}")
                else:
                    lines.append(f"{prefix}{k}:")
                    lines.append(dump_yaml(v, indent + 2))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{prefix}{k}: []")
                else:
                    lines.append(f"{prefix}{k}:")
                    for item in v:
                        if isinstance(item, (dict, list)):
                            item_lines = dump_yaml(item, indent + 4).splitlines()
                            lines.append(f"{prefix}  - " + item_lines[0].lstrip())
                            lines.extend(item_lines[1:])
                        else:
                            lines.append(f"{prefix}  - {_format_scalar(item)}")
            else:
                lines.append(f"{prefix}{k}: {_format_scalar(v)}")
    return "\n".join(lines)


def set_nested(cfg: dict, path: str, value) -> None:
    parts = path.split(".")
    curr = cfg
    for part in parts[:-1]:
        if part not in curr or not isinstance(curr[part], dict):
            curr[part] = {}
        curr = curr[part]
    curr[parts[-1]] = value


def apply(canonical_path: Path, hermes_root: Path) -> None:
    config_path = hermes_root / "config.yaml"
    cfg = load(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
    canonical = load(canonical_path.read_text(encoding="utf-8"))
    for key, value in settings(canonical):
        val = _scalar(value)
        set_nested(cfg, key, val)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(dump_yaml(cfg) + "\n", encoding="utf-8")


def provider_keys(env_text: str) -> str:
    """The main agent's .env without messaging-channel credentials or settings."""
    kept = []
    for line in env_text.splitlines():
        match = KEY.match(line.strip())
        if match and match.group(1).upper().startswith(CHANNEL_PREFIXES):
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def main(argv: list[str]) -> int:
    if argv[:1] == ["apply"] and len(argv) in (2, 3):
        canonical_path = Path(argv[1])
        hermes_root = Path(argv[2]) if len(argv) == 3 else Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        apply(canonical_path, hermes_root)
        return 0
    if argv[:1] == ["settings"] and len(argv) == 2:
        for key, value in settings(load(Path(argv[1]).read_text(encoding="utf-8"))):
            if "\t" in value or "\n" in value:
                raise SystemExit(f"{key}: tabs and newlines are not supported")
            print(f"{key}\t{value}")
        return 0
    if argv[:1] == ["keys"] and len(argv) == 3:
        source, target = Path(argv[1]), Path(argv[2])
        text = source.read_text(encoding="utf-8") if source.is_file() else ""
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.write_text("# Copied from the main agent by theSystem's installer; messaging channels left out.\n"
                          + provider_keys(text), encoding="utf-8")
        os.chmod(target, 0o600)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
