#!/usr/bin/env python3
"""Check the minimum tutorial structure requirements."""
from __future__ import annotations
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TUTORIALS = ROOT / "docs" / "tutorials"
REQUIRED = ("Lesson Goals","Prerequisites","New and Changed Files","Key Flow","Implementation Breakdown","Version Features, Next Lesson, and Code Index")
def version_key(path: Path):
    match = re.search(r"(\d+)(?:-(\d+))?", path.name)
    return tuple(int(part) for part in match.groups(default="0")) if match else (0,)
def latest_tutorial():
    files = [p for p in TUTORIALS.glob("*.md") if re.search(r"\d", p.name)]
    if not files: raise RuntimeError("no version tutorial found")
    return max(files, key=version_key)
def check(path: Path):
    text = path.read_text(encoding="utf-8")
    errors = [f"missing section: ## {s}" for s in REQUIRED if f"## {s}" not in text]
    if "git checkout" not in text: errors.append("missing git checkout version switch command")
    if "git diff --stat" not in text: errors.append("missing git diff --stat diff entry")
    if "## Why This Design" not in text and "## Why This Version Is Needed" not in text:
        errors.append("missing \"Why This Design\" section")
    if not re.search(r"\[[^]]+\]\(https://github\.com/liiiiiiiiil/agent-from-scratch/blob/v[^/]+/[^)]+\.py\)", text): errors.append("missing tag-pinned implementation file index link")
    return errors
def main(argv):
    paths = [ROOT / arg for arg in argv] if argv else [latest_tutorial()]
    failed = False
    for path in paths:
        if not path.exists():
            print(f"ERROR {path}: file does not exist"); failed = True; continue
        errors = check(path)
        if errors:
            failed = True
            for error in errors: print(f"ERROR {path.relative_to(ROOT)}: {error}")
        else: print(f"PASS  {path.relative_to(ROOT)}")
    return 1 if failed else 0
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
