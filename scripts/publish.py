#!/usr/bin/env python3
"""
PyPI Publishing Script for MXCP

This script automates the process of building and publishing the MXCP package to PyPI.
It includes safety checks, cleanup, and supports both test and production PyPI.

Usage:
    python scripts/publish.py --test     # Publish to test PyPI
    python scripts/publish.py --prod     # Publish to production PyPI
    python scripts/publish.py --check    # Just build and validate, don't publish
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(cmd, check=True):
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(1)

    return result


def clean_build_artifacts():
    """Clean up build artifacts."""
    print("Cleaning build artifacts...")

    dirs_to_clean = ["dist", "build", "*.egg-info"]
    for pattern in dirs_to_clean:
        for path in Path(".").glob(pattern):
            if path.is_dir():
                print(f"Removing directory: {path}")
                shutil.rmtree(path)
            elif path.is_file():
                print(f"Removing file: {path}")
                path.unlink()


def check_git_status():
    """Check if git repo is clean."""
    result = run_command(["git", "status", "--porcelain"], check=False)
    if result.stdout.strip():
        print("Warning: Git working directory is not clean!")
        print("Uncommitted changes:")
        print(result.stdout)
        response = input("Continue anyway? (y/N): ")
        if response.lower() != "y":
            sys.exit(1)


def get_version():
    """Get the current version from pyproject.toml."""
    import tomllib

    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    version = data["project"]["version"]
    print(f"Current version: {version}")
    return version


def build_package():
    """Build the package."""
    print("Building package...")
    run_command([sys.executable, "-m", "build"])

    # List built artifacts
    dist_files = list(Path("dist").glob("*"))
    print(f"Built {len(dist_files)} files:")
    for file in dist_files:
        print(f"  {file}")


def check_package():
    """Check the built package."""
    print("Checking package...")
    run_command([sys.executable, "-m", "twine", "check", "dist/*"])


def publish_package(repository):
    """Publish the package to PyPI."""
    if repository == "test":
        print("Publishing to Test PyPI...")
        run_command([sys.executable, "-m", "twine", "upload", "--repository", "testpypi", "dist/*"])
        print("\nPackage published to Test PyPI!")
        print("Install with: pip install --index-url https://test.pypi.org/simple/ mxcp")

    elif repository == "prod":
        print("Publishing to Production PyPI...")
        version = get_version()
        response = input(
            f"Are you sure you want to publish version {version} to production PyPI? (y/N): "
        )
        if response.lower() != "y":
            print("Aborted.")
            sys.exit(0)

        run_command([sys.executable, "-m", "twine", "upload", "dist/*"])
        print("\nPackage published to Production PyPI!")
        print("Install with: pip install mxcp")


def main():
    parser = argparse.ArgumentParser(description="Publish MXCP to PyPI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true", help="Publish to Test PyPI")
    group.add_argument("--prod", action="store_true", help="Publish to Production PyPI")
    group.add_argument("--check", action="store_true", help="Build and check only, don't publish")

    parser.add_argument("--skip-git-check", action="store_true", help="Skip git status check")
    parser.add_argument("--no-clean", action="store_true", help="Don't clean build artifacts first")

    args = parser.parse_args()

    # Change to the project root directory
    project_root = Path(__file__).parent.parent
    if project_root.exists():
        import os

        os.chdir(project_root)

    # Check git status
    if not args.skip_git_check:
        check_git_status()

    # Clean build artifacts
    if not args.no_clean:
        clean_build_artifacts()

    # Build package
    build_package()

    # Check package
    check_package()

    # Publish if requested
    if args.test:
        publish_package("test")
    elif args.prod:
        publish_package("prod")
    elif args.check:
        print("Package built and validated successfully!")

    print("Done!")


if __name__ == "__main__":
    main()
