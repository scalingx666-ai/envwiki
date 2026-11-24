"""Tests for the execution-level gate and the Harbor execution contract.

The contract under test is Harbor's: one script per directory, uploaded
alone, and a task that has never been run has never been checked.
"""

from __future__ import annotations

import json
from pathlib import Path

from envwiki.convert.builder import (
    render_solution_entry,
    render_verifier_entry,
    write_task,
)
from envwiki.convert.gate import gate_task, repair_reward
from envwiki.convert.validate import validate_task
from envwiki.schemas import (
    EnvironmentSpec,
    Provenance,
    SolutionSpec,
    TaskDraft,
    TaskMetadata,
    VerifierSpec,
)

BASH_VERIFIER = (
    "#!/bin/bash" + chr(10)
    + "mkdir -p /logs/verifier" + chr(10)
    + "echo 1 > /logs/verifier/reward.txt" + chr(10)
    + "test -f /app/out.txt" + chr(10)
)


def _draft(**overrides) -> TaskDraft:
    data = dict(
        name="demo-task",
        description="A demo task.",
        metadata=TaskMetadata(category="demo", tags=["x"]),
        instruction_md="Do the thing.",
        environment=EnvironmentSpec(base_image="ubuntu:24.04", workdir="/app"),
        verifier=VerifierSpec(language="bash", code=BASH_VERIFIER),
        solution=SolutionSpec(
            language="bash", code="#!/bin/bash" + chr(10) + "echo hi > /app/out.txt" + chr(10)
        ),
    )
    data.update(overrides)
    return TaskDraft(**data)


# ---------------------------------------------------------------- contract


