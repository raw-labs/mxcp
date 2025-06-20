#!/usr/bin/env python3
"""
Release Helper Script for MXCP

This script helps create releases with proper git tags using semantic versioning.
It performs pre-release checks and creates/pushes the git tag to trigger CI/CD.

Usage:
    python scripts/release.py --version 0.1.5     # Create release v0.1.5
    python scripts/release.py --check             # Just run pre-release checks
    python scripts/release.py --list              # List recent releases
"""

import argparse
import subprocess
import sys
import re
from pathlib import Path


def run_command(cmd, check=True, capture_output=True):
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture_output, text=True, check=False)
    
    if not capture_output:
        # If we're not capturing output, the command output is already shown
        pass
    elif result.stdout and result.stdout.strip():
        print(result.stdout.strip())
    
    if result.stderr and result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(1)
    
    return result


def validate_version(version):
    """Validate semantic version format."""
    pattern = r'^[0-9]+\.[0-9]+\.[0-9]+([a-zA-Z0-9\.\-]+)?$'
    if not re.match(pattern, version):
        print(f"Error: Version '{version}' does not follow semantic versioning")
        print("Examples: 1.0.0, 0.1.5, 2.1.0-rc1, 1.0.0-beta.1")
        return False
    return True


def check_git_status():
    """Check if git repo is clean and up to date."""
    print("🔍 Checking git status...")
    
    # Check for uncommitted changes
    result = run_command(["git", "status", "--porcelain"], check=False)
    if result.stdout.strip():
        print("❌ Git working directory is not clean!")
        print("Uncommitted changes:")
        print(result.stdout)
        return False
    
    # Check if we're on main branch
    result = run_command(["git", "branch", "--show-current"], check=False)
    current_branch = result.stdout.strip()
    if current_branch != "main":
        print(f"⚠️  Warning: You're on branch '{current_branch}', not 'main'")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return False
    
    # Check if we're up to date with remote
    run_command(["git", "fetch"], check=False)
    result = run_command(["git", "status", "-uno"], check=False)
    if "ahead" in result.stdout or "behind" in result.stdout:
        print("⚠️  Warning: Local branch is not in sync with remote")
        print(result.stdout)
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return False
    
    print("✅ Git status OK")
    return True


def check_existing_tag(version):
    """Check if tag already exists."""
    tag = f"v{version}"
    result = run_command(["git", "tag", "-l", tag], check=False)
    if result.stdout.strip():
        print(f"❌ Tag '{tag}' already exists!")
        return False
    
    # Check remote tags too
    result = run_command(["git", "ls-remote", "--tags", "origin", tag], check=False)
    if result.stdout.strip():
        print(f"❌ Tag '{tag}' already exists on remote!")
        return False
    
    return True


def run_pre_release_checks():
    """Run pre-release checks."""
    print("🔍 Running pre-release checks...")
    
    checks = [
        (["python", "-m", "pytest", "--tb=short"], "Running tests"),
        (["python", "-m", "black", "--check", "src", "tests"], "Checking code formatting"),
        (["python", "-m", "isort", "--check-only", "src", "tests"], "Checking import sorting"),
        (["python", "-m", "mypy", "src/mxcp"], "Running type checks"),
    ]
    
    for cmd, description in checks:
        print(f"  {description}...")
        result = run_command(cmd, check=False)
        if result.returncode != 0:
            print(f"❌ {description} failed!")
            return False
        print(f"  ✅ {description} passed")
    
    print("✅ All pre-release checks passed")
    return True


def create_and_push_tag(version):
    """Create and push git tag."""
    tag = f"v{version}"
    
    print(f"🏷️  Creating tag '{tag}'...")
    run_command(["git", "tag", tag])
    
    print(f"🚀 Pushing tag '{tag}' to trigger release...")
    run_command(["git", "push", "origin", tag])
    
    print(f"✅ Tag '{tag}' created and pushed!")
    print(f"🔗 Monitor the release at: https://github.com/raw-labs/mxcp/actions")
    

