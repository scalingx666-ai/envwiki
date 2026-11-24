---
name: env-synthesis
description: Build a verifiable Harbor benchmark task from source material (a repository, a document, a dataset, a web or terminal application). Use when authoring a Harbor task, or when you must choose an environment or task synthesis method - the envwiki MCP server serves recipes distilled from the synthesis literature plus the tools that stage the material, write the task and check it.
---

# Environment and task synthesis

You build one Harbor task out of the material you are given. The method comes
from the envwiki MCP server, not from you.

## The tools

| tool | what it is for |
| --- | --- |
| `mcp__envwiki__stage_source` | resolve a link or an upload into a workspace you can explore: returns the workspace, a file tree and a digest |
| `mcp__envwiki__list_staged` | see what is currently staged in a workspace |
| `mcp__envwiki__plan_task` | describe the material, get the ranked methods plus the full procedure of the best one |
| `mcp__envwiki__get_recipe` | read one method in full: inputs, steps, verification, pitfalls, papers |
| `mcp__envwiki__search_recipes`, `mcp__envwiki__list_recipes` | when the fit is unclear |
| `mcp__envwiki__scaffold_task` | write the task directory from your spec |
| `mcp__envwiki__validate_task` | check it, and fix whatever it reports |

`scaffold_task` is your only way to write files. `validate_task` is
the only way to know the task is acceptable.

## Workflow

1. **Stage the material.** Call `stage_source` with the link or the upload
   the user gave you. It returns a workspace directory, a file tree and a
   digest you can read without opening every file.
2. **Profile the material.** One paragraph: what it is, what capability it
   exercises, what could be checked without a network.
3. **Pick a method.** Call `plan_task` with that paragraph and read the top
   result's steps. If they do not fit, read the alternatives with
   `get_recipe`.
4. **Follow the method.** A method is a procedure, the material is fixed, and
   the task is one concrete instance of it. Keep the steps the material can
   actually support.
5. **Scaffold.** Call `scaffold_task` with your spec. Give it `staging_dir`
   (the workspace from step 1): the task then lands in `<staging>/tasks/<name>`.
   Only pass `task_dir` when you know the path is writable; if it is not,
   the task goes into the workspace instead and the tool tells you where.
   If the answer lists `missing_assets`, a file you named is not in the
   workspace: name the path that is, or drop that requirement.
6. **Validate.** Call `validate_task`. Fix every error, and every warning
   you can, then validate again.

## What a good task is

- One concrete, checkable outcome. Not "improve the code", not "write good
  tests". The check should be a file, an exit code, an output line, a state.
- Grounded in something that really exists in the material: a real script, a
  real defect, a real data file, a real API contract, a real document section.
- Solvable offline, from the instruction alone, in the sandbox.

## The verifier is the contract

- Deterministic, and it must fail on an untouched workspace.
- It writes the reward to `@/logs/verifier/reward.txt`@: "1" pass,
  "0" fail. It exits 0 either way; the reward file is the signal.
- Prefer small checks: file contents, command output, exit codes.
- Never needs the network, never depends on which tools the agent used.

## The reference solution

- It must make the verifier pass, run from the environment's working directory.
- It is the proof that the task is solvable, so write it as if you were
  solving the task, not as a sketch.
- It must not depend on anything the verifier itself created.

## Paths

- `environment/Dockerfile` is built with `environment/` as the
  Docker build context.
- A file you list in `copy_from_staging` lands at the root of the
  working directory under its own file name: `repos/x/readme.md`
  becomes `/app/readme.md`. Name that exact path in the
  instruction, in the verifier and in the solution.
- The task name is org/name: `scaffold_task` prefixes the org you pass it,
  so pass the org the task belongs to.
- Base image `ubuntu:24.04` and working directory `/app` are
  safe defaults.
- Install what the task needs at build time; the sandbox has no network later.

## Before you validate

`
1. The task is solvable from instruction.md alone, offline, in the sandbox.
2. The verifier fails on an empty workspace and passes on the solution result.
3. The verifier writes /logs/verifier/reward.txt.
4. The instruction, the verifier and the solution agree on every path.
5. source_notes names the recipe you followed.
`
