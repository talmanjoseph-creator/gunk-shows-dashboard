#!/usr/bin/env python3
"""PostToolUse: after shows-data.js is edited, run tools/clean_shows.py.

The cleanup merges venue spellings, removes duplicates, sorts, regenerates
AREA, unwraps affiliate links and rebuilds the pages in shows/ and venues/,
so the pages are always regenerated alongside the data (AGENTS.md).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
TARGET = os.path.join(ROOT, "shows-data.js")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    path = (data.get("tool_input") or {}).get("file_path") or ""
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(ROOT, path))
    if full != TARGET:
        return
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "clean_shows.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-25:])
    if r.returncode != 0:
        # exit 2 sends this back to Claude so it fixes the data.
        print(f"tools/clean_shows.py failed after editing shows-data.js:\n{tail}", file=sys.stderr)
        sys.exit(2)
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "tools/clean_shows.py ran automatically after the shows-data.js edit and rebuilt "
                "shows/ and venues/. Commit the regenerated pages with the data change. Output:\n" + tail
            ),
        }
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
