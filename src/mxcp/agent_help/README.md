# MXCP Agent Help System

A hierarchical, AI-agent-optimized help system designed for programmatic navigation and understanding of MXCP. This system provides structured, actionable guidance that AI agents can parse and execute without prior MXCP training.

## 🤖 AI Agent Quick Context

**MXCP = SQL-powered MCP server that runs DuckDB under the hood**

### Technology Stack
- **Core Engine**: DuckDB (in-memory/persistent SQL analytics database)
- **Transformation Layer**: dbt (data build tool) for SQL modeling
- **Protocol**: MCP (Model Context Protocol) for AI integration
- **Interface**: SQL queries with parameter injection for safety

### When to Search External Resources
AI agents should search for additional information when encountering:
- **DuckDB concepts**: Extensions, functions, data types, SQL syntax → "DuckDB [concept]"
- **dbt concepts**: Models, sources, macros, configurations → "dbt [concept]"
- **MCP concepts**: Tools, resources, prompts, protocols → "MCP [concept]"
- **SQL patterns**: Complex queries, CTEs, window functions → "SQL [pattern]"

## 🎯 Agent Navigation Strategy

### Priority-Based Access Pattern
```
1. START → mxcp agent-help examples (2-min working code)
2. ISSUES → mxcp agent-help troubleshooting quick-diagnosis
3. DATABASE → mxcp agent-help data-sources databases [db-type]
4. ENDPOINTS → mxcp agent-help endpoints [tool|resource|prompt]
5. SECURITY → mxcp agent-help policies [topic]
```

### Information Architecture
```
agent-help/
├── examples/          🔒 BASIC    # Working code patterns (START HERE)
├── getting-started/   🔒 BASIC    # Project initialization
├── data-sources/      🔒 BASIC    # DuckDB connections & extensions  
├── endpoints/         🔒 BASIC    # SQL-based tools/resources/prompts
├── troubleshooting/   🔒 BASIC    # Error diagnosis & fixes
├── testing/           🔒 MEDIUM   # Validation & security testing
├── deployment/        🔒 MEDIUM   # Server & production setup
├── policies/          🔒 HIGH     # Security & access control
├── integration/       🔒 HIGH     # MCP client connections
├── advanced/          🔒 HIGH     # Secrets, plugins, optimization
└── schemas/           🔒 BASIC    # YAML structure validation
```

## 🔧 Core Technology Integration

### DuckDB as SQL Engine
MXCP translates endpoint parameters into DuckDB SQL queries:

```sql
-- Parameter: $user_id (integer) 
-- Becomes: SELECT * FROM users WHERE id = 123
SELECT * FROM users WHERE id = $user_id
```

**Key DuckDB Features Used**:
- **Extensions**: `postgres_scanner`, `httpfs`, `mysql_scanner`
- **JSON Functions**: `read_json_auto()`, `json_extract()`
- **HTTP Data**: Direct URL querying with `read_csv_auto('https://...')`
- **Memory Management**: Automatic optimization for analytics workloads

### dbt for Data Transformation
Optional but powerful for complex data pipelines:

```yaml
# dbt_project.yml enables SQL models
# models/ contains .sql transformation files
# mxcp automatically detects and runs dbt models
```

### MCP Protocol Layer
MXCP exposes DuckDB results as MCP endpoints:
- **Tools**: Execute SQL, return structured data
- **Resources**: Provide data via URI patterns  
- **Prompts**: Include SQL results in AI context

## 🚨 Agent Security Guidelines

### Parameter Safety (CRITICAL)
```yaml
# ✅ SAFE: Parameterized queries
source:
  code: "SELECT * FROM users WHERE id = $user_id"

# ❌ DANGEROUS: String concatenation
source:  
  code: "SELECT * FROM users WHERE id = '" + $user_id + "'"
```

### Secret Management (CRITICAL)
```yaml
# ✅ SAFE: Environment variables
secrets:
  - name: db_password
    value: ${DB_PASSWORD}

# ❌ DANGEROUS: Hardcoded credentials  
secrets:
  - name: db_password
    value: "mypassword123"
```

## 📋 Agent Command Patterns

### Discovery Commands
```bash
# List all available help
mxcp agent-help

# Get working examples immediately  
mxcp agent-help examples

# Diagnose problems quickly
mxcp agent-help troubleshooting quick-diagnosis
```

