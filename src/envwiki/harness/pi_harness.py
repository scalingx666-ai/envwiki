"""Pi as an envwiki harness.

Pi is a minimal, extensible agent harness that already speaks skills and MCP.
envwiki uses it to explore the staged source material and emit a task spec.

The staged material is untrusted (it can be any GitHub repository), so pi runs
with its host-modifying tools disabled by default: exploration is read-only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from envwiki.config import EnvwikiConfig, ModelEndpoint
from envwiki.harness.base import Harness, HarnessResult
from envwiki.skills import builtin_skill_dirs

#: Remote Jina Reader MCP server. read_url works without an API key.
JINA_MCP_URL = "https://mcp.jina.ai/v1"

#: Local Docling MCP server (document parsing). Heavy; opt-in.
DOCLING_MCP_COMMAND = "uvx"
DOCLING_MCP_ARGS = ["docling-mcp"]

#: Tools that can change the machine pi runs on.
WRITE_TOOLS = ("bash", "edit", "write", "multi_edit")


@dataclass(slots=True)
class RegistrationResult:
    changed: bool
    message: str
    path: str = ""


def _provider_entry(endpoint: ModelEndpoint) -> dict:
    return {
        "name": endpoint.provider,
        "api": "openai-completions",
        "baseUrl": endpoint.base_url,
        "apiKey": "$" + endpoint.api_key_env_var,
        "models": [
            {
                "id": endpoint.model,
                "name": endpoint.model,
                "api": "openai-completions",
                "reasoning": False,
                "input": ["text", "image"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": endpoint.context_window,
                "maxTokens": endpoint.max_tokens,
            }
        ],
    }


def register_provider(
    agent_dir: Path, endpoint: ModelEndpoint, *, dry_run: bool = False
) -> RegistrationResult:
    """Add (or refresh) the endpoint inside pi's models.json.

    The API key is written as an environment reference so the secret never
    lands in a config file.
    """
    path = agent_dir / "models.json"
    data: dict = {"providers": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"providers": {}}

    providers = data.setdefault("providers", {})
    desired = _provider_entry(endpoint)
    if providers.get(endpoint.provider) == desired:
        return RegistrationResult(
            False, "provider '" + endpoint.provider + "' already registered", str(path)
        )

    if dry_run:
        return RegistrationResult(True, "would register '" + endpoint.provider + "'", str(path))

    providers[endpoint.provider] = desired
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    return RegistrationResult(True, "registered provider '" + endpoint.provider + "'", str(path))


def build_mcp_config(
    *,
    enable_jina: bool = True,
    enable_docling: bool = False,
    enable_envwiki: bool = True,
    python_executable: str | None = None,
) -> dict:
    """MCP servers exposed to the harness while it explores.

    The envwiki server carries the synthesis recipe library: the harness
    calls it to choose a method before it writes the task.
    """
    servers: dict = {}
    if enable_jina:
        servers["jina-reader"] = {
            "type": "streamable-http",
            "url": JINA_MCP_URL,
            "description": "Read any web page or PDF as markdown via the Jina Reader.",
        }
    if enable_docling:
        servers["docling"] = {
            "command": DOCLING_MCP_COMMAND,
            "args": DOCLING_MCP_ARGS,
            "description": "Convert local documents (PDF, DOCX, HTML) into structured markdown.",
        }
    if enable_envwiki:
        servers["envwiki"] = {
            "command": python_executable or sys.executable,
            "args": ["-m", "envwiki.mcp_server"],
            "description": (
                "Environment and task synthesis recipes distilled from the literature. "
                "Use recommend_recipes to pick a method, get_recipe to read it."
            ),
        }
    return {"mcpServers": servers}


class PiHarness(Harness):
    """Drives the pi CLI in print mode."""

    name = "pi"

    def __init__(self, config: EnvwikiConfig, *, allow_write_tools: bool = False) -> None:
        super().__init__(config)
        self._bin: str | None = config.pi_bin
        self.allow_write_tools = allow_write_tools

    # -- setup ---------------------------------------------------------
    def _resolve_bin(self) -> str | None:
        if self._bin:
            return self._bin
        found = shutil.which("pi")
        if found:
            self._bin = found
        return found

    def prepare(
        self,
        cwd: Path,
        *,
        enable_jina: bool = True,
        enable_docling: bool = False,
        enable_skills: bool = True,
        enable_envwiki: bool = True,
        extra_skill_dirs: list[Path] | None = None,
    ) -> None:
        """Write project-level pi configuration into the staging directory."""
        pi_dir = cwd / ".pi"
        pi_dir.mkdir(parents=True, exist_ok=True)
        (pi_dir / "mcp.json").write_text(
            json.dumps(
                build_mcp_config(
                    enable_jina=enable_jina,
                    enable_docling=enable_docling,
                    enable_envwiki=enable_envwiki,
                ),
                indent=2,
            )
            + chr(10),
            encoding="utf-8",
        )
        if not enable_skills:
            return
        skills_root = pi_dir / "skills"
        for source in builtin_skill_dirs() + [Path(p) for p in (extra_skill_dirs or [])]:
            if not source.is_dir():
                continue
            shutil.copytree(source, skills_root / source.name, dirs_exist_ok=True)

    # -- execution -----------------------------------------------------
    def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        images: list[Path] | None = None,
        timeout: float = 900.0,
        system_prompt: str | None = None,
    ) -> HarnessResult:
        binary = self._resolve_bin()
        if not binary:
            return HarnessResult(
                "", False, "pi executable not found on PATH; install it or use --harness direct"
            )

        endpoint = self.config.endpoint
        cmd = [
            binary,
            "--provider",
            endpoint.provider,
            "--model",
            endpoint.model,
            "--print",
            "--no-session",
            "--approve",
            "--no-context-files",
        ]
        if system_prompt:
            cmd += ["--system-prompt", system_prompt]
        if not self.allow_write_tools:
            # pi takes one comma separated list, not repeated flags.
            cmd += ["--exclude-tools", ",".join(WRITE_TOOLS)]

        env = self.config.harness_env()
        env.setdefault("NO_COLOR", "1")
        # The envwiki MCP server writes into this workspace by default.
        env["ENVWIKI_STAGING_DIR"] = str(cwd)

        try:
            proc = subprocess.run(
                cmd + [prompt],
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout if isinstance(exc.stdout, str) else ""
            return HarnessResult(
                partial or "", False, "pi timed out after " + str(timeout) + "s", raw_output=partial
            )
        except FileNotFoundError:
            return HarnessResult("", False, "pi executable not found: " + str(binary))

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return HarnessResult(
                stdout,
                False,
                "pi exited " + str(proc.returncode) + ": " + (stderr[:500] or stdout[:200]),
                raw_output=stdout,
            )
        if not stdout:
            return HarnessResult(
                "", False, "pi produced no output; stderr: " + stderr[:500], raw_output=stderr
            )
        return HarnessResult(stdout, True, raw_output=stdout)
