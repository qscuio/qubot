---
name: API Design
description: Design REST APIs with endpoints, methods, and schemas. Use when asked to design, plan, or structure an API.
---

# API Design Skill

Design clean, RESTful APIs following best practices.

## Resource Naming

- Use **nouns**, not verbs: `/users` not `/getUsers`
- Use **plural** names: `/orders` not `/order`
- Use **kebab-case**: `/user-profiles` not `/userProfiles`
- Nest for relationships: `/users/{id}/orders`

## HTTP Methods

| Method | Purpose | Idempotent |
|--------|---------|------------|
| GET | Retrieve resource | Yes |
| POST | Create resource | No |
| PUT | Replace resource | Yes |
| PATCH | Update fields | Yes |
| DELETE | Remove resource | Yes |

## Response Codes

- `200` - Success
- `201` - Created
- `204` - No Content (delete)
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `422` - Validation Error
- `500` - Server Error

## Schema Design

```json
{
  "data": { ... },
  "meta": {
    "page": 1,
    "total": 100
  },
  "errors": []
}
```

## Output Format

For each endpoint, specify:
1. Method + Path
2. Request body/params
3. Response schema
4. Error cases
