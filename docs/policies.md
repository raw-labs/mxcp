# Policy Enforcement

MXCP supports policy enforcement to control access to endpoints and filter sensitive data based on user context. Policies are defined using the Common Expression Language (CEL) and can be applied at both input and output stages of endpoint execution.

## Overview

Policy enforcement allows you to:

- **Control access** to endpoints based on user roles, permissions, or other attributes
- **Filter sensitive fields** from responses based on user context
- **Mask sensitive data** instead of removing it completely
- **Implement fine-grained authorization** beyond simple authentication

## Policy Configuration

Policies are defined in the endpoint YAML files using the `policies` section:

```yaml
mxcp: '1.0.0'

tool:
  name: employee_profile
  parameters:
    - name: employee_id
      type: string
      description: Employee ID
  return:
    type: object
    properties:
      id: { type: string }
      name: { type: string }
      email: { type: string }
      salary: { type: number }
      ssn: { type: string }
  source:
    file: sql/employee_profile.sql

policies:
  input:
    - condition: "user.role == 'guest'"
      action: deny
      reason: "Guests cannot query employee profiles."
    
    - condition: "!('employee.read' in user.permissions)"
      action: deny
      reason: "Missing 'employee.read' permission."
  
  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["salary", "ssn"]
      reason: "Hide sensitive fields from non-admin users."
    
    - condition: "response.email.endsWith('@sensitive.com')"
      action: deny
      reason: "Emails from sensitive.com must not be exposed."
```

## Policy Structure

### Input Policies

Input policies are evaluated before the endpoint executes. They have access to:

- **User context** (available as `user` in CEL expressions)
- **All query parameters** (available at the top level)

Available actions for input policies:
- `deny`: Blocks the request and returns an error with the specified reason

### Output Policies

Output policies are evaluated after the endpoint executes but before returning the response. They have access to:

- **User context** (available as `user`)
- **Response data** (available as `response`)

Available actions for output policies:
- `deny`: Blocks the response and returns an error
- `filter_fields`: Removes specified fields from the response
- `mask_fields`: Replaces field values with `"****"`

## User Context

The user context object available in CEL expressions contains:

```json
{
  "user_id": "123",              // Unique user identifier
  "username": "john.doe",        // Username
  "email": "john@example.com",   // Email address
  "name": "John Doe",           // Display name
  "provider": "github",         // Auth provider (github, atlassian, cli)
  "role": "admin",             // User role (from raw_profile)
  "permissions": ["read", "write"]  // User permissions (from raw_profile)
}
```

For anonymous users (when no authentication is configured), the user context defaults to:

```json
{
  "role": "anonymous",
  "permissions": [],
  "user_id": null,
  "username": null,
  "email": null,
  "provider": null
}
```

## CEL Context Structure

### Input Policies

For input policies, the CEL evaluation context contains:

- **`user`** - User context object (see above)
- **All query parameters at the top level** - Direct access to endpoint parameters

Example context for an endpoint with parameters `employee_id` and `department`:
```json
{
  "user": {
    "user_id": "123",
    "role": "admin",
    "permissions": ["employee.read"]
  },
  "employee_id": "emp456",
  "department": "engineering"
}
```

This means you can reference query parameters directly:
```yaml
# Check if user is viewing their own profile
condition: "employee_id != user.user_id && user.role != 'admin'"
```

### Output Policies

For output policies, the CEL evaluation context contains:

- **`user`** - User context object
- **`response`** - The complete response data from the endpoint

Example context for an employee endpoint response:
```json
{
  "user": {
    "user_id": "123",
    "role": "user",
    "permissions": ["employee.read"]
  },
  "response": {
    "id": "emp456",
    "name": "John Doe",
    "department": "HR",
    "salary": 95000,
    "ssn": "123-45-6789"
  }
}
```

This allows policies based on response content:
```yaml
# Filter salary for HR department employees viewed by non-HR users
condition: "response.department == 'HR' && user.role != 'hr_manager'"
action: filter_fields
fields: ["salary"]
```

### Variable Namespacing

**Important**: There is no overlap between user context and query parameters/response data because:

1. **User context is always nested under `user`**
2. **Query parameters are available at the top level** (input policies only)
3. **Response data is nested under `response`** (output policies only)

This prevents naming conflicts. For example, if an endpoint has a parameter called `role`, it won't conflict with `user.role`:

```yaml
# This condition checks the user's role vs a query parameter
condition: "user.role == 'admin' && role == 'manager'"
```

## Field Filtering and Masking Behavior

### Non-existent Fields

When using `filter_fields` or `mask_fields` actions, **non-existent fields are silently ignored**. This allows you to define consistent policies across endpoints that may have different schemas:

```yaml
# This policy works on any endpoint, even if some fields don't exist
output:
  - condition: "user.role != 'admin'"
    action: filter_fields
    fields: ["salary", "ssn", "internal_notes", "performance_rating"]
    # Only existing fields will be filtered
```

This behavior is thoroughly tested in the test suite to ensure reliability across different endpoint schemas.

### Data Structure Support

Field operations work with:

- **Single objects** (dictionaries)
- **Arrays of objects** (list of dictionaries)
- **Scalar values** (passed through unchanged)

Example with array data:
```yaml
# Will filter 'salary' from each employee object in the array
output:
  - condition: "user.role != 'hr_manager'"
    action: filter_fields
    fields: ["salary"]
```

### Masking Behavior

The `mask_fields` action replaces field values with the string `"****"`:

```yaml
# Original: {"ssn": "123-45-6789", "phone": "555-1234"}
# After masking: {"ssn": "****", "phone": "****"}
output:
  - condition: "!('pii.view' in user.permissions)"
    action: mask_fields
    fields: ["ssn", "phone"]
```

