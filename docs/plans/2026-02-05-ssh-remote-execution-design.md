# SSH Remote Execution Toolkit Design

## Overview

Python module with CLI for executing commands, transferring files, and managing services on remote VPS servers via SSH. Outputs structured JSON for easy parsing by Claude.

## Module Structure

```
scripts/remote/
├── __init__.py          # Package init
├── __main__.py          # Entry point: python -m remote
├── cli.py               # CLI using typer
├── executor.py          # SSH command execution
├── transfer.py          # SCP upload/download
├── shortcuts.py         # Predefined tasks (deploy, logs, status)
└── output.py            # JSON output formatting
```

## CLI Commands

### Core Commands

```bash
# Arbitrary command execution
remote exec --host HOST --user USER [--key PATH | --password] "command"

# File transfer
remote upload --host HOST --user USER [--key PATH | --password] LOCAL REMOTE
remote download --host HOST --user USER [--key PATH | --password] REMOTE LOCAL
```

### Predefined Shortcuts

```bash
remote deploy --host HOST --user USER [--path /app] [--service app]
remote logs --host HOST --user USER [--service nginx] [--lines 100]
remote status --host HOST --user USER
remote restart --host HOST --user USER --service SERVICE
```

### Common Flags

- `--timeout 30` - Command timeout in seconds (default: 30)
- `--port 22` - SSH port (default: 22)
- `--quiet` - Suppress JSON, show raw stdout/stderr
- `--verbose` - Show connection details

## Authentication

1. `--key ~/.ssh/id_rsa` - Use specific SSH key
2. `--password` - Triggers secure password prompt
3. Neither - Uses SSH agent or default key

## Output Format

Success:
```json
{
  "success": true,
  "host": "192.168.1.10",
  "command": "df -h",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "duration_ms": 234
}
```

Failure:
```json
{
  "success": false,
  "host": "192.168.1.10",
  "command": "bad-command",
  "exit_code": 127,
  "stdout": "",
  "stderr": "command not found",
  "error": "Command failed with exit code 127"
}
```

## Shortcut Details

### `remote deploy`
1. `cd PATH && git pull`
2. `pip install -r requirements.txt` (if exists)
3. `systemctl restart SERVICE`

### `remote logs`
- `journalctl -u SERVICE -n LINES --no-pager`
- Falls back to `/var/log/SERVICE/error.log`

### `remote status`
Returns parsed JSON with: disk, memory, load, uptime, services

### `remote restart`
- `systemctl restart SERVICE && systemctl status SERVICE`

## Dependencies

```
paramiko>=3.0.0
typer>=0.9.0
```

## Skill Document

Location: `~/.claude/skills/ssh-remote-execution/SKILL.md`

Contents:
- When to use
- Quick reference table
- Authentication patterns
- Interpreting JSON output
- Common workflows (deploy, debug, health check)
- Error handling
- Security notes
