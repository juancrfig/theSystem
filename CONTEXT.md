# Workspace glossary

Terms of the agent system itself, shared by every project. A project's domain terms go in
`<project>/CONTEXT.md`.

**Role**: a named combination of rules, skills, tools, utils, CLIs, and MCP servers. A role may
define only some of these. An agent gets an ordered list of roles and receives everything they
list; when two roles hold an item with the same name, the later role's item wins. The name is a
free label chosen by whoever defines the role; it does not imply a responsibility.
_Avoid_: profile, which means a Hermes profile; specialization.

**Worker**: the agent that writes the change for one task, inside a run's container.
_Avoid_: implementer.

**Ticket**: the official, named item of work assigned to the developer, in Jira or any other
tracker. The main agent plans a ticket into a spec.
_Avoid_: task, issue.

**Task**: a local piece of a ticket, divided as the developer chooses. One orchestrator run
implements one task. A ticket always has at least one task.
_Avoid_: ticket, issue, sub-ticket.
