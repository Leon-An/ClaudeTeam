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


def _run_script_file(script: Path, team_dir: Path, env: dict[str, str],
                     *args: str) -> tuple[int, list[str], str, str]:
    proc = subprocess.run(
        ["bash", str(script), *args],
        cwd=team_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    log = Path(env["TEAM_TEST_LOG"])
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc.returncode, lines, proc.stdout, proc.stderr


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
        env["CLAUDETEAM_TEAM_SH_IGNORE_VENV"] = "1"
        return _run_script_file(SCRIPT, team_dir, env, *args)


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
        assert "ANTHROPIC_BASE_URL=" in env_text
        assert "ANTHROPIC_AUTH_TOKEN=" in env_text
        assert "ANTHROPIC_MODEL=" in env_text


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


def test_copied_script_anchors_commands_to_script_directory_from_any_cwd():
    with tempfile.TemporaryDirectory(prefix="TeamRoot") as td:
        root = Path(td)
        source = root / "ClaudeTeam"
        team_dir = root / "YuanLiu"
        other_dir = root / "SomewhereElse"
        fake_bin = root / "fake-bin"
        (source / "src" / "claudeteam").mkdir(parents=True)
        team_dir.mkdir()
        other_dir.mkdir()
        fake_bin.mkdir()
        (source / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        script = team_dir / "team.sh"
        script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o755)

        fake = fake_bin / "claudeteam"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'pwd=%s\\n' \"$PWD\" > \"$TEAM_TEST_LOG\"\n"
            "printf 'config=%s\\n' \"${CLAUDETEAM_CONFIG_FILE:-}\" >> \"$TEAM_TEST_LOG\"\n"
            "printf 'state=%s\\n' \"${CLAUDETEAM_STATE_DIR:-}\" >> \"$TEAM_TEST_LOG\"\n"
            "printf '%s\\n' \"$@\" >> \"$TEAM_TEST_LOG\"\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)

        log = root / "calls.log"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}{os.pathsep}/usr/bin:/bin"
        env["TEAM_TEST_LOG"] = str(log)
        env["CLAUDETEAM_TEAM_SH_IGNORE_VENV"] = "1"

        rc, lines, _out, err = _run_script_file(script, other_dir, env, "health")

        assert rc == 0, err
        assert lines == [
            f"pwd={team_dir.resolve()}",
            f"config={team_dir.resolve() / 'claudeteam.toml'}",
            f"state={team_dir.resolve() / 'state'}",
            "health",
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


def test_adjacent_venv_claudeteam_is_preferred_when_available():
    with tempfile.TemporaryDirectory(prefix="TeamRoot") as td:
        root = Path(td)
        source = root / "ClaudeTeam"
        team_dir = root / "YuanLiu"
        venv_bin = source / ".venv" / "bin"
        (source / "src" / "claudeteam").mkdir(parents=True)
        venv_bin.mkdir(parents=True)
        team_dir.mkdir()
        (source / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        script = source / "team.sh"
        script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o755)

        fake = venv_bin / "claudeteam"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$PWD\" > \"$TEAM_TEST_LOG\"\n"
            "case \"$PATH\" in\n"
            "  *\"$TEAM_EXPECTED_VENV_BIN\"*) printf 'VENV_ON_PATH=yes\\n' >> \"$TEAM_TEST_LOG\" ;;\n"
            "  *) printf 'VENV_ON_PATH=no\\n' >> \"$TEAM_TEST_LOG\" ;;\n"
            "esac\n"
            "printf '%s\\n' \"$@\" >> \"$TEAM_TEST_LOG\"\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)

        log = root / "calls.log"
        env = os.environ.copy()
        env["PATH"] = "/usr/bin:/bin"
        env["TEAM_TEST_LOG"] = str(log)
        env["TEAM_EXPECTED_VENV_BIN"] = str(venv_bin)

        rc, lines, _out, err = _run_script_file(script, team_dir, env, "health")

        assert rc == 0, err
        assert lines == [str(team_dir.resolve()), "VENV_ON_PATH=yes", "health"]


def test_init_creates_adjacent_venv_when_missing():
    with tempfile.TemporaryDirectory(prefix="TeamRoot") as td:
        root = Path(td)
        source = root / "ClaudeTeam"
        team_dir = root / "YuanLiu"
        fake_bin = root / "fake-bin"
        venv_bin = source / ".venv" / "bin"
        (source / "src" / "claudeteam").mkdir(parents=True)
        team_dir.mkdir()
        fake_bin.mkdir()
        (source / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        script = source / "team.sh"
        script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o755)

        fake_python3 = fake_bin / "python3"
        fake_python3.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'python3 %s\\n' \"$*\" >> \"$TEAM_TEST_LOG\"\n"
            "if [ \"$1\" = \"-m\" ] && [ \"$2\" = \"venv\" ]; then\n"
            "  mkdir -p \"$3/bin\"\n"
            "  cat > \"$3/bin/python\" <<'PY'\n"
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$PWD\" >> \"$TEAM_TEST_LOG\"\n"
            "printf 'venv-python %s\\n' \"$*\" >> \"$TEAM_TEST_LOG\"\n"
            "PY\n"
            "  chmod +x \"$3/bin/python\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 99\n",
            encoding="utf-8",
        )
        fake_python3.chmod(0o755)

        log = root / "calls.log"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}{os.pathsep}/usr/bin:/bin"
        env["TEAM_TEST_LOG"] = str(log)

        rc, lines, out, err = _run_script_file(script, team_dir, env, "init")

        assert rc == 0, err
        assert any(line.startswith("python3 -m venv ") for line in lines), lines
        assert "venv-python -m claudeteam.cli init --session YuanLiuTeam --no-connect" in lines
        assert str(team_dir.resolve()) in lines, lines
        assert (venv_bin / "claudeteam").exists()
        assert "created ClaudeTeam venv" in out


