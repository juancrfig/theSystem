# Workspace glossary

## Language

**Main agent**: the agent the human talks to. It is the human's only interface to theSystem.

**Project**: one of the company's products, e.g. an Android app. A folder directly inside the workspace.

**Source clone**: a git repository with a project's code, inside the project folder. A project can have several.

**Role**: a named selection of rules, skills and tools (Hermes toolsets), which may include only some of these. Its name is a freely
chosen label, not an implied responsibility.
_Avoid_: profile, which means a Hermes profile; specialization.

**Worker**: the agent that writes the change for one task.
_Avoid_: implementer.

**Reviewer**: the agent that independently checks the worker's change and gives a verdict.

**Ticket**: the official, named item of work assigned to the developer in the scope's selected tracker.
_Avoid_: task, issue.

**Task**: a bounded piece of a ticket, divided as the developer chooses. A ticket has at least one task.
_Avoid_: ticket, issue, sub-ticket.

**Run**: one attempt at a task: the worker, then the reviewer. A task can have several runs.
