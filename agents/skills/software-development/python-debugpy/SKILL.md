---
name: python-debugpy
description: "Use when a Python failure needs interactive inspection beyond tests and logs."
version: 1.0.0
author: Hermes Agent (adapted for theSystem)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [debugging, python, pdb, debugpy, breakpoints]
    related_skills: [systematic-debugging, node-inspect-debugger]
---

Source: https://github.com/juancrfig/hermes-agent/tree/13c238327eebfff862d9ed60593751e419989785/skills (vendored snapshot)

# Python Debugger (pdb and debugpy)

A debugger may be used to reproduce and diagnose an existing failure; use automated tests only when a human explicitly asks for them. Keep the reproduction narrow.

## Choose the lightest tool

- Use `python -m pdb path/to/script.py` to step through a script without editing it. Set a breakpoint with `b file.py:42`, continue with `c`, step with `n` or `s`, inspect the stack with `w`, and inspect values with `p expression`.
- Use `breakpoint()` only as a temporary local probe when launching under pdb is impractical. Remove it immediately.
- Use `debugpy` only when attaching to or pausing a long-running process is necessary. Prefer binding to `127.0.0.1`; never expose a debug listener to a public or shared network.

## Reviewer-agent constraints

A reviewer must preserve the worker's tree. Prefer read-only inspection; do not add `breakpoint()` or other instrumentation to the source tree. The reviewer's container may use an overlay, but do not rely on changes there being available to the worker. If interactive debugging requires modifying source, report the limitation and the evidence gathered rather than changing the reviewed implementation.

Do not weaken host security settings, change ptrace permissions, install packages into a shared or production environment, or expose a debug port to make attachment work. Use only dependencies and runtime environments already provided for the task unless the task explicitly authorizes a disposable development environment.

## Cleanup

