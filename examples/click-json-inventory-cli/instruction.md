# Build a persistent inventory CLI with Click

Create `inventory.py` in `/app`. Click 8.1.8 is preinstalled. The staged references `commands-and-groups.md` and `options.md` describe the command group and parameter APIs. Implement a command line program named `inventory` and persist all state as JSON at the path selected by the root `--db PATH` option. The default path is `inventory.json` in the current working directory.

The command group must provide:

- `add NAME QUANTITY`: add a positive integer quantity. If NAME already exists, add to its current quantity.
- `remove NAME`: remove an existing item. If NAME does not exist, print an error to stderr and exit with status 1 without changing the database.
- `list`: print items sorted by name, one per line as `NAME<TAB>QUANTITY`. An empty inventory prints no lines.

The database must be a JSON object mapping item names to positive integers. Missing database files represent an empty inventory. Reject malformed JSON, a non-object top-level value, or entries whose keys are not strings or values are not positive integers; do not silently replace invalid data. Invalid quantities for `add` must be rejected by Click with a nonzero exit status.

Every successful mutation must write valid JSON to the selected database path. The global `--db` option must work before the command name. Use Click's command/group and parameter APIs. The program must run offline and must not access the network.

Example:

```console
$ python inventory.py --db pantry.json add rice 3
$ python inventory.py --db pantry.json add rice 2
$ python inventory.py --db pantry.json list
rice	5
$ python inventory.py --db pantry.json remove rice
```
