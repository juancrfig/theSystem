# Overview

A framework to reliably build high-quality software by leveraging AI agents

```bash
curl -fsSL https://raw.githubusercontent.com/juancrfig/theSystem/master/install | bash
```

# Infrastructure

- **[Hermes Harness](hermes-agent.nousresearch.com)**
- **[llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)**
- **[OpenTelemetry](opentelemetry.io)**

# The Four Problems

1. How to gather, curate, and maintain knowledge?
2. What are skills, tools, scripts, and context in general an agent needs to operate effectively?
3. How to ensure the implementation respects the constraints and follows the plan, while mitigating 
blast radius write-allowed agents may cause?
4. How the system will improve over time?

# Decisions

- Instructions for agents must be carefully maintained. Ideally, agents should handle entirely the 
self-improvement mechanism. However, the protocol agents follow to do this must not be left in
charge of agents. I've noticed agents are not good (by default) when trying to generalize their 
reflections from mistakes, effectivelly bloating their own memory with ticket-specific learnings. 
Until a clear protocol is designed and battle-tested, the feedback loop must remain in charge of humans. 

## theSystem work tracking

Work on this repository is tracked in the public GitHub Issues for
[`juancrfig/theSystem`](https://github.com/juancrfig/theSystem/issues) and the private
[`theSystem` Project](https://github.com/users/juancrfig/projects/8). The agent working on
theSystem owns ticket creation, review, updates, organization, dependency links, evidence,
verification, and closure; the user is not expected to maintain the tracker. Product projects
retain their own documented tracker and execution contract.

See `agents/skills/ticket-system-maintenance/SKILL.md` for the required create/review/migration
workflow. Durable design decisions live in `docs/ADRs/`, indexed by `docs/stuff/decisions.md`.
