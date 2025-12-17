---
title: "Data Management Example"
description: "Build a user management system with MXCP. CRUD operations, pagination, policies, and data resources."
sidebar:
  order: 4
---

Build a user management system that lets AI assistants create, read, update, and list users with proper access control.

## What You'll Learn

- CRUD operations with SQL tools
- Pagination for list endpoints
- Input policies for authorization
- Resources for direct data access
- Soft delete patterns

## Project Structure

```
data-management/
├── mxcp-site.yml
├── sql/
│   └── setup.sql
├── tools/
│   ├── create_user.yml
│   ├── get_user.yml
│   ├── update_user.yml
│   ├── delete_user.yml
│   └── list_users.yml
├── resources/
│   └── user.yml
└── prompts/
    └── admin.yml
```

## Configuration

```yaml title="mxcp-site.yml"
mxcp: 1
project: data-management
profile: default

profiles:
  default:
    duckdb:
      path: data/users.duckdb

extensions:
  - json
```

## Schema Setup

```sql title="sql/setup.sql"
CREATE SEQUENCE IF NOT EXISTS user_id_seq START 100;

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    name VARCHAR NOT NULL,
    role VARCHAR DEFAULT 'user',
    status VARCHAR DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Test data
INSERT INTO users (id, email, name, role, status) VALUES
    (1, 'alice@example.com', 'Alice Johnson', 'admin', 'active'),
    (2, 'bob@example.com', 'Bob Smith', 'user', 'active'),
    (3, 'carol@example.com', 'Carol Davis', 'manager', 'active'),
    (4, 'dan@example.com', 'Dan Wilson', 'user', 'inactive'),
    (5, 'eve@example.com', 'Eve Brown', 'user', 'active');
```

## CRUD Pattern Overview

| Operation | Tool | HTTP Analog | Idempotent? |
|-----------|------|-------------|-------------|
| Create | `create_user` | POST | No |
| Read | `get_user` | GET | Yes |
| Update | `update_user` | PATCH | Yes |
| Delete | `delete_user` | DELETE | Yes |
| List | `list_users` | GET (collection) | Yes |

**When to use Resources vs Tools:**
- Use **Resources** (`users://{id}`) for simple, direct data retrieval
- Use **Tools** (`get_user`) when you need validation, complex logic, or multiple lookup methods

## Tools

### Create User

Creates a new user. Only admins can create users.

```yaml title="tools/create_user.yml"
mxcp: 1
tool:
  name: create_user
  description: Create a new user account
  tags: ["users", "create"]
  annotations:
    readOnlyHint: false
    idempotentHint: false

  parameters:
    - name: email
      type: string
      format: email
      description: User email address
    - name: name
      type: string
      description: User full name
    - name: role
      type: string
      enum: ["user", "admin", "manager"]
      default: "user"
      description: User role

  return:
    type: object
    properties:
      id:
        type: integer
      email:
        type: string
      name:
        type: string
      role:
        type: string

  policies:
    input:
      - condition: "user.role != 'admin'"
        action: deny
        reason: "Only admins can create users"

  source:
    code: |
      INSERT INTO users (id, email, name, role)
      VALUES (nextval('user_id_seq'), $email, $name, $role)
      RETURNING id, email, name, role

  tests:
    - name: create_basic_user
      arguments:
        - key: email
          value: "newuser@example.com"
        - key: name
          value: "New User"
      user_context:
        role: admin
      result_contains:
        email: "newuser@example.com"
        role: "user"
```

### Get User

Retrieve a user by ID or email.

```yaml title="tools/get_user.yml"
mxcp: 1
tool:
  name: get_user
  description: Get user by ID or email
  tags: ["users", "read"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: user_id
      type: integer
      default: null
      description: User ID
    - name: email
      type: string
      default: null
      description: User email

  return:
    type: object
    properties:
      id:
        type: integer
      email:
        type: string
      name:
        type: string
      role:
        type: string
      status:
        type: string

  source:
    code: |
      SELECT id, email, name, role, status
      FROM users
      WHERE ($user_id IS NOT NULL AND id = $user_id)
         OR ($email IS NOT NULL AND email = $email)
      LIMIT 1

  tests:
    - name: get_by_id
      arguments:
        - key: user_id
          value: 1
      result_contains:
        id: 1
        name: "Alice Johnson"

    - name: get_by_email
      arguments:
        - key: email
          value: "bob@example.com"
      result_contains:
        email: "bob@example.com"
        name: "Bob Smith"
```

### Update User

Update user fields. Users can update their own profile; admins can update anyone.

```yaml title="tools/update_user.yml"
mxcp: 1
tool:
  name: update_user
  description: Update user information
  tags: ["users", "update"]
  annotations:
    readOnlyHint: false
    idempotentHint: true

  parameters:
    - name: user_id
      type: integer
      description: User ID to update
    - name: name
      type: string
      default: null
      description: New name (optional)
    - name: role
      type: string
      default: null
      description: New role (user, admin, or manager - admin only)
    - name: status
      type: string
      default: null
      description: New status (active or inactive)

  return:
    type: object
    properties:
      success:
        type: boolean
      id:
        type: integer
      name:
        type: string
      role:
        type: string
      status:
        type: string

  policies:
    input:
      - condition: "user.role != 'admin' && input.role != null"
        action: deny
        reason: "Only admins can change roles"

  source:
    code: |
      UPDATE users
      SET name = COALESCE($name, name),
          role = COALESCE($role, role),
          status = COALESCE($status, status),
          updated_at = CURRENT_TIMESTAMP
      WHERE id = $user_id
      RETURNING true as success, id, name, role, status

  tests:
    - name: update_name
      arguments:
        - key: user_id
          value: 2
        - key: name
          value: "Robert Smith"
      user_context:
        role: admin
      result_contains:
        success: true
        name: "Robert Smith"
```

