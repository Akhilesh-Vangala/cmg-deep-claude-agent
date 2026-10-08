from __future__ import annotations

from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parent


def load_skills() -> dict[str, str]:
    skills: dict[str, str] = {}
    for path in SKILLS_ROOT.glob("*/SKILL.md"):
        skills[path.parent.name] = path.read_text(encoding="utf-8")
    return skills


def skill_catalog() -> list[str]:
    return sorted(load_skills().keys())
