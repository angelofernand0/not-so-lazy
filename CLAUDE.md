# Angelo's Claude Code

Follow AGENTS.md and docs/AGENT-BOARD.md. Use GitHub issue #11 in
angelofernand0/not-so-lazy and the prefix [Angelo's Claude].

Set BOARD_AGENT=claude for board.sh. Use a separate worktree from Codex.
Register READY only after verifying your actual repo/account and board access.
The shared budget is one task TOTAL per hour, not one task per agent.
Run python3 tools/board_gate.py claim --agent claude --task "TASK-ID: scope"
before editing; any failure means STOP. Follow the returned stop_by deadline.
After reporting completion, release only your own claim with finish.
Do not create a second independent schedule if this Claude session already has one.
