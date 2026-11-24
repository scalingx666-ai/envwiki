import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REWARD = Path('/logs/verifier/reward.txt')
APP = Path('/app/inventory.py')
ENV = dict(os.environ)

def run(db, *args):
    return subprocess.run([sys.executable, str(APP), '--db', str(db), *args], text=True, capture_output=True, env=ENV)

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    check(APP.is_file(), 'inventory.py is missing')
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / 'state.json'
        r = run(db, 'list')
        check(r.returncode == 0 and r.stdout == '', 'empty inventory should list successfully with no output')
        r = run(db, 'add', 'pear', '2')
        check(r.returncode == 0, 'adding a positive quantity should succeed')
        r = run(db, 'add', 'apple', '4')
        check(r.returncode == 0, 'adding another item should succeed')
        r = run(db, 'add', 'pear', '3')
        check(r.returncode == 0, 'adding a duplicate should succeed')
        check(json.loads(db.read_text()) == {'apple': 4, 'pear': 5}, 'add must persist and accumulate quantities')
        r = run(db, 'list')
        check(r.returncode == 0 and r.stdout == 'apple\t4\npear\t5\n', 'list must sort items and use NAME<TAB>QUANTITY lines')
        r = run(db, 'add', 'invalid', '0')
        check(r.returncode != 0 and 'invalid' not in json.loads(db.read_text()), 'zero quantity must be rejected without mutation')
        before = db.read_text()
        r = run(db, 'remove', 'missing')
        check(r.returncode == 1 and r.stderr and db.read_text() == before, 'removing a missing item must fail without changing state')
        r = run(db, 'remove', 'apple')
        check(r.returncode == 0 and json.loads(db.read_text()) == {'pear': 5}, 'remove must delete an existing item')
        db.write_text('{bad json')
        r = run(db, 'list')
        check(r.returncode != 0 and db.read_text() == '{bad json', 'malformed JSON must be rejected and preserved')
        db.write_text(json.dumps({'bad': 0}))
        r = run(db, 'list')
        check(r.returncode != 0, 'non-positive stored quantity must be rejected')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        REWARD.parent.mkdir(parents=True, exist_ok=True)
        REWARD.write_text('0')
        print(f'FAIL: {exc}', file=sys.stderr)
    else:
        REWARD.parent.mkdir(parents=True, exist_ok=True)
        REWARD.write_text('1')
        print('PASS')
