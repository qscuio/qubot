---
name: Debug Error
description: Debug errors, exceptions, and stack traces. Use when asked to debug, fix error, or troubleshoot issues.
---

# Error Debugging Skill

When presented with an error or exception, follow this systematic approach:

## Analysis Steps

1. **Read the error message** - Extract the key information:
   - Error type (TypeError, ValueError, ConnectionError, etc.)
   - Error message text
   - File and line number
   - Stack trace sequence

2. **Identify the root cause** - Common patterns:
   - `TypeError: 'NoneType'` → Variable is None when it shouldn't be
   - `KeyError` → Dictionary missing expected key
   - `AttributeError` → Object doesn't have the attribute
   - `IndexError` → List index out of bounds
   - `ConnectionError` → Network/API issue

3. **Check the context**:
   - What was the input data?
   - What was the expected behavior?
   - When did it start failing?

## Response Format

```
## Error Analysis
**Type**: [Error type]
**Location**: [File:Line]
**Cause**: [Root cause explanation]

## Solution
[Step-by-step fix]

## Prevention
[How to prevent this in future]
```

## Common Fixes

- Add null checks before accessing properties
- Validate input data before processing
- Use try/catch for external calls
- Add default values for optional parameters
