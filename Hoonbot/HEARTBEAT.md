# Heartbeat Checklist

On each tick, check if any of the following need attention. Be proactive — if there's something worth doing, do it. Use `{"action": "none"}` only when there is genuinely nothing useful to act on right now.

## Checks

- **Time-sensitive memories** — Are there upcoming deadlines, appointments, or events the user should be reminded of? Check timestamps in memory.
- **System resources** — Is disk usage above 90%? CPU sustained high? Battery critically low (below 15%)? Alert once per issue.
- **Long silence** — Has there been an unusually long gap in conversation where a gentle check-in would be welcome?
- **Scheduled job gaps** — Is there something recurring the user mentioned in memory that should have a scheduled job but doesn't? Check existing schedules before creating new ones.
- **Useful proactive info** — Is there a genuinely helpful insight, follow-up, or update worth surfacing right now based on context?

## Rules

- Do not repeat yourself — if you already sent a message about something recently (check daily logs), don't send it again.
- System alerts fire once per issue, not every tick.
- Only create a schedule if there's clear evidence from memories that the user would want it.
