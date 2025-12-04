# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.10.x  | :white_check_mark: |
| < 0.10  | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them through GitHub's private vulnerability reporting feature:

1. Go to the [Security tab](https://github.com/raw-labs/mxcp/security) of this repository
2. Click "Report a vulnerability"
3. Fill in the details of the vulnerability

Alternatively, you can email us at: **security@raw-labs.com**

### What to Include

Please include the following information in your report:

- Type of vulnerability (e.g., SQL injection, authentication bypass, privilege escalation)
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability and how an attacker might exploit it

### Response Timeline

- **Initial Response**: Within 48 hours of receiving your report
- **Status Update**: Within 7 days with an assessment of the vulnerability
- **Resolution**: We aim to release patches for confirmed vulnerabilities within 30 days

### Disclosure Policy

- We will acknowledge your contribution in the release notes (unless you prefer to remain anonymous)
- We ask that you give us reasonable time to address the vulnerability before public disclosure
- We will coordinate with you on the timing of any public announcement

## Security Measures

MXCP implements several security measures:

- **Input Validation**: All tool inputs are validated against JSON schemas
- **Policy Enforcement**: CEL-based policies for access control and data filtering
- **Audit Logging**: Comprehensive audit trails for all tool executions
- **Data Redaction**: Configurable redaction for sensitive data in responses
- **Secrets Management**: Integration with external secret providers (environment variables, HashiCorp Vault, AWS Secrets Manager)

## Security Scanning

This project uses automated security scanning:

- **Dependabot**: Weekly scans for dependency vulnerabilities
- **Trivy**: Container image and Dockerfile scanning
- **CodeQL**: Static Application Security Testing (SAST) for Python code
- **Safety**: Python dependency vulnerability checks

Scan results are available in the [Security tab](https://github.com/raw-labs/mxcp/security) of this repository.

