#!/usr/bin/env python3
"""PreToolUse guard for file edits. Blocks (exit 2) edits that break AGENTS.md:

  * hand edits to generated pages in shows/ or venues/
  * affiliate ticket redirects (evyy.net, pxf.io) in listings or pages
  * Supabase secrets: a service_role JWT, an sb_secret_ key, or a
    Postgres connection string with a password

It looks only at the text being written, not the text being removed.
"""
import base64
import json
import os
import re
import sys

ROOT = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

GENERATED_DIRS = ("shows", "venues")
# Files that legitimately talk about affiliate domains (the cleanup script
# strips them; the docs explain the rule).
AFFILIATE_OK = {"tools/clean_shows.py", "AGENTS.md", "README.md", ".claude/hooks/guard_edits.py"}
AFFILIATE_RE = re.compile(r"(?:^|[/.@\s\"'])(?:evyy\.net|pxf\.io)\b", re.I)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.(eyJ[A-Za-z0-9_-]{5,})\.[A-Za-z0-9_-]{10,}")
SB_SECRET_RE = re.compile(r"\bsb_secret_[A-Za-z0-9_-]{10,}")
PG_PASSWORD_RE = re.compile(r"postgres(?:ql)?://[^:\s/]+:[^@\s]+@", re.I)


def block(msg):
    print(f"Blocked by .claude/hooks/guard_edits.py: {msg}", file=sys.stderr)
    sys.exit(2)


def rel_path(path):
    if not path:
        return ""
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(ROOT, path))
    if not full.startswith(ROOT + os.sep):
        return None  # outside the repo: not our business
    return os.path.relpath(full, ROOT).replace(os.sep, "/")


def new_text(tool, inp):
    if tool == "Write":
        return inp.get("content") or ""
    if tool == "Edit":
        return inp.get("new_string") or ""
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string") or "" for e in inp.get("edits") or [])
    if tool == "NotebookEdit":
        return inp.get("new_source") or ""
    return ""


def jwt_is_service_role(payload_b64):
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        return json.loads(raw).get("role") == "service_role"
    except Exception:
        return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    rel = rel_path(inp.get("file_path") or inp.get("notebook_path") or "")
    if rel is None:
        return

    top = rel.split("/", 1)[0]
    if top in GENERATED_DIRS and "/" in rel:
        block(
            f"{rel} is a generated page. Do not edit shows/ or venues/ by hand: change "
            "shows-data.js and run `python3 tools/clean_shows.py`, which rebuilds the pages."
        )

    text = new_text(tool, inp)
    if not text:
        return

    if rel not in AFFILIATE_OK and AFFILIATE_RE.search(text):
        block(
            "the new text contains an affiliate ticket redirect (evyy.net / pxf.io). "
            "Ticket links must go straight to the ticket page. (Eventim `afflky=` keys are fine.)"
        )

    for m in JWT_RE.finditer(text):
        if jwt_is_service_role(m.group(1)):
            block("the new text contains a Supabase service_role key. Only the anon / publishable key may be committed.")
    if SB_SECRET_RE.search(text):
        block("the new text contains a Supabase secret key (sb_secret_...). Only the publishable key may be committed.")
    if PG_PASSWORD_RE.search(text):
        block("the new text contains a database connection string with a password. Never commit it.")


if __name__ == "__main__":
    main()
