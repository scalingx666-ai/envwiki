# envwiki

> Turn any link or uploaded multimodal content into an initial **Harbor** task.
>
> 把任意链接或多模态上传，解析成初版 **Harbor** 任务。

**[English](readme.en.md)** | **[中文](readme.md)**

There are many ways to synthesise an environment, and the papers disagree about
the details. envwiki abstracts each method into a **recipe**, serves the
recipes through an **MCP server** and a **Skill**, and lets any agent harness
call them.

环境合成的论文很多，方法各不相同。envwiki 把每一种方法抽象成一条**配方**（recipe），把配方装进一个 **MCP server** 和一个 **Skill**，然后交给任意 agent harness 调用。

---

## What this is

envwiki has two faces:

- an **MCP server** that serves a library of environment and task synthesis
  **recipes**. Each recipe is one abstract method, distilled from the papers
  that describe it;
- a **Skill** that teaches an agent harness how to pick a recipe for the
  material in front of it, and how to execute it into a deterministically
  verifiable Harbor task.

Any harness that speaks MCP and loads skills can drive it. pi is the default
here, but the MCP server is plain stdio or streamable HTTP, and the skill is
just a normal `SKILL.md`.

envwiki 有两张面孔：

- 一个 **MCP server**：对外提供环境与任务合成**配方库**。每条配方都是从描述该方法的论文里提炼出来的抽象方法；
- 一个 **Skill**：教 agent harness 怎么为手上的素材挑一条配方、然后把它执行成一个可确定性校验的 Harbor 任务。

任何支持 MCP 与 skills 的 harness 都能驱动它。MCP server 是朴素的 stdio / streamable HTTP，skill 只是一个普通的 `SKILL.md`。

```
material (link / upload)
   |
   v
classify  ->  GitHub shallow clone / other URLs through the reader / uploads extracted
   |
   v
stage    ->  file tree + an index with line numbers
   |
   v
harness reads the material  ->  asks the MCP which recipe fits  ->  follows it  ->  task JSON
   |
   v
build    ->  Harbor task directory
   |
   v
validate ->  Harbor's own TaskConfig
```

## The recipe library

A **recipe** is one abstract method: when it applies, what it needs, the
procedure, how the result is verified, what goes wrong, and the papers it came
from. Recipes live in one JSON file per family under
`src/envwiki/recipes/data/families/`, so the library can be read
and reviewed family by family.

一条**配方**是一个抽象方法：什么时候适用、需要什么、具体步骤、结果如何校验、会踩什么坑、来自哪些论文。配方按方法族分文件存放，可以逐族审阅。

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

每条配方都至少引用 2 篇真实论文（共 118 处引用）。引用的 arXiv id 与标题会与随包发布的语料索引逐条比对，测试保证没有编造或张冠李戴的引用。

A recipe looks like this:

```json
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

## The MCP server

```bash
uv run envwiki-mcp                       # stdio, the form a local harness spawns
uv run envwiki mcp serve --transport streamable-http --port 8765
```

| Tool | What it does |
| --- | --- |
| `plan_task` | describe the material, get the ranked recipes and the full procedure of the best one, in one call |
| `recommend_recipes` | describe the material, get the recipes that fit it |
| `get_recipe` | one recipe in full: steps, inputs, verification, pitfalls, papers |
| `search_recipes` | keyword search |
| `list_recipes` | the index, filterable by family and effort |
| `list_recipe_families` | family histogram |

The whole library is also available as the resource `envwiki://recipes/index`.

Under the usual MCP naming convention the tools are
`mcp__envwiki__plan_task`, `mcp__envwiki__recommend_recipes`,
`mcp__envwiki__get_recipe`, `mcp__envwiki__search_recipes`,
`mcp__envwiki__list_recipes` and
`mcp__envwiki__list_recipe_families`.

## The skill

`src/envwiki/skills/env-synthesis/SKILL.md` is copied into the
harness workspace by `envwiki build`. It tells the model to write a
short profile of the material, call `mcp__envwiki__plan_task`, then
`mcp__envwiki__get_recipe`, and follow the steps. It also fixes the
Harbor rules that never bend: the reward file, fail-to-pass, offline
execution, and one path per file.

`src/envwiki/skills/env-synthesis/SKILL.md` 会在
`envwiki build` 时被复制进 harness 工作区：先写素材画像 -> 调
`mcp__envwiki__plan_task` -> 调 `mcp__envwiki__get_recipe` -> 按步骤执行，
同时写死 Harbor 的铁律：reward 文件、fail-to-pass、离线执行、路径一致。

