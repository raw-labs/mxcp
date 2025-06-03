# E2E Test Configuration

This directory contains an isolated configuration for LSP e2e tests.

## Purpose

This isolated setup ensures that:
- E2E tests don't depend on the main project's `mxcp-site.yml`
- Tests run with a predictable, minimal configuration
- No test artifacts are left in the file system
- Tests can run consistently across different environments

## Configuration

- **`mxcp-site.yml`**: Minimal test configuration with in-memory database
- **Test fixtures**: Copies of the main fixture files for testing LSP features

## Database Configuration

The test configuration uses:
- **In-memory database** (`:memory:`) - no file persistence
- **Disabled audit logging** - no log files created
- **No drift tracking** - no manifest files created
- **No extensions** - minimal dependencies

## Test Execution

E2E tests are configured to:
1. Run the LSP server from this directory (`server_cwd`)
2. Use the isolated `mxcp-site.yml` configuration
3. Reference test files relative to this directory
4. Leave no artifacts after completion

## Maintenance

When adding new LSP features that require test fixtures:
1. Add the fixture files to this directory
2. Update the test references to use relative paths
3. Ensure the configuration supports the new feature

This isolation pattern can be extended to other test types that need specific configurations. 