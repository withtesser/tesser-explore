#!/usr/bin/env bash
# tesser installer. Run this in your terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/withtesser/tesser-explore/main/install.sh | bash
#
# Installs tesser (a set of Claude Code skills) into ~/.claude/skills/tesser and
# links its two skills. It runs entirely in YOUR shell — there is no agent and
# no autonomous clone — so it does not trip Claude Code's untrusted-code
# guardrail (that guardrail fires when an AGENT tries to clone code into the
# skills dir, not when you install it yourself). When it finishes it prints a
# claude command you copy-paste to run the first example wherever you like.
#
# Prefer to read before you run? Download and inspect first:
#   curl -fsSL https://raw.githubusercontent.com/withtesser/tesser-explore/main/install.sh -o tesser-install.sh
#   less tesser-install.sh && bash tesser-install.sh

set -euo pipefail

REPO_URL="https://github.com/withtesser/tesser-explore"
DEST="${TESSER_INSTALL_DEST:-$HOME/.claude/skills/tesser}"
EXAMPLE="/tesser-benchmark how does sourcegraph/conc's WaitGroup differ from the stdlib one?"

say()  { printf '%s\n' "$*"; }
die()  { printf 'tesser install: %s\n' "$*" >&2; exit 1; }

command -v git      >/dev/null 2>&1 || die "git is required but was not found on PATH."
command -v python3  >/dev/null 2>&1 || die "python3 is required but was not found on PATH."

say "==> Installing tesser into $DEST"
if [ -d "$DEST/.git" ]; then
  say "    already cloned — updating (git pull --ff-only)"
  ( cd "$DEST" && git pull --ff-only --quiet ) || say "    update skipped; keeping the existing clone"
elif [ -e "$DEST" ]; then
  die "$DEST already exists and is not a git clone. Move it aside and re-run."
else
  git clone --quiet "$REPO_URL" "$DEST" || die "clone failed (is $REPO_URL reachable?)"
fi

say "==> Setting up tesser's environment (private venv + skill links)"
# Suppress setup's first-skill session-restart notice: it is meant for a skill
# installed INTO a running Claude Code session. Here we install from a plain
# terminal and hand back a command that launches a FRESH session (which sees the
# skills at startup), so that notice would be wrong.
TESSER_SUPPRESS_SESSION_NOTICE=1 "$DEST/scripts/setup"

cat <<EOF

==> Done. tesser is installed.
    Skills ready: /tesser-benchmark  /tesser-discover

Try the first example — copy-paste this and run it in any project directory:

    claude "$EXAMPLE"

EOF
