---
name: Test Cases
description: Generate test cases and unit tests. Use when asked to test, write tests, or create test cases.
---

# Test Case Generation Skill

Create comprehensive test suites for code.

## Test Structure (AAA Pattern)

```python
def test_function_name():
    # Arrange - Set up test data
    input_data = {...}
    
    # Act - Execute the code
    result = function_under_test(input_data)
    
    # Assert - Verify the result
    assert result == expected
```

## Test Categories

### 1. Happy Path
- Normal expected inputs
- Typical use cases

### 2. Edge Cases
- Empty inputs ([], "", None, 0)
- Single item collections
- Maximum values
- Boundary conditions

### 3. Error Cases
- Invalid inputs
- Missing required fields
- Wrong types
- Null/undefined values

### 4. Integration
- Multiple components together
- Database interactions
- API calls

## Naming Convention

```
test_<function>_<scenario>_<expected_result>

Examples:
test_login_valid_credentials_returns_token
test_login_wrong_password_raises_error
test_calculate_empty_list_returns_zero
```

## Output Format

For each function, generate:
1. 2-3 happy path tests
2. 2-3 edge case tests
3. 1-2 error case tests

Include setup/teardown if needed.
