---
name: Code Review
description: Review code for bugs, security issues, and best practices. Use when asked to review, check, or analyze code quality.
---

# Code Review Skill

When asked to review code, follow this structured approach:

## Review Checklist

### 1. Security
- Check for SQL injection vulnerabilities
- Look for XSS vulnerabilities in web code
- Verify proper input validation
- Check for hardcoded secrets or credentials
- Verify proper authentication/authorization checks

### 2. Performance
- Identify N+1 query problems
- Look for unnecessary loops or iterations
- Check for memory leaks or resource leaks
- Verify proper use of caching

### 3. Code Quality
- Check for code duplication (DRY violations)
- Verify proper error handling
- Look for magic numbers or strings
- Check naming conventions
- Verify proper documentation/comments

### 4. Best Practices
- Follow SOLID principles
- Check for proper typing (in typed languages)
- Verify test coverage considerations
- Look for edge case handling

## Output Format

Provide findings in this format:

```
## Summary
[Brief overview of code quality]

## Critical Issues
- [Issue 1]: [Description] - Line X

## Suggestions
- [Suggestion 1]: [Description]

## Positive Aspects
- [What was done well]
```