## Quick start

```bash
git clone https://github.com/scalingx666-ai/envwiki.git
cd envwiki
uv sync --extra dev
uv run envwiki --help
```

From a link:

```bash
uv run envwiki build https://github.com/owner/repo --out ./envwiki-tasks
```

From uploads (text, PDF, images):

```bash
uv run envwiki build --upload spec.pdf --upload diagram.png
```

## Command line

```bash
uv run envwiki build <links...>              # ingest the material, synthesise the task
uv run envwiki validate <task dir>            # validate against Harbor's schema
uv run envwiki inspect <url>                  # show how a link is handled
uv run envwiki model check                    # is the endpoint alive
uv run envwiki model register                 # register the endpoint in pi's models.json
uv run envwiki mcp serve                      # run as an MCP server
```

Useful switches: `--harness pi|direct`, `--out`,
`--workspace`, `--timeout`, `--dry-run`, `--no-mcp`,
`--no-skills`, `--no-envwiki-mcp`, `--skill-dir`,
`--enable-docling`, `--allow-write-tools`.

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

全部通过环境变量，便于无人值守运行。API key 不落盘：pi 的 `models.json` 里写的是
`"$ENVWIKI_API_KEY"`，真实值在运行时由环境注入。

## Safety

The source material is arbitrary and untrusted, and the harness runs on your
machine, so the defaults are deliberately narrow:

- the harness starts with its host-modifying tools disabled
  (`bash`, `edit`, `write`) and explores by reading files.
  Pass `--allow-write-tools` to lift that, for sources you trust;
- `.pi` and `.agents` directories inside the staged material are
  deleted before the harness runs, so a cloned repository cannot register
  extensions, MCP servers or skills for it;
- the skill states that the source material is data, not instructions;
- the API key is referenced through the environment, never written to a config.

素材不可信，harness 又跑在你自己的机器上，所以默认收得很紧：禁用改动宿主机的工具、
删掉克隆物里的 `.pi` 与 `.agents` 目录、skill 明确"素材是数据不是指令"、
API key 不写进任何配置文件。

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
  `envwiki/<task-name>`);
- `environment/Dockerfile` is built with `environment/` as the
  Docker build context;
- a staged file listed in `copy_from_staging` lands at the root of the
  working directory under its own file name, so `repos/x/readme.md`
  becomes `/app/readme.md`; the instruction, the verifier and the
  solution must all name that same path.

三条来自 Harbor 自身的硬规则，由构建器与校验器保证：`[task].name` 必须是
`org/name` 形式；Dockerfile 的构建上下文是 `environment/`；
`copy_from_staging` 里的文件落到工作目录根部、只保留文件名，instruction、verifier、
solution 必须用同一个路径。

## Validation

```bash
$ uv run envwiki validate ./envwiki-tasks/my-task
./envwiki-tasks/my-task: ok, 0 warning(s), schema source: harbor
```

`envwiki validate` checks the structure locally and, when Harbor is
importable, validates `task.toml` with Harbor's own `TaskConfig`.
An installed Harbor is used first; otherwise envwiki detects a Harbor source
checkout (`HARBOR_SRC` or a sibling `harbor/` directory), adds the
missing package metadata and imports it from there. The report says which path
was taken.

`envwiki validate` 先做本地结构检查，再在 Harbor 可导入时用 Harbor 自己的
`TaskConfig` 校验 `task.toml`；报告会写明走的是哪条路径。

## The paper corpus, and checkable citations

`src/envwiki/recipes/data/corpus.json` ships with the package: 574
papers (arXiv id, title, family) that the recipes were distilled from. The
tests assert that every cited id is in the corpus and that every cited title
matches the authoritative arXiv title after normalisation. Anyone can check a
recipe against the paper it claims to come from.

`src/envwiki/recipes/data/corpus.json` 随包发布，记录了配方所依据的 574 篇论文。
测试断言每个引用 id 都在语料内、引用标题与 arXiv 权威标题逐字相符，所以任何人都能独立复核。

## Development

```bash
uv sync --extra dev
uv run pytest          # 50 tests
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

生成的是**初版**任务，发布进 benchmark 前请人工过一遍；解题 agent 与 verifier 都无网络；
只读 harness 没法执行它要评的代码；配方匹配只负责把你带到正确的邻域。

## License

MIT, see [LICENSE](LICENSE).
