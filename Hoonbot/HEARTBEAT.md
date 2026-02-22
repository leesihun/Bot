# Heartbeat Checklist

On each tick, check if any of the following need attention.
If nothing needs attention, respond with `{"action": "none"}` — this is the most common and preferred response.

## Checks

- **Time-sensitive memories** — Are there upcoming deadlines, appointments, or events the user should be reminded of?
- **System resources** — Is disk usage above 90%? CPU sustained high? Battery critically low (below 15%)?
- **Long silence** — Has there been an unusually long gap in conversation where a gentle check-in would be welcome?
- **Scheduled job gaps** — Is there something recurring the user mentioned that should have a scheduled job but doesn't?
- **Useful proactive info** — Is there a genuinely helpful insight, follow-up, or update worth surfacing right now?

## Rules

- Be conservative. Most ticks should return `{"action": "none"}`.
- Do not repeat yourself — if you already sent a message about something recently, don't send it again.
- Only create a scheduled job if there's clear evidence from memories that the user would want it.
- System alerts should only fire once per issue, not every tick.