def list_recent_releases():
    """List recent git tags/releases."""
    print("📋 Recent releases:")
    result = run_command(["git", "tag", "-l", "--sort=-version:refname"], check=False)
    
    if not result.stdout.strip():
        print("No releases found.")
        return
    
    tags = result.stdout.strip().split('\n')[:10]  # Show last 10
    for tag in tags:
        # Get tag date
        date_result = run_command(["git", "log", "-1", "--format=%ai", tag], check=False)
        date = date_result.stdout.strip()[:10] if date_result.stdout else "unknown"
        print(f"  {tag:<12} ({date})")


def get_next_version_suggestions(current_version=None):
    """Suggest next version numbers."""
    if current_version:
        try:
            # Remove 'v' prefix if present
            version = current_version.lstrip('v')
            
            # Split version and handle pre-release suffixes
            version_parts = version.split('.')
            if len(version_parts) >= 3:
                major = int(version_parts[0])
                minor = int(version_parts[1])
                
                # Handle patch version which might have pre-release suffix
                patch_part = version_parts[2]
                # Extract numeric part before any non-numeric characters
                patch_match = re.match(r'^(\d+)', patch_part)
                if patch_match:
                    patch = int(patch_match.group(1))
                else:
                    patch = 0
                
                print(f"Current version: {current_version}")
                print("Suggested next versions:")
                print(f"  Patch:  v{major}.{minor}.{patch + 1}")
                print(f"  Minor:  v{major}.{minor + 1}.0")
                print(f"  Major:  v{major + 1}.0.0")
            else:
                print("Could not parse version format for suggestions")
        except Exception as e:
            print(f"Could not parse current version for suggestions: {e}")


def main():
    parser = argparse.ArgumentParser(description="Release helper for MXCP")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--version", help="Version to release (e.g., 0.1.5)")
    group.add_argument("--check", action="store_true", help="Run pre-release checks only")
    group.add_argument("--list", action="store_true", help="List recent releases")
    
    parser.add_argument("--skip-checks", action="store_true", help="Skip pre-release checks")
    parser.add_argument("--force", action="store_true", help="Force release (skip confirmations)")
    
    args = parser.parse_args()
    
    # Change to project root
    project_root = Path(__file__).parent.parent
    if project_root.exists():
        import os
        os.chdir(project_root)
    
    if args.list:
        list_recent_releases()
        return
    
    if args.check:
        success = run_pre_release_checks()
        sys.exit(0 if success else 1)
    
    # Release workflow
    version = args.version
    
    # Validate version format
    if not validate_version(version):
        sys.exit(1)
    
    # Get current version for suggestions
    result = run_command(["git", "tag", "-l", "--sort=-version:refname"], check=False)
    latest_tag = result.stdout.strip().split('\n')[0] if result.stdout.strip() else None
    if latest_tag:
        get_next_version_suggestions(latest_tag)
        print()
    
    # Check if tag already exists
    if not check_existing_tag(version):
        sys.exit(1)
    
    # Check git status
    if not check_git_status():
        sys.exit(1)
    
    # Run pre-release checks
    if not args.skip_checks:
        if not run_pre_release_checks():
            sys.exit(1)
    
    # Final confirmation
    if not args.force:
        print(f"\n🚀 Ready to release version {version}")
        print("This will:")
        print(f"  1. Create git tag 'v{version}'")
        print(f"  2. Push tag to GitHub")
        print(f"  3. Trigger automated PyPI publishing")
        print()
        response = input("Proceed with release? (y/N): ")
        if response.lower() != 'y':
            print("Release cancelled.")
            sys.exit(0)
    
    # Create and push tag
    create_and_push_tag(version)
    
    print("\n🎉 Release initiated successfully!")
    print("The GitHub Actions workflow will now:")
    print("  1. Build the package")
    print("  2. Publish to Test PyPI")
    print("  3. Test the installation")  
    print("  4. Publish to Production PyPI")
    print("  5. Create GitHub Release")


if __name__ == "__main__":
    main() 