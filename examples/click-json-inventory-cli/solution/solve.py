from __future__ import annotations

import json
from pathlib import Path

import click


def load_inventory(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f'cannot read inventory: {exc}') from exc
    if not isinstance(data, dict):
        raise click.ClickException('inventory JSON must be an object')
    for name, quantity in data.items():
        if not isinstance(name, str) or type(quantity) is not int or quantity <= 0:
            raise click.ClickException('inventory entries must map string names to positive integers')
    return data


def save_inventory(path: Path, data: dict[str, int]) -> None:
    try:
        path.write_text(json.dumps(data, sort_keys=True) + '\n', encoding='utf-8')
    except OSError as exc:
        raise click.ClickException(f'cannot write inventory: {exc}') from exc


@click.group()
@click.option('--db', type=click.Path(path_type=Path), default=Path('inventory.json'), show_default=True)
@click.pass_context
def cli(ctx: click.Context, db: Path) -> None:
    ctx.ensure_object(dict)
    ctx.obj['db'] = db


@cli.command()
@click.argument('name')
@click.argument('quantity', type=click.IntRange(min=1))
@click.pass_context
def add(ctx: click.Context, name: str, quantity: int) -> None:
    db = ctx.obj['db']
    inventory = load_inventory(db)
    inventory[name] = inventory.get(name, 0) + quantity
    save_inventory(db, inventory)


@cli.command()
@click.argument('name')
@click.pass_context
def remove(ctx: click.Context, name: str) -> None:
    db = ctx.obj['db']
    inventory = load_inventory(db)
    if name not in inventory:
        raise click.ClickException(f'item not found: {name}')
    del inventory[name]
    save_inventory(db, inventory)


@cli.command('list')
@click.pass_context
def list_items(ctx: click.Context) -> None:
    inventory = load_inventory(ctx.obj['db'])
    for name in sorted(inventory):
        click.echo(f'{name}\t{inventory[name]}')


if __name__ == '__main__':
    cli(obj={})
