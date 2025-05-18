# Introduction

RAW is evolving to support the Model Context Protocol (MCP) as a first-class capability — enabling developers to define tools, resources, and prompts in a Git-backed, declarative, and fully testable format. This new direction is built upon the lessons learned from real-world client engagements (notably Vodafone), where the need for local-first workflows, flexible ETL pipelines, and minimal infrastructure became abundantly clear.

With this evolution, we are positioning RAW not just as a SaaS platform, but as a developer toolkit that can be used locally, integrated in CI pipelines, and optionally deployed as a fully managed service. Inspired by tools like dbt, Vercel, and Retool, RAW aims to flip the development model: local-first tooling with optional cloud orchestration.

The goal is simple: clone a repo, run raw serve, and you are up and running — creating a well-governed, testable MCP server that serves SQL-based endpoints from operational data. No external services or coordination layers required.

## Table of Contents

- [Introduction](#introduction)
- [Architecture Overview](#architecture-overview)
  - [DuckDB](#duckdb)
  - [dbt](#dbt)
  - [RAW CLI](#raw-cli)
- [RAW Tool](#raw-tool)
  - [~/.raw/config.yml](#rawconfigyaml)
  - [Repository](#repository)
    - [Site Configuration](#site-configuration)
    - [Endpoint file](#endpoint-file)
- [Type System](#type-system)
- [Commands](#commands)
  - [raw list](#raw-list)
  - [raw validate](#raw-validate-endpoint---profile-profilename)
  - [raw run](#raw-run-endpoint---param_name-param_value----profile-profilename)
  - [raw test](#raw-test-endpoint---profile-profilename)
  - [raw serve](#raw-serve---profile-profilename)
  - [raw drift-init](#raw-drift-init)
  - [raw drift-check](#raw-drift-check)
  - [raw init](#raw-init---project_name---hello-world-folder)
  - [raw dbt-config](#raw-dbt-config)
  - [raw dbt-cron](#raw-dbt-cron)
  - [raw vscode-config](#raw-vscode-config)
  - [raw cloud](#raw-cloud-)
- [Adapters](#adapters)
  - [Declaring Adapters](#declaring-adapters)
  - [Providing Configuration](#providing-configuration)
  - [Runtime Behavior](#runtime-behavior)
  - [Adapter Interface](#adapter-interface)
  - [SQL Usage](#sql-usage)
  - [Package Installation](#package-installation)
- [Integrations](#integrations)
  - [DuckDB](#duckdb-1)
  - [dbt](#dbt-1)
- [Implementation for SaaS](#implementation-for-saas)
  - [SaaS CI](#saas-ci)
  - [SaaS CD](#saas-cd)
- [Questions](#questions)
  - [I find a GitHub repo I like. How do I start using RAW?](#i-find-a-github-repo-i-like-how-do-i-start-using-raw)
- [Exploratory Tasks](#exploratory-tasks)

# Architecture Overview

At its core, the new RAW stack is built around three components:
*	DuckDB: The query and execution engine.
*	dbt: The ETL layer for transforming raw data into usable, efficient models.
* RAW CLI: The orchestration and governance layer that binds everything together.

Together, these components form a powerful yet simple architecture:

```
┌────────┐      ┌────────┐      ┌────────────┐
│  dbt   ├─────►│ DuckDB │◄─────┤  RAW CLI   │
└────────┘      └────────┘      └────────────┘
     ▲                                ▲
     │                                │
  Git repo                    ~/.raw/config.yml
                              + raw-site.yml
```

## DuckDB

DuckDB serves as the runtime glue of the system. It offers:
*	Native support for OLAP-style analytics and columnar data formats (Parquet, CSV, JSON).
*	Optional support for Python UDFs via embedded extensions — enabling domain-specific functions or connectors to be defined inline.
*	Seamless local development and file-based persistence (e.g., .duckdb files) with no server required.

Because of its flexible I/O and extensibility model, DuckDB is ideal for the operational workloads MCP targets. And because the RAW CLI always loads the raw extension into DuckDB, secrets, Python functions, and repository-specific setup are injected automatically.

## dbt

dbt is the engine for ETL: defining transformations as views or materialized tables, expressed in SQL and managed in Git. It is:
*	Declarative and idempotent — great for CI/CD workflows.
*	Compatible with DuckDB (via the dbt-duckdb adapter).
*	Easily integrated into RAW via shared metadata and config files.

In the managed/SaaS model, RAW can take care of running dbt for the user on a schedule via Airflow or Kubernetes cron jobs. In the local-first CLI model, the user simply runs dbt run themselves — all the config and database setup is already done.

## RAW CLI

RAW provides a CLI that:
*	Reads project definitions (raw-site.yml) and secrets (~/.raw/config.yml).
*	Serves endpoints (raw serve) as an MCP-compatible HTTP interface.
*	Validates endpoint definitions and tests them (raw validate, raw test).
*	Integrates with dbt and Python seamlessly.
*	Is designed to be usable locally, in CI/CD pipelines, or in a managed SaaS runtime.

By combining Git, DuckDB, dbt, and RAW, we deliver a complete declarative stack to define and serve enterprise-grade MCP tools — all with zero infrastructure.

In the managed version, RAW simply wraps this exact toolchain in a Kubernetes-native CI/CD orchestrator that connects to GitHub, manages secrets via Vault, and runs raw serve on demand.

## RAW Tool

### `~/.raw/config.yml`

The RAW tool requires a config file in the user account (e.g. ~/.raw/config.yml), which defines user profiles (including FDW database to use, DASes to use, and sources to use in each DAS). (The user can override its location by setting the `RAW_CONFIG` env var.)

An example of the configuration file:

```yaml
raw: "1.0.0"
projects:
  project_a:
    default: dev
    profiles:
      dev:
        secrets:
        - name: my_s3_secret
          type: s3
          parameters:
            KEY_ID: abc
            SECRET: xyz
            REGION: us-east-1
        - name: my_azure_secret
          type: azure
          parameters:
            ACCOUNT_NAME: myaccount
            ACCOUNT_KEY: vault://azure/myaccount/mykey
        - name: http
          type: HTTP
          parameters:
            EXTRA_HTTP_HEADERS:
              Authorization: "Bearer sk_test_VePHdqKTYQjKNInc7u56JBrQ"
        adapter_configs:
          salesforce_config01:
            USERNAME: user@example.com
            PASSWORD: secret
            TOKEN: token123
          salesforce_config02:
            USERNAME: user2@example.com
            PASSWORD: secret2
            TOKEN: token456
vault:
  enabled: true
  address: https://vault.acme.com
  token_env: ${VAULT_TOKEN}
```

The configuration file has the following [schema](../src/raw/config/schemas/raw-config-schema-1.0.0.json).

The configuration strings can either be literal strings, environment variables, or vault URLs. The resolution is as follows:
1. If string matches `${SOME_ENV_VAR}`, then resolve from env
2. Else if string starts with `vault://`, then resolve from Vault
3. Else, then use the literal string

The secret parameters are typically key (string) to value (string). The value, however, may also be a map (string->string) as shown for the http secret type.

### Repository

#### Site Configuration

The root of the repository must contain `raw-site.yml` such as:
```yaml
raw: "1.0.0"  # (Mandatory): Version of the raw-site.yml format

project: project_a         # (Mandatory): Name of the project in ~/.raw/config.yml
profile: prod              # (Mandatory): Profile name under the project

base_url: demo             # (Optional): Deployment base URL (used for endpoint publishing)
enabled: true              # (Optional): Whether to enable this repo in CI/deploy flows

secrets:                   # (Mandatory): List of secret names from ~/.raw/config.yml
  - my_s3_secret
  - my_azure_secret

adapters:
  - name: salesforce01
    package: raw-adapter-salesforce>=1.0.0,<2.0
    config: salesforce_config01

  - name: salesforce02
    package: raw-adapter-salesforce
    secret: salesforce_config02

dbt:
  enabled: true            # (Optional): Whether to enable dbt integration (defaults to true)
  models: ./models         # (Optional): Path to dbt models
  manifest_path: ./target/manifest.json  # (Optional): Path to dbt manifest.json for validation

python:
  path: ./init.py          # (Optional): Python file to import/execute at bootstrap (for custom functions, etc.)

duckdb:
  path: ./.duckdb          # (Optional): Location of the DuckDB file for this repo

drift:
  path: ./.drift.json      # (Optional): Path to RAW schema drift manifest file

cloud:                     # (Optional): SaaS/Cloud-specific settings
  github:
    prefix_with_branch_name: true
    skip_prefix_for_branches:
      - master
      - main
```

The site configuration must conform to the following [schema](../src/raw/config/schemas/raw-site-schema-1.0.0.json).

The `cloud` section is ignored when running locally; it only applies to the managed/SaaS solution.

#### Endpoint file

Each endpoint is defined by a YAML file and typically by an accompaining SQL file.

An example of tool endpoint (with code inlined):
```yaml
raw: "1.0.0"

tool:
  name: filter_users
  enabled: true

  parameters:
    - name: user_id
      type: string
      description: Unique identifier for the user
      format: uuid
      examples: ["550e8400-e29b-41d4-a716-446655440000"]

    - name: signup_date
      type: string
      description: Filter users who signed up after this date
      format: date-time
      examples: ["2023-01-01T00:00:00Z"]

    - name: is_active
      type: boolean
      description: Whether the user is currently active
      default: true
      examples: [true]

    - name: region
      type: string
      description: Geographic region
      enum: [us, eu, apac]
      default: eu
      examples: ["us"]

    - name: tags
      type: array
      description: Tags the user belongs to
      items:
        type: string
        description: Individual tag name
      minItems: 0
      maxItems: 10
      examples: [["beta", "early-access"]]

    - name: preferences
      type: object
      description: User preference settings
      required: [notifications]
      properties:
        notifications:
          type: boolean
          description: Whether notifications are enabled
        theme:
          type: string
          description: Theme selected by the user
          enum: [light, dark]

  return:
    name: result
    type: array
    description: List of user objects
    items:
      name: user
      type: object
      description: A user record
      required: [user_id, email]
      properties:
        user_id:
          type: string
          format: uuid
          description: The user's unique ID
        email:
          type: string
          format: email
          description: The user's email address
        created_at:
          type: string
          format: date-time
          description: The signup timestamp

  source:
    code: |
      SELECT *
      FROM users
      WHERE (user_id = $user_id OR $user_id IS NULL)
        AND signup_date >= $signup_date
        AND is_active = $is_active
        AND region = $region

  tests:
    - name: simple filter test
      description: Filter by region and is_active
      arguments:
        - key: region
          value: us
        - key: is_active
          value: true
      result:
        - user_id: "123"
          email: "user@example.com"
          created_at: "2023-03-01T10:00:00Z"
```

These YAML files must conform to the following [schema](../src/raw/config/schemas/endpoint-schema-1.0.0.json).

Within a parameter definition, if `default` is set, then the argument may is optional.
The `required` field is not to be confused with `default`; instead, `required` (similarly to OpenAPI spec) is to define the inner fields that are required if the parameter is itself an object.

The `cloud` section is ignored when running locally; it only applies to the managed/SaaS solution.

### Type System

RAW’s type system defines how input parameters and return values are described in endpoint definitions. It draws inspiration from multiple schemas — including JSON Schema, OpenAPI, MCP, and AI function calling conventions (e.g. OpenAI). While it borrows structure from these ecosystems, RAW enforces a consistent and validated schema with a clear mapping to SQL/DuckDB types.

#### Supported Types

RAW supports the following base types:

| Type     | Description                         | Example              |
|----------|-------------------------------------|----------------------|
| string   | Text values                         | `"hello"`            |
| number   | Floating-point number               | `3.14`               |
| integer  | Whole number                        | `42`                 |
| boolean  | `true` or `false`                   | `true`               |
| null     | Explicit null (rarely used)         | `null`               |
| array    | Ordered list of elements            | `["a", "b", "c"]`    |
| object   | Key-value structure with schema     | `{ "foo": 1 }`       |

Each type supports standard JSON Schema annotations such as:

- `description`
- `default`
- `examples`
- `enum`
- `required`
- `items` (for arrays)
- `properties` (for objects)
- `minItems`, `maxItems`
- `minLength`, `maxLength`
- `format`

#### Format Annotations

RAW uses `format` annotations to further specialize `string` types into well-defined subtypes. These formats are **mandatory** in certain contexts and are used to control serialization, validation, and SQL/DuckDB type mapping.

| Format     | Description                          | Example                           | Mapped DuckDB Type             |
|------------|--------------------------------------|-----------------------------------|-------------------------------|
| email      | RFC 5322 email address               | `"alice@example.com"`             | `VARCHAR`                     |
| uri        | URI/URL string                       | `"https://raw-labs.com"`          | `VARCHAR`                     |
| date       | ISO 8601 date                        | `"2023-01-01"`                    | `DATE`                        |
| time       | ISO 8601 time                        | `"14:30:00"`                      | `TIME`                        |
| date-time  | ISO 8601 timestamp (Z or offset)     | `"2023-01-01T14:30:00Z"`          | `TIMESTAMP WITH TIME ZONE`    |
| duration   | ISO 8601 duration                    | `"P1DT2H"`                        | `INTERVAL`                    |
| timestamp  | Unix timestamp (seconds since epoch) | `1672531199`                      | `TIMESTAMP` (converted)       |

> **Note:** Format annotations are validated and converted automatically when passed to SQL endpoints. For example, `timestamp` values are transformed into proper DuckDB `TIMESTAMP` types during execution.

#### Unsupported or Limited Schema Features

RAW intentionally restricts schema complexity to promote clarity and compatibility with DuckDB and AI tooling. The following are **not supported**:

- `$ref` (no schema reuse or references)
- `allOf`, `oneOf`, `anyOf` (no union or intersection types)
- `patternProperties`, `pattern` (no regex-based constraints)
- Conditional schemas (`if` / `then`)
- Complex numeric constraints (`multipleOf`, `exclusiveMinimum`, etc.)

This allows RAW endpoints to remain static, serializable, and directly usable in SQL-based execution environments.

## Commands

| Command              | Purpose                                             |
|----------------------|-----------------------------------------------------|
| `raw deps`           | Installs the required RAW adapters via pip.         |
| `raw list`           | Lists all MCP endpoints (tool/resource/prompt)      |
| `raw validate`       | Validates endpoint structure and types              |
| `raw run`            | Runs an endpoint with parameters                    |
| `raw test`           | Runs tests defined in each endpoint YAML            |
| `raw serve`          | Starts the local HTTP server                        |
| `raw drift-init`     | Saves current endpoint schema + test state          |
| `raw drift-check`    | Detects changes vs previous drift snapshot          |
| `raw init`           | Creates a new RAW project folder                    |
| `raw dbt-config`     | Syncs dbt config to match RAW settings              |
| `raw dbt-cron`       | Runs only outdated dbt models                       |
| `raw vscode-config`  | Bootstraps VSCode project config                    |
| `raw cloud ...`      | Reserved for SaaS/managed-mode commands             |

### Endpoints

#### `raw deps`

Description: Install the declared adapter packages via pip.

Actions:
*	Parse package strings from all adapters from ~/.raw/config.yml.
* Run pip install

This is optional: users may prefer pin requirements in requirements.txt or poetry/pipenv and manage these separately.

#### `raw list`

Description: Lists all the endpoints (tools, resources, prompts) defined and currently active in the repo.

Requirements:
* A valid RAW repository (raw-site.yml must exist at repo root).
*	Proper secrets and profile must be resolvable from ~/.raw/config.yml.

Actions:
*	Locate the root directory of the repo (look upward for raw-site.yml).
*	Parse raw-site.yml to find project/profile and secrets used.
*	Load all endpoint files (*.yaml) across all sub-folders.
* Output report with:
  *	Type (tool/resource/prompt)
  *	Path
  *	Enabled/disabled status

Implementation notes:
*	Should be fast and not require a DuckDB connection.
*	Can validate basic YAML schema structure (optional).
* Add optional --json flag to output machine-readable report.

#### `raw validate [<endpoint>] [--profile <profile_name>]`

Description: Validates schema, metadata, and test definitions for one or all endpoints.

Requirements:
* Valid RAW repo and project/profile resolution.
* If dbt is enabled, ensure `dbt ls --select state:modified` is clean (no dirty models).
* RAW DuckDB extension must be loaded (for secret resolution and Python function loading).

Actions:
* Load raw-site.yml and resolve secrets.
* If dbt is enabled, check manifest.json is present and has no dirty state.
* For each endpoint:
  * Parse and validate endpoint schema (YAML).
  * Check types and required parameters.
  * Validate tests blocks.
  * If return schema is defined, validate that structure against mocked output (optional).
* Output report (status, warnings, errors).

Implementation notes:
* Can be extended to catch schema drift issues if integrated with raw drift-check.Valid RAW repo and project/profile resolution.
* If dbt is enabled, ensure dbt ls --select state:modified is clean (no dirty models).
* DuckDB extension must be loaded (for secret resolution).
* Add optional --json flag to output machine-readable report.

#### `raw run <endpoint> [--<param_name> <param_value> ...] [--profile <profile_name>]`

Description: Executes a single endpoint with given parameter values.

Requirements:
* Valid RAW repo and endpoint.
* DuckDB must be available.
* dbt models must be up-to-date (if dbt is enabled).

Actions:
* Resolve DuckDB file and secrets for the profile.
* Load Python bootstrap if defined.
* If source.code: render SQL inline using provided parameters.
* If source.file: load referenced SQL file.
* Execute SQL via DuckDB, inject parameters.
* Return query result.

Implementation notes:
* For testing CLI usage, ensure robust error reporting (invalid param, bad SQL).
* Consider auto-converting CLI args to the expected types from the endpoint schema. Otherwise, accept only JSON payload for parameter value.
* Add optional --json flag to output machine-readable report.

#### `raw test [<endpoint>] [--profile <profile_name>]`

Description: Executes the test cases defined for one or all endpoints.

Requirements:
* Valid RAW repo and endpoints with tests defined.
* dbt models up-to-date if enabled.
* Python and DuckDB environments loaded.

Actions:
* For each endpoint with tests:
  * Load test cases from YAML.
  * For each test:
    * Pass arguments as input.
    * Run endpoint.
    * Compare returned results with expected result.
* Return a structured test report:
  * Passed/failed
  * Error messages (if any)
  * Time taken

Implementation notes:
* Consider leveraging DuckDB for result comparisons.
* Consider large result diffs: support partial match assertions (e.g., row_count == 10) instead of full JSON equality.
* Add optional --json flag to output machine-readable report.
    
### Serve

#### `raw serve [--profile <profile_name>]`

Description: Launches a local MCP-compatible HTTP server exposing endpoints.

Requirements:
* Valid RAW repo
* All required secrets and bootstrap config resolved
* dbt models must be up-to-date (if enabled)

Actions:
* Load all endpoints and validate.
* Build parameter parsing and type checking logic.
* Serve endpoints as REST API over HTTP.
* Support graceful shutdown and log active sessions.

Implementation notes:
* Add internal metrics service: number of calls, avg. latency, etc.
* Support SSE HTTP Streaming and other common transport protocols supported by MCP servers.
* Include drain support to enabled (in SaaS/managed) graceful migration of one RAW server to another.

### Drift 

#### `raw drift-init`

Description: Initializes a drift manifest capturing the current state of schemas and endpoints.

Requirements:
* Valid RAW repo with .duckdb file
* Endpoint and type definitions must be correct

Actions:
* Load all active catalog entries in DuckDb
* For each entry (table, schema):
  * List all tables/columns/column types
* Load all active endpoints
  * Inspect parameters and returned types
  * Run tests and capture results
* Save result as .drift.json manifest

Implementation notes:
* Manifest includes all signatures, schema hash, and test summary.
* Add optional --json flag to output machine-readable report.

#### `raw drift-check`

Description: Compares current repo state against a previous .drift.json manifest. Used to catch unintentional breaking changes.

Requirements:
* Valid RAW repo and existing .drift.json manifest

Actions:
* Perform a fresh drift-init (in-memory)
* Compare:
  * Endpoints present
  * Schema definitions (column names, types)
  * Parameter changes
  * Test results
* Highlight additions, deletions, and schema changes

Implementation Notes:
* Add optional --json flag to output machine-readable report.

### Local Development

#### `raw init [--project_name=...] [--hello-world] <folder>`

Description: Bootstraps a new RAW repo in a given folder.

Actions:
* Create:
  * raw-site.yml with project/profile names
  * dbt_project.yml and update ~/.dbt/profiles.yml
  * .duckdb database file
* Install and load RAW DuckDB extension (`INSTALL RAW`)
* Optionally generate:
  * Example endpoint file
  * init.py for bootstrap functions

Implementation notes:
* Should support clean re-init if already exists.
* Use current folder name as default project_name.

#### `raw dbt-config`

Description: Ensures the local dbt configuration matches RAW expectations.

Requirements:
* Valid RAW repo (raw-site.yml, .duckdb)

Actions:
* Read raw-site.yml to find project and profile
* Check ~/.dbt/profiles.yml:
  * Add missing project entry
  * Update path to .duckdb
  * Add RAW DuckDB extension pre-hook
* Validate dbt is correctly set up

Implementation notes:
* Key for people moving repos between folders or machines.

#### `raw dbt-cron`

Description: Detects outdated dbt models and refreshes them.

Actions:
* Check manifest.json
* Run dbt ls --select state:modified
* Optionally return models or run dbt run --select model+

Implementation notes:
* Used in scheduled refresh jobs (e.g., SaaS backend).

#### `raw vscode-config`

Description: Creates VSCode-friendly project config.

Actions:
* Generate .vscode/settings.json with:
  * Python interpreter
  * dbt plugin plugin suggestions + config
  * SQL/DuckDb plugin suggestions + config
  * Syntax highlighting, path mappings

Implementation notes:
* Helpful for onboarding teams to local dev.

### Cloud-specific

#### `raw cloud ...`

Placeholder for:
* SaaS-specific workflows
* Auth, org, GitHub/GitLab linkage
* Secret management via Vault
* CI/CD pipeline integration

Examples to consider:
* raw cloud login
* raw cloud sync
* raw cloud deploy
* raw cloud secrets

## Adapters

RAW adapters enable seamless integration with external data sources by exposing them as DuckDB schemas, using a standardized Python SDK interface. Adapters are defined declaratively and initialized dynamically at runtime, using pre-installed Python packages and user-provided configurations.

### Declaring Adapters

Adapters are configured in the `raw-site.yml` file under the `adapters` section. Each adapter declaration must specify:

- `name`: Logical name of the adapter instance. This becomes the DuckDB schema name.
- `package`: Python module name of the adapter (must already be installed).
- `config`: Name of the configuration block defined in `~/.raw/config.yml`.

#### Example

```yaml
adapters:
  - name: salesforce01
    package: raw_salesforce
    config: salesforce_config01

  - name: hubspot
    package: raw_hubspot
    config: hubspot_prod
```

### Providing Configuration

Each adapter can reference a named configuration object defined in the user’s profile in `~/.raw/config.yml`. This configuration is passed as a dictionary to the adapter’s constructor at runtime.

#### Example

```yaml
raw: "1.0.0"
projects:
  project_a:
    default: dev
    profiles:
      dev:
        adapter_configs:
          salesforce_config01:
            USERNAME: user@example.com
            PASSWORD: secret
            TOKEN: token123

          hubspot_prod:
            API_KEY: vault://hubspot/api-key
```

All configuration values must be strings. Environment variable resolution (`${ENV_VAR}`) and Vault resolution (`vault://...`) are supported as normally in `~/.raw/config.yml`.

### Runtime Behavior

When running `raw serve`, `raw run`, or any command that loads adapters (by loading the RAW DuckDB extenssion):

1. RAW dynamically imports the specified `package` using Python’s import system.
2. It loads an `Adapter` class (by convention) or a standard factory method (e.g. `get_adapter()`).
3. The class is instantiated with the corresponding config dict:
   ```python
   adapter = Adapter(config_dict)
   ```
4. The adapter is registered in DuckDB under the schema name given in `name`.

### Adapter Interface

Adapters must implement a minimal Python interface to integrate with RAW. This interface should include:

```python
class Adapter:
    def __init__(self, config: dict):
        ...

    def get_tables(self) -> List[str]:
        ...

    def get_schema(self, table: str) -> Dict[str, str]:
        ...

    def query(self, table: str, filters: Dict[str, Any]) -> pd.DataFrame:
        ...
```

- `get_tables()` returns the available table names.
- `get_schema(table)` returns column names and types.
- `query(table, filters)` returns a DataFrame representing the result.

### SQL Usage

Once initialized, all adapter tables are accessible in SQL using the schema name:

```sql
SELECT * FROM salesforce01.Account WHERE Industry = 'Technology';
```

All filters and queries are delegated to the adapter’s logic behind the scenes.

### Package Installation

RAW does not install adapter packages automatically. Users must install required packages manually or via tooling such as `pip`, Poetry, or a `requirements.txt` file.

You may optionally run:

```bash
raw deps
```

This command parses adapter packages from `raw-site.yml` and installs them using pip.

This adapter system enables reusable, configurable, and testable integrations with external systems, while preserving local-first workflows and DuckDB-native queryability.

## Integrations

RAW is built on an opinionated yet modular integration of powerful open-source components. These integrations enable RAW to operate as a **self-contained local data platform** with optional orchestration in the cloud.

### DuckDB

DuckDB is the foundation of RAW's runtime. It acts as both the **query engine** and the **in-memory application host** — thanks to a custom **C++ extension** built by RAW.

This extension (`raw.duckdb_extension`) is loaded automatically in every session and enables seamless integration between:
* project-specific configuration (from `~/.raw/config.yml`)
* repository-specific setup (`raw-site.yml`)
* Python code (`init.py` bootstrap - see below)
* secret management (see below)
* ... as to provide a complete environment for execution in SQL.

#### Overview of Responsibilities

The RAW DuckDB extension must implement the following:

1. **Secret Injection**
  * On session start, resolve the `~/.raw/config.yml` (or the path from the `RAW_CONFIG` env var).
  * Determine the current project/profile based on `raw-site.yml`.
  * Load the relevant secrets from config (supporting environment and Vault resolution).
  * Inject them into DuckDB as `CREATE TEMPORARY SECRET` so that DuckDB connectors can find them in the session.

2. **Python Bootstrap Support (`init.py`)**
  * Look for a file path defined under `python.path` in `raw-site.yml`.
  * Import that Python file **into the same DuckDB session**.
  * Expect the file to define a function:
     ```python
     def init(session):
         ...
     ```
  * Call this `init()` function from C++ and pass in a **`session` object**, which contains:
    * `register_function(name, arg_types, return_type, py_func)`
    * `register_table_function(name, py_func)`
    * `get_secret(name)`

Example Python bootstrap file:
```python
def init(session):
    # 1. Register a scalar function
    session.register_function(
        "greet",
        ["VARCHAR"],
        "VARCHAR",
        lambda name: f"Hello, {name}!"
    )

    # 2. Register a table function
    def all_regions():
        return [{"region": "us"}, {"region": "eu"}, {"region": "apac"}]

    session.register_table_function("regions", all_regions)

    # 3. Read a secret
    creds = session.get_secret("my_s3_secret")
    print("Loaded S3 creds:", creds["KEY_ID"])
```

3. **Custom DuckDB Type for Secrets**
  * Define a new DuckDB secret type `RAW_SECRET` so that users can define their own "custom secrets" and use them from SQL queries.

#### RAW DuckDB C++ Extension Installation and Usage

- Built in C++ and compiled into `.duckdb_extension` format.
- Loaded automatically via:
  ```sql
  INSTALL raw;
  LOAD raw;
  ```
-	This should happen transparently in the CLI anytime a DuckDB session is initialized (i.e., `raw serve`, `raw run`, etc.).

The `session` object is a C++-defined Python object exposed in the `init()` call. It acts as a **registration and utility interface** that Python users can use to extend the runtime.

### Dbt

dbt (Data Build Tool) is used in RAW to define ETL pipelines using modular SQL transformations. These models are built and materialized in DuckDB and then consumed by RAW endpoints.

Features to Support:

1. Automatic Configuration
  * RAW must generate and manage the ~/.dbt/profiles.yml entry for each RAW project.
  * This entry should:
    * Point to the correct DuckDB file
  * Include pre-hook or init_command to LOAD raw extension
2. State Validation
  * Before any of the following commands, RAW must ensure no unapplied dbt changes:
    * raw validate
    * raw test
	  * raw run
	  * raw serve
	* Done via:
```bash
dbt ls --select state:modified --state ./target/manifest.json
```
  * If modified models are found, RAW should halt and instruct the user to run:
```bash
dbt run
```
3. Optional Execution (Local or Managed)
	* In local workflows, the user runs dbt run manually.
	* In SaaS mode, RAW runs dbt run via cron or orchestration.
4. Support raw-site.yml configuration
	*	Support disabling dbt integration:
```yaml  
dbt:
  enabled: false
```  
  * Support specifying model and manifest paths:
 ```yaml 
dbt:
  models: ./models
  manifest_path: ./target/manifest.json
```
5. CLI Sync Command
	* raw dbt-config ensures dbt’s profiles.yml has the right entries for each repo.

Sample ~/.dbt/profiles.yml Entry (Auto-managed):
```yaml
  project_a:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: /path/to/project/.duckdb
      extensions:
        - raw
```
        
## Implementation for SaaS

One VPC per org/repo.
One pod per raw serve.
Solution: 30 day paid trial to avoid running them forever.

GitHub App.
Clone DB with cp.
User and UI trigger cron job refresh

Airflow for cronjobs on SaaS?

### SaaS CI

```
dbt deps
dbt seed
dbt test
raw validate
raw test
raw drift-check
```

### SaaS CD

```
...
raw serve
```

# Questions

## I find a GitHub repo I like. How do I start using RAW?

Normally you just need to do:
```bash
git clone https://github.com/org/raw-example.git
cd raw-example
pip install raw # Installs both RAW cli, duckdb, maybe dbt, and well as RAW DuckDB extension
raw serve
```

To make modifications in DBT models, you may need to get your local dbt config ready by running `raw dbt-config`.
A more complex example would be:

```bash
# On repo checkout:
git clone https://github.com/org/raw-example.git
cd raw-example

# Install dependencies:
pip install raw  # includes DuckDB, RAW CLI, dbt, and raw.duckdb extension

# Bootstrap config:
raw dbt-config

# Check for modified dbt models:
raw validate  # will fail if state:modified is not empty

# Apply changes:
dbt run

# Run the endpoint:
raw run tools://list_users --region=us
```

# Exploratory Tasks

| Task                          | Description                                                |
|-------------------------------|------------------------------------------------------------|
| Validate YAML endpoint schema | Does it include all the required features? (annotations?)  |
| RAW DuckDB C++ Extensions     | Prototype the RAW DuckDB C++ Extension.                    |
| RAW Python Adapters           | Alternative to DAS as managed Python code for DuckDB.      | 
| DuckDB DAS                    | Protoype a DAS connector to DuckDB as a vanilla extension. |
