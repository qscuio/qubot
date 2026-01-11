---
name: File Editing
description: |
  Best practices for reading, writing, and editing files precisely.
  Use when: editing code, modifying files, reading file contents.
keywords:
  - edit
  - modify
  - change
  - write file
  - read file
  - update code
---

# File Editing Skill

## Reading Files

- Use absolute paths, not relative paths
- Batch multiple file reads together speculatively
- Default reads up to 2000 lines from start
- Lines longer than 2000 characters are truncated
- Results include line numbers starting at 1
- Can read image files

## Writing Files

- Writing **overwrites** existing files
- For existing files, you MUST **read the file first**
- ALWAYS prefer editing existing files over creating new ones
- NEVER proactively create documentation files (*.md, README) unless requested
- Only use emojis if explicitly requested

## Editing Files

### Rules
1. **Read first**: You MUST read the file before editing
2. **Preserve whitespace**: Match exact indentation (tabs/spaces) from original
3. **Edit existing**: ALWAYS prefer editing over creating new files
4. **Be precise**: Use exact string matching for replacements

### Error Cases
- Edit fails if `oldString` not found in content
- Edit fails if `oldString` found multiple times - provide more context
- Use `replaceAll` for renaming strings across the file

### Best Practices

```python
# Good: Precise, minimal edit
old: "    def calculate_total(self):"
new: "    def calculate_sum(self):"

# Bad: Too much context, prone to mismatch
old: "entire function body..."
new: "entire function body with one change..."
```

## File Operations Priority

1. **Search**: Use glob/file_search tools (NOT find, ls, grep commands)
2. **Read**: Use file_read tool (NOT cat, head, tail)
3. **Edit**: Use file_write tool (NOT sed, awk)
4. **Write**: Use file_write tool (NOT echo >, cat <<EOF)
