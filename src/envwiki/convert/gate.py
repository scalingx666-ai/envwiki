"""The execution-level gate a task has to pass before it counts.

ScienceIDE's most transferable idea: a task is not done when it parses.
It is done when it has been run. The reference solution has to earn the
full reward, the broken baseline has to leave reward space to compete
for, and the agent must not be able to read the answer out of the image.

This module runs that gate against a task directory using Harbor itself,
so the thing being checked is the same thing that will be graded later.

Every check reports what it measured. A gate that cannot run says so
instead of quietly passing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

NL = chr(10)

#: How long a single gate run may take.
DEFAULT_TIMEOUT_SEC = 1800.0


@dataclass
class GateCheck:
    """One measured condition of the gate."""

    name: str
    status: str  # "pass" | "fail" | "skip"
    detail: str = ""
    measured: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"pass", "skip"}


@dataclass
class GateReport:
    """What the gate measured about one task."""

    task_dir: str
    checks: list[GateCheck] = field(default_factory=list)
    executed: bool = False
    reward: float | None = None
    floor: float | None = None
    reward_repair: float | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when nothing failed.

        A gate that could not run is not a pass: the executed flag says
        whether the checks really happened.
        """
        return not self.errors

    @property
    def verified(self) -> bool:
        """True when the gate really executed the task."""
        return self.executed and not self.errors

    def check(self, name: str) -> GateCheck | None:
        for item in self.checks:
            if item.name == name:
                return item
        return None


def _harbor_binary() -> str | None:
    """The Harbor CLI, if it is on PATH."""
    return shutil.which("harbor")


def harbor_available() -> bool:
    """Whether the execution gate can run at all on this machine."""
    return _harbor_binary() is not None


def docker_available() -> bool:
    """Whether a Docker daemon answers."""
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _job_config(task_dir: Path, jobs_dir: Path, job_name: str, agent: str) -> str:
    """A Harbor job config that runs one local task with one agent."""
    return (
        "job_name: " + job_name + NL
        + "jobs_dir: " + str(jobs_dir) + NL
        + "n_concurrent_trials: 1" + NL
        + "tasks:" + NL
        + "  - path: " + str(task_dir) + NL
        + "agents:" + NL
        + "  - name: " + agent + NL
    )


