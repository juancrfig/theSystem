# Overview

A framework to reliably build high-quality software by leveraging AI agents

Install infrastructure without a Hermes runtime:

```bash
curl -fsSLo /tmp/thesystem https://raw.githubusercontent.com/juancrfig/theSystem/master/bin/thesystem
bash /tmp/thesystem install --workspace "$HOME/workspace" --runtime none --non-interactive
```

The public command is `thesystem`; run it without arguments or with `--help` to see usage.

# Infrastructure

- **[Hermes Harness](https://hermes-agent.nousresearch.com/docs)**
- **[llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)**
- **[OpenTelemetry](https://opentelemetry.io)**

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
