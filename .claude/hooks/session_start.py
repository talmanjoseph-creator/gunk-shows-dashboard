#!/usr/bin/env python3
"""SessionStart: warn when this copy is behind origin/main (AGENTS.md rule 1).

Never changes the working tree. Prints a note that Claude sees at the start
of the session. Exits 0 even when git or the network fails.
"""
import os
import subprocess

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def git(*args, timeout=45):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def main():
    try:
        fetched = git("fetch", "--quiet", "origin", "main").returncode == 0
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        behind = git("rev-list", "--count", "HEAD..origin/main").stdout.strip()
        dirty = bool(git("status", "--porcelain").stdout.strip())
    except Exception as e:  # git missing, timeout, etc.
        print(f"[pull-first check] Could not check origin/main ({e}). Pull the latest main before editing.")
        return
    if not fetched:
        print("[pull-first check] Could not fetch origin/main. Pull the latest main before editing (AGENTS.md rule 1).")
        return
    if behind and behind != "0":
        print(
            f"[pull-first check] WARNING: branch '{branch}' is {behind} commit(s) behind origin/main. "
            "Before editing anything, bring it up to date (git pull origin main, or start a new branch "
            "from origin/main). Never push a stale copy of index.html or shows-data.js."
            + (" There are uncommitted changes, so update with care." if dirty else "")
        )
    else:
        print(f"[pull-first check] '{branch}' is up to date with origin/main.")


if __name__ == "__main__":
    main()
