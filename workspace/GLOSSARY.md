# Workspace glossary

## Language

**Main agent**: the agent the human talks to. It is the human's only interface to theSystem. It is also the
orchestrator: it runs each approved task by delegating it to a worker and a reviewer subagent.

**Project**: one of the company's products, e.g. an Android app. A folder directly inside the workspace.

**Source clone**: a git repository with a project's code, inside the project folder. A project can have several.

**Role**: a named selection of rules and skills, which may include only one of these. Its name is a freely chosen
label, not an implied responsibility.
_Avoid_: profile, which means a Hermes profile; specialization.

**Worker**: the subagent that writes the change for one task.
_Avoid_: implementer.

**Reviewer**: the subagent that independently reads the worker's change and gives a verdict.

**Ticket**: the official, named item of work assigned to the developer in the scope's selected tracker.
_Avoid_: task, issue.

**Task**: a bounded piece of a ticket, divided as the developer chooses. A ticket has at least one task.
_Avoid_: ticket, issue, sub-ticket.

**Run**: one attempt at a task: the worker, then the reviewer. A task can have several runs.

**Release**: a published version of theSystem that servers install and update to. On the
`no-tests-main-orchestrator` channel, a release is the newest commit of that branch.

**Baseline**: the release a workspace was installed or last updated from.

**Proposal**: a pull request from a workspace that offers a local improvement as a new theSystem default.
