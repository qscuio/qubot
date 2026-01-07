---
name: Security Audit
description: Analyze code for security vulnerabilities. Use when asked about security, vulnerabilities, or safety of code.
---

# Security Audit Skill

Identify security vulnerabilities in code.

## OWASP Top 10 Checklist

### 1. Injection (SQL, Command, XSS)
```python
# BAD
query = f"SELECT * FROM users WHERE id = {user_input}"

# GOOD
query = "SELECT * FROM users WHERE id = ?"
cursor.execute(query, (user_input,))
```

### 2. Broken Authentication
- Check password strength requirements
- Verify session management
- Look for hardcoded credentials

### 3. Sensitive Data Exposure
- Are secrets in environment variables?
- Is data encrypted at rest/transit?
- Are logs sanitized?

### 4. XXE (XML External Entities)
- Disable external entity processing
- Use safe XML parsers

### 5. Broken Access Control
- Verify authorization on all endpoints
- Check for IDOR vulnerabilities
- Validate user permissions

### 6. Security Misconfiguration
- Debug mode disabled in production?
- Default credentials changed?
- Unnecessary features disabled?

### 7. Cross-Site Scripting (XSS)
- Escape user output
- Use Content-Security-Policy
- Validate and sanitize input

## Output Format

```
## Critical Issues
🔴 [Issue]: [Description]
   Fix: [Solution]

## Warnings
🟡 [Issue]: [Description]
   Recommendation: [Solution]

## Good Practices Found
🟢 [What's done well]
```
