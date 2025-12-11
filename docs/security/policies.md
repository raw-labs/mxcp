---
title: "Policy Enforcement"
description: "Fine-grained access control with CEL expressions. Input policies, output filtering, and role-based permissions in MXCP."
sidebar:
  order: 3
---

MXCP's policy engine provides fine-grained access control for your endpoints. Policies can control who can call endpoints (input policies) and what data they can see (output policies).

## Policy Types

### Input Policies
Evaluated **before** endpoint execution:
- Block unauthorized requests
- Validate user permissions
- Enforce business rules

### Output Policies
Evaluated **after** endpoint execution:
- Filter sensitive fields
- Mask data values
- Redact information

## Basic Policy Structure

Policies are defined in endpoint YAML files:

```yaml
tool:
  name: employee_data
  # ... parameters and return ...

policies:
  input:
    - condition: "user.role != 'hr'"
      action: deny
      reason: "HR role required"

  output:
    - condition: "user.role != 'hr_manager'"
      action: filter_fields
      fields: ["salary", "ssn"]
      reason: "Sensitive data restricted"
```

## Policy Conditions

Conditions use a CEL-like expression syntax:

### User Context Variables

| Variable | Type | Description |
|----------|------|-------------|
| `user.id` | string | User identifier |
| `user.email` | string | User email address |
| `user.name` | string | User display name |
| `user.role` | string | Primary role |
| `user.permissions` | array | List of permissions |
| `user.groups` | array | Group memberships |

### Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `==` | Equals | `user.role == 'admin'` |
| `!=` | Not equals | `user.role != 'guest'` |
| `>` | Greater than | `user.level > 5` |
| `<` | Less than | `user.level < 10` |
| `>=` | Greater or equal | `user.age >= 18` |
| `<=` | Less or equal | `user.count <= 100` |

### Logical Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `&&` | And | `user.role == 'admin' && user.verified` |
| `\|\|` | Or | `user.role == 'admin' \|\| user.role == 'manager'` |
| `!` | Not | `!user.banned` |

### String Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `.contains()` | Contains substring | `user.email.contains('@company.com')` |
| `.startsWith()` | Starts with | `user.id.startsWith('EMP')` |
| `.endsWith()` | Ends with | `user.email.endsWith('.edu')` |

### Array Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `in` | Item in array | `'admin' in user.roles` |
| `all` | All items match | `user.permissions.all(p, p.startsWith('read'))` |
| `exists` | Any item matches | `user.groups.exists(g, g == 'admins')` |

## Input Policy Actions

### deny
Block the request entirely:

```yaml
input:
  - condition: "!('data.read' in user.permissions)"
    action: deny
    reason: "Missing data.read permission"
```

### warn
Log a warning but allow the request:

```yaml
input:
  - condition: "user.role == 'guest'"
    action: warn
    reason: "Guest access logged for review"
```

## Output Policy Actions

### filter_fields
Remove specific fields from the response:

```yaml
output:
  - condition: "user.role != 'admin'"
    action: filter_fields
    fields: ["ssn", "salary", "internal_notes"]
    reason: "Restricted to admins"
```

### filter_sensitive_fields
Remove all fields marked as `sensitive: true`:

```yaml
output:
  - condition: "!('pii.view' in user.permissions)"
    action: filter_sensitive_fields
    reason: "PII access not authorized"
```

### mask_fields
Replace field values with masked versions:

```yaml
output:
  - condition: "user.role == 'support'"
    action: mask_fields
    fields:
      email: "***@***.***"
      phone: "***-***-****"
    reason: "Data masked for support role"
```

## Complete Examples

### Role-Based Access Control

```yaml
tool:
  name: financial_report
  description: Generate financial reports

policies:
  input:
    # Only finance team can access
    - condition: "user.role != 'finance' && user.role != 'executive'"
      action: deny
      reason: "Finance or executive role required"

    # Warn on executive access
    - condition: "user.role == 'executive'"
      action: warn
      reason: "Executive access to financial data"

  output:
    # Non-executives see summary only
    - condition: "user.role != 'executive'"
      action: filter_fields
      fields: ["detailed_breakdown", "individual_salaries"]
      reason: "Detailed data restricted to executives"
```

### Permission-Based Access

```yaml
tool:
  name: customer_data
  description: Access customer information

policies:
  input:
    # Require base permission
    - condition: "!('customer.read' in user.permissions)"
      action: deny
      reason: "Missing customer.read permission"

  output:
    # Filter PII without special permission
    - condition: "!('customer.pii' in user.permissions)"
      action: filter_fields
      fields: ["email", "phone", "address"]
      reason: "PII access requires customer.pii permission"

    # Additional filter for financial data
    - condition: "!('customer.financial' in user.permissions)"
      action: filter_fields
      fields: ["credit_card", "bank_account", "credit_score"]
      reason: "Financial data requires customer.financial permission"
```

