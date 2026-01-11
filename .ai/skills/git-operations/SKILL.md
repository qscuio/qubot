---
name: Git Operations
description: |
  Comprehensive git commit and pull request guidelines with safety protocols.
  Use when: committing changes, creating PRs, pushing code, managing git workflows.
keywords:
  - commit
  - push
  - pull request
  - PR
  - git
  - merge
  - branch
---

# Git Operations Skill

## Git Safety Protocol

- **NEVER** update git config without permission
- **NEVER** run destructive commands (push --force, hard reset) unless explicitly requested
- **NEVER** skip hooks (--no-verify) unless explicitly requested
- **NEVER** force push to main/master branch - warn if requested
- **NEVER** commit changes unless explicitly asked

## Git Commit Workflow

1. **Analyze the situation** (run in parallel):
   ```bash
   git status          # See untracked files
   git diff            # See staged and unstaged changes
   git log -n 5        # See recent commit style
   ```

2. **Draft commit message**:
   - Summarize the nature: feature, enhancement, bug fix, refactor, test, docs
   - Focus on "why" not "what"
   - Keep it to 1-2 sentences
   - Do NOT commit files with secrets (.env, credentials.json)

3. **Execute** (in sequence):
   ```bash
   git add <files>
   git commit -m "message"
   git status          # Verify success
   ```

4. **If pre-commit hook fails**: Fix issues and create a NEW commit (don't amend)

## Amend Rules

Only use `git commit --amend` when ALL these conditions are met:
1. User explicitly requested amend, OR commit succeeded but pre-commit hook auto-modified files
2. HEAD commit was created by you in this conversation
3. Commit has NOT been pushed to remote

## Pull Request Workflow

1. **Understand branch state** (run in parallel):
   ```bash
   git status
   git diff
   git log
   git diff <base-branch>...HEAD
   ```

2. **Analyze ALL commits** (not just latest) and draft PR summary

3. **Create PR**:
   ```bash
   gh pr create --title "title" --body "$(cat <<'EOF'
   ## Summary
   - First bullet point
   - Second bullet point
   EOF
   )"
   ```

4. Return the PR URL when done
