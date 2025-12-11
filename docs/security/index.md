---
title: "Security"
description: "Enterprise security features in MXCP: OAuth authentication, policy enforcement, and audit logging for compliance."
sidebar:
  order: 1
---

> **Related Topics:** [Configuration](/operations/configuration) (secrets setup) | [Deployment](/operations/deployment) (production security) | [Common Tasks](/reference/common-tasks#security) (quick how-to)

MXCP provides enterprise-grade security features for production AI applications. This section covers authentication, authorization, and audit capabilities.

## Security Features

### Authentication
Control who can access your MCP server:
- **OAuth 2.0** - GitHub, Atlassian, Salesforce, Google, Keycloak
- **Session Management** - Secure token handling with persistence
- **Stateless Mode** - For serverless deployments

[Learn about authentication →](authentication)

### Policies
Control what users can do and see:
- **Input Policies** - Block unauthorized requests
- **Output Policies** - Filter sensitive data
- **CEL Expressions** - Flexible condition evaluation

[Learn about policies →](policies)

### Audit Logging
Track all operations for compliance:
- **Complete Trail** - Every operation logged
- **User Attribution** - Who did what and when
- **Query Interface** - Search and analyze logs

[Learn about auditing →](auditing)

## Security Model

MXCP implements a layered security model:

```mermaid
flowchart TB
    Request["Request"]

    Auth["**Authentication**<br/>OAuth token validation<br/>Session verification<br/>User identity extraction"]

    Input["**Input Policies**<br/>Role-based access control<br/>Permission checks<br/>Parameter validation"]

    Exec["**Execution**<br/>SQL or Python code<br/>Database operations"]

    Output["**Output Policies**<br/>Field filtering<br/>Data masking<br/>Sensitive data protection"]

    Audit["**Audit Logging**<br/>Request details<br/>User context<br/>Execution result"]

    Response["Response"]

    Request --> Auth
    Auth --> Input
    Input --> Exec
    Exec --> Output
    Output --> Audit
    Audit --> Response
```

## Quick Start

### Enable Authentication

Add to your user configuration (`~/.mxcp/config.yml`):

```yaml
mxcp: 1
projects:
  my-project:
    profiles:
      default:
        auth:
          provider: github
          github:
            client_id: your_client_id
            client_secret: your_client_secret
```

### Add Policies

In your endpoint definition:

```yaml
tool:
  name: sensitive_data
  # ...

policies:
  input:
    - condition: "user.role != 'admin'"
      action: deny
      reason: "Admin access required"

  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["salary", "ssn"]
```

### Enable Audit Logging

In `mxcp-site.yml`:

```yaml
profiles:
  default:
    audit:
      enabled: true
      path: audit/logs.jsonl
```

## Best Practices

### 1. Defense in Depth
Use multiple security layers:
- Authentication (who is the user)
- Authorization (what can they do)
- Data filtering (what can they see)
- Audit logging (what did they do)

### 2. Least Privilege
Grant minimum necessary permissions:
```yaml
# Only allow specific permissions
condition: "'data.read' in user.permissions"
```

### 3. Mark Sensitive Data
Use `sensitive: true` for PII:
```yaml
return:
  type: object
  properties:
    ssn:
      type: string
      sensitive: true
```

### 4. Log Everything in Production
Enable audit logging for compliance:
```yaml
audit:
  enabled: true
  path: /var/log/mxcp/audit.jsonl
```

### 5. Regular Log Review
Monitor for anomalies:
```bash
mxcp log --policy deny --since 24h
mxcp log --status error --since 1h
```

## Compliance

MXCP's security features support various compliance requirements:

| Requirement | MXCP Feature |
|-------------|--------------|
| Access Control | OAuth + Policies |
| Data Protection | Sensitive field filtering |
| Audit Trail | Comprehensive logging |
| Data Minimization | Output policies |
| User Consent | Policy enforcement |

## Security Considerations

### Transport Security
- Use HTTPS in production
- Configure TLS for HTTP transport
- Secure WebSocket connections

### Secret Management
- Never commit secrets to version control
- Use Vault or 1Password integration
- Rotate secrets regularly

### Database Security
- Use read-only mode when appropriate
- Limit DuckDB file permissions
- Regular backups

### Network Security
- Restrict network access
- Use firewalls appropriately
- Monitor for suspicious activity

## Next Steps

- [Authentication](authentication) - Configure OAuth providers
- [Policies](policies) - Implement access control
- [Auditing](auditing) - Set up audit logging
