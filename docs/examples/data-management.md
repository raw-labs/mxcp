---
title: "Data Management Example"
description: "Complete MXCP example for data management. CRUD operations, user management, document storage, and batch processing."
sidebar:
  order: 4
---

This example demonstrates a data management MXCP project with CRUD operations, user management, and document handling.

## Project Structure

```
data-management/
├── mxcp-site.yml
├── tools/
│   ├── users/
│   │   ├── create_user.yml
│   │   ├── get_user.yml
│   │   ├── update_user.yml
│   │   ├── delete_user.yml
│   │   └── list_users.yml
│   ├── documents/
│   │   ├── upload_document.yml
│   │   ├── get_document.yml
│   │   └── search_documents.yml
│   └── batch/
│       ├── import_data.yml
│       └── export_data.yml
├── resources/
│   ├── user.yml
│   └── document.yml
├── sql/
│   └── setup.sql
└── python/
    ├── users.py
    └── documents.py
```

## Configuration

```yaml
# mxcp-site.yml
mxcp: 1
project: data-management
profile: default

profiles:
  default:
    duckdb:
      path: data/data.duckdb

extensions:
  - json
  - parquet
```

## Schema Setup

```sql
-- sql/setup.sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    name VARCHAR NOT NULL,
    role VARCHAR DEFAULT 'user',
    status VARCHAR DEFAULT 'active',
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    owner_id INTEGER REFERENCES users(id),
    title VARCHAR NOT NULL,
    content TEXT,
    mime_type VARCHAR DEFAULT 'text/plain',
    tags JSON,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    action VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    entity_id INTEGER,
    old_value JSON,
    new_value JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE user_id_seq START 1;
CREATE SEQUENCE document_id_seq START 1;
CREATE SEQUENCE audit_id_seq START 1;
```

## User Management Tools

### Create User

```yaml
# tools/users/create_user.yml
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
    - name: metadata
      type: object
      default: null
      description: Additional user metadata

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
      created_at:
        type: string

  policies:
    input:
      - condition: "user.role != 'admin'"
        action: deny
        reason: "Only admins can create users"
      - condition: "input.role == 'admin' && user.permissions not contains 'users:create:admin'"
        action: deny
        reason: "Cannot create admin users without permission"

  source:
    file: ../../python/users.py
    function: create_user

  tests:
    - name: create_basic_user
      arguments:
        - key: email
          value: "test@example.com"
        - key: name
          value: "Test User"
      user_context:
        role: admin
      result_contains:
        email: "test@example.com"
        role: "user"

    # Policy denial tests are done via CLI:
    # mxcp run tool create_user --param email=test@example.com --param name=Test --user-context '{"role": "user"}'
    # Expected: Policy enforcement failed: Only admins can create users
```

### Get User

```yaml
# tools/users/get_user.yml
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
      metadata:
        type: object
      created_at:
        type: string
      updated_at:
        type: string

  source:
    code: |
      SELECT
        id,
        email,
        name,
        role,
        status,
        metadata,
        strftime(created_at, '%Y-%m-%d %H:%M:%S') as created_at,
        strftime(updated_at, '%Y-%m-%d %H:%M:%S') as updated_at
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

    - name: get_by_email
      arguments:
        - key: email
          value: "test@example.com"
      result_contains:
        email: "test@example.com"
```

### Update User

```yaml
# tools/users/update_user.yml
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
      enum: ["user", "admin", "manager"]
      default: null
      description: New role (optional)
    - name: status
      type: string
      enum: ["active", "inactive", "suspended"]
      default: null
      description: New status (optional)
    - name: metadata
      type: object
      default: null
      description: New metadata (optional)

  return:
    type: object
    properties:
      success:
        type: boolean
      user_id:
        type: integer
      updated_fields:
        type: array
        items:
          type: string

  policies:
    input:
      - condition: "user.role != 'admin' && input.user_id != user.id"
        action: deny
        reason: "Can only update own profile"
      - condition: "user.role != 'admin' && input.role != null"
        action: deny
        reason: "Only admins can change roles"

  source:
    file: ../../python/users.py
    function: update_user
```

