# Main README Authoring Rules

This file defines the role of the main README (`README.md`). The project keeps one README, in English.

## Role and Boundaries

- `README.md` is the project entry point: it describes the project, current status, how to run it, the full learning path, main directories, design constraints, and documentation entry points.
- `docs/tutorials/README.md` is the learning guide: it describes prerequisites, the learning route, how to read lessons, and the version workflow; lesson details stay in each lesson.
- `docs/operation/` is the manual for the latest version; `docs/plans/` records the roadmap and intent; governance documents record writing and decision rules. The README only links to them and does not copy their content.

## Structure and Naming

- The first screen says what the project is, who it is for, the current version, and how to read it; the body keeps Quick Start, Learning Path, Project Structure, Design Constraints, and Documentation.
- The learning path is organized as "stage → version lessons"; versions and links in the lesson table, tutorial index, plans, and CHANGELOG must agree.
- Stage names and version topics must use plain English. Protocol fields, code identifiers, and well-known technical terms may keep their original form. Titles are short and specific; avoid marketing slogans and repeated synonyms.
- Commands must be copyable; configuration examples must not contain a real `BASE_URL`, `API_KEY`, or `MODEL`.

## Updates and Acceptance

When you add a version or change an entry point, check versions, links, and status in `README.md`, `docs/tutorials/README.md`, the operation manual, and CHANGELOG, then run:

```bash
PYTHONPATH=src python scripts/check_readme.py
```
