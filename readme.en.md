# envwiki

> Turn any link or uploaded multimodal content into a verifiable **Harbor** task.
>
> 把任意链接或多模态上传，变成一个可校验的 **Harbor** 任务。

**[English](readme.en.md)** | **[中文](readme.md)**

There are many ways to synthesise an environment, and the papers disagree about
the details. envwiki abstracts each method into a **recipe**, and ships the
recipes, the material and the scaffolding through one **MCP server**. The
**agent decides what task to write**; envwiki itself does not synthesise.

---

## What this is

envwiki is three things:

- an **MCP server** that gives an agent a toolbox: recipes (the methods),
  material (a staging area) and scaffolding (write a task, check a task). It
  holds **no synthesis logic of its own**: it never decides what a task should
  look like;
- a **Skill** that is the single place where "how to write a Harbor task"
  lives: the method, the verifier contract, the reference-solution contract,
  the path rules and the pre-submit checklist;
- a **CLI** that is a thin driver. It stages the material, runs the agent,
  collects what the agent wrote, validates it and publishes it. It does not
  parse model output into a task, and it never writes task content itself.

Any harness that speaks MCP and loads skills can drive it. pi is the default
here, but the MCP server is plain stdio or streamable HTTP, and the skill is
just a normal `SKILL.md`.

## Who does what

This is the central convention of the project: **the synthesis lives in the
agent, envwiki is the toolbox.**

| Who | Responsible for | Not responsible for |
| --- | --- | --- |
| the agent | reading the material, choosing a method, deciding what task to write, iterating on validation errors | parsing material, judging the schema |
| the envwiki MCP server | handing over methods (recipes), material (staging), writing the task (scaffolding) and checking it | deciding what the task is, generating task content |
| the envwiki CLI | staging, running the agent, finding the product, validating, publishing | reading model output as a task, writing the task for the agent |

**There is exactly one contract.** The shape of a task is enforced by the
signature of the `scaffold_task` tool and by `TaskDraft` (pydantic) in
`envwiki/schemas.py`. envwiki's prompt no longer carries a parallel task
JSON structure, and Harbor's rules live **only** in the skill. Want to know
what a task looks like? Read the tool signature. Want to know how to write a
good one? Read the skill.

```
material (link / upload)
   |
   v
staging     ->  file tree + an index with line numbers
   |
   v
agent reads the material  ->  plan_task picks a method  ->  get_recipe returns
the procedure  ->  the agent follows it
   |
   v
scaffold_task writes the task  ->  validate_task checks it  ->  fix and repeat
   |
   v
the CLI finds the product  ->  validates  ->  publishes it to --out
```

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

## The MCP server: a toolbox

```
uv run envwiki-mcp                       # stdio, the form a local harness spawns
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

Under the usual MCP naming convention the tools are
`mcp__envwiki__plan_task`, `mcp__envwiki__scaffold_task`,
`mcp__envwiki__validate_task` and so on.

## The skill

`src/envwiki/skills/env-synthesis/SKILL.md` is copied into the harness
workspace by `envwiki build`. It is the **single source of the method and the
rules**: the tool table, the five-step workflow, what makes a good task, the
verifier contract, the reference-solution contract, the path rules and the
checklist to run before validating.

## Quick start

```
git clone https://github.com/scalingx666-ai/envwiki.git
cd envwiki
uv sync --extra dev
uv run envwiki --help
```

From a link:

```
uv run envwiki build https://github.com/owner/repo --out ./envwiki-tasks
```

From uploads (text, PDF, images):

```
uv run envwiki build --upload spec.pdf --upload diagram.png
```

## Command line

```
uv run envwiki build <links...>              # stage, run the agent, validate and publish
uv run envwiki validate <task dir>            # validate against Harbor's schema
uv run envwiki inspect <url>                  # show how a link is handled
uv run envwiki model check                    # is the endpoint alive
uv run envwiki model register                 # register the endpoint in pi's models.json
uv run envwiki mcp serve                      # run as an MCP server
```

Useful switches: `--harness pi|direct`, `--out`, `--workspace`, `--org`,
`--timeout`, `--dry-run`, `--no-mcp`, `--no-skills`, `--no-envwiki-mcp`,
`--skill-dir`, `--enable-docling`, `--allow-write-tools`.

`--harness direct` runs without pi: the model talks straight to the
OpenAI-compatible endpoint, but it uses **the same tools** (the MCP server's
tool functions, called in process), so both paths share one contract. It needs
an endpoint that accepts OpenAI-style `tools` parameters.

## Configuration

Everything comes from the environment, so envwiki can run unattended.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENVWIKI_BASE_URL` | `http://127.0.0.1:8787/v1` | OpenAI-compatible base URL |
| `ENVWIKI_API_KEY` | `sk-my-secret` | API key for that endpoint |
| `ENVWIKI_MODEL` | `hy4flash-free` | Model id |
| `ENVWIKI_PROVIDER` | `envwiki-local` | Provider name written into pi's models.json |
| `ENVWIKI_HARNESS` | `pi` | Harness backend: `pi` or `direct` |
| `HARBOR_SRC` | auto-detected | Path to Harbor's `src` directory, used for schema validation |

The API key never lands on disk: pi's `models.json` receives
`"$ENVWIKI_API_KEY"` and the real value is exported at run time.

## Safety

The source material is arbitrary and untrusted, and the harness runs on your
machine, so the defaults are deliberately narrow:

- the harness starts with its host-modifying tools disabled
  (`bash`, `edit`, `write`) and explores by reading files.
  Pass `--allow-write-tools` to lift that, for sources you trust;
- **the model can only write through `scaffold_task`**: it cannot write any
  other file, and whatever it writes goes through pydantic and Harbor's schema
  immediately;
- `.pi` and `.agents` directories inside the staged material are deleted
  before the harness runs, so a cloned repository cannot register extensions,
  MCP servers or skills for it;
- the skill states that the source material is data, not instructions;
- the API key is referenced through the environment, never written to a config.

## Task layout

```
envwiki-tasks/my-task/
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

- `[task].name` must be in `org/name` format (envwiki uses
  `envwiki/<task-name>` by default, and `--org` changes it);
- `environment/Dockerfile` is built with `environment/` as the Docker build
  context;
- a staged file listed in `scaffold_task`'s `copy_from_staging` lands at the
  root of the working directory under its own file name, so
  `repos/x/readme.md` becomes `/app/readme.md`; the instruction, the verifier
  and the solution must all name that same path.

## Validation

```
$ uv run envwiki validate ./envwiki-tasks/my-task
./envwiki-tasks/my-task: ok, 0 warning(s), schema source: harbor
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
uv sync --extra dev
uv run pytest          # 62 tests
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
- A read-only harness cannot run the code it is asked to grade. Tasks that
  need execution-time facts (a stack trace, a computed output) come out
  weaker than they would with `--allow-write-tools`.
- Recipe matching is keyword weighted. It gets you the right neighbourhood,
  but the model still has to choose.
- `--harness direct` needs an endpoint that accepts OpenAI-style `tools`
  parameters.

## License

MIT, see [LICENSE](LICENSE).