def test_verifier_is_written_as_the_entry_point_harbor_runs(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    assert (task_dir / "tests" / "test.sh").is_file()
    assert not (task_dir / "tests" / "test.py").exists()


def test_solution_is_written_as_the_entry_point_harbor_runs(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    assert (task_dir / "solution" / "solve.sh").is_file()
    assert not (task_dir / "solution" / "solve.py").exists()


def test_a_python_verifier_travels_inside_the_entry_point(tmp_path: Path):
    """Harbor uploads one file per directory, so a second file is invisible."""
    draft = _draft(
        verifier=VerifierSpec(
            language="python",
            code="print('checking')" + chr(10) + "open('/logs/verifier/reward.txt','w').write('1')",
        )
    )
    task_dir = write_task(draft, tmp_path / "task")
    entry = (task_dir / "tests" / "test.sh").read_text(encoding="utf-8")
    assert "ENVWIKI_PYTHON_VERIFIER" in entry
    assert "checking" in entry
    assert len(list((task_dir / "tests").iterdir())) == 1


def test_a_python_solution_travels_inside_the_entry_point(tmp_path: Path):
    draft = _draft(
        solution=SolutionSpec(
            language="python",
            code="open('/app/out.txt','w').write('hi')",
        )
    )
    task_dir = write_task(draft, tmp_path / "task")
    entry = (task_dir / "solution" / "solve.sh").read_text(encoding="utf-8")
    assert "ENVWIKI_PYTHON_SOLUTION" in entry
    assert "out.txt" in entry


def test_a_verifier_without_test_sh_is_reported(tmp_path: Path):
    """The defect the execution gate found in the shipped example task."""
    task_dir = write_task(_draft(), tmp_path / "task")
    (task_dir / "tests" / "test.sh").unlink()
    (task_dir / "tests" / "test.py").write_text("print('x')", encoding="utf-8")
    report = validate_task(task_dir)
    assert not report.ok
    assert any("test.sh" in issue.message for issue in report.errors)


def test_entry_helpers_keep_a_shebang():
    assert render_verifier_entry("echo hi", "bash").startswith("#!/bin/bash")
    assert render_solution_entry("echo hi", "bash").startswith("#!/bin/bash")


# ---------------------------------------------------------------- metadata


def test_difficulty_is_unrated_until_it_is_measured(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    toml_text = (task_dir / "task.toml").read_text(encoding="utf-8")
    assert 'difficulty = "unrated"' in toml_text


def test_provenance_pins_the_upstream(tmp_path: Path):
    draft = _draft(
        metadata=TaskMetadata(
            category="demo",
            provenance=Provenance(
                upstream_repo="https://github.com/pallets/click",
                upstream_commit="abc123",
                upstream_license="BSD-3-Clause",
            ),
        )
    )
    task_dir = write_task(draft, tmp_path / "task")
    toml_text = (task_dir / "task.toml").read_text(encoding="utf-8")
    assert "[metadata.provenance]" in toml_text
    assert 'upstream_commit = "abc123"' in toml_text
    assert 'upstream_license = "BSD-3-Clause"' in toml_text


def test_a_repo_without_a_commit_is_flagged(tmp_path: Path):
    draft = _draft(
        metadata=TaskMetadata(
            category="demo",
            provenance=Provenance(upstream_repo="https://github.com/pallets/click"),
        )
    )
    task_dir = write_task(draft, tmp_path / "task")
    report = validate_task(task_dir)
    assert any("pin the commit" in issue.message for issue in report.warnings)


def test_measured_facts_are_written_when_there_are_any(tmp_path: Path):
    draft = _draft()
    draft.metadata.difficulty_facts = {
        "container_floor": 0.0,
        "checks_count": 2,
        "instruction_disclosure": "clean",
    }
    task_dir = write_task(draft, tmp_path / "task")
    toml_text = (task_dir / "task.toml").read_text(encoding="utf-8")
    assert "[metadata.difficulty_facts]" in toml_text
    assert "container_floor = 0.0" in toml_text
    assert "checks_count = 2" in toml_text


def test_reward_floor_is_recorded(tmp_path: Path):
    draft = _draft()
    draft.reward_floor = 0.2
    task_dir = write_task(draft, tmp_path / "task")
    toml_text = (task_dir / "task.toml").read_text(encoding="utf-8")
    assert "reward_floor = 0.2" in toml_text
    meta = json.loads((task_dir / "envwiki.json").read_text(encoding="utf-8"))
    assert meta["reward_floor"] == 0.2


# ---------------------------------------------------------------- the gate


def test_the_reward_is_read_from_the_harbor_result_shape():
    """Harbor groups the trials by the reward they earned."""
    from envwiki.convert.gate import _job_reward

    result = {
        "stats": {
            "evals": {
                "oracle__adhoc": {
                    "reward_stats": {"reward": {"1.0": ["trial-a", "trial-b"]}},
                }
            }
        }
    }
    assert _job_reward(result) == 1.0


def test_a_result_without_a_reward_reads_as_none():
    from envwiki.convert.gate import _job_reward

    assert _job_reward({"stats": {"evals": {}}}) is None
    assert _job_reward({}) is None
    assert _job_reward(None) is None


def test_the_reward_of_several_trials_is_their_mean():
    from envwiki.convert.gate import _job_reward

    result = {
        "stats": {
            "evals": {
                "oracle__adhoc": {
                    "reward_stats": {"reward": {"1.0": ["a"], "0.0": ["b", "c"]}},
                }
            }
        }
    }
    assert abs(_job_reward(result) - (1.0 / 3.0)) < 1e-9


def test_the_gate_reports_a_missing_task():
    report = gate_task(Path("/nonexistent/envwiki-task"))
    assert not report.ok
    assert not report.verified
    assert report.errors


def test_the_gate_checks_the_verifier_entry_point(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    report = gate_task(task_dir, run_oracle=False, run_baseline=False)
    check = report.check("verifier_entrypoint")
    assert check is not None
    assert check.status == "pass"


def test_the_gate_flags_a_missing_verifier_entry_point(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    (task_dir / "tests" / "test.sh").unlink()
    report = gate_task(task_dir, run_oracle=False, run_baseline=False)
    check = report.check("verifier_entrypoint")
    assert check is not None
    assert check.status == "fail"
    assert not report.ok


def test_the_gate_flags_an_instruction_that_hands_out_the_answer(tmp_path: Path):
    draft = _draft()
    draft.instruction_md = (
        "Do the thing." + chr(10) + "run exactly: echo hi > /app/out.txt" + chr(10)
    )
    task_dir = write_task(draft, tmp_path / "task")
    report = gate_task(task_dir, run_oracle=False, run_baseline=False)
    check = report.check("instruction_disclosure")
    assert check is not None
    assert check.status == "fail"


def test_the_gate_says_so_when_it_cannot_run(tmp_path: Path):
    """A gate that cannot run is not a pass, and it says which part is missing."""
    task_dir = write_task(_draft(), tmp_path / "task")
    report = gate_task(task_dir)
    if not report.executed:
        assert not report.verified
        assert report.errors
        assert any(
            "harbor" in issue.lower() or "docker" in issue.lower()
            for issue in report.errors
        )


# ---------------------------------------------------------------- end to end


def test_the_gate_runs_a_real_task(tmp_path: Path):
    """The gate against a task that Harbor really runs.

    It needs Harbor and a Docker daemon, so it is skipped when either is
    missing rather than failing: the gate has to work on a machine that
    cannot build containers, and that is a different situation from a
    broken task.
    """
    import pytest

    from envwiki.convert.gate import docker_available, harbor_available

    if not harbor_available() or not docker_available():
        pytest.skip("harbor or docker is not available here")

    draft = _draft(
        instruction_md="Write /app/out.txt containing the word hello.",
        environment=EnvironmentSpec(
            base_image="ubuntu:24.04", workdir="/app", setup_commands=[]
        ),
        verifier=VerifierSpec(
            language="bash",
            code=(
                "#!/bin/bash" + chr(10)
                + "mkdir -p /logs/verifier" + chr(10)
                + "echo 0 > /logs/verifier/reward.txt" + chr(10)
                + "grep -q hello /app/out.txt && echo 1 > /logs/verifier/reward.txt" + chr(10)
            ),
        ),
        solution=SolutionSpec(
            language="bash",
            code=(
                "#!/bin/bash" + chr(10)
                + "mkdir -p /app" + chr(10)
                + "echo hello > /app/out.txt" + chr(10)
            ),
        ),
    )
    task_dir = write_task(draft, tmp_path / "task")
    report = gate_task(task_dir, timeout_sec=900)
    assert report.verified, report.errors
    assert report.reward == 1.0
    assert report.floor == 0.0


# ---------------------------------------------------------------- the math


def test_the_repair_reward_is_measured_above_the_floor():
    # A floor of 0.2 leaves 0.8 of the reward space; 0.45 of it is 0.3125.
    assert abs(repair_reward(0.45, 0.2) - 0.3125) < 1e-9


def test_the_repair_reward_never_goes_below_zero():
    assert repair_reward(0.1, 0.2) == 0.0


def test_the_repair_reward_never_goes_above_one():
    assert repair_reward(1.0, 0.0) == 1.0


def test_a_floor_of_one_leaves_no_reward_space():
    assert repair_reward(1.0, 1.0) == 0.0
