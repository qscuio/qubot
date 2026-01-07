---
name: SQL Query
description: Write and optimize SQL queries. Use when asked to query database, write SQL, or optimize queries.
---

# SQL Query Skill

Write efficient, safe SQL queries.

## Query Structure

```sql
SELECT columns
FROM table
JOIN other_table ON condition
WHERE filters
GROUP BY columns
HAVING group_filters
ORDER BY columns
LIMIT n OFFSET m
```

## Best Practices

### Performance
- Select only needed columns, avoid `SELECT *`
- Use indexes on WHERE and JOIN columns
- Use EXPLAIN to analyze query plans
- Avoid functions on indexed columns in WHERE
- Use appropriate JOIN types

### Safety
- Always use parameterized queries (prevent SQL injection)
- Use transactions for multiple writes
- Add appropriate WHERE clauses to UPDATE/DELETE
- Test on small dataset first

## Common Patterns

**Pagination:**
```sql
SELECT * FROM users
ORDER BY created_at DESC
LIMIT 20 OFFSET 40
```

**Search:**
```sql
SELECT * FROM products
WHERE name ILIKE '%search%'
   OR description ILIKE '%search%'
```

**Aggregation:**
```sql
SELECT category, COUNT(*), AVG(price)
FROM products
GROUP BY category
HAVING COUNT(*) > 5
```

## Output Format

Provide:
1. The SQL query
2. Explanation of what it does
3. Performance considerations
4. Index recommendations if applicable
