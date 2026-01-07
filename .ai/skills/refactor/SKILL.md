---
name: Refactor Code
description: Refactor and improve code quality. Use when asked to refactor, clean up, simplify, or improve code.
---

# Code Refactoring Skill

Improve code quality while preserving functionality.

## Refactoring Priorities

1. **Readability** - Make code self-documenting
2. **Simplicity** - Remove unnecessary complexity
3. **DRY** - Don't Repeat Yourself
4. **Single Responsibility** - One purpose per function/class
5. **Testability** - Make code easy to test

## Common Refactorings

### Extract Method
```python
# Before
def process():
    # 20 lines of validation
    # 20 lines of processing

# After  
def process():
    validate_input()
    do_processing()
```

### Replace Magic Numbers
```python
# Before
if status == 3:

# After
STATUS_COMPLETED = 3
if status == STATUS_COMPLETED:
```

### Simplify Conditionals
```python
# Before
if x == True:
    return True
else:
    return False

# After
return x
```

### Use Guard Clauses
```python
# Before
def func(x):
    if x:
        # lots of code
    
# After
def func(x):
    if not x:
        return
    # lots of code
```

## Output Format

1. Show the refactored code
2. Explain each change made
3. Note any behavior changes (should be none)
4. Suggest tests to verify correctness
