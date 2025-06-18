# Release Process Guide

This document explains how to release new versions of MXCP using our automated GitHub Actions workflows.

## Overview

We use **git tag-based versioning** with automated publishing to PyPI. The process is:

1. 🏷️ Create a git tag → 🤖 GitHub Actions automatically publishes to PyPI
2. 📦 Package is published to Test PyPI first, then Production PyPI
3. 🚀 GitHub Release is created automatically

## Required Secrets

Ensure these secrets are configured in your GitHub repository:

- `PYPI_API_TOKEN` - Production PyPI API token
- `TEST_PYPI_API_TOKEN` - Test PyPI API token

### Getting PyPI API Tokens

1. **Production PyPI**: Go to [pypi.org/manage/account/token](https://pypi.org/manage/account/token/)
2. **Test PyPI**: Go to [test.pypi.org/manage/account/token](https://test.pypi.org/manage/account/token/)

## Release Steps

### 1. Prepare for Release

```bash
# Ensure you're on main branch and up to date
git checkout main
git pull origin main

# Ensure all tests pass locally
pytest

# Ensure code quality is good
black src tests
isort src tests
mypy src/mxcp
```

### 2. Create and Push Tag

```bash
# Create a new version tag (follow semantic versioning)
git tag v0.1.5

# Push the tag to trigger the release
git push origin v0.1.5
```

**Tag Format**: Use `v` prefix followed by semantic version (e.g., `v1.0.0`, `v0.1.5`, `v2.1.0-rc1`)

### 3. Monitor the Release

1. Go to **Actions** tab in GitHub
2. Watch the "Publish to PyPI" workflow
3. The workflow will:
   - ✅ Extract version from tag
   - ✅ Update `pyproject.toml` 
   - ✅ Build package
   - ✅ Publish to Test PyPI
   - ✅ Test installation from Test PyPI
   - ✅ Publish to Production PyPI
   - ✅ Create GitHub Release

### 4. Verify Release

```bash
# Test installation from PyPI
pip install mxcp==0.1.5

# Verify it works
mxcp --help
```

## Workflow Details

### CI Workflow (`.github/workflows/ci.yml`)

**Triggers**: Push/PR to main, develop branches

**What it does**:
- ✅ Tests on Python 3.10, 3.11, 3.12
- ✅ Tests on Linux, Windows, macOS  
- ✅ Code formatting (black)
- ✅ Import sorting (isort)
- ✅ Type checking (mypy)
- ✅ Test coverage (80% minimum)
- ✅ Security scanning (bandit)
- ✅ Package validation

### Publish Workflow (`.github/workflows/publish.yml`)

**Triggers**: Git tags matching `v*`

**What it does**:
1. 🏷️ Extract version from git tag
2. 📝 Update `pyproject.toml` version
3. 🔨 Build package
4. 🧪 Publish to Test PyPI
5. ✅ Test installation from Test PyPI
6. 🚀 Publish to Production PyPI
7. 📋 Create GitHub Release

### PR Validation (`.github/workflows/pr-validation.yml`)

**Triggers**: Pull requests to main

**What it does**:
- ⚡ Quick format/import checks
- ⚡ Fast tests only
- ⚡ Security scan

## Version Strategy

### Semantic Versioning

Follow [semver.org](https://semver.org/) format: `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Examples

```bash
# Patch release (bug fixes)
git tag v0.1.5

# Minor release (new features)
git tag v0.2.0

# Major release (breaking changes)  
git tag v1.0.0

# Pre-release
git tag v1.0.0-rc1
```

## Troubleshooting

### Release Failed

1. Check the Actions logs in GitHub
2. Common issues:
   - PyPI API tokens expired/invalid
   - Version already exists on PyPI
   - Package validation failed

### Rollback a Release

❌ **You cannot delete versions from PyPI**, but you can:

1. Create a new patch version with fixes
2. Mark the problematic version as "yanked" on PyPI

### Testing Before Release

```bash
# Run the full test suite locally
pytest --cov=mxcp --cov-fail-under=80

# Test package building
python -m build
twine check dist/*

# Test with your changes
pip install -e .
mxcp --help
```

## Environment Protection

The publish workflow uses GitHub's `release` environment for additional security:

- Requires manual approval for production deployments
- Only certain users can approve releases
- Provides audit trail

Configure this in **Settings → Environments → release**.

## Next Steps

After setting up:

1. ✅ Configure PyPI API tokens in GitHub secrets
2. ✅ Set up the `release` environment protection
3. ✅ Test with a pre-release version (e.g., `v0.1.5-test`)
4. ✅ Monitor first production release