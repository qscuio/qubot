---
name: Git Commit
description: Generate clear, conventional commit messages. Use when asked to commit changes or write commit messages.
---

# Git Commit Message Skill

Generate commit messages following the Conventional Commits specification.

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation only
- **style**: Formatting, no code change
- **refactor**: Code change, no feature or fix
- **perf**: Performance improvement
- **test**: Adding tests
- **chore**: Maintenance tasks
- **ci**: CI/CD changes
- **build**: Build system changes

## Rules

1. **Subject line**: Max 50 characters, imperative mood, no period
2. **Body**: Wrap at 72 characters, explain what and why
3. **Breaking changes**: Start footer with `BREAKING CHANGE:`

## Examples

```
feat(auth): add OAuth2 login support

Implement Google and GitHub OAuth2 providers.
Users can now link social accounts for faster login.

Closes #123
```

```
fix(api): handle null response from external service

The external pricing API occasionally returns null.
Added defensive check to prevent 500 errors.
```