### Data Sensitivity Levels

```yaml
tool:
  name: employee_record

  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      email:
        type: string
        sensitive: true
      salary:
        type: number
        sensitive: true
      ssn:
        type: string
        sensitive: true
      department:
        type: string

policies:
  input:
    - condition: "user.role == 'guest'"
      action: deny
      reason: "Guests cannot access employee records"

  output:
    # Remove all sensitive fields for non-HR
    - condition: "user.role != 'hr'"
      action: filter_sensitive_fields
      reason: "HR role required for sensitive data"
```

### Conditional Field Access

```yaml
tool:
  name: project_details

policies:
  output:
    # Team members see their own projects only
    - condition: "user.role == 'member' && !result.team_members.contains(user.id)"
      action: deny
      reason: "Can only view your own projects"

    # Contractors see limited info
    - condition: "user.type == 'contractor'"
      action: filter_fields
      fields: ["budget", "internal_roadmap", "client_contacts"]
      reason: "Contractor access limited"
```

## Testing Policies

### Command Line Testing

Test with simulated user context:

```bash
# Test as regular user
mxcp run tool employee_data \
  --param employee_id=123 \
  --user-context '{"role": "user", "permissions": ["data.read"]}'

# Test as admin
mxcp run tool employee_data \
  --param employee_id=123 \
  --user-context '{"role": "admin", "permissions": ["data.read", "pii.view"]}'

# Test denied access
mxcp run tool employee_data \
  --param employee_id=123 \
  --user-context '{"role": "guest"}'
```

### YAML Test Cases

Add policy tests to your endpoint:

```yaml
tool:
  name: sensitive_tool

  tests:
    - name: admin_full_access
      description: Admin sees all fields
      arguments:
        - key: id
          value: 1
      user_context:
        role: admin
        permissions: ["all"]
      result_contains:
        salary: 85000
        ssn: "123-45-6789"

    - name: user_filtered_access
      description: Regular user sees filtered data
      arguments:
        - key: id
          value: 1
      user_context:
        role: user
        permissions: ["data.read"]
      result_not_contains:
        - salary
        - ssn
```

Note: Policy denial tests cannot be directly tested via YAML test assertions. Use CLI testing with `--user-context` to verify deny policies work correctly.

## Policy Evaluation Order

Policies are evaluated in order:

1. **Input policies** - Top to bottom
   - First `deny` stops execution
   - `warn` actions continue

2. **Endpoint execution** - If input policies pass

3. **Output policies** - Top to bottom
   - All matching policies applied
   - Fields filtered cumulatively

## SQL User Functions

Access user context in SQL queries:

```sql
SELECT *
FROM data
WHERE
  department = mxcp_user_role()
  OR mxcp_user_role() = 'admin'
```

Available functions:
- `mxcp_user_id()` - User ID
- `mxcp_user_email()` - User email
- `mxcp_user_role()` - User role

## Best Practices

### 1. Default Deny
Start restrictive, then allow:

```yaml
input:
  - condition: "true"  # Default deny all
    action: deny
    reason: "Access denied by default"

  - condition: "'data.read' in user.permissions"
    action: allow
```

### 2. Clear Reasons
Provide helpful error messages:

```yaml
# Good
reason: "Finance role required. Contact your manager for access."

# Avoid
reason: "Denied"
```

### 3. Layer Policies
Use multiple policies for clarity:

```yaml
input:
  # Authentication check
  - condition: "user.id == ''"
    action: deny
    reason: "Authentication required"

  # Role check
  - condition: "user.role == 'guest'"
    action: deny
    reason: "Guest access not allowed"

  # Permission check
  - condition: "!('data.read' in user.permissions)"
    action: deny
    reason: "Missing data.read permission"
```

### 4. Use Sensitive Markers
Mark sensitive fields in schema:

```yaml
return:
  type: object
  properties:
    ssn:
      type: string
      sensitive: true  # Easy to filter with filter_sensitive_fields
```

### 5. Test Thoroughly
Test all user roles and edge cases.

## Troubleshooting

### "Policy evaluation failed"
- Check condition syntax
- Verify user context fields exist
- Test with debug mode

### "Field not filtered"
- Verify field name matches exactly
- Check policy condition evaluates correctly
- Ensure policy order is correct

### "Unexpected deny"
- Review policy conditions
- Check user context values
- Use `--debug` flag

## Next Steps

- [Authentication](authentication) - Configure user context source
- [Auditing](auditing) - Log policy decisions
- [Testing](/quality/testing) - Test policies comprehensively