### Delete User

```yaml
# tools/users/delete_user.yml
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
    - name: hard_delete
      type: boolean
      default: false
      description: Permanently delete (admin only)

  return:
    type: object
    properties:
      success:
        type: boolean
      user_id:
        type: integer
      deletion_type:
        type: string
        enum: ["soft", "hard"]

  policies:
    input:
      - condition: "user.role != 'admin'"
        action: deny
        reason: "Only admins can delete users"
      - condition: "input.hard_delete && user.permissions not contains 'users:hard_delete'"
        action: deny
        reason: "Hard delete requires special permission"

  source:
    code: |
      WITH deletion AS (
        UPDATE users
        SET status = CASE WHEN $hard_delete THEN 'deleted' ELSE 'inactive' END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $user_id
        RETURNING id
      )
      SELECT
        COUNT(*) > 0 as success,
        $user_id as user_id,
        CASE WHEN $hard_delete THEN 'hard' ELSE 'soft' END as deletion_type
      FROM deletion
```

### List Users

```yaml
# tools/users/list_users.yml
mxcp: 1
tool:
  name: list_users
  description: List users with filtering and pagination
  tags: ["users", "list"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: role
      type: string
      enum: ["all", "user", "admin", "manager"]
      default: "all"
    - name: status
      type: string
      enum: ["all", "active", "inactive", "suspended"]
      default: "active"
    - name: search
      type: string
      default: null
      description: Search by name or email
    - name: page
      type: integer
      default: 1
      minimum: 1
    - name: page_size
      type: integer
      default: 20
      maximum: 100

  return:
    type: object
    properties:
      users:
        type: array
        items:
          type: object
      total:
        type: integer
      page:
        type: integer
      page_size:
        type: integer
      total_pages:
        type: integer

  source:
    code: |
      WITH filtered AS (
        SELECT *
        FROM users
        WHERE ($role = 'all' OR role = $role)
          AND ($status = 'all' OR status = $status)
          AND ($search IS NULL
               OR name ILIKE '%' || $search || '%'
               OR email ILIKE '%' || $search || '%')
      ),
      paginated AS (
        SELECT *
        FROM filtered
        ORDER BY created_at DESC
        LIMIT $page_size
        OFFSET ($page - 1) * $page_size
      )
      SELECT json_object(
        'users', (SELECT json_group_array(json_object(
          'id', id,
          'email', email,
          'name', name,
          'role', role,
          'status', status
        )) FROM paginated),
        'total', (SELECT COUNT(*) FROM filtered),
        'page', $page,
        'page_size', $page_size,
        'total_pages', CEIL((SELECT COUNT(*) FROM filtered)::FLOAT / $page_size)
      ) as result
```

## Python Implementations

### Users Module

```python
# python/users.py
from mxcp.runtime import db
from typing import Optional
import json

def create_user(email: str, name: str, role: str = "user", metadata: Optional[dict] = None) -> dict:
    # Check if email already exists
    existing = db.execute(
        "SELECT id FROM users WHERE email = $email",
        {"email": email}
    )
    if existing:
        raise ValueError(f"User with email {email} already exists")

    # Get next ID
    next_id = db.execute("SELECT nextval('user_id_seq') as id")[0]["id"]

    # Insert user
    db.execute(
        """
        INSERT INTO users (id, email, name, role, metadata)
        VALUES ($id, $email, $name, $role, $metadata)
        """,
        {
            "id": next_id,
            "email": email,
            "name": name,
            "role": role,
            "metadata": json.dumps(metadata) if metadata else None
        }
    )

    # Return created user
    return db.execute(
        """
        SELECT id, email, name, role,
               strftime(created_at, '%Y-%m-%d %H:%M:%S') as created_at
        FROM users WHERE id = $id
        """,
        {"id": next_id}
    )[0]


def update_user(
    user_id: int,
    name: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[dict] = None
) -> dict:
    # Build update fields
    updates = []
    params = {"user_id": user_id}
    updated_fields = []

    if name is not None:
        updates.append("name = $name")
        params["name"] = name
        updated_fields.append("name")

    if role is not None:
        updates.append("role = $role")
        params["role"] = role
        updated_fields.append("role")

    if status is not None:
        updates.append("status = $status")
        params["status"] = status
        updated_fields.append("status")

    if metadata is not None:
        updates.append("metadata = $metadata")
        params["metadata"] = json.dumps(metadata)
        updated_fields.append("metadata")

    if not updates:
        return {
            "success": False,
            "user_id": user_id,
            "updated_fields": []
        }

    updates.append("updated_at = CURRENT_TIMESTAMP")

    query = f"""
        UPDATE users
        SET {', '.join(updates)}
        WHERE id = $user_id
    """

    db.execute(query, params)

    return {
        "success": True,
        "user_id": user_id,
        "updated_fields": updated_fields
    }
```

