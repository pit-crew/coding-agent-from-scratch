#!/usr/bin/env python3
"""Check the main README's navigation and naming conventions."""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
TUTORIALS = ROOT / "docs" / "tutorials"
CJK_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")


def _plain_text(fragment: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def main() -> int:
    text = README.read_text(encoding="utf-8")
    errors: list[str] = []
    for heading in ("Stage 1 ·", "Stage 2 ·", "Stage 3 ·", "Stage 4 ·", "Stage 5 ·", "Stage 6 ·", "Stage 7 ·"):
        if heading not in text:
            errors.append(f"missing learning stage heading: {heading}")
    topic_rows = re.findall(
        r"<tr>\s*<td>.*?</td>\s*<td>(.*?)</td>\s*<td>",
        text,
        flags=re.DOTALL,
    )
    for topic_fragment in topic_rows:
        topic = _plain_text(topic_fragment)
        if CJK_RE.search(topic):
            errors.append(f"learning path topic must use English: {topic}")
    if "docs/tutorials/README.md" not in text:
        errors.append("missing tutorial index link: docs/tutorials/README.md")
    for tutorial in sorted(TUTORIALS.glob("[0-9][0-9]-*.md")):
        if tutorial.name not in text:
            errors.append(f"learning path does not list tutorial: {tutorial.name}")
    if not re.search(r"Current status.*v0\.\d+", text):
        errors.append("missing current version status")
    if errors:
        for error in errors:
            print(f"ERROR README.md: {error}")
        return 1
    print("PASS  README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
