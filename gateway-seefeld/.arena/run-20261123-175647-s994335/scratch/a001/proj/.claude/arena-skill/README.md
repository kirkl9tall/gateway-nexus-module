# The Arena skill

When your coding agent keeps giving you bad answers, make 100 versions of it compete. One skill
for Codex and Claude Code. Free, MIT, no separate signup or API key.

You use it when you are not happy with an answer. Instead of asking again and again, `$arena` in
Codex (or `/arena` in Claude Code) creates 100 competitors and gives every one of them the exact
same task, word for word.
Each one gets a different strategy card: a way of reasoning, a workflow and a strategy, so each one
attacks the task differently. Then they pair off. Each attacks the other's solution, each defends
and revises its own, and a judge scores the match on a written rubric. The loser is out. 100
becomes 50, then 25, 13, 7, 4, 2, 1.

What comes back is the one solution that survived, the attacks it beat on the way, and how many
rounds it took.

**Tournament artifacts go inside `.arena/`.** Sub-agents are instructed to leave project files
alone and return proposed changes in their answers. This is prompt discipline, not a filesystem
sandbox. Applying the winning proposal is a separate step.

## Install

### Codex

Clone this Codex-compatible version, then install the skill for your user. The install step
refuses to overwrite an existing installation:

```bash
git clone https://github.com/hs487667/arena-skill.git
cd arena-skill

arena_dest="$HOME/.agents/skills/arena"
if [ -e "$arena_dest" ] || [ -L "$arena_dest" ]; then
  echo "Already exists: $arena_dest. Review it before replacing it."
else
  mkdir -p "$HOME/.agents/skills"
  cp -R skills/arena "$arena_dest"
fi
```

For a project-local installation, use the same guarded copy with `arena_dest` set to the target
project's `.agents/skills/arena`, and create that project's `.agents/skills` parent directory.
Do not copy into an existing `arena` directory: that can create an unintended nested installation.

