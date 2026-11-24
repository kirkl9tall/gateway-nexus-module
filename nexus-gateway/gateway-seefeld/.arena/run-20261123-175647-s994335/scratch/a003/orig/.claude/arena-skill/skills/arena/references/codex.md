# Codex runtime

Use the subagent tools exposed in the current session. This skill uses the signed-in Codex runtime;
it does not require an API key, a Claude installation or a nested `codex exec` process.

## Capacity and lifecycle

- Read the live tool descriptions for the thread limit and whether it includes the coordinator.
  Account for agents already in use. Choose no more than the available slots, bounded by any user
  `--wave` request. When capacity is unknown, use `--wave 1` for both `plan` and `init`.
- If no slots are free, wait for Arena's active jobs. Do not close unrelated agents to make room.
  If unrelated work occupies all capacity, report that blocker.
- Use a fresh agent for every competitor, attack, defense and judge job, with no conversation fork.
  Do not reuse an agent through `send_input` or `followup_task`: retained context would compromise
  the independent strategies and blind judging. These tools can deliver a correction to the same
  unfinished job when needed, not switch the worker to another job.
- Inherit the session's model and reasoning settings unless the user explicitly requests an
  available override. Do not change global configuration to run Arena. If the host caps total fresh
  agents for a session, checkpoint and report the limit; do not substitute reused contexts or a
  smaller tournament without the user's direction.

## Native Codex tools

When the session provides `spawn_agent`, a completion-wait tool and `close_agent`:

1. Spawn one agent per brief with `message` set to the shared wrapper from `SKILL.md`. Use the
   general-purpose/default role exposed by the schema, not a role with unrelated instructions.
   If `fork_context` exists, set it to `false`; otherwise follow the exposed fresh-context option.
2. Collect each returned agent ID. Wait using the tool actually available (`wait` or `wait_agent`
   in different versions) and its documented parameters. Check all IDs until each is completed or
   explicitly failed; a wait timeout is not a job failure.
3. Close each finished Arena agent using `close_agent` before the next wave. Completed agents may
   still occupy slots until closed. Never close a worker while it is writing its output.

## Hosted `collaboration` tools

When the host exposes the `collaboration` namespace instead:

1. Use `collaboration.spawn_agent` with a unique `task_name`, the shared wrapper as `message`,
   `agent_type: "default"`, and `fork_turns: "none"`. Omit model/effort overrides.
2. `collaboration.wait_agent` waits for a mailbox update, not necessarily completion of every
   worker. Process the delivered completion messages and use `list_agents` when status is unclear.
   Continue waiting until all jobs in the wave have ended.
3. This host may not expose a close operation. Follow its active-agent limit and start a fresh
   agent for the next job. Never treat `interrupt_agent` as closing or clearing a worker's context.
   Use it only when cancelling active work, such as a user stop request.

These are capability branches, not interchangeable APIs. If the tools do not offer independent
subagents or fresh context, explain the missing capability and stop before initializing a run.

## Installation and invocation

Install the whole skill directory at `~/.agents/skills/arena` or a project's `.agents/skills/arena`.
Invoke `$arena --quick <task>` or select Arena from the skill picker. Resolve `bracket.py` relative
to the loaded skill location, including when installed through a symlink or another supported root.
If discovery has not refreshed, start a new Codex session. Do not edit global configuration.

Official references: [skills](https://learn.chatgpt.com/docs/build-skills),
[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
