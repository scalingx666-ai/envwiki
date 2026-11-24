"""envwiki command line interface."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from envwiki.config import EnvwikiConfig, ModelEndpoint
from envwiki.convert.builder import discover_tasks, publish_task
from envwiki.convert.prompt import SYSTEM_PROMPT, build_user_prompt
from envwiki.convert.validate import validate_task
from envwiki.harness.direct import DirectHarness
from envwiki.harness.pi_harness import PiHarness, register_provider
from envwiki.ingest.bundle import build_bundle
from envwiki.ingest.classify import classify_url, parse_github_url
from envwiki.llm.client import LLMClient

app = typer.Typer(
    add_completion=False,
    help="Drive an agent that turns links or uploads into a Harbor task.",
)
model_app = typer.Typer(help="Inspect and register the model endpoint.")
app.add_typer(model_app, name="model")
mcp_app = typer.Typer(help="Serve the envwiki toolbox over MCP.")
app.add_typer(mcp_app, name="mcp")


def _endpoint(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    provider: str | None,
) -> ModelEndpoint:
    return ModelEndpoint.from_env(
        base_url=base_url, api_key=api_key, model=model, provider=provider
    )


@app.command("build")
def build_cmd(
    links: list[str] | None = typer.Argument(None, help="Links to ingest."),
    upload: list[Path] | None = typer.Option(
        None, "--upload", "-u", help="File to upload (repeatable)."
    ),
    out: Path = typer.Option(
        Path("envwiki-tasks"),
        "--out",
        "-o",
        help="Where the finished task directories are written.",
    ),
    harness: str = typer.Option("pi", "--harness", help="Harness backend: pi or direct."),
    workspace: Path | None = typer.Option(
        None, "--workspace", "-w", help="Staging directory for the source material."
    ),
    base_url: str | None = typer.Option(None, "--base-url"),
    api_key: str | None = typer.Option(
        None, "--api-key", envvar="ENVWIKI_API_KEY", help="API key for the endpoint."
    ),
    model: str | None = typer.Option(None, "--model"),
    provider: str | None = typer.Option(None, "--provider"),
    org: str = typer.Option("envwiki", "--org", help="org/ prefix used in [task].name."),
    enable_docling: bool = typer.Option(False, "--enable-docling"),
    no_mcp: bool = typer.Option(
        False, "--no-mcp", help="Do not expose MCP servers to the harness."
    ),
    no_skills: bool = typer.Option(
        False, "--no-skills", help="Do not inject skills into the harness."
    ),
    no_envwiki_mcp: bool = typer.Option(
        False,
        "--no-envwiki-mcp",
        help="Do not expose the envwiki recipe server to the harness.",
    ),
    skill_dir: list[Path] = typer.Option(
        [], "--skill-dir", help="Extra skill directory to inject (repeatable)."
    ),
    allow_write_tools: bool = typer.Option(
        False,
        "--allow-write-tools",
        help="Let the harness run shell commands and write files. Off by default: "
        "the source material is untrusted.",
    ),
    register: bool = typer.Option(
        True, "--register/--no-register", help="Register the endpoint in pi's models.json."
    ),
    timeout: float = typer.Option(1800.0, "--timeout", help="Harness timeout in seconds."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Ingest only, do not call the model."),
) -> None:
    """Stage the material, let the agent build a task, validate what it wrote."""
    link_list = [link.strip() for link in (links or []) if link and link.strip()]
    upload_list = [Path(p).expanduser() for p in (upload or [])]
    if not link_list and not upload_list:
        typer.echo("nothing to do: pass a link or --upload", err=True)
        raise typer.Exit(2)

    endpoint = _endpoint(base_url, api_key, model, provider)
    config = EnvwikiConfig(endpoint=endpoint, harness=harness)
    if workspace is not None:
        config.workspace = workspace

    typer.echo("staging sources ...")
    bundle = build_bundle(link_list, upload_list, config.workspace, config.max_context_chars)
    for warning in bundle.warnings:
        typer.echo("warning: " + warning, err=True)
    if not bundle.sources:
        typer.echo("no sources were ingested", err=True)
        raise typer.Exit(2)
    typer.echo(
        "staged "
        + str(len(bundle.sources))
        + " source(s) in "
        + str(bundle.staging_dir)
    )
    if dry_run:
        typer.echo(bundle.tree)
        raise typer.Exit(0)

    if harness == "pi":
        agent = PiHarness(config, allow_write_tools=allow_write_tools)
        agent.prepare(
            bundle.staging_dir,
            enable_jina=not no_mcp,
            enable_docling=enable_docling,
            enable_skills=not no_skills,
            enable_envwiki=not no_envwiki_mcp,
            extra_skill_dirs=list(skill_dir or []),
        )
        if register:
            registration = register_provider(config.agent_dir, endpoint)
            typer.echo("model provider: " + registration.message)
    elif harness == "direct":
        agent = DirectHarness(config)
    else:
        typer.echo("unknown harness: " + harness, err=True)
        raise typer.Exit(2)

    prompt = build_user_prompt(
        bundle.digest, str(bundle.staging_dir), bundle.tree, org=org
    )
    typer.echo("running harness (" + harness + ") ...")
    result = agent.run(
        prompt,
        cwd=bundle.staging_dir,
        images=bundle.images,
        timeout=timeout,
        system_prompt=SYSTEM_PROMPT,
    )
    if not result.ok:
        typer.echo("harness failed: " + result.error, err=True)
        if result.text:
            typer.echo(result.text[:1500], err=True)
        raise typer.Exit(1)

    produced = discover_tasks(bundle.staging_dir)
    if not produced:
        typer.echo(
            "the agent wrote no task under " + str(bundle.staging_dir), err=True
        )
        typer.echo(
            "scaffold_task writes tasks/<name>/task.toml there; nothing was found",
            err=True,
        )
        if result.text:
            typer.echo(result.text[:1500], err=True)
        raise typer.Exit(1)

    failed = False
    for task_dir in produced:
        report = validate_task(task_dir)
        for issue in report.issues:
            typer.echo(issue.level + ": " + issue.message, err=(issue.level == "error"))
        published = publish_task(task_dir, out)
        typer.echo("task: " + str(published))
        typer.echo(
            "validation: "
            + ("ok" if report.ok else "failed")
            + " (schema source: "
            + report.schema_source
            + ")"
        )
        if not report.ok:
            failed = True

    typer.echo("staging dir: " + str(bundle.staging_dir))
    if failed:
        raise typer.Exit(1)


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
