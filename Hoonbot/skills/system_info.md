---
name: system_info
description: Current system hardware and resource status (CPU, RAM, disk, battery)
---

Current system resource usage is automatically included in your context under **## System Status** during heartbeat ticks.

When the user asks about system performance, disk space, memory usage, CPU load, or battery status, reference those stats directly.

Proactively alert the user (via message action or notification) if:
- Disk usage exceeds 90%
- Battery is below 15% and discharging
- RAM usage is above 95%

These alerts should only be sent once per issue — use memory to track whether you already alerted.
