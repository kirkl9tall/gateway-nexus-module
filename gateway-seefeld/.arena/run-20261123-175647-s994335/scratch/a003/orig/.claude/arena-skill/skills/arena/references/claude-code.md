# Claude Code runtime

Use Claude Code's `Agent` tool (`Task` in older versions), using the parameters actually exposed:

- `subagent_type`: `general-purpose`
- `description`: `arena <job id>`
- `prompt`: the shared wrapper from `SKILL.md`, with the absolute generated brief path
- `run_in_background`: `false`, when that option exists

Each job must use a fresh agent rather than resuming an earlier one. Send one wave of calls, wait
for every result, then continue. If background execution is required by the available tool, track
each worker through the host's completion tools before checking outputs or retrying anything.

The helper retains its historical default wave size of 10. Use 10 only when the host supports that
many concurrent calls; otherwise choose the available capacity (or 1 when unknown), bounded by the
user's `--wave` request. Pass that same value explicitly to `plan` and `init`.

Resolve `bracket.py` relative to the loaded skill's base directory. `${CLAUDE_SKILL_DIR}` can be
used only if the host actually expanded it. Read task arguments from the user's invocation; an
unexpanded `$ARGUMENTS` placeholder is not a task.

Install the complete skill folder at `~/.claude/skills/arena` or `.claude/skills/arena`. Invoke
`/arena`; a Claude plugin installation may namespace this as `/arena-skill:arena`.
The existing `.claude-plugin` manifests remain usable. Follow current host permissions for writes
inside `.arena/`; do not change the user's approval settings.
