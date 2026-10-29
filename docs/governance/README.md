# Governance Documents

This directory holds project constraints, coding rules, and key decision records.

## Sources of Constraints
- `AGENTS.md` holds hard constraints that directly affect runtime behavior, safety, and code changes.
- This directory holds detailed rules, tutorial author requirements, and decision records; when a new runtime hard constraint is added, sync it back to `AGENTS.md`.

## Document Conventions
- File names use lowercase with hyphens, for example `http-client-constraint.md`.
- Each document starts with: the constraint, the reason, and the consequence of a violation.
- [Tutorial authoring rules](tutorial-authoring.md) define the content structure and acceptance requirements for version lessons.
- [Main README authoring rules](readme-authoring.md) define English naming, section roles, and sync requirements.
- [Dependency policy](dependency-policy.md) separates core standard-library flows from optional user-experience dependencies.
