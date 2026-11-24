# click-json-inventory-cli

A Harbor task an agent synthesised through the envwiki MCP server from the
documentation of [pallets/click](https://github.com/pallets/click), using the
`dockerized-terminal-blueprint` recipe.

The solving agent has to build a persistent inventory CLI with Click: an
`add`, a `remove` and a `list` command over a JSON file selected by a global
`--db` option. The verifier exercises the behaviour, not the file.

## What is in here

```
task.toml            # schema_version 1.4, difficulty unrated, provenance
instruction.md       # what the solving agent is asked to do
environment/
  Dockerfile         # the Docker build context is this directory
  commands-and-groups.md
  options.md
tests/
  test.sh            # the entry point Harbor runs; the Python verifier travels with it
solution/
  solve.sh           # the reference solution; it writes /app/inventory.py
envwiki.json         # provenance: name, description, source notes, metadata, recipe ids
```

Harbor discovers one script per directory and uploads only that file into
the container, so the Python verifier and the Python solution are embedded in
`tests/test.sh` and `solution/solve.sh` rather than living beside them.

## Checking it

```
$ envwiki validate .
$ envwiki gate .
```

The gate runs the task in a container twice: the reference solution has to
earn the full reward, and an agent that does nothing has to earn less.

```
pass: instruction_disclosure - the instruction does not contain the solution
pass: verifier_entrypoint - tests/test.sh is present, the entry point Harbor runs
pass: oracle - the reference solution earned the full reward
pass: baseline - an agent that does nothing earns less than the full reward
pass: reward_space - the reward an agent competes for, above the floor
reward: 1.0
floor: 0.0
reward_repair: 1.0
```

The gate needs the Harbor CLI and a running Docker daemon.
