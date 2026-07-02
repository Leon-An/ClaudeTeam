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
TEAM_DIR="$(pwd)"
TEAM_NAME="$(basename "$TEAM_DIR")"
DEFAULT_SESSION="${TEAM_NAME}Team"

usage() {
  cat <<EOF
usage: ./team.sh <command> [args...]

Copy this file into a new team directory beside ClaudeTeam, then run it there.

Common:
  init [args...]           claudeteam init --session ${DEFAULT_SESSION} --no-connect, then create .env template
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

claudeteam_cmd() {
  load_env_file

  if command -v claudeteam >/dev/null 2>&1; then
    command claudeteam "$@"
    return
  fi

  local source_dir
  if source_dir="$(find_claudeteam_dir)"; then
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

  if source_dir="$(find_claudeteam_dir)"; then
    echo "ClaudeTeam source: $source_dir"
  else
    echo "ClaudeTeam source: not found"
  fi

  if command -v claudeteam >/dev/null 2>&1; then
    echo "claudeteam: $(command -v claudeteam)"
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