def _run_job(
    task_dir: Path,
    workdir: Path,
    agent: str,
    label: str,
    timeout_sec: float,
) -> tuple[float | None, str, str]:
    """Run one Harbor agent over the task and read back the reward.

    Returns (reward, verifier stdout, error text). The reward is None
    when the run did not produce one.
    """
    harbor = _harbor_binary()
    if harbor is None:
        return None, "", "the harbor CLI is not on PATH"

    jobs_dir = workdir / "jobs"
    config_path = workdir / (label + ".yaml")
    config_path.write_text(
        _job_config(task_dir, jobs_dir, label, agent), encoding="utf-8"
    )

    try:
        proc = subprocess.run(
            [harbor, "job", "start", "-c", str(config_path)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "", "the run timed out after " + str(int(timeout_sec)) + "s"
    except OSError as exc:
        return None, "", "could not start the run: " + str(exc)

    reward, stdout = _read_reward(jobs_dir / label)
    if reward is None:
        detail = (proc.stderr or proc.stdout or "").strip()
        return None, stdout, detail[-800:] or "the run produced no reward"
    return reward, stdout, ""


def _read_reward(job_dir: Path) -> tuple[float | None, str]:
    """Read the reward and the verifier output of a finished Harbor job.

    Harbor's job result keeps the reward under
    stats.evals.<agent>.reward_stats.reward, keyed by the reward value
    and listing the trials that earned it. The mean of the per-trial
    rewards is what the gate compares against.
    """
    result_path = job_dir / "result.json"
    if not result_path.is_file():
        return None, ""
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ""

    reward = _job_reward(data)
    stdout = _verifier_output(job_dir)
    if reward is None:
        return None, stdout
    return reward, stdout


def _job_reward(data: object) -> float | None:
    """The mean reward of a Harbor job result, if it has one."""
    if not isinstance(data, dict):
        return None
    stats = data.get("stats")
    if not isinstance(stats, dict):
        return None
    evals = stats.get("evals")
    if not isinstance(evals, dict):
        return None

    values: list[float] = []
    for entry in evals.values():
        if not isinstance(entry, dict):
            continue
        stats_block = entry.get("reward_stats")
        if not isinstance(stats_block, dict):
            continue
        for key, buckets in stats_block.items():
            if key != "reward" or not isinstance(buckets, dict):
                continue
            # Harbor groups the trials by the reward they earned, so the
            # key is the value and the list holds the trial names.
            for value, trials in buckets.items():
                if not isinstance(trials, list) or not trials:
                    continue
                try:
                    score = float(value)
                except (TypeError, ValueError):
                    continue
                values.extend([score] * len(trials))
    if not values:
        return None
    return sum(values) / len(values)


def _verifier_output(job_dir: Path) -> str:
    """The verifier's own output, which is what explains a failed run."""
    for trial in sorted(job_dir.glob("*")):
        candidate = trial / "verifier" / "test-stdout.txt"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="replace")
    return ""


def _static_checks(task_dir: Path, report: GateReport) -> None:
    """The checks that do not need a container."""
    instruction = task_dir / "instruction.md"
    if instruction.is_file():
        text = instruction.read_text(encoding="utf-8", errors="replace")
        leak = _answer_leak(text, task_dir)
        if leak:
            report.checks.append(
                GateCheck(
                    name="instruction_disclosure",
                    status="fail",
                    detail="the instruction discloses the answer: " + leak,
                )
            )
            report.errors.append(
                "the instruction discloses the answer: " + leak
            )
        else:
            report.checks.append(
                GateCheck(
                    name="instruction_disclosure",
                    status="pass",
                    detail="the instruction does not contain the solution",
                )
            )
    else:
        report.checks.append(
            GateCheck(
                name="instruction_disclosure",
                status="skip",
                detail="no instruction.md to inspect",
            )
        )

    verifier = task_dir / "tests" / "test.sh"
    if verifier.is_file():
        report.checks.append(
            GateCheck(
                name="verifier_entrypoint",
                status="pass",
                detail="tests/test.sh is present, the entry point Harbor runs",
            )
        )
    else:
        report.checks.append(
            GateCheck(
                name="verifier_entrypoint",
                status="fail",
                detail=(
                    "tests/test.sh is missing: Harbor discovers and uploads only "
                    "tests/test.sh, so a task without it is never verified"
                ),
            )
        )
        report.errors.append(
            "tests/test.sh is missing: Harbor only discovers tests/test.sh, so "
            "this task would never be verified"
        )


def _answer_leak(instruction: str, task_dir: Path) -> str:
    """Does the instruction hand the solution to the agent?

    The check is deliberately literal: a distinctive line of the reference
    solution appearing in the instruction is a disclosure. It is a
    conservative check, not a proof: it catches the easy mistakes, and it
    never guesses.
    """
    solution_dir = task_dir / "solution"
    if not solution_dir.is_dir():
        return ""
    for path in sorted(solution_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in body.splitlines():
            line = raw.strip()
            if len(line) < 16 or line.startswith("#"):
                continue
            if line.startswith("ENVWIKI_PYTHON"):
                continue
            if line in instruction:
                return "a line of the reference solution appears verbatim"
    return ""


def gate_task(
    task_dir: Path,
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    run_oracle: bool = True,
    run_baseline: bool = True,
) -> GateReport:
    """Run the execution-level gate over a task directory.

    The oracle run has to earn the full reward; the baseline run has to
    earn less, otherwise the task hands out its reward for free. The
    reward space between them is the reward an agent has to compete for.
    """
    task_dir = Path(task_dir).expanduser().resolve()
    report = GateReport(task_dir=str(task_dir))

    if not task_dir.is_dir():
        report.errors.append("task directory does not exist: " + str(task_dir))
        return report

    _static_checks(task_dir, report)

    if not run_oracle and not run_baseline:
        report.notes.append("no execution was requested")
        return report

    if not harbor_available():
        report.errors.append(
            "the harbor CLI is not on PATH, so the task could not be executed"
        )
        report.checks.append(
            GateCheck(
                name="execution",
                status="skip",
                detail="harbor is not installed",
            )
        )
        return report

    if not docker_available():
        report.errors.append(
            "no Docker daemon is running, so the task could not be executed"
        )
        report.checks.append(
            GateCheck(
                name="execution",
                status="skip",
                detail="docker is not available",
            )
        )
        return report

    with tempfile.TemporaryDirectory(prefix="envwiki-gate-") as tmp:
        workdir = Path(tmp)

        if run_oracle:
            reward, stdout, error = _run_job(
                task_dir, workdir, "oracle", "oracle", timeout_sec
            )
            if error:
                report.errors.append("the oracle run failed: " + error)
                report.checks.append(
                    GateCheck(
                        name="oracle",
                        status="fail",
                        detail=error,
                        measured={"verifier_output": stdout},
                    )
                )
            else:
                report.reward = reward
                status = "pass" if reward is not None and reward >= 1.0 else "fail"
                detail = (
                    "the reference solution earned the full reward"
                    if status == "pass"
                    else "the reference solution did not earn the full reward"
                )
                report.checks.append(
                    GateCheck(
                        name="oracle",
                        status=status,
                        detail=detail,
                        measured={"reward": reward, "verifier_output": stdout},
                    )
                )
                if status == "fail":
                    report.errors.append(
                        "the reference solution must earn reward 1.0, got "
                        + str(reward)
                    )

        if run_baseline:
            floor, stdout, error = _run_job(
                task_dir, workdir, "nop", "baseline", timeout_sec
            )
            if error:
                report.warnings.append("the baseline run failed: " + error)
                report.checks.append(
                    GateCheck(
                        name="baseline",
                        status="skip",
                        detail=error,
                        measured={"verifier_output": stdout},
                    )
                )
            else:
                report.floor = floor
                status = "pass" if floor is not None and floor < 1.0 else "fail"
                detail = (
                    "an agent that does nothing earns less than the full reward"
                    if status == "pass"
                    else "an agent that does nothing already earns the full reward"
                )
                report.checks.append(
                    GateCheck(
                        name="baseline",
                        status=status,
                        detail=detail,
                        measured={"floor": floor, "verifier_output": stdout},
                    )
                )
                if status == "fail":
                    report.errors.append(
                        "the task must leave reward space: doing nothing already "
                        "earns the full reward"
                    )

        if report.reward is not None and report.floor is not None:
            report.reward_repair = repair_reward(report.reward, report.floor)
            report.checks.append(
                GateCheck(
                    name="reward_space",
                    status="pass",
                    detail="the reward an agent competes for, above the floor",
                    measured={
                        "reward": report.reward,
                        "floor": report.floor,
                        "reward_repair": report.reward_repair,
                    },
                )
            )

    report.executed = True
    return report


def repair_reward(reward: float, floor: float) -> float:
    """The reward above the floor, normalised to the space that is left.

    A task whose unfixed build already earns 0.2 leaves 0.8 of the reward
    space to compete for; a reward of 0.45 is then 0.31 of that space.
    """
    if floor >= 1.0:
        return 0.0
    value = (reward - floor) / (1.0 - floor)
    return max(0.0, min(1.0, value))