### Documents Module

```python
# python/documents.py
from mxcp.runtime import db
from typing import Optional
import json

def upload_document(
    title: str,
    content: str,
    mime_type: str = "text/plain",
    tags: Optional[list] = None
) -> dict:
    # Get current user ID from context (would come from auth in production)
    owner_id = 1  # Default owner for demo

    # Get next document ID
    next_id = db.execute("SELECT nextval('document_id_seq') as id")[0]["id"]

    # Insert document
    db.execute(
        """
        INSERT INTO documents (id, owner_id, title, content, mime_type, tags)
        VALUES ($id, $owner_id, $title, $content, $mime_type, $tags)
        """,
        {
            "id": next_id,
            "owner_id": owner_id,
            "title": title,
            "content": content,
            "mime_type": mime_type,
            "tags": json.dumps(tags) if tags else "[]"
        }
    )

    return {
        "id": next_id,
        "title": title,
        "version": 1
    }


def get_document(document_id: int) -> dict:
    results = db.execute(
        """
        SELECT d.*, u.name as owner_name
        FROM documents d
        JOIN users u ON d.owner_id = u.id
        WHERE d.id = $id
        """,
        {"id": document_id}
    )

    if not results:
        return {"error": f"Document {document_id} not found"}

    return results[0]
```

## Document Management

### Upload Document

```yaml
# tools/documents/upload_document.yml
mxcp: 1
tool:
  name: upload_document
  description: Upload a new document
  tags: ["documents", "create"]
  annotations:
    readOnlyHint: false

  parameters:
    - name: title
      type: string
      description: Document title
    - name: content
      type: string
      description: Document content
    - name: mime_type
      type: string
      default: "text/plain"
      description: MIME type
    - name: tags
      type: array
      items:
        type: string
      default: []
      description: Document tags

  return:
    type: object
    properties:
      id:
        type: integer
      title:
        type: string
      version:
        type: integer

  source:
    file: ../../python/documents.py
    function: upload_document
```

### Search Documents

```yaml
# tools/documents/search_documents.yml
mxcp: 1
tool:
  name: search_documents
  description: Search documents by title, content, or tags
  tags: ["documents", "search"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: query
      type: string
      description: Search query
    - name: tags
      type: array
      items:
        type: string
      default: []
      description: Filter by tags
    - name: owner_id
      type: integer
      default: null
      description: Filter by owner
    - name: limit
      type: integer
      default: 20

  return:
    type: array
    items:
      type: object
      properties:
        id:
          type: integer
        title:
          type: string
        owner_name:
          type: string
        tags:
          type: array
        relevance:
          type: number

  source:
    code: |
      WITH search_results AS (
        SELECT
          d.id,
          d.title,
          u.name as owner_name,
          d.tags,
          -- Simple relevance scoring
          CASE
            WHEN d.title ILIKE $query THEN 3
            WHEN d.title ILIKE '%' || $query || '%' THEN 2
            WHEN d.content ILIKE '%' || $query || '%' THEN 1
            ELSE 0
          END as relevance
        FROM documents d
        JOIN users u ON d.owner_id = u.id
        WHERE (d.title ILIKE '%' || $query || '%'
               OR d.content ILIKE '%' || $query || '%')
          AND ($owner_id IS NULL OR d.owner_id = $owner_id)
      )
      SELECT id, title, owner_name, tags, relevance
      FROM search_results
      WHERE relevance > 0
      ORDER BY relevance DESC, title
      LIMIT $limit
```