Start a fresh Codex chat after installing, then invoke `$arena`. Codex must expose native sub-agent
tools in that session; installing this skill does not enable them or change your configuration.
See the official [skill documentation](https://learn.chatgpt.com/docs/build-skills) and
[sub-agent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).

### Claude Code

From this converted checkout, copy the same skill into Claude Code's skill directory:

```bash
arena_dest="$HOME/.claude/skills/arena"
if [ -e "$arena_dest" ] || [ -L "$arena_dest" ]; then
  echo "Already exists: $arena_dest. Review it before replacing it."
else
  mkdir -p "$HOME/.claude/skills"
  cp -R skills/arena "$arena_dest"
fi
```

Project-local installations use the target project's `.claude/skills/arena` directory instead.
Claude Code uses `/arena` for a copied skill. You can also install this version as a Claude Code
plugin:

```
/plugin marketplace add hs487667/arena-skill
/plugin install arena-skill@arena-skill
```

Claude Code namespaces plugin skills, so the plugin shows up as `/arena-skill:arena`.

Both hosts need Python 3.8 or newer and native sub-agent support (Codex's sub-agent tools or Claude
Code's Agent tool). `bracket.py` uses only Python's standard library. Nothing to pip install, and
no direct model API integration or API key is required by this skill. Your host's existing model
access and usage limits still apply. Without native sub-agent tools, the skill reports the missing
capability instead of simulating competitors in the main chat.

## Use it

```
$arena
$arena --quick write the headline for our pricing page
$arena --agents 32 fix the flaky test in tests/test_api.py
$arena --seed 7 plan my launch week, I have 6 hours a day
```

In Claude Code, replace `$arena` with `/arena` (or `/arena-skill:arena` for the plugin). On its own,
the skill takes your last request as the task and the answer you did not like as the one to beat.
Your agent can also suggest it when you say something like "that's a bad answer, make them
compete". When the agent chooses Arena without an explicit invocation, it asks before starting.

| flag | what it does |
| --- | --- |
| `--agents N` | N competitors. Default 100. |
| `--quick` | 16 competitors. The everyday setting. |
| `--seed S` | Same seed, same cards and same bracket. Default random, and recorded. |
| `--wave W` | Sub-agents per wave. Use known available capacity; Codex uses 1 when capacity is unknown. Claude Code's existing default is 10, capped by known available capacity. |

Competitor count is separate from concurrency. Codex selects a wave size from the current
session's available sub-agent slots, including other active work; there is no universal Codex
concurrency value. If capacity cannot be established, it uses `--wave 1`. It waits for and releases
finished workers before dispatching more. An explicit `--wave` must also fit the available
capacity. The skill does not change host settings or permission modes.

## How it works

1. **Spawn.** N competitors, one native sub-agent call each. Every one gets the same task text, byte for byte
   (a test checks it), plus one strategy card. There are 15 reasoning modes (first principles,
   inversion, analogy, adversarial, constraint first, worked example, Socratic, contrarian, systems
   thinking and more), 12 workflows (draft, critique, rewrite; outline first; test first; research,
   then synthesise; three drafts, pick one...) and 12 strategies (simplest thing that works, maximal
   rigour, user empathy first, edge cases first, speed...). That is 2,160 different cards. The
   dealer gives each agent its own, with no repeats.
2. **Attack.** Solutions are paired, and the pairing avoids putting two agents with the same
   reasoning mode against each other. Each side attacks the other's solution through its own card:
   what is wrong, what requirement it missed, the exact input that breaks it. Up to 7 attacks,
   labelled FATAL, MAJOR or MINOR.
3. **Defend.** Each side answers every attack it took, conceding or rebutting with evidence, then
   rewrites its solution to fix everything it conceded.
4. **Judge.** A separate judge sub-agent reads both revised solutions, checks every attack itself,
   and scores both on [the rubric](skills/arena/rubric.md): correctness 30, completeness against the
   task 25, robustness to the attacks raised 20, specificity 15, clarity 10. The judge never sees
   the cards. `bracket.py` does the arithmetic: the higher total goes through, and a solution with a
   verified fatal flaw cannot beat one without. The loser is out.
5. **Repeat.** The survivors carry their revised solutions into the next round. An odd number means
   one bye, never to the same agent twice while anyone else is waiting for one.
6. **Result.** One solution left. You get it, the attacks it survived, its card and the round count.
   If you started from an answer you rejected, a last judge compares the winner with it blind and
   the skill tells you the score, even when the old answer wins.

Example 100-agent bracket with waves of 10, from
`python3 skills/arena/bracket.py plan --agents 100 --wave 10`:

```
  round  alive  matches  bye  sub-agent calls  waves
  spawn    100        -    -              100     10
      1    100       50    -              250     25
      2     50       25    -              125     13
      3     25       12  yes               60      8
      4     13        6  yes               30      5
      5      7        3  yes               15      3
      6      4        2    -               10      3
      7      2        1    -                5      3
  total                                 595     70

  alive per round: 100 -> 50 -> 25 -> 13 -> 7 -> 4 -> 2 -> 1
```

The whole tournament lives in one JSON file, managed by `bracket.py`. The main agent session
only runs the loop and never reads the hundreds of solution files: every sub-agent writes its work
to disk and replies with one line, so the main context holds receipts and bookkeeping, not the
work. If the conversation gets compacted halfway through, `bracket.py next` picks it up from the
file.

## What it costs

The skill is free. The tokens are yours, and 100 agents is a lot of them.

| agents | rounds | sub-agent calls | example: waves of 10 |
| --- | --- | --- | --- |
| 100, the default | 7 | 595 | 70 |
| 64 | 6 | 379 | 49 |
| 32 | 5 | 187 | 28 |
| 16, `--quick` | 4 | 91 | 16 |
| 8 | 3 | 43 | 10 |

Add one call when there is a rejected answer to beat. Every call reads the task and one or two
solutions, so the bill grows with the size of the task. Use `--quick` or `--agents 16` for
everyday things and save the full 100 for the answer that matters. The skill prints these numbers
before it starts. `python3 skills/arena/bracket.py plan --agents 16 --wave 1` prints an estimate for
16 competitors running one worker at a time. Smaller waves increase the number of waves without
changing the number of sub-agent calls.

## The tool

`bracket.py` is standard-library Python. It is the reason the orchestrator never loses track.

Use the same `--wave` value for `plan` and `init` so the estimate matches the saved run. The CLI
retains its default of 10 for compatibility; the Codex skill always passes its resolved wave size
explicitly. From `skills/arena`, an example using one worker at a time is:

```bash
python3 bracket.py plan --agents 100 --wave 1        # rounds, calls, waves. Writes nothing
python3 bracket.py init --agents 100 --wave 1 --seed 7 --task-file task.md
python3 bracket.py next                     # what to do now, with the exact command
python3 bracket.py prompts attack           # write every sub-agent brief, list the jobs in waves
python3 bracket.py pairings                 # this round's matches, including the bye
python3 bracket.py collect                  # record the judges' verdicts
python3 bracket.py record r3-m07 a042 --reason "..."   # or record one by hand
python3 bracket.py advance                  # eliminate the losers, pair the survivors
python3 bracket.py status                   # alive and eliminated, per round
python3 bracket.py winner                   # the survivor, the attacks it survived, the rounds
```

Add `--baseline-file old.md` to `init` when comparing against a rejected answer. Task and baseline
files must already exist. `bracket.py` manages state and prompt files; the host agent dispatches
the native workers. Running the Python CLI alone does not call any models.

The tests run a full 100-agent tournament through that command line with random winners and check
it ends with exactly one survivor, plus 16, 7 and 1 agents, the dealer's guarantees, and every
phase from spawn to the final check with stand-in sub-agents. Run from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

These tests exercise the tournament engine and prompt contract. A live host run is also needed
to verify that your Codex or Claude Code session exposes the required sub-agent and file tools.

## The fine print

**"100 competitors" means 100 strategy-and-solution entries.** The host's worker model settings
apply; Arena does not select 100 different models. What makes competitors different is the card.
The dealer guarantees that no two agents get the
same card, that every reasoning mode, workflow and strategy is dealt as evenly as possible, and that
up to 144 agents, no two agents even share two of their three parts.

**A competitor is its card plus its solution file.** Sub-agents do not remember anything between
calls, so when competitor a017 attacks in round 3, that is a fresh sub-agent handed a017's card and
a017's latest solution. 100 competitors, 595 calls.

**"The best answer" means the one that survived every match.** The judges are model sub-agents too, scoring
against a written rubric that is in this repo for you to read and change. What you get is the
strongest answer this tournament found, not a proof that it is right. That is why it shows you the
attacks it survived, and why it tells you straight when the answer you rejected scored higher.

**100 agents do not all run at the same moment.** Arena dispatches one wave at a time within the
host's available capacity. The example above uses 10 workers: 10 spawn waves and 70 waves for the
whole tournament. Codex uses a smaller wave when its current session requires it. The saved
wave size controls both scheduling and estimates.

**The host's existing permissions apply.** Workers need to read task inputs and write artifacts
inside `.arena/`. The skill does not change permission modes or weaken sandbox settings; if an
operation is denied, resolve it through the host's normal controls.

**Sub-agents receive a standalone task.** The skill writes the relevant requirements into a task
file and starts fresh workers for each job. If a requirement never made it into the file, the
competitors can miss it. It is at
`.arena/<run>/task.md` if you want to check.

**Project changes are proposals.** Workers are instructed to return code changes as a diff or as
full files inside their answers, not apply them to the project. Review the winning answer before
applying it; these instructions do not create technical write isolation.

**The same seed gives the same cards and the same bracket.** Not the same answers. The model is not
deterministic.

**It does not fix a bad task.** Vague task in, 100 flavours of vague out.

## Files

```
skills/arena/SKILL.md          the orchestration steps and the exact brief every sub-agent gets
skills/arena/bracket.py        the tournament state machine, standard library only
skills/arena/strategies.json   15 reasoning modes, 12 workflows, 12 strategies. Edit freely
skills/arena/rubric.md         the five criteria every judge scores on
skills/arena/references/       Codex and Claude Code runtime instructions
skills/arena/agents/openai.yaml Codex skill picker metadata
tests/test_bracket.py          the tests
```

## Credit

Original skill by Jake Schincariol, [opusjake.ai](https://opusjake.ai), from
[Jakeschincariol/arena-skill](https://github.com/Jakeschincariol/arena-skill).
This repository adds Codex compatibility while retaining Claude Code support.

## License

MIT. Take it, change it, ship it.
