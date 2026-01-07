---
name: Performance Optimization
description: Optimize code for speed and efficiency. Use when asked to optimize, speed up, or improve performance.
---

# Performance Optimization Skill

Improve code performance systematically.

## Optimization Process

1. **Measure First** - Profile before optimizing
2. **Find Bottlenecks** - Focus on hot paths
3. **Optimize** - Apply targeted improvements
4. **Verify** - Measure improvement

## Common Optimizations

### Algorithm Complexity
```python
# O(n²) - BAD
for i in items:
    if i in other_items:  # O(n) lookup
        
# O(n) - GOOD  
other_set = set(other_items)  # O(1) lookup
for i in items:
    if i in other_set:
```

### Caching
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def expensive_calculation(n):
    ...
```

### Batch Operations
```python
# BAD - N database calls
for user in users:
    db.save(user)

# GOOD - 1 database call
db.save_all(users)
```

### Lazy Evaluation
```python
# Use generators for large datasets
def process(items):
    for item in items:
        yield transform(item)
```

## Database Optimizations
- Add indexes for frequent queries
- Use EXPLAIN to analyze queries
- Avoid N+1 query problems
- Use connection pooling

## Output Format

1. Current performance issue
2. Root cause analysis
3. Proposed optimization
4. Expected improvement
5. Trade-offs (if any)
