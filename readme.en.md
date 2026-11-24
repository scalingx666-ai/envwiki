# envwiki

> A **toolbox** for agents that synthesise environments and tasks.
>
> 给 agent 用的环境与任务合成**工具箱**。

**[English](readme.en.md)** | **[中文](readme.md)**

There are many ways to synthesise an environment, and the papers disagree about
the details. envwiki abstracts each method into a **recipe**, ships the
recipes, the material and the scaffolding through one **MCP server**, and
writes the method into a **Skill**.

**The agent does the synthesis.** envwiki generates no tasks and makes no
decisions on the agent's behalf.

---

## What this is

envwiki is three things, all of them for the agent:

- an **MCP server** that is a toolbox: recipes (the methods), material (a
  staging area) and scaffolding (write a task, check a task). It holds **no
  synthesis logic of its own**: it never decides what a task should look
  like;
- a **Skill** that is the single place where "how to write a Harbor task"
  lives: the method, the verifier contract, the reference-solution contract,
  the path rules and the pre-submit checklist;
- a small set of **diagnostic commands**: putting the toolbox into your
  agent (print the MCP config, install the skill), checking a task directory,
  showing how a link is handled.

envwiki **does not** start an agent for you and **does not** synthesise a
task by itself. You own the agent: hang the MCP server on it, install the
skill, then tell it "turn this link into a Harbor task".

Any harness that speaks MCP and loads skills can use it: pi, Claude Code,
Codex, OpenCode, whatever you already run.

## Who does what

| Who | Responsible for | Not responsible for |
| --- | --- | --- |
| the agent | reading the material, choosing a method, deciding what task to write, iterating on validation errors | parsing material, judging the schema |
| the envwiki MCP server | handing over methods (recipes), material (staging), writing the task (scaffolding) and checking it | deciding what the task is, generating task content |
| the envwiki CLI | printing the MCP config, installing the skill, validating a task, showing how a link is handled | synthesising tasks, orchestrating agents |

**There is exactly one contract.** The shape of a task is enforced by the
signature of the `scaffold_task` tool and by `TaskDraft` (pydantic) in
`envwiki/schemas.py`. There is no second task JSON structure anywhere in
envwiki, and Harbor's rules live **only** in the skill. Want to know what a
task looks like? Read the tool signature. Want to know how to write a good
one? Read the skill.

```
link / upload
   |
   v
agent calls stage_source  ->  staging area: file tree + an index with line numbers
   |
   v
agent calls plan_task  ->  pick a method  ->  get_recipe  ->  follow it
   |
   v
agent calls scaffold_task  ->  write the task  ->  validate_task  ->  fix and repeat
```

## How to use it

Three steps.

### 1. Hang the MCP server on your agent

```
uv run envwiki mcp config
```
```
{
  "mcpServers": {
    "envwiki": {
      "command": "/path/to/python",
      "args": ["-m", "envwiki.mcp_server"],
      "description": "..."
    }
  }
}
```

Write it into your agent's MCP configuration: for pi that is
`~/.pi/agent/mcp.json` (global) or the project's `.pi/mcp.json`; every other
harness has its own place. The tools are named
`mcp__envwiki__plan_task`, `mcp__envwiki__scaffold_task`,
`mcp__envwiki__validate_task` and so on.

### 2. Install the skill

```
uv run envwiki skill install --to ~/.pi/agent/skills
```

Without `--to` the command prints where the skill lives, so you can copy it
yourself.

### 3. Say one sentence to your agent

"Use envwiki to turn https://github.com/owner/repo into a Harbor task."

The agent walks the whole path by itself: `stage_source` → `plan_task` →
`get_recipe` → `scaffold_task` → `validate_task`, and hands you the task
directory at the end.

## The recipe library

A **recipe** is one abstract method: when it applies, what it needs, the
procedure, how the result is verified, what goes wrong, and the papers it came
from. Recipes live in one JSON file per family under
`src/envwiki/recipes/data/families/`, so the library can be read and
reviewed family by family.

| Family | What it covers | Recipes |
| --- | --- | --- |
| `environment-synthesis` | general environment synthesis: skeleton, state, scenarios and difficulty into one executable environment | 3 |
| `experience-synthesis` | experience and interaction synthesis: execute first, ask second, let the trace become the material | 3 |
| `web-gui` | web and GUI: rebuild a real application as a light environment, rewards as code assertions | 3 |
| `terminal-coding` | terminal and coding: taxonomy sampling, evidence grounding, Dockerisation, fail-to-pass | 3 |
| `simulation` | model-based simulation and language world models: worldbooks, deterministic engines, probeable rules | 3 |
| `task-scenario` | task and scenario synthesis: checkpoints, curricula, capability frontiers, requirement compilation | 3 |
| `mcp-tools` | MCP tool environments: dependencies mined from real call traces, dynamic disruption, adversarial injection | 3 |
| `enterprise-professional` | enterprise and professional work: repository workflows, zero-execution specification tasks, intervention windows | 3 |
| `platform-infra` | platforms and infrastructure: call capture and replay, simulated APIs, UI state validation | 2 |
| `sandbox` | sandboxes: pick the isolation substrate, compose in layers, state capsule lifecycle | 2 |
| `computer-use` | computer use: deterministic application docking, execution gating, perturbation recovery | 3 |
| `data-synthesis` | data synthesis: verify then complicate, deterministic cache provenance, decision grounding | 3 |
| `embodied` | embodied work: constraint-driven instances, skill-library exploration, asset and scene co-evolution | 3 |
| `multi-agent` | multi-agent: interdependent task graphs, coopetition mechanisms | 2 |
| `verification` | difficulty and verification: state-diff verifiers, IRT difficulty banding, negative-control screening | 3 |
| **Total** | | **42** |