## CEL Expression Examples

### Basic Role Checks

```yaml
# Allow only admins
condition: "user.role == 'admin'"

# Allow users and admins, but not guests
condition: "user.role in ['user', 'admin']"

# Deny anonymous users
condition: "user.user_id == null"
```

### Permission Checks

```yaml
# Check for specific permission
condition: "'employee.read' in user.permissions"

# Check for multiple permissions
condition: "'employee.read' in user.permissions && 'employee.write' in user.permissions"

# Check for any of several permissions
condition: "user.permissions.exists(p, p in ['admin', 'manager'])"
```

### Parameter-based Policies

```yaml
# Allow users to only query their own profile
condition: "employee_id != user.user_id && user.role != 'admin'"
action: deny
reason: "Users can only view their own profile"

# Restrict date ranges for non-admins
condition: "user.role != 'admin' && (end_date - start_date).getDays() > 30"
action: deny
reason: "Non-admins can only query up to 30 days of data"
```

### Output-based Policies

```yaml
# Filter fields based on response content
condition: "response.department == 'HR' && user.role != 'hr_manager'"
action: filter_fields
fields: ["salary", "performance_rating"]

# Mask PII for non-privileged users
condition: "!('pii.view' in user.permissions)"
action: mask_fields
fields: ["ssn", "phone", "address"]
```

## Using Policies with Different Commands

### With `mxcp serve`

When running MXCP in server mode with authentication enabled, the user context is automatically populated from the OAuth token:

```bash
mxcp serve --profile production
```

The auth middleware will extract user information and make it available to policies.

### With `mxcp run`

For command-line execution, you can provide user context manually:

```bash
# Inline JSON
mxcp run tool employee_profile \
  --param employee_id=123 \
  --user-context '{"user_id": "456", "role": "admin", "permissions": ["employee.read"]}'

# From file
mxcp run tool employee_profile \
  --param employee_id=123 \
  --user-context @user_context.json
```

Example `user_context.json`:
```json
{
  "user_id": "456",
  "username": "admin.user",
  "email": "admin@company.com",
  "role": "admin",
  "permissions": ["employee.read", "employee.write", "pii.view"]
}
```

### With `mxcp test`

Currently, the test command doesn't support user context. Tests run without policy enforcement to ensure they can validate the raw endpoint behavior.

## Best Practices

### 1. Fail Secure

Always default to denying access when in doubt:

```yaml
# Good: Explicitly allow known roles
condition: "user.role in ['admin', 'manager', 'user']"
action: deny
reason: "Unknown role"

# Bad: Only deny specific roles (might miss new roles)
condition: "user.role == 'guest'"
action: deny
```

### 2. Layer Your Policies

Use multiple policies for defense in depth:

```yaml
input:
  # First check authentication
  - condition: "user.user_id == null"
    action: deny
    reason: "Authentication required"
  
  # Then check role
  - condition: "user.role == 'guest'"
    action: deny
    reason: "Guests not allowed"
  
  # Finally check specific permissions
  - condition: "!('resource.access' in user.permissions)"
    action: deny
    reason: "Missing required permission"
```

### 3. Consistent Field Filtering

Apply the same filtering rules across related endpoints:

```yaml
# In all employee-related endpoints
output:
  - condition: "user.role != 'hr_manager'"
    action: filter_fields
    fields: ["salary", "ssn", "performance_rating"]
```

### 4. Meaningful Error Messages

Provide clear reasons for policy denials:

```yaml
# Good: Specific and actionable
reason: "Only HR managers can view salary information"

# Bad: Generic
reason: "Access denied"
```

### 5. Test Your Policies

Test policies with different user contexts:

```bash
# Test as regular user
mxcp run tool employee_profile \
  --param employee_id=123 \
  --user-context '{"role": "user", "permissions": ["employee.read"]}'

# Test as admin
mxcp run tool employee_profile \
  --param employee_id=123 \
  --user-context '{"role": "admin", "permissions": ["employee.read", "pii.view"]}'

# Test as guest (should be denied)
mxcp run tool employee_profile \
  --param employee_id=123 \
  --user-context '{"role": "guest", "permissions": []}'
```

## Advanced Examples

### Dynamic Field Filtering Based on Relationship

```yaml
output:
  # Users can see full details of their direct reports
  - condition: |
      user.role == 'manager' && 
      !response.exists(r, r.manager_id == user.user_id)
    action: filter_fields
    fields: ["salary", "performance_rating", "personal_goals"]
```

### Time-based Access Control

```yaml
input:
  # Restrict access during off-hours for non-admins
  - condition: |
      user.role != 'admin' && 
      (timestamp.now().getHours() < 8 || timestamp.now().getHours() > 18)
    action: deny
    reason: "Access restricted to business hours (8 AM - 6 PM)"
```

### Conditional Data Masking

```yaml
output:
  # Mask data based on multiple conditions
  - condition: |
      response.security_clearance > user.security_clearance ||
      (response.classified && !('classified.view' in user.permissions))
    action: mask_fields  
    fields: ["details", "location", "contacts"]
```

## Troubleshooting

### Policy Not Being Applied

1. Check that the endpoint YAML has valid syntax
2. Verify the condition expression is valid CEL
3. Check logs for policy evaluation errors
4. Ensure user context is being passed correctly

### CEL Expression Errors

Common issues:
- String comparisons are case-sensitive
- Use `in` for list membership, not `contains`
- Null checks should use `== null`, not `!exists`

### Performance Considerations

- Keep CEL expressions simple for better performance
- Filter fields at the output stage rather than fetching and then denying
- Consider caching policy evaluation results for repeated queries