def test_init_installs_feishu_channel_deps_when_missing():
    with tempfile.TemporaryDirectory(prefix="TeamRoot") as td:
        root = Path(td)
        source = root / "ClaudeTeam"
        team_dir = root / "YuanLiu"
        fake_bin = root / "fake-bin"
        sidecar_dir = source / "scripts" / "feishu_channel"
        (source / "src" / "claudeteam").mkdir(parents=True)
        sidecar_dir.mkdir(parents=True)
        team_dir.mkdir()
        fake_bin.mkdir()
        (source / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (sidecar_dir / "package.json").write_text('{"dependencies": {}}\n', encoding="utf-8")
        script = source / "team.sh"
        script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o755)

        _write_fake_claudeteam(fake_bin)
        fake_npm = fake_bin / "npm"
        fake_npm.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'npm-cwd=%s\\n' \"$PWD\" >> \"$TEAM_TEST_NPM_LOG\"\n"
            "printf 'npm %s\\n' \"$*\" >> \"$TEAM_TEST_NPM_LOG\"\n"
            "if [ \"$1\" = \"install\" ]; then\n"
            "  mkdir -p node_modules/@larksuite/channel\n"
            "  exit 0\n"
            "fi\n"
            "exit 99\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)

        log = root / "calls.log"
        npm_log = root / "npm.log"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}{os.pathsep}/usr/bin:/bin"
        env["TEAM_TEST_LOG"] = str(log)
        env["TEAM_TEST_NPM_LOG"] = str(npm_log)
        env["CLAUDETEAM_TEAM_SH_IGNORE_VENV"] = "1"

        rc, lines, out, err = _run_script_file(script, team_dir, env, "init")
        npm_lines = npm_log.read_text(encoding="utf-8").splitlines()

        assert rc == 0, err
        assert f"npm-cwd={sidecar_dir.resolve()}" in npm_lines
        assert "npm install --omit=dev --no-fund --no-audit" in npm_lines
        assert (sidecar_dir / "node_modules" / "@larksuite" / "channel").exists()
        assert lines[-4:] == ["init", "--session", "YuanLiuTeam", "--no-connect"]
        assert "installing Feishu channel deps" in out
