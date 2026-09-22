import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
POWERSHELL = shutil.which("pwsh")


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    for name in ("dev", "dev.ps1", ".env.example", "docker-compose.yml"):
        shutil.copy2(ROOT / name, project / name)
    return project


def _fake_docker(tmp_path: Path, *, engine_available: bool = True) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    shell_script = bin_dir / "docker"
    shell_script.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$DEV_TEST_LOG\"\n"
        + ("exit 1\n" if not engine_available else "exit 0\n"),
        encoding="utf-8",
        newline="\n",
    )
    shell_script.chmod(shell_script.stat().st_mode | stat.S_IEXEC)
    cmd_script = bin_dir / "docker.cmd"
    cmd_script.write_text(
        "@echo off\r\n"
        "echo %*>>\"%DEV_TEST_LOG%\"\r\n"
        + ("exit /b 1\r\n" if not engine_available else "exit /b 0\r\n"),
        encoding="utf-8",
    )
    return bin_dir, log


def _environment(bin_dir: Path, log: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
    environment["DEV_TEST_LOG"] = log.as_posix()
    return environment


@pytest.mark.skipif(not GIT_BASH.exists(), reason="Git Bash is not installed")
def test_bash_apply_uses_cached_non_destructive_path_and_creates_env(tmp_path: Path) -> None:
    project = _project(tmp_path)
    bin_dir, log = _fake_docker(tmp_path)
    result = subprocess.run(
        [str(GIT_BASH), "./dev", "apply"],
        cwd=project,
        env=_environment(bin_dir, log),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    commands = log.read_text(encoding="utf-8")
    assert "compose up -d --build --remove-orphans" in commands
    assert "compose down" not in commands
    assert "--no-cache" not in commands
    assert "scripts.seed_demo_data" not in commands
    assert (project / ".env").read_text(encoding="utf-8") == (project / ".env.example").read_text(encoding="utf-8")


@pytest.mark.skipif(not GIT_BASH.exists(), reason="Git Bash is not installed")
def test_bash_clean_seed_runs_full_rebuild_in_order(tmp_path: Path) -> None:
    project = _project(tmp_path)
    bin_dir, log = _fake_docker(tmp_path)
    result = subprocess.run(
        [str(GIT_BASH), "./dev", "apply", "--clean", "--seed"],
        cwd=project,
        env=_environment(bin_dir, log),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    commands = log.read_text(encoding="utf-8")
    down = commands.index("compose down")
    build = commands.index("compose build --no-cache api worker inference web")
    up = commands.index("compose up -d --force-recreate")
    seed = commands.index("compose exec -T api python -m scripts.seed_demo_data")
    assert down < build < up < seed
    assert "down -v" not in commands


@pytest.mark.skipif(not POWERSHELL, reason="PowerShell is not installed")
def test_powershell_apply_preserves_existing_env(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / ".env").write_text("KEEP_ME=true\n", encoding="utf-8")
    bin_dir, log = _fake_docker(tmp_path)
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-File", str(project / "dev.ps1"), "apply"],
        cwd=project,
        env=_environment(bin_dir, log),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert (project / ".env").read_text(encoding="utf-8") == "KEEP_ME=true\n"
    commands = log.read_text(encoding="utf-8")
    assert "compose up -d --build --remove-orphans" in commands
    assert "compose down" not in commands


@pytest.mark.skipif(not GIT_BASH.exists(), reason="Git Bash is not installed")
def test_apply_explains_when_docker_engine_is_unavailable(tmp_path: Path) -> None:
    project = _project(tmp_path)
    bin_dir, log = _fake_docker(tmp_path, engine_available=False)
    result = subprocess.run(
        [str(GIT_BASH), "./dev", "apply"],
        cwd=project,
        env=_environment(bin_dir, log),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode != 0
    assert "Docker Desktop" in result.stdout + result.stderr
    assert "info" in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", ["dev", "dev.ps1"])
def test_unknown_command_fails_before_running_docker(tmp_path: Path, script: str) -> None:
    project = _project(tmp_path)
    if script == "dev":
        if not GIT_BASH.exists():
            pytest.skip("Git Bash is not installed")
        command = [str(GIT_BASH), "./dev", "unknown"]
    else:
        if not POWERSHELL:
            pytest.skip("PowerShell is not installed")
        command = [POWERSHELL, "-NoProfile", "-File", str(project / "dev.ps1"), "unknown"]
    result = subprocess.run(
        command,
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode != 0
    assert "unknown" in result.stdout + result.stderr
