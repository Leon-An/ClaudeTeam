from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "team.sh"


def _write_fake_claudeteam(bin_dir: Path) -> Path:
    fake = bin_dir / "claudeteam"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$PWD\" > \"$TEAM_TEST_LOG\"\n"
        "printf 'FEISHU_APP_ID=%s\\n' \"${FEISHU_APP_ID:-}\" >> \"$TEAM_TEST_LOG\"\n"
        "printf 'FEISHU_APP_SECRET=%s\\n' \"${FEISHU_APP_SECRET:-}\" >> \"$TEAM_TEST_LOG\"\n"
        "printf '%s\\n' \"$@\" >> \"$TEAM_TEST_LOG\"\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


def _run_script(team_dir: Path, *args: str) -> tuple[int, list[str], str, str]:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        log = tmp / "calls.log"
        _write_fake_claudeteam(bin_dir)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env["TEAM_TEST_LOG"] = str(log)
        proc = subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=team_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return proc.returncode, lines, proc.stdout, proc.stderr


def _run_script_with_fake_tmux(team_dir: Path, *args: str) -> tuple[int, list[str], str, str]:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fake_tmux = tmp / "tmux"
        log = tmp / "tmux.log"
        fake_tmux.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$@\" > \"$TEAM_TEST_TMUX_LOG\"\n",
            encoding="utf-8",
        )
        fake_tmux.chmod(0o755)
        env = os.environ.copy()
        env["CLAUDETEAM_TMUX_BIN"] = str(fake_tmux)
        env["TEAM_TEST_TMUX_LOG"] = str(log)
        proc = subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=team_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return proc.returncode, lines, proc.stdout, proc.stderr


def test_init_uses_directory_name_plus_team_as_default_session():
    with tempfile.TemporaryDirectory(prefix="YuanLiu", dir=ROOT.parent) as td:
        team_dir = Path(td)
        session = f"{team_dir.name}Team"

        rc, lines, _out, err = _run_script(team_dir, "init")

        assert rc == 0, err
        assert lines == [
            str(team_dir),
            "FEISHU_APP_ID=",
            "FEISHU_APP_SECRET=",
            "init",
            "--session",
            session,
            "--no-connect",
        ]
        assert (team_dir / ".env").exists()
        env_text = (team_dir / ".env").read_text(encoding="utf-8")
        assert "FEISHU_APP_ID=cli_xxxxxxxxxxxxxxx" in env_text
        assert "FEISHU_APP_SECRET=" in env_text
        assert "FEISHU_TENANT=feishu" in env_text


def test_init_keeps_explicit_session_args():
    with tempfile.TemporaryDirectory(prefix="YuanLiu", dir=ROOT.parent) as td:
        team_dir = Path(td)

        rc, lines, _out, err = _run_script(team_dir, "init", "--session", "CustomTeam")

        assert rc == 0, err
        assert lines == [
            str(team_dir),
            "FEISHU_APP_ID=",
            "FEISHU_APP_SECRET=",
            "init",
            "--session",
            "CustomTeam",
        ]


def test_tmux_attaches_to_default_session():
    with tempfile.TemporaryDirectory(prefix="YuanLiu", dir=ROOT.parent) as td:
        team_dir = Path(td)
        session = f"{team_dir.name}Team"

        rc, lines, out, err = _run_script_with_fake_tmux(team_dir, "tmux")

        assert rc == 0, err
        assert f"tmux attach -t {session}" in out
        assert lines == ["attach", "-t", session]


def test_forwarded_commands_run_in_team_directory():
    with tempfile.TemporaryDirectory(prefix="YuanLiu", dir=ROOT.parent) as td:
        team_dir = Path(td)

        rc, lines, _out, err = _run_script(team_dir, "health", "--json")

        assert rc == 0, err
        assert lines == [
            str(team_dir),
            "FEISHU_APP_ID=",
            "FEISHU_APP_SECRET=",
            "health",
            "--json",
        ]


def test_env_file_is_loaded_before_forwarding_commands():
    with tempfile.TemporaryDirectory(prefix="YuanLiu", dir=ROOT.parent) as td:
        team_dir = Path(td)
        (team_dir / ".env").write_text(
            "FEISHU_APP_ID=cli_existing\n"
            "FEISHU_APP_SECRET=secret_existing\n",
            encoding="utf-8",
        )

        rc, lines, _out, err = _run_script(team_dir, "health")

        assert rc == 0, err
        assert lines == [
            str(team_dir),
            "FEISHU_APP_ID=cli_existing",
            "FEISHU_APP_SECRET=secret_existing",
            "health",
        ]
