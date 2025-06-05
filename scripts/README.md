# Publishing Scripts

This directory contains scripts to help with publishing MXCP to PyPI.

## Scripts

### `publish.py`
Main Python script that handles the complete build and publish workflow.

**Usage:**
```bash
# Test the build without publishing
python scripts/publish.py --check

# Publish to Test PyPI (recommended first)
python scripts/publish.py --test

# Publish to Production PyPI
python scripts/publish.py --prod
```

**Options:**
- `--check`: Build and validate the package without publishing
- `--test`: Publish to Test PyPI (https://test.pypi.org)
- `--prod`: Publish to Production PyPI
- `--skip-git-check`: Skip checking if git working directory is clean
- `--no-clean`: Don't clean build artifacts before building

### `publish.sh`
Simple bash wrapper for the Python script.

**Usage:**
```bash
# Same options as publish.py
./scripts/publish.sh --check
./scripts/publish.sh --test
./scripts/publish.sh --prod
```

## Prerequisites

Make sure you have the required tools installed. The easiest way is to install the dev dependencies:

```bash
pip install -e ".[dev]"
```

Or install the tools manually:

```bash
pip install build twine
```

## Workflow

1. **First time setup**: Configure your PyPI credentials
   ```bash
   # For Test PyPI
   twine configure --repository testpypi
   
   # For Production PyPI  
   twine configure
   ```

2. **Test your changes**: Always test on Test PyPI first
   ```bash
   python scripts/publish.py --test
   ```

3. **Install and test from Test PyPI**:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ mxcp
   ```

4. **Publish to production** when ready:
   ```bash
   python scripts/publish.py --prod
   ```

## What the Script Does

1. **Checks git status** (can be skipped with `--skip-git-check`)
2. **Cleans build artifacts** (can be skipped with `--no-clean`)
3. **Builds the package** using `python -m build`
4. **Validates the package** using `twine check`
5. **Publishes to PyPI** using `twine upload`

## Safety Features

- Checks if git working directory is clean before publishing
- Requires explicit confirmation for production PyPI
- Cleans old build artifacts automatically
- Validates package before upload
- Clear error messages and command output 