Every recipe cites at least two real papers (118 citations in total). The arXiv
id and the title of each citation are checked against the corpus index shipped
with the package, so the tests prove that no citation is invented or
misattributed.

A recipe looks like this:

```
{
  "id": "execution-first-trace-anchored-task",
  "family": "experience-synthesis",
  "summary": "Build the executable artifact before the prompt...",
  "when_to_use": ["..."], "not_when_to_use": ["..."], "inputs": ["..."],
  "steps": [{"title": "Pick the workflow before the prompt", "detail": "..."}],
  "verifier": ["the check command exits non-zero on the unmodified workspace"],
  "pitfalls": ["request written first: it reads plausibly but no valid call sequence satisfies it"],
  "effort": "high",
  "source_papers": [{"arxiv_id": "2607.29175", "title": "...", "note": "..."}]
}
```

### How recipes are matched

Recipes are not matched by bumping keywords into each other. envwiki turns
every recipe into vectors and keeps them in **zvec**, an in-process vector
store:

- **signal vector**: a BM25 sparse vector over summary, when_to_use,
  not_when_to_use and inputs;
- **detail vector**: a BM25 sparse vector over the whole recipe (steps,
  verification, pitfalls);
- **dense vector**: one more semantic layer when an embedding endpoint is
  configured;
- **full text index**: zvec's own FTS.

A query searches those signals together and fuses them with reciprocal rank
fusion. The index is cached under `~/.cache/envwiki/recipes-<hash>.zvec`,
keyed by the content of the recipe library, so a changed library gets its
own index.

Dense vectors need an embedding endpoint:

| Variable | Meaning |
| --- | --- |
| `ENVWIKI_EMBEDDING_BASE_URL` | OpenAI-compatible `/embeddings` endpoint |
| `ENVWIKI_EMBEDDING_MODEL` | Model id |
| `ENVWIKI_EMBEDDING_API_KEY` | API key for that endpoint (optional) |

`plan_task`, `recommend_recipes` and `search_recipes` all report an `engine`
field: `zvec-hybrid`, `zvec-bm25` or `lexical`.

## The MCP server: a toolbox

```
uv run envwiki-mcp                       # stdio, the form an agent spawns
uv run envwiki mcp serve --transport streamable-http --port 8765
```

**Recipes (the methods)**

| Tool | What it does |
| --- | --- |
| `plan_task` | describe the material, get the ranked recipes and the full procedure of the best one, in one call |
| `recommend_recipes` | describe the material, get the recipes that fit it |
| `get_recipe` | one recipe in full: steps, inputs, verification, pitfalls, papers |
| `search_recipes` | keyword search |
| `list_recipes` | the index, filterable by family and effort |
| `list_recipe_families` | family histogram |

The whole library is also available as the resource `envwiki://recipes/index`.

**Material**

| Tool | What it does |
| --- | --- |
| `stage_source` | resolve links and uploads into a workspace you can explore; returns the file tree and a digest with line numbers |
| `list_staged` | show what is currently staged in a workspace |

**Scaffolding**

| Tool | What it does |
| --- | --- |
| `scaffold_task` | write the task directory from the spec you produced. **This is the only way to write files**, and the spec is enforced by the tool signature |
| `validate_task` | check the task directory: local structure plus Harbor's own TaskConfig |

## The skill

`src/envwiki/skills/env-synthesis/SKILL.md` is the **single source of the
method and the rules**: the tool table, the six-step workflow, what makes a
good task, the verifier contract, the reference-solution contract, the path
rules and the checklist to run before validating.

## Command line

The command line does two things: put the toolbox into your agent, and
diagnose.

```
uv run envwiki validate <task dir>            # validate against Harbor's schema
uv run envwiki inspect <url>                  # show how a link is handled
uv run envwiki model check                    # is the endpoint alive
uv run envwiki model register                 # register the endpoint in pi's models.json
uv run envwiki mcp serve                      # run as an MCP server
uv run envwiki mcp config                     # print the MCP config that reaches envwiki
uv run envwiki skill install --to <dir>       # install the skill for an agent
```

