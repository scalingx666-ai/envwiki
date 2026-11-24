---
name: env-synthesis
description: Turn source material (a repository, a document, a dataset, a web or terminal application) into a verifiable Harbor benchmark task. Use when authoring a Harbor task, or when you must choose an environment or task synthesis method - the envwiki MCP server serves recipes distilled from the synthesis literature.
---

# Environment and task synthesis

envwiki serves a library of **recipes**: each one is an environment or task
synthesis method abstracted from the papers that describe it, with the
procedure, the required inputs, the verification strategy and the pitfalls.

Do not invent a method from scratch. Pick the recipe that fits the material,
then execute it.

## Workflow

1. **Profile the source.** One paragraph: what the material is, what capability
   it exercises, and what could be checked without a network.
2. **Ask for candidates.** Call the envwiki MCP server's
   `mcp__envwiki__plan_task` tool with that paragraph. It returns the
   ranked recipes, and the full procedure of the best one.
3. **Read the winner.** Call `mcp__envwiki__get_recipe` with the
   chosen id for the full procedure. `mcp__envwiki__recommend_recipes`,
   `mcp__envwiki__search_recipes` and `mcp__envwiki__list_recipes` are
   there when the fit is unclear.
4. **Execute the recipe.** The recipe is a method; the source material is
   fixed; the task is one concrete instance of it. Keep only the steps that
   the material can actually support.
5. **Build the Harbor task.** Follow the recipe's verifier section, then the
   non-negotiables below.

## Writing the source profile

Good profiles name the artefact, the capability and the observable outcome:

    A Python CLI that converts CSV to JSON. The capability is data wrangling
    with argument parsing; the outcome is a JSON file whose rows and key
    order can be compared exactly.

    A bilingual markdown reading list. The capability is precise extraction
    from a long document; the outcome is a sorted report file.

Avoid profiles that only say "a repository" or "a paper".

## Non-negotiables for the task

- The verifier is deterministic and must fail on an untouched workspace.
- It writes the reward to `/logs/verifier/reward.txt`
  ("1" pass, "0" fail) and exits 0 either way.
- The reference solution makes the verifier pass, from the environment workdir.
- No network at solve time or verify time.
- The instruction, the verifier and the solution must name the same paths. A
  file listed in `copy_from_staging` lands at the root of the working
  directory under its own file name, so `repos/x/readme.md` becomes
  `/app/readme.md`.
- One concrete, checkable outcome. Not "improve the code".

## Environment rules

- `environment/Dockerfile` is built with `environment/` as the
  Docker build context.
- Default base image `ubuntu:24.04`, working directory `/app`.
- Install what the task needs at build time; the sandbox has no network later.

## Before answering

```
1. The recipe was fetched and followed, and the summary says which one.
2. The task is solvable from instruction.md alone, offline, in the sandbox.
3. The verifier fails on an empty workspace and passes on the solution result.
4. The verifier writes /logs/verifier/reward.txt.
5. Instruction, verifier and solution agree on every file path.
```

Return the task as a single JSON object matching the shape the caller asked
for, and nothing else.
