"""Installer helpers for the Hermes harness (F1). Standard library only: PyYAML edits Hermes' config when present
(Ubuntu ships it), and `hermes config set` does it otherwise.

  python3 -m thesystem.harness apply <hermes_root> [--canonical <canonical_config.yaml>] [--set KEY VALUE]...
                                   [--default KEY VALUE]... [--trust FOLDER]...
      Writes the canonical config and every --set to <hermes_root>/config.yaml in one pass, each --default only
      where that key is unset or empty, and trusts each --trust folder's skills.
  python3 -m thesystem.harness settings <canonical_config.yaml>
      Prints one `<dot.key>\t<value>` line per setting, ready for `hermes config set`.
  python3 -m thesystem.harness keys <main .env> <profile .env>
      Writes the main agent's keys to a profile, without messaging-channel credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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


def leaves(config: dict, prefix: str = ""):
    """(dot.key, value) for every leaf setting; lists are one setting."""
    for key, value in config.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            yield from leaves(value, path + ".")
        else:
            yield path, value


def settings(config: dict, prefix: str = ""):
    """(dot.key, value text for `hermes config set`) for every leaf setting."""
    for path, value in leaves(config, prefix):
        yield path, value if isinstance(value, str) else json.dumps(value)


class ApplyError(Exception):
    pass


def _yaml():
    try:
        import yaml
    except ImportError:
        return None
    return yaml


def _set_nested(cfg: dict, path: str, value) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(cfg.get(part), dict):
            cfg[part] = {}
        cfg = cfg[part]
    cfg[parts[-1]] = value


def _get_nested(cfg: dict, path: str):
    value: object = cfg
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def apply(hermes_root: Path, changes, defaults=(), trust=(), yaml_module=None) -> None:
    """Writes *changes* ((dot.key, value) pairs) to the main agent's config, each of *defaults* only when that key is
    unset or empty, and adds each *trust* folder to skills.trusted_project_dirs (as `hermes skills trust` does).
    Hermes' config is full YAML, so it is edited with PyYAML in one pass (Ubuntu ships it). Without PyYAML, each
    setting goes through the Hermes command: same result, one Hermes start per setting."""
    yaml = yaml_module or _yaml()
    if yaml is None:
        _apply_with_cli(changes, defaults, trust)
        return
    config_path = (hermes_root / "config.yaml").resolve()
    text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    try:
        cfg = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as error:
        # Never rewrite a config we can't read: Hermes itself refuses to, and the human's settings would be lost.
        raise ApplyError(f"{config_path} is not valid YAML, so it was left unchanged: {error}") from None
    if not isinstance(cfg, dict):
        raise ApplyError(f"{config_path} is not a YAML mapping, so it was left unchanged")
    for key, value in changes:
        _set_nested(cfg, key, value)
    for key, value in defaults:
        if _get_nested(cfg, key) in (None, ""):
            _set_nested(cfg, key, value)
    for folder in trust:
        root = str(Path(folder).expanduser().resolve())
        trusted = _get_nested(cfg, "skills.trusted_project_dirs") or []
        trusted = [str(t) for t in (trusted if isinstance(trusted, list) else [trusted])]
        if not any(str(Path(t).expanduser().resolve()) == root for t in trusted):
            _set_nested(cfg, "skills.trusted_project_dirs", trusted + [root])

    class Dumper(yaml.SafeDumper):
        pass

    def text_block(dumper, data):  # multi-line text (personalities) stays readable, as Hermes writes it
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|" if "\n" in data else None)

    Dumper.add_representer(str, text_block)
    output = yaml.dump(cfg, Dumper=Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False,
                       width=4096)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    mode = config_path.stat().st_mode & 0o777 if config_path.exists() else 0o600
    temporary = config_path.with_name(f".{config_path.name}.thesystem-{os.getpid()}")
    temporary.write_text(output, encoding="utf-8")
    os.chmod(temporary, mode)
    os.replace(temporary, config_path)  # a reader never sees a half-written config


def _apply_with_cli(changes, defaults, trust) -> None:
    def hermes(*args):
        return subprocess.run(["hermes", *args], capture_output=True, text=True)

    for folder in trust:
        hermes("skills", "trust", str(folder))
    for key, value in changes:
        hermes("config", "set", key, value if isinstance(value, str) else json.dumps(value))
    for key, value in defaults:
        if not hermes("config", "get", key).stdout.strip():
            hermes("config", "set", key, value)


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
    if argv[:1] == ["apply"]:
        parser = argparse.ArgumentParser(prog="python3 -m thesystem.harness apply")
        parser.add_argument("hermes_root", type=Path)
        parser.add_argument("--canonical", type=Path)
        parser.add_argument("--set", nargs=2, action="append", default=[], metavar=("KEY", "VALUE"))
        parser.add_argument("--default", nargs=2, action="append", default=[], metavar=("KEY", "VALUE"))
        parser.add_argument("--trust", action="append", default=[], metavar="FOLDER")
        args = parser.parse_args(argv[1:])
        changes = list(leaves(load(args.canonical.read_text(encoding="utf-8")))) if args.canonical else []
        try:
            apply(args.hermes_root, changes + [tuple(pair) for pair in args.set], [tuple(p) for p in args.default],
                  args.trust)
        except ApplyError as error:
            print(f"install: Hermes settings not applied: {error}", file=sys.stderr)
            return 1
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
