---
name: git-pushing
description: Stage, commit, and push git changes with conventional commit messages. Use when user wants to commit and push changes, mentions pushing to remote, or asks to save and push their work. Also activates when user says "push changes", "commit and push", "push this", "push to github", or similar git workflow requests.
---

# Git Push Workflow

Stage all changes, create a conventional commit, and push to the remote branch.

## When to Use

Automatically activate when the user:
- Explicitly asks to push changes ("push this", "commit and push")
- Mentions saving work to remote ("save to github", "push to remote")
- Completes a feature and wants to share it
- Says phrases like "let's push this up" or "commit these changes"

## Workflow

### 1. Check Status
```bash
git status
```

### 2. Stage Changes
```bash
# Stage all changes
git add -A

# Or stage specific files
git add <file1> <file2>
```

### 3. Create Conventional Commit

Use conventional commit format:
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, semicolons, etc.)
- `refactor`: Code refactoring
- `test`: Adding or modifying tests
- `chore`: Build process or auxiliary tool changes

**Examples:**
```bash
git commit -m "feat(auth): add login functionality"
git commit -m "fix(api): resolve null pointer in user service"
git commit -m "docs: update README with setup instructions"
git commit -m "refactor(db): optimize query performance"
```

### 4. Push to Remote
```bash
# Push with upstream tracking
git push -u origin <branch-name>

# Or if already tracking
git push
```

## Best Practices

- **Atomic commits**: One logical change per commit
- **Clear messages**: Describe what changed and why
- **Pull before push**: Avoid merge conflicts
- **Review changes**: Use `git diff` before committing
- **Branch naming**: Use descriptive branch names like `feature/user-auth` or `fix/login-bug`

## Troubleshooting

**Push rejected:**
```bash
git pull --rebase origin <branch>
git push
```

**Forgot to add files:**
```bash
git add <forgotten-file>
git commit --amend --no-edit
git push --force-with-lease
```
