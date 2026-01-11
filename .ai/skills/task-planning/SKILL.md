---
name: Task Planning
description: |
  Structured task management for complex coding sessions.
  Use when: planning work, tracking multiple steps, managing todos.
keywords:
  - todo
  - task
  - plan
  - checklist
  - workflow
  - steps
---

# Task Planning Skill

## When to Use Task Lists

Use structured task lists when:
1. **Complex multistep tasks** - 3+ distinct steps required
2. **Non-trivial work** - requires careful planning
3. **User requests** - explicitly asks for task tracking
4. **Multiple tasks** - user provides numbered/comma-separated list
5. **New instructions** - capture requirements immediately
6. **After completion** - mark complete and add follow-up tasks

## When NOT to Use

Skip task lists when:
1. Single, straightforward task
2. Trivial task (no organizational benefit)
3. Less than 3 trivial steps
4. Purely conversational/informational request

## Task States

| State | Description |
|-------|-------------|
| `pending` | Not yet started |
| `in_progress` | Currently working on (limit to ONE at a time) |
| `completed` | Finished successfully |
| `cancelled` | No longer needed |

## Best Practices

1. **Real-time updates**: Update status as you work
2. **Immediate completion**: Mark tasks complete RIGHT after finishing
3. **One at a time**: Only one `in_progress` task at any time
4. **Complete first**: Finish current tasks before starting new ones
5. **Specific items**: Create actionable, specific tasks
6. **Break down**: Split complex tasks into smaller steps

## Example

```markdown
User: "Add dark mode toggle and run tests"

Task List:
1. [x] Create dark mode toggle component
2. [x] Add dark mode state management
3. [x] Implement CSS styles for dark theme
4. [x] Update existing components for theme switching
5. [ ] Run tests and fix any failures
```

## Workflow

1. **Receive request** → Create task list if complex
2. **Start work** → Mark first task as `in_progress`
3. **Complete step** → Mark as `completed` immediately
4. **Next step** → Mark next as `in_progress`
5. **New subtasks** → Add them to the list
6. **Finish** → Ensure all tasks marked appropriately
