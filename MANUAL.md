# theSystem · User manual

Use theSystem's verified workspace operations. Keep control of your projects, configuration, and learning decisions.

[Verified capabilities](#verified-capabilities) · [Get started](#get-started) · [Projects](#register-a-project) · [Source clones](#register-a-source-clone) · [Roles](#configure-project-roles) · [Evidence](#inspect-an-existing-run-record) · [Learning](#review-pending-hermes-memory-writes)

## Verified capabilities

Verification applies only to the source, runtime, and environment identified in the linked records. Historical probes are not fresh deployment checks. Current checkout tests establish only the behavior they exercise, not authenticated agent execution or broader distribution coverage.

| Capability | Evidence-backed scope | Evidence |
| --- | --- | --- |
| Infrastructure-only installation | The current public command's runtime-free install, registration, upgrade, rollback, uninstall, aliases, and preservation behavior passed isolated temporary-home tests outside the checkout cwd. No fresh Ubuntu/Arch certification is claimed for the current command. | [Current bounded delivery evidence](https://github.com/juancrfig/theSystem/issues/30) |
| Non-chat company command | Current checkout tests verified no-argument help and rejection of removed launch options without launching subprocesses. | [CLI change record](https://github.com/juancrfig/theSystem/issues/28) and [checkout verification](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912380760) |
| Project and source-clone registration; role configuration | An installed blank-mode Ubuntu command registered a project and Git clone and set worker/reviewer roles. Current checkout subprocess tests also verified registration/idempotence, project content preservation, and role configuration/refusal paths. | [Historical ledger](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5908905757) and [checkout verification](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912380760) |
| Software upgrade, rollback, and uninstall | Current public-command tests exercised runtime-free install → project registration → upgrade → rollback → uninstall in temporary homes outside the checkout cwd; they verified preservation of modified files and project knowledge, independent aliases, shared command availability, and separate rollback readiness output. No fresh Ubuntu/Arch certification is claimed. | [Current bounded delivery evidence](https://github.com/juancrfig/theSystem/issues/30) |
| Hermes configure and doctor | Native isolated Hermes v0.21.5 configured a disposable Git-root fixture twice, accepted 32/32 included skills, verified canonical settings/toolsets/review imports, set `.githooks` as `core.hooksPath`, and passed read-only doctor. The hook file was executable; direct execution was blocked by the session's fail-closed Tirith timeout. The fixture excluded a quarantined vendored Hermes skill; with the full distribution present Hermes quarantined `autonomous-ai-agents/hermes-agent`, configure failed, and doctor correctly reported not ready. This does not certify readiness for the unmodified full distribution. | [Current bounded delivery evidence](https://github.com/juancrfig/theSystem/issues/30) |
| Existing run-record inspection | A current checkout subprocess test read a fixture record through `evidence` and returned its recorded status. This verifies record retrieval, not creation, accuracy, or end-to-end execution of a run. | [Checkout verification](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912380760) |
| Hermes pending-memory-write review and application | An isolated `master` profile's inventory, display, and explicit human approval applied a pending memory write; the pending count became zero and `MEMORY.md` contained the approved line. This does not establish every profile or every kind of learning proposal. | [Native pending-write evidence](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5908905757), artifact `NATIVE_PENDING_APPLY_VERIFIED` |

## Get started

### 1. Install

#### Infrastructure-only installation

The current runtime-free path has been exercised by isolated temporary-home tests; the older fresh-install probes on Ubuntu 24.04 and Arch base containers used the retired `--blank=yes` installer and do not certify the current command. No fresh-machine or no-Python acquisition certification is claimed for this delivery.

Download the public launcher to a file, then run it. The launcher downloads and validates the distribution source before dispatching Python when it is outside a checkout:

```bash
curl -fsSLo /tmp/thesystem https://raw.githubusercontent.com/juancrfig/theSystem/master/bin/thesystem
bash /tmp/thesystem install --workspace "$HOME/workspace" --runtime none --company company --non-interactive
```

This installs theSystem infrastructure and a workspace-bound company alias. It does not install an agent runtime or configure a model. No Hermes profile is required for this mode. The installed files are a distribution, not a Git checkout. The current Hermes setup path is blocked for non-Git workspaces because Hermes project-skill discovery requires a Git root; setup does not initialize user workspaces.

| Tested option | Effect |
| --- | --- |
| `--workspace PATH` | Select the installation workspace. |
| `--company NAME` | Name the workspace-bound command; the example uses `company`. |
| `--runtime none` | Install infrastructure only, without an agent runtime or model setup. |
| `--non-interactive` | Run without interactive setup; Hermes mode requires an already configured selected profile. |
| `--help` | Show command usage without installing. |

**Success:** the command reports completion with runtime `none` and the workspace path. Completion confirms deployment only; run `thesystem doctor --workspace "$HOME/workspace" --runtime none` to inspect installed distribution readiness. `Ready` does not establish authenticated agent operation.

**Verification boundary:** runtime-free install and lifecycle tests ran in isolated temporary homes outside the checkout cwd. Native Hermes checks used an isolated profile and disposable Git-root workspace: configure succeeded twice and doctor was read-only/ready for a fixture with the quarantined vendored Hermes skill excluded. With the full distribution skill set, Hermes quarantined `autonomous-ai-agents/hermes-agent`; configure refused and doctor reported not ready. Non-Git Hermes setup is unsupported; the command does not initialize user workspaces or use profile-wide external skill paths. No authenticated model call or fresh Ubuntu/Arch/no-Python certification was performed.

#### Software lifecycle

The current runtime-free lifecycle path is covered by the isolated public-command tests summarized above. Historical Ubuntu/Arch lifecycle evidence applies to the retired installer only. Rollback output now distinguishes restored software from the independent Hermes readiness report; a successful restoration does not imply a ready Hermes workspace.

### 2. Use your company command

If you chose `company`:

```bash
company --help
```

The launcher lives in `~/.local/bin`; use its absolute path if that directory is not on your shell's `PATH`. It is bound to the installed workspace.

Calling the command without arguments shows help. It does not open an interactive agent session. `launch` and `--direct` are rejected; `--json` alone returns a usage error. With a command, `--json` requests JSON-mode output. Project registration returns structured JSON even without that flag.

Help lists registration, role, task/orchestrator, evidence, and learning interfaces. A listed interface is not evidence that its complete workflow has been verified. This manual describes only the verified operations below. Blank installation does not provide an agent runtime or the Hermes learning dependencies.

## Register a project

A **workspace** contains projects. A **project** holds its knowledge and work records and may contain multiple **source clones**—Git working trees registered beneath the project. See [GLOSSARY.md](GLOSSARY.md) for terminology.

Create or choose an existing project directory inside your workspace. For the example workspace and command:

```bash
mkdir -p "$HOME/workspace/payments"
company add-project "$HOME/workspace/payments"
```

**Success:** JSON with `status: "ok"`, the project path, and `idempotent: false` for a new registration or `true` for an existing registration. Registration creates missing `wiki`, `agents`, and `tickets` directories. Repeating it preserves existing content and does not duplicate the registry entry.

Registration does not clone repositories, populate knowledge, or configure roles.

| If registration fails | Check |
| --- | --- |
| Missing or invalid directory | The project must already exist; relative paths start from your current directory. |
| Wrong location | Use a project inside the workspace—not the workspace itself, reserved infrastructure, or a source clone. |
| Overlapping projects | A project cannot contain or be contained by an already registered project. |
| Unsafe infrastructure or registry | Existing project infrastructure must be real directories, not symlinks. Registry symlinks and invalid registry paths are rejected. |

Errors return `status: "error"`, a code, and a message. These behaviors were exercised by [current checkout subprocess tests](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912380760).

## Register a source clone

Register an existing Git working tree strictly inside a registered project:

```bash
company add-source-clone "$HOME/workspace/payments" "$HOME/workspace/payments/api"
```

The `api` directory must already be a Git working tree. This command registers it; it does not clone a remote repository.

**Success:** JSON with `status: "ok"`, `project`, `source_clone`, and an `idempotent` flag. Repeating registration avoids a duplicate entry. An unregistered project is rejected.

Source-clone registration has an [installed Ubuntu probe](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5908905757) and [current checkout subprocess tests](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912380760). Registration alone does not start or approve work.

## Configure project roles

The verified `set-role` operation writes a project role entry in `<project>/agents/roles.yaml`. The file written by this command uses JSON syntax, which is also valid YAML.

For example, to configure an `api` role:

```bash
company set-role "$HOME/workspace/payments" api --rule rules/no-secrets.md --cli git
```

The command records the references; this example does not create the rule or install Git. The tested result contains a `rules` list with `rules/no-secrets.md` and a `clis` list with `git`, and returns `status: "ok"` with the role configuration path.

**Configuration limitations:**

- Setting a role replaces that role's entry; it is not an additive update. Other role entries are retained.
- Role names start with a letter and contain letters and numbers.
- The command rejects a worker/reviewer configuration in which the reviewer lacks a worker rule. Configure the reviewer with matching rules before adding those rules to the worker.
- An existing `roles.yaml` that is not JSON-compatible is refused rather than overwritten. A symlink or non-file target is also refused.

The write and reviewer-rule refusal paths were exercised by [current checkout tests](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912380760). Role configuration is not certification of runtime guidance delivery, capability enforcement, or permission isolation.

## Inspect an existing run record

For a registered project and an existing record, substitute the actual run identifier for `RUN_ID`:

```bash
company evidence --project "$HOME/workspace/payments" --run RUN_ID
```

**Success:** JSON with `status: "ok"` and the stored record under `run`. The command reads `<project>/.thesystem/orchestrator/runs/<run-id>.json`.

The [current checkout evidence test](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912380760) used a fixture record and verified that its stored status was returned. This establishes retrieval only: it does not prove the record's claims or certify the workflow that produced it.

## Review pending Hermes memory writes

The recorded working path used a real pending memory write in an isolated Hermes `master` profile:

```bash
company learning inventory
company learning show
```

`inventory` lists pending requests and their record hashes. `show` displays a request for review. To leave a request pending, make no decision; viewing it or continuing the conversation is not approval.

The verified approval used `company learning decide` with `--human-decision`, `--decision approve`, the reviewed profile/subsystem/request identifiers, and `--expected-record-sha256` from the reviewed request. Use the exact identifiers and hash from the inventory, not guessed values. The recorded application returned success, cleared the pending request, and added the approved line to `MEMORY.md`.

**Verification boundary:** the evidence covers that isolated native memory-write path, not every installed profile, skill-write application, run-learning integration, or remote evaluator. The company bridge invokes the local review script; infrastructure-only installation does not install its Hermes dependencies. A recorded blank-mode invocation returned `MEMORY_REVIEW_FAILED` rather than providing review capability.

See [native application evidence](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5908905757), artifact `NATIVE_PENDING_APPLY_VERIFIED`. The current checkout learning-bridge test mocks its subprocess and is not independent evidence of native application.

## About this manual

Usage claims are scoped to their linked evidence. If observed behavior differs from the manual, report the discrepancy on [GitHub](https://github.com/juancrfig/theSystem/issues); do not treat a documented bug as an approved requirement.

Detailed historical evidence and the requirements removed during this cleanup are preserved in the [GitHub migration record](https://github.com/juancrfig/theSystem/issues/27#issuecomment-5912352177). That record preserves draft material without approving it. The manual is not a backlog, acceptance checklist, or authority for planned behavior.
