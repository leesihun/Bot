"""Skills system — Markdown-based capability extensions.

Skills are .md files in the Hoonbot/skills/ directory. Each file injects
its instructions into the LLM system prompt, extending Hoonbot's capabilities.

The LLM can also create new skills autonomously by emitting [SKILL_CREATE: ...] blocks.

Format for self-creating skills:
    [SKILL_CREATE: name=skill_name, description=What this skill does]
    Instructions for the agent go here.
    Can span multiple lines.
    [/SKILL_CREATE]
"""
import os
import re
import logging
from typing import List, Dict

import config

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(config.SOUL_PATH), "skills")


def load_skills() -> str:
    """Load all skill files and return formatted context string for the system prompt.
    Called fresh on every LLM request so new skills are available immediately.
    """
    if not os.path.isdir(SKILLS_DIR):
        return ""

    skills = []
    for filename in sorted(os.listdir(SKILLS_DIR)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(SKILLS_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                # Strip YAML frontmatter (--- ... ---) for cleaner injection
                body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL).strip()
                if body:
                    name = filename[:-3]  # strip .md
                    skills.append((name, body))
        except Exception as e:
            logger.warning(f"[Skills] Failed to load {filename}: {e}")

    if not skills:
        return ""

    lines = ["## Skills\n"]
    for name, body in skills:
        lines.append(f"### {name}\n\n{body}\n")
    return "\n".join(lines)


def list_skills() -> List[str]:
    """Return a list of installed skill names."""
    if not os.path.isdir(SKILLS_DIR):
        return []
    return [f[:-3] for f in sorted(os.listdir(SKILLS_DIR)) if f.endswith(".md")]


def create_skill(name: str, description: str, instructions: str) -> str:
    """Write a new skill file. Returns the created file path."""
    os.makedirs(SKILLS_DIR, exist_ok=True)

    # Sanitize name to a safe filename
    safe_name = re.sub(r"[^\w\-]", "_", name.strip().lower())
    path = os.path.join(SKILLS_DIR, f"{safe_name}.md")

    content = (
        f"---\n"
        f"name: {safe_name}\n"
        f"description: {description.strip()}\n"
        f"---\n\n"
        f"{instructions.strip()}\n"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"[Skills] Created skill '{safe_name}' at {path}")
    return path


def parse_skill_create_commands(text: str) -> List[Dict]:
    """Extract [SKILL_CREATE: name=..., description=...]...[/SKILL_CREATE] blocks."""
    pattern = (
        r"\[SKILL_CREATE:\s*name=([^,\]]+),\s*description=([^\]]*)\]\s*\n"
        r"(.*?)"
        r"\[/SKILL_CREATE\]"
    )
    commands = []
    for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
        name = m.group(1).strip()
        description = m.group(2).strip()
        instructions = m.group(3).strip()
        if name and instructions:
            commands.append({"name": name, "description": description, "instructions": instructions})
    return commands


def strip_skill_create_commands(text: str) -> str:
    """Remove [SKILL_CREATE: ...] blocks from text before sending to user."""
    pattern = r"\[SKILL_CREATE:[^\]]*\].*?\[/SKILL_CREATE\]\n?"
    return re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL).strip()
