---
name: daily_log
description: Append important notes to today's daily log for cross-session narrative memory
---

You have access to an append-only daily log at `data/memory/YYYY-MM-DD.md`. Recent logs (today + yesterday) are already included in your context above under **## Daily Log**.

To append a note to today's log, emit at the end of your response:

```
[DAILY_LOG: Brief note about what happened, was decided, or should be remembered tomorrow]
```

**When to log:**
- The user started or finished an important task
- A significant decision was made
- A deadline or event was mentioned
- The user shared something personally important
- You completed a background task with a notable result

**Keep notes concise** — one sentence is enough. The goal is a readable narrative of the day, not a transcript.

**Example:**
```
[DAILY_LOG: User finished writing the Hoonbot skills system. Decided to defer browser automation.]
[DAILY_LOG: Meeting with team scheduled for Monday 3pm.]
```
