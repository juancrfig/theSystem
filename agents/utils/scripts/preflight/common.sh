#!/usr/bin/env bash

PREFLIGHT_HOME="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PREFLIGHT_WORKSPACE="$(cd -- "$PREFLIGHT_HOME/../../../.." && pwd)"
PREFLIGHT_FAILED=0

fail() {
    printf 'FAIL %s\n' "$*"
    PREFLIGHT_FAILED=1
}

pass() {
    printf 'PASS %s\n' "$*"
}

for prerequisite in python3 timeout; do
    if ! command -v "$prerequisite" >/dev/null 2>&1; then
        fail "Shared checker requires $prerequisite; provision it in the execution environment."
    fi
done
if (( PREFLIGHT_FAILED )); then
    printf 'Read %s/AGENTS.md for recovery.\n' "$PREFLIGHT_HOME"
    exit 1
fi

json_pin() {
    python3 - "$1" "$2" <<'PY'
import json
import sys
try:
    with open(sys.argv[1]) as stream:
        value = json.load(stream)[sys.argv[2]]
    if not isinstance(value, str):
        raise ValueError()
    print(value)
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)
PY
}

check_exact() {
    local label="$1" expected="${2#v}" source="$3" observed
    shift 3
    if [[ ! "$expected" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][a-zA-Z0-9.-]+)?$ ]]; then
        fail "$label: missing or unsupported exact pin in $source; resolve the requirement."
    elif ! observed=$(timeout 20 "$@" 2>/dev/null); then
        fail "$label: version probe unavailable or failed; install/activate the pin from $source."
    elif [[ "${observed#v}" != "$expected" ]]; then
        fail "$label: expected $expected from $source; observed ${observed:-empty}; activate the pinned tool."
    else
        pass "$label matches $source"
    fi
}

check_agent_skill_harnesses() {
    local source_root="$PREFLIGHT_WORKSPACE/agents/skills" harness skill target relative resolved_source resolved_target

    if [[ ! -d "$source_root" ]]; then
        fail "Agent skills: canonical directory $source_root is missing."
        return
    fi

    while IFS= read -r -d '' skill; do
        if [[ ! -f "$skill/SKILL.md" ]]; then
            fail "Agent skills: $skill has no SKILL.md."
            continue
        fi
        if [[ -e "$skill/agents/openai.yaml" ]]; then
            fail "Agent skills: remove legacy UI metadata from $skill/agents/openai.yaml."
            continue
        fi

        for harness in "$PREFLIGHT_WORKSPACE/.agents/skills"; do
            mkdir -p -- "$harness" || {
                fail "Agent skills: cannot create harness directory $harness."
                continue
            }
            target="$harness/${skill##*/}"
            if [[ -e "$target" && ! -L "$target" ]]; then
                fail "Agent skills: $target exists and is not a symlink to the canonical skill."
                continue
            fi
            resolved_source=$(readlink -f -- "$skill")
            resolved_target=$(readlink -f -- "$target" 2>/dev/null || true)
            if [[ "$resolved_target" == "$resolved_source" ]]; then
                pass "Agent skills: ${harness#$PREFLIGHT_WORKSPACE/}/${skill##*/} links to agents/skills."
                continue
            fi
            relative=$(python3 - "$harness" "$skill" <<'PY'
import os
import sys
print(os.path.relpath(sys.argv[2], sys.argv[1]))
PY
)
            if ln -sfnT -- "$relative" "$target"; then
                pass "Agent skills: repaired ${harness#$PREFLIGHT_WORKSPACE/}/${skill##*/} link."
            else
                fail "Agent skills: cannot link $target to agents/skills/${skill##*/}."
            fi
        done
    done < <(find "$source_root" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
}

finish_preflight() {
    check_agent_skill_harnesses
    if (( PREFLIGHT_FAILED )); then
        printf 'Read %s/AGENTS.md for recovery.\n' "$PREFLIGHT_HOME"
    fi
    return "$PREFLIGHT_FAILED"
}
