"""envwiki command line interface.

envwiki is a toolbox for agents that build Harbor tasks: an MCP server that
carries the recipes, the material and the scaffolding, plus a skill that
carries the method. The commands below prepare that toolbox and diagnose it.

None of them synthesises a task. The agent does that, through the MCP server.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer

from envwiki.config import EnvwikiConfig, ModelEndpoint
from envwiki.convert.gate import gate_task
from envwiki.convert.validate import validate_task
from envwiki.ingest.classify import classify_url, parse_github_url
from envwiki.llm.client import LLMClient
from envwiki.pi_setup import mcp_server_entry, register_provider
from envwiki.skills import builtin_skill_dirs

app = typer.Typer(
    add_completion=False,
    help="A toolbox for agents that build Harbor tasks.",
)
model_app = typer.Typer(help="Inspect and register the model endpoint.")
app.add_typer(model_app, name="model")
mcp_app = typer.Typer(help="Serve envwiki over MCP.")
app.add_typer(mcp_app, name="mcp")
skill_app = typer.Typer(help="Install the synthesis skill into an agent.")
app.add_typer(skill_app, name="skill")


@app.command("validate")
def validate_cmd(
    task_dir: Path = typer.Argument(..., help="Task directory to validate."),
) -> None:
    """Validate an existing task directory against Harbor's schema."""
    report = validate_task(task_dir)
    for issue in report.issues:
        typer.echo(issue.level + ": " + issue.message)
    typer.echo(
        str(report.task_dir)
        + ": "
        + ("ok" if report.ok else str(len(report.errors)) + " error(s)")
        + ", "
        + str(len(report.warnings))
        + " warning(s), schema source: "
        + report.schema_source
    )
    if not report.ok:
        raise typer.Exit(1)


@app.command("gate")
def gate_cmd(
    task_dir: Path = typer.Argument(..., help="Task directory to run."),
    skip_oracle: bool = typer.Option(
        False, "--skip-oracle", help="Only run the baseline."
    ),
    skip_baseline: bool = typer.Option(
        False, "--skip-baseline", help="Only run the reference solution."
    ),
) -> None:
    """Run a task and check that it really works.

    The reference solution has to earn the full reward, and an agent that
    does nothing has to earn less. A task that only parses can still be
    broken, and this is what catches it.
    """
    report = gate_task(
        task_dir,
        run_oracle=not skip_oracle,
        run_baseline=not skip_baseline,
    )
    for check in report.checks:
        typer.echo(check.status + ": " + check.name + " - " + check.detail)
    for issue in report.errors:
        typer.echo("error: " + issue)
    for issue in report.warnings:
        typer.echo("warning: " + issue)
    if report.reward is not None:
        typer.echo("reward: " + str(report.reward))
    if report.floor is not None:
        typer.echo("floor: " + str(report.floor))
    if report.reward_repair is not None:
        typer.echo("reward_repair: " + str(round(report.reward_repair, 4)))
    typer.echo(
        report.task_dir
        + ": "
        + ("passed" if report.ok else str(len(report.errors)) + " error(s)")
        + (", verified" if report.verified else ", not verified")
    )
    if not report.ok:
        raise typer.Exit(1)


@app.command("inspect")
def inspect_cmd(
    url: str = typer.Argument(..., help="Link to inspect."),
) -> None:
    """Show how envwiki would treat a link."""
    kind = classify_url(url)
    ref = parse_github_url(url) if kind.value == "github" else None
    payload = {"url": url, "kind": kind.value}
    if ref is not None:
        payload["owner"] = ref.owner
        payload["repo"] = ref.repo
        payload["clone_url"] = ref.clone_url
        payload["ref"] = ref.ref
        payload["path"] = ref.path
        payload["strategy"] = "git clone (shallow)"
    else:
        payload["strategy"] = "reader"
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@model_app.command("register")
def model_register(
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register the endpoint inside pi's models.json."""
    endpoint = ModelEndpoint.from_env()
    config = EnvwikiConfig(endpoint=endpoint)
    result = register_provider(config.agent_dir, endpoint, dry_run=dry_run)
    typer.echo(
        json.dumps(
            {"changed": result.changed, "message": result.message, "path": result.path},
            indent=2,
        )
    )


@model_app.command("check")
def model_check() -> None:
    """Check that the endpoint answers and lists the configured model."""
    endpoint = ModelEndpoint.from_env()
    client = LLMClient(endpoint)
    models = client.list_models()
    payload = {
        "base_url": endpoint.base_url,
        "model": endpoint.model,
        "provider": endpoint.provider,
        "reachable": bool(models),
        "models": models,
        "model_present": endpoint.model in models,
    }
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    if not models:
        raise typer.Exit(1)


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option(
        "stdio", "--transport", help="stdio, sse or streamable-http."
    ),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Serve the envwiki toolbox over MCP: recipes, staging and scaffolding."""
    from envwiki.mcp_server import server

    if transport == "stdio":
        server.run(transport="stdio")
        return
    server.run(transport=transport, host=host, port=port)


@mcp_app.command("config")
def mcp_config(
    python_executable: str | None = typer.Option(
        None, "--python", help="Interpreter that runs envwiki."
    ),
) -> None:
    """Print the MCP client configuration that reaches envwiki."""
    entry = mcp_server_entry(python_executable)
    typer.echo(json.dumps({"mcpServers": entry}, indent=2, ensure_ascii=False))


@skill_app.command("install")
def skill_install(
    to: Path | None = typer.Option(
        None, "--to", help="Skill directory to install into."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show what would happen."),
) -> None:
    """Install the env-synthesis skill where an agent can load it."""
    directories = builtin_skill_dirs()
    if not directories:
        typer.echo("no skill ships with this installation", err=True)
        raise typer.Exit(1)

    if to is None:
        for directory in directories:
            typer.echo(str(directory))
        return

    target = Path(to).expanduser()
    for directory in directories:
        destination = target / directory.name
        if not dry_run:
            shutil.copytree(directory, destination, dirs_exist_ok=True)
        typer.echo("skill: " + str(destination))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