## Batch Operations

### Import Data

```yaml
# tools/batch/import_data.yml
mxcp: 1
tool:
  name: import_data
  description: Import data from CSV or JSON
  tags: ["batch", "import"]
  annotations:
    readOnlyHint: false

  parameters:
    - name: source_url
      type: string
      description: URL to import from (CSV or JSON)
    - name: table_name
      type: string
      enum: ["users", "documents"]
      description: Target table
    - name: mode
      type: string
      enum: ["append", "replace"]
      default: "append"
      description: Import mode

  return:
    type: object
    properties:
      success:
        type: boolean
      rows_imported:
        type: integer
      mode:
        type: string

  policies:
    input:
      - condition: "user.role != 'admin'"
        action: deny
        reason: "Only admins can import data"

  source:
    file: ../../python/batch.py
    function: import_data
```

### Export Data

```yaml
# tools/batch/export_data.yml
mxcp: 1
tool:
  name: export_data
  description: Export data to Parquet format
  tags: ["batch", "export"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: table_name
      type: string
      enum: ["users", "documents"]
      description: Table to export
    - name: format
      type: string
      enum: ["parquet", "csv", "json"]
      default: "parquet"

  return:
    type: object
    properties:
      success:
        type: boolean
      file_path:
        type: string
      row_count:
        type: integer

  policies:
    input:
      - condition: "user.role != 'admin' && user.role != 'manager'"
        action: deny
        reason: "Export requires admin or manager role"

  source:
    code: |
      WITH export AS (
        SELECT * FROM (
          SELECT CASE $table_name
            WHEN 'users' THEN (SELECT COUNT(*) FROM users)
            WHEN 'documents' THEN (SELECT COUNT(*) FROM documents)
          END as row_count
        )
      )
      SELECT
        true as success,
        '/exports/' || $table_name || '_' || strftime(NOW(), '%Y%m%d_%H%M%S') || '.' || $format as file_path,
        row_count
      FROM export
```

## Resources

### User Resource

```yaml
# resources/user.yml
mxcp: 1
resource:
  uri: users://{id}
  name: User Resource
  description: Individual user resource
  mimeType: application/json

  parameters:
    - name: id
      type: integer

  return:
    type: object

  source:
    code: |
      SELECT
        id,
        email,
        name,
        role,
        status,
        metadata,
        strftime(created_at, '%Y-%m-%d %H:%M:%S') as created_at,
        strftime(updated_at, '%Y-%m-%d %H:%M:%S') as updated_at
      FROM users
      WHERE id = $id
```

### Document Resource

```yaml
# resources/document.yml
mxcp: 1
resource:
  uri: documents://{id}
  name: Document Resource
  description: Individual document resource
  mimeType: application/json

  parameters:
    - name: id
      type: integer

  return:
    type: object

  policies:
    output:
      - condition: "user.id != result.owner_id && user.role != 'admin'"
        action: filter_fields
        fields: ["content"]
        reason: "Only owner can view full content"

  source:
    code: |
      SELECT
        d.*,
        u.name as owner_name
      FROM documents d
      JOIN users u ON d.owner_id = u.id
      WHERE d.id = $id
```

## Running the Example

```bash
# Initialize database
mxcp query --file sql/setup.sql

# Validate all endpoints
mxcp validate

# Run tests
mxcp test

# Start server
mxcp serve --transport stdio
```

## Example Operations

```bash
# Create a user
mxcp run tool create_user \
  --param email=alice@example.com \
  --param name="Alice Johnson" \
  --param role=user

# List users
mxcp run tool list_users \
  --param status=active \
  --param page=1

# Search documents
mxcp run tool search_documents \
  --param query="meeting notes"

# Export data
mxcp run tool export_data \
  --param table_name=users \
  --param format=parquet
```

## Next Steps

- [Customer Service Example](/examples/customer-service) - Support tools
- [Analytics Example](/examples/analytics) - Business intelligence
- [Policies](/security/policies) - Access control