There is no `build`: envwiki does not synthesise for you and does not
orchestrate your agent. The agent does that, through the MCP server.

## Configuration

Everything comes from the environment, so envwiki can run unattended.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENVWIKI_BASE_URL` | `http://127.0.0.1:8787/v1` | OpenAI-compatible base URL |
| `ENVWIKI_API_KEY` | `sk-my-secret` | API key for that endpoint |
| `ENVWIKI_MODEL` | `hy4flash-free` | Model id |
| `ENVWIKI_PROVIDER` | `envwiki-local` | Provider name written into pi's models.json |
| `HARBOR_SRC` | auto-detected | Path to Harbor's `src` directory, used for schema validation |
| `ENVWIKI_STAGING_DIR` | empty | Workspace `scaffold_task` writes into by default |
| `ENVWIKI_INDEX_DIR` | `~/.cache/envwiki` | Where the recipe vector index is cached |
| `ENVWIKI_EMBEDDING_BASE_URL` | empty | OpenAI-compatible `/embeddings` endpoint for dense vectors |
| `ENVWIKI_EMBEDDING_MODEL` | empty | Model id for dense vectors |
| `ENVWIKI_EMBEDDING_API_KEY` | empty | API key for that embedding endpoint |

The API key never lands on disk: pi's `models.json` receives
`"$ENVWIKI_API_KEY"` and the real value is exported at run time.

## Safety

The source material is arbitrary and untrusted, so the defaults are
deliberately narrow:

- **the model can only write through `scaffold_task`**: it cannot write any
  other file, and whatever it writes goes through pydantic and Harbor's schema
  immediately;
- `.pi` and `.agents` directories inside the staged material are deleted
  before anything explores them, so a cloned repository cannot register
  extensions, MCP servers or skills;
- the skill states that the source material is data, not instructions;
- the API key is referenced through the environment, never written to a config.

## Task layout

```
my-task/
  task.toml            # schema_version 1.4, [task] [metadata] [verifier] [agent] [environment]
  instruction.md       # what the solving agent is asked to do
  environment/
    Dockerfile         # the Docker build context is this directory
  tests/
    test.sh            # must write /logs/verifier/reward.txt
  solution/
    solve.sh           # reference solution
  envwiki.json         # provenance: name, description, source notes, metadata, recipe ids used
```

Three rules come from Harbor itself and are enforced by the builder and the
validator:

- `[task].name` must be in `org/name` format (the `org` parameter of
  `scaffold_task` sets the prefix);
- `environment/Dockerfile` is built with `environment/` as the Docker build
  context;
- a staged file listed in `scaffold_task`'s `copy_from_staging` lands at the
  root of the working directory under its own file name, so
  `repos/x/readme.md` becomes `/app/readme.md`; the instruction, the verifier
  and the solution must all name that same path.

## Validation

```
$ uv run envwiki validate ./my-task
./my-task: ok, 0 warning(s), schema source: harbor
```

`envwiki validate` checks the structure locally and, when Harbor is
importable, validates `task.toml` with Harbor's own `TaskConfig`.
An installed Harbor is used first; otherwise envwiki detects a Harbor source
checkout (`HARBOR_SRC` or a sibling `harbor/` directory), adds the
missing package metadata and imports it from there. The report says which path
was taken. The agent also calls `validate_task` on its own task while it
builds, and fixes whatever the validator reports.

## The paper corpus, and checkable citations

`src/envwiki/recipes/data/corpus.json` ships with the package: 574
papers (arXiv id, title, family) that the recipes were distilled from. The
tests assert that every cited id is in the corpus and that every cited title
matches the authoritative arXiv title after normalisation. Anyone can check a
recipe against the paper it claims to come from.

## Development

```
uv sync --extra dev --extra vector
uv run pytest          # 66 tests

The `vector` extra installs zvec: recipe retrieval then goes through the
vector store instead of keyword weighting. zvec ships wheels for CPython
3.10 to 3.14 only, so the repository is pinned to 3.13 (see
`.python-version`). Without the extra envwiki still works, on the built-in
lexical matcher.
uv run ruff check src tests
```

## Limitations

- The generated task is a **first draft**. It is schema-valid and structurally
  complete, but the difficulty calibration and the verifier's strictness are
  whatever the model produced. Review before publishing to a benchmark.
- The solver agent and the verifier both run without network access, so a task
  that needs to fetch something at solve time will fail.
- Only `linux` and `windows` target environments are supported,
  matching Harbor's own enum.
- envwiki does not run the agent for you: the quality of the result is the
  quality of your agent and your model, and the agent may not even follow the
  tools.
- Recipe retrieval runs on BM25 sparse vectors by default; semantic retrieval
  needs an embedding endpoint you configure yourself.
- The match only gets the agent into the right neighbourhood; the model
  still has to choose.

## License

MIT, see [LICENSE](LICENSE).
