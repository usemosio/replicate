#!/usr/bin/env bash
# Install the replicate-video helper and the replicate + style-writer skills.
#
#   curl -fsSL https://raw.githubusercontent.com/usemosio/replicate/main/install.sh | bash
#
# Options (environment):
#   REPLICATE_REF=<branch|tag>   version to install (default: main)
#   SKILLS_DIRS="dir1 dir2"      where to put the skills (default: ~/.claude/skills ~/.agents/skills)
#   NO_CLI=1 / NO_SKILLS=1       skip a part
set -euo pipefail

REPO="https://github.com/usemosio/replicate"
REF="${REPLICATE_REF:-main}"
SKILLS_DIRS="${SKILLS_DIRS:-$HOME/.claude/skills $HOME/.agents/skills}"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }

if [ -z "${NO_CLI:-}" ]; then
  say "Installing the replicate-video CLI ($REF)"
  if command -v uv >/dev/null 2>&1; then
    uv tool install --force "git+$REPO@$REF"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install --force "git+$REPO@$REF"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m pip install --user --upgrade "git+$REPO@$REF"
  else
    warn "Need uv, pipx or Python 3.10+. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
fi

if [ -z "${NO_SKILLS:-}" ]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  if [ -d "$(dirname "${BASH_SOURCE[0]:-.}")/skills/replicate" ] && [ -z "${REPLICATE_REF:-}" ]; then
    src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills"
  else
    git clone --quiet --depth 1 --branch "$REF" "$REPO" "$tmp/repo"
    src="$tmp/repo/skills"
  fi
  for dir in $SKILLS_DIRS; do
    mkdir -p "$dir"
    for skill in replicate style-writer; do
      rm -rf "${dir:?}/$skill"
      cp -R "$src/$skill" "$dir/$skill"
    done
    say "Skills installed in $dir"
  done
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  warn "FFmpeg is missing. Install it, then run: replicate-video doctor"
  case "$(uname -s)" in
    Darwin) warn "  brew install ffmpeg" ;;
    Linux) warn "  sudo apt install ffmpeg   (or: sudo dnf install ffmpeg, sudo pacman -S ffmpeg)" ;;
  esac
else
  command -v replicate-video >/dev/null 2>&1 && replicate-video doctor || true
fi
