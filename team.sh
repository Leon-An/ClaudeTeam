#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_PATH" ]; do
  SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd)"
  SCRIPT_PATH="$(readlink "$SCRIPT_PATH")"
  case "$SCRIPT_PATH" in
    /*) ;;
    *) SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_PATH" ;;
  esac
done
SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd)"

# When this file lives in ClaudeTeam itself it acts as a template and can be
# run from a sibling team directory. Once copied into a team directory, anchor
# all operations to the script's own directory so calls from any cwd stay on
# the right claudeteam.toml/state pair.
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && [ -d "$SCRIPT_DIR/src/claudeteam" ]; then
  TEAM_DIR="$(pwd)"
else
  TEAM_DIR="$SCRIPT_DIR"
fi
TEAM_DIR="$(cd -P "$TEAM_DIR" >/dev/null 2>&1 && pwd)"
TEAM_NAME="$(basename "$TEAM_DIR")"
DEFAULT_SESSION="${TEAM_NAME}Team"
export CLAUDETEAM_CONFIG_FILE="$TEAM_DIR/claudeteam.toml"
export CLAUDETEAM_STATE_DIR="$TEAM_DIR/state"
cd "$TEAM_DIR"

usage() {
  cat <<EOF
usage: ./team.sh <command> [args...]

Copy this file into a new team directory beside ClaudeTeam, then run it there
or call it by absolute path; it anchors to its own team directory.

Common:
  init [args...]           claudeteam init --session ${DEFAULT_SESSION} --no-connect, prepare Feishu deps + .env
  connect [args...]        claudeteam feishu connect
  hooks [args...]          claudeteam install-hooks
  up [args...]             claudeteam up
  start [args...]          claudeteam start
  down [args...]           claudeteam down
  restart [args...]        claudeteam restart
  health [args...]         claudeteam health
  tmux [session]           attach tmux session, default: ${DEFAULT_SESSION}
  status|log|team|usage    forwarded to claudeteam

Ops:
  cmd <args...>            run any claudeteam command verbatim
  session                  print default tmux session name
  doctor                   check nearby ClaudeTeam + claudeteam + tmux
  copy-to <dir>            copy this script to another team directory

Examples:
  ./team.sh init
  ./team.sh connect --quick
  ./team.sh up
  ./team.sh tmux
  ./team.sh health
  ./team.sh cmd send manager user "hello"
EOF
}

load_env_file() {
  local env_file="$TEAM_DIR/.env"
  if [ ! -f "$env_file" ]; then
    return 0
  fi
  set -a
  # shellcheck disable=SC1090
  . "$env_file"
  set +a
}

ensure_env_template() {
  local env_file="$TEAM_DIR/.env"
  if [ -e "$env_file" ]; then
    return 0
  fi
  umask 077
  cat >"$env_file" <<EOF
# Optional existing Feishu/Lark bot credentials for this team.
# Fill these when you already have a bot. If left blank, run:
#   ./team.sh connect --quick
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxx
FEISHU_APP_SECRET=
FEISHU_TENANT=feishu

# Optional Claude Code provider overrides for this team.
# Leave blank to inherit your normal Claude Code/ccswitch settings on restart.
# Fill these to pin this team to a specific Anthropic-compatible endpoint.
ANTHROPIC_BASE_URL=
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_MODEL=
ANTHROPIC_DEFAULT_OPUS_MODEL=
ANTHROPIC_DEFAULT_SONNET_MODEL=
ANTHROPIC_DEFAULT_HAIKU_MODEL=
EOF
  echo "created .env template; fill FEISHU_APP_ID/FEISHU_APP_SECRET if reusing an existing bot"
}

find_claudeteam_dir() {
  local candidates=(
    "$SCRIPT_DIR"
    "$SCRIPT_DIR/ClaudeTeam"
    "$SCRIPT_DIR/../ClaudeTeam"
    "$TEAM_DIR/ClaudeTeam"
    "$TEAM_DIR/../ClaudeTeam"
  )
  local d
  for d in "${candidates[@]}"; do
    if [ -f "$d/pyproject.toml" ] && [ -d "$d/src/claudeteam" ]; then
      cd "$d" >/dev/null 2>&1 && pwd
      return 0
    fi
  done
  return 1
}

ensure_claudeteam_venv() {
  local source_dir
  if ! source_dir="$(find_claudeteam_dir)"; then
    echo "error: cannot find nearby ClaudeTeam source directory; cannot create venv" >&2
    return 127
  fi
  if [ -x "$source_dir/.venv/bin/claudeteam" ]; then
    return 0
  fi
  if command -v claudeteam >/dev/null 2>&1; then
    return 0
  fi

  local py="${PYTHON:-python3}"
  if [ ! -x "$source_dir/.venv/bin/python" ]; then
    echo "creating ClaudeTeam venv: $source_dir/.venv"
    "$py" -m venv "$source_dir/.venv"
  fi
  cat >"$source_dir/.venv/bin/claudeteam" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd)"
export PYTHONPATH="$SOURCE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$SOURCE_DIR/.venv/bin/python" -m claudeteam.cli "$@"
EOF
  chmod +x "$source_dir/.venv/bin/claudeteam"
  if [ ! -x "$source_dir/.venv/bin/claudeteam" ]; then
    echo "error: failed to create claudeteam entrypoint in venv" >&2
    return 1
  fi
  echo "created ClaudeTeam venv: $source_dir/.venv/bin/claudeteam"
}

ensure_feishu_channel_deps() {
  local source_dir
  if ! source_dir="$(find_claudeteam_dir)"; then
    echo "error: cannot find nearby ClaudeTeam source directory; cannot prepare Feishu channel deps" >&2
    return 127
  fi

  local sidecar_dir="$source_dir/scripts/feishu_channel"
  local marker="$sidecar_dir/node_modules/@larksuite/channel"
  if [ -d "$marker" ]; then
    return 0
  fi
  if [ ! -f "$sidecar_dir/package.json" ]; then
    echo "warning: Feishu channel package not found at $sidecar_dir; skipping Node deps" >&2
    return 0
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "error: Feishu channel deps are missing, but npm is not on PATH" >&2
    echo "       install Node.js/npm, then rerun ./team.sh init" >&2
    return 127
  fi

  echo "installing Feishu channel deps: $sidecar_dir"
  if ! (cd "$sidecar_dir" && npm install --omit=dev --no-fund --no-audit); then
    echo "error: failed to install Feishu channel deps in $sidecar_dir" >&2
    return 1
  fi
  if [ ! -d "$marker" ]; then
    echo "error: npm install finished, but @larksuite/channel is still missing" >&2
    echo "       expected: $marker" >&2
    return 1
  fi
}

claudeteam_cmd() {
  load_env_file

  local source_dir
  if source_dir="$(find_claudeteam_dir)"; then
    if [ "${CLAUDETEAM_TEAM_SH_IGNORE_VENV:-}" != "1" ] && \
        [ -x "$source_dir/.venv/bin/claudeteam" ]; then
      export PATH="$source_dir/.venv/bin:$PATH"
      command claudeteam "$@"
      return
    fi
  fi

  if command -v claudeteam >/dev/null 2>&1; then
    command claudeteam "$@"
    return
  fi

  if [ -n "${source_dir:-}" ]; then
    PYTHONPATH="$source_dir/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m claudeteam.cli "$@"
    return
  fi

  echo "error: cannot find claudeteam on PATH or nearby ClaudeTeam source directory" >&2
  echo "       keep this team directory beside ClaudeTeam, or install ClaudeTeam first." >&2
  return 127
}

has_session_arg() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --session|--session=*) return 0 ;;
    esac
  done
  return 1
}

run_init() {
  local rc
  ensure_claudeteam_venv
  rc=$?
  if [ "$rc" -ne 0 ]; then
    return "$rc"
  fi
  ensure_feishu_channel_deps
  rc=$?
  if [ "$rc" -ne 0 ]; then
    return "$rc"
  fi
  if has_session_arg "$@"; then
    claudeteam_cmd init "$@"
    rc=$?
  else
    claudeteam_cmd init --session "$DEFAULT_SESSION" --no-connect "$@"
    rc=$?
  fi
  if [ "$rc" -eq 0 ]; then
    ensure_env_template
  fi
  return "$rc"
}

copy_to() {
  if [ "$#" -ne 1 ]; then
    echo "usage: ./team.sh copy-to <dir>" >&2
    return 2
  fi
  local target="$1"
  mkdir -p "$target"
  cp "$SCRIPT_PATH" "$target/team.sh"
  chmod +x "$target/team.sh"
  echo "copied to $target/team.sh"
}

doctor() {
  echo "team_dir: $TEAM_DIR"
  echo "default_session: $DEFAULT_SESSION"
  echo "config_file: $CLAUDETEAM_CONFIG_FILE"
  echo "state_dir: $CLAUDETEAM_STATE_DIR"

  if source_dir="$(find_claudeteam_dir)"; then
    echo "ClaudeTeam source: $source_dir"
  else
    echo "ClaudeTeam source: not found"
  fi

  if command -v claudeteam >/dev/null 2>&1; then
    echo "claudeteam: $(command -v claudeteam)"
  elif [ -n "${source_dir:-}" ] && [ -x "$source_dir/.venv/bin/claudeteam" ]; then
    echo "claudeteam: $source_dir/.venv/bin/claudeteam"
  else
    echo "claudeteam: not on PATH; will use nearby source if available"
  fi

  if command -v tmux >/dev/null 2>&1; then
    echo "tmux: $(command -v tmux)"
  else
    echo "tmux: not on PATH"
  fi

  if [ -f "$TEAM_DIR/.env" ]; then
    echo ".env: present"
  else
    echo ".env: missing (run ./team.sh init to create a template)"
  fi
}

cmd="${1:-help}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$cmd" in
  -h|--help|help)
    usage
    ;;
  init)
    run_init "$@"
    ;;
  connect)
    claudeteam_cmd feishu connect "$@"
    ;;
  hooks|install-hooks)
    claudeteam_cmd install-hooks "$@"
    ;;
  tmux|attach)
    session="${1:-$DEFAULT_SESSION}"
    tmux_bin="${CLAUDETEAM_TMUX_BIN:-tmux}"
    echo "$tmux_bin attach -t $session"
    exec "$tmux_bin" attach -t "$session"
    ;;
  cmd)
    claudeteam_cmd "$@"
    ;;
  session)
    echo "$DEFAULT_SESSION"
    ;;
  doctor)
    doctor
    ;;
  copy-to)
    copy_to "$@"
    ;;
  up|start|down|restart|team-restart|team-shutdown|health|usage|status|log|team|workspace|peek|send|inbox|read|say|router|watchdog|task|remember|recall|forget|hire|fire|reset|reidentify|switch|version)
    claudeteam_cmd "$cmd" "$@"
    ;;
  *)
    claudeteam_cmd "$cmd" "$@"
    ;;
esac