### Implementation Commands  
```bash
# Database connection setup
mxcp agent-help data-sources databases [postgres|mysql|csv]

# Create endpoints
mxcp agent-help endpoints [tools|resources|prompts] 

# Security hardening
mxcp agent-help policies access-control
```

### Debugging Commands
```bash
# Validate project structure
mxcp validate

# Test endpoints
mxcp test

# Query DuckDB directly
mxcp query "SELECT version()"
```

## 🔍 Content Structure for Agents

### Predictable YAML Schema
```yaml
category: string
description: string  
technical_context: |        # NEW: Technology background
  DuckDB concepts: [...]
  dbt concepts: [...]
  External search terms: [...]
subcategories:
  - name: string
    description: string
    agent_priority: [high|medium|low]  # NEW: Agent importance
    topics:
      - name: string
        description: string
        content:
          overview: string
          technical_requirements: [...]   # NEW: Tech prerequisites
          code_examples: [...]           # NEW: Copy-paste ready
          verification_commands: [...]    # NEW: Test success
          troubleshooting_commands: [...] # NEW: Debug failures
          external_search_hints: [...]   # NEW: When to search web
```

### JSON Output for Agents
```bash
# Get structured data for parsing
mxcp agent-help examples --json-output

# Example response:
{
  "level": "topic",
  "path": ["examples", "basic", "calculator-tool"],
  "content": {
    "overview": "...",
    "code_examples": [...],
    "verification_commands": [...],
    "external_search_hints": ["DuckDB CASE statements", "SQL parameter injection"]
  },
  "navigation": {
    "parent": "mxcp agent-help examples basic",
    "siblings": ["earthquake-api"],
    "related": ["endpoints tools", "troubleshooting sql-errors"]
  }
}
```

## 🚀 Agent Workflow Optimization

### 1. Fast Start Pattern (2 minutes)
```
agent-help examples basic → copy working code → test immediately
```

### 2. Problem-Solving Pattern  
```
agent-help troubleshooting quick-diagnosis → specific error section → fix
```

### 3. Database Integration Pattern
```
agent-help data-sources → extension setup → connection test → query development
```

### 4. Security Hardening Pattern
```  
agent-help policies → access control → secret management → testing
```

## 📚 External Knowledge Integration

### DuckDB Documentation Triggers
When help content mentions these concepts, agents should search "DuckDB [concept]":
- SQL functions, extensions, data types
- Performance optimization, memory management  
- File formats (Parquet, JSON, CSV)
- HTTP data access, cloud storage

### dbt Documentation Triggers  
When help content mentions these concepts, agents should search "dbt [concept]":
- Models, sources, seeds, snapshots
- Macros, tests, documentation
- Project structure, profiles, deployment
- Incremental models, materialization strategies

### Security Research Triggers
When help content mentions these concepts, agents should search security best practices:
- SQL injection prevention
- Credential management  
- Access control patterns
- HTTPS/TLS configuration

## 🔧 Implementation Notes

### Caching Strategy
```python
# Content is cached for performance
self._content_cache: Dict[str, Any] = {}
self._tech_context_cache: Dict[str, List[str]] = {}  # NEW
```

### Error Handling for Agents
```python
# Structured error responses
{
  "error": "content_not_found",
  "path": ["invalid", "path"],
  "suggestions": ["valid", "alternatives"],
  "search_hints": ["DuckDB concept", "dbt concept"]
}
```

### Progressive Disclosure
1. **Overview**: High-level understanding
2. **Code Examples**: Working implementations  
3. **Technical Details**: DuckDB/dbt specifics
4. **Troubleshooting**: Common issues + fixes
5. **External Resources**: When to search beyond MXCP

## 🎯 Success Metrics for Agents

### Effective Help Usage
- **Time to Working Code**: < 5 minutes from help → running endpoint
- **Error Resolution**: < 3 help lookups to solve common problems  
- **Security Compliance**: 100% parameterized queries, no hardcoded secrets
- **External Search Efficiency**: Clear triggers for DuckDB/dbt documentation

### Quality Indicators
- **Verification Commands**: Every example includes test commands
- **Error Prevention**: Proactive warnings about common mistakes
- **Technology Context**: Clear explanation of underlying systems
- **Search Integration**: Explicit guidance on when to search externally

This help system transforms MXCP from a complex database tool into an accessible, AI-agent-friendly platform with clear guidance on the underlying DuckDB and dbt technologies. 