### Delete User

Soft delete - sets status to 'deleted' rather than removing the record.

```yaml title="tools/delete_user.yml"
mxcp: 1
tool:
  name: delete_user
  description: Delete a user (soft delete)
  tags: ["users", "delete"]
  annotations:
    readOnlyHint: false
    destructiveHint: true

  parameters:
    - name: user_id
      type: integer
      description: User ID to delete

  return:
    type: object
    properties:
      success:
        type: boolean
      user_id:
        type: integer
      deletion_type:
        type: string

  policies:
    input:
      - condition: "user.role != 'admin'"
        action: deny
        reason: "Only admins can delete users"

  source:
    code: |
      UPDATE users
      SET status = 'deleted',
          updated_at = CURRENT_TIMESTAMP
      WHERE id = $user_id AND status != 'deleted'
      RETURNING
        true as success,
        id as user_id,
        'soft' as deletion_type

  tests:
    - name: soft_delete
      arguments:
        - key: user_id
          value: 4
      user_context:
        role: admin
      result_contains:
        success: true
        deletion_type: "soft"
```

### List Users

Paginated user listing with filters.

```yaml title="tools/list_users.yml"
mxcp: 1
tool:
  name: list_users
  description: List users with filtering and pagination
  tags: ["users", "list"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: status
      type: string
      enum: ["all", "active", "inactive", "deleted"]
      default: "active"
      description: Filter by status
    - name: role
      type: string
      enum: ["all", "user", "admin", "manager"]
      default: "all"
      description: Filter by role
    - name: page
      type: integer
      default: 1
      minimum: 1
      description: Page number
    - name: page_size
      type: integer
      default: 10
      minimum: 1
      maximum: 100
      description: Results per page

  return:
    type: array
    items:
      type: object
      properties:
        id:
          type: integer
        email:
          type: string
        name:
          type: string
        role:
          type: string
        status:
          type: string

  source:
    code: |
      SELECT id, email, name, role, status
      FROM users
      WHERE ($status = 'all' OR status = $status)
        AND ($role = 'all' OR role = $role)
      ORDER BY id
      LIMIT $page_size
      OFFSET ($page - 1) * $page_size

  tests:
    - name: list_active_users
      arguments: []
      result_contains_item:
        email: "alice@example.com"

    - name: filter_by_role
      arguments:
        - key: role
          value: "admin"
      result_contains_item:
        role: "admin"
```

## Resources

### User Resource

Direct access to user data via URI pattern.

```yaml title="resources/user.yml"
mxcp: 1
resource:
  uri: users://{user_id}
  name: User Profile
  description: Get user profile by ID

  parameters:
    - name: user_id
      type: integer
      description: User ID

  return:
    type: object
    properties:
      id:
        type: integer
      email:
        type: string
      name:
        type: string
      role:
        type: string
      status:
        type: string

  source:
    code: |
      SELECT id, email, name, role, status
      FROM users
      WHERE id = $user_id

  tests:
    - name: get_user_resource
      arguments:
        - key: user_id
          value: 1
      result_contains:
        id: 1
        email: "alice@example.com"
```

## Prompt

Guide the AI for user management tasks.

```yaml title="prompts/admin.yml"
mxcp: 1
prompt:
  name: admin
  description: User administration assistant

  parameters:
    - name: task
      type: string
      description: The admin task to perform

  messages:
    - role: user
      type: text
      prompt: |
        You are a user administration assistant. Help with the following task.

        **Available tools:**
        - `create_user`: Create new users (requires admin role)
        - `get_user`: Look up users by ID or email
        - `update_user`: Modify user details
        - `delete_user`: Remove users (soft delete)
        - `list_users`: List and filter users
        - `users://{user_id}`: Direct user profile access

        **Guidelines:**
        - Always verify user exists before updating/deleting
        - Use list_users to find users when ID is unknown
        - Respect role-based permissions

        **Task:** {{task}}
```

## Running the Example

```bash
# Setup
mxcp query --file sql/setup.sql
mxcp validate
mxcp test

# Create a user (requires admin context)
mxcp run tool create_user \
  --param email=frank@example.com \
  --param name="Frank Miller" \
  --user-context '{"role": "admin"}'

# Get a user
mxcp run tool get_user --param user_id=1
mxcp run tool get_user --param email=bob@example.com

# Update a user (requires admin context for role changes)
mxcp run tool update_user \
  --param user_id=2 \
  --param name="Robert Smith" \
  --user-context '{"role": "admin"}'

# List users with pagination
mxcp run tool list_users --param status=active --param page=1

# Access user resource directly
mxcp run resource "users://{user_id}" --param user_id=1

# Start server
mxcp serve
```

## Policy Testing

Test that policies are enforced correctly:

```bash
# This should fail - non-admin trying to create user
mxcp run tool create_user \
  --param email=test@example.com \
  --param name="Test" \
  --user-context '{"role": "user"}'
# Expected: Policy enforcement failed: Only admins can create users

# This should fail - non-admin trying to change role
mxcp run tool update_user \
  --param user_id=2 \
  --param role=admin \
  --user-context '{"role": "user"}'
# Expected: Policy enforcement failed: Only admins can change roles
```

## Next Steps

- [Customer Service Example](/examples/customer-service) - Complex policies
- [Analytics Example](/examples/analytics) - Reporting and dashboards
- [Policies](/security/policies) - Access control patterns
