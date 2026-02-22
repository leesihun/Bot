---
name: self_extend
description: Create new skills to extend your own capabilities
---

You can create new skills to extend your capabilities. A skill is a Markdown file with instructions that gets injected into your system prompt.

To create a new skill, emit at the end of your response:

```
[SKILL_CREATE: name=skill_name, description=One-line description of what this skill does]
Instructions for how to use this skill.
Can span multiple lines.
Include examples, rules, and output formats.
[/SKILL_CREATE]
```

**When to create a skill:**
- The user asks you to do something new repeatedly that you want to remember how to do
- You find a useful workflow or pattern worth codifying
- The user explicitly asks you to save a new capability

**Good skill examples:**
- A skill for a specific API the user frequently uses
- A skill with formatting rules for a recurring document type
- A skill that defines how to handle a specific category of questions

**Rules:**
- Skill names must be lowercase with underscores (e.g., `code_review`, `expense_report`)
- Instructions should be clear and actionable
- Don't create duplicate skills — check what skills already exist in your context first
- New skills are available immediately on the next message
