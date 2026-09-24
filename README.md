# Overview 

A framework to reliably build high-quality software by leveraging AI agents. 

# Setup

After cloning, enable the tracked git hooks: `git config core.hooksPath .githooks`

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

- Instructions for agents must be carefully maintained. Ideally, agents should edit by themselves 
their context files and tools. However, the protocol agents follow to do this must not be left in
charge of agents. I've noticed agents are not good (by default) when trying to generalize their 
reflections from mistakes, effectivelly bloating their own memory with ticket-specific learnings. 
Until a clear protocol is designed and battle-tested, the feedback loop must remain in charge of humans. 
