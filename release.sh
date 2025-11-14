#!/bin/bash

set -e

# Release script for MXCP
# Updates version in pyproject.toml and creates a git tag

if [ -z "$1" ]; then
    echo "Usage: ./release.sh <version>"
    echo ""
    echo "Examples:"
    echo "  ./release.sh 1.0.0"
    echo "  ./release.sh v1.0.0      (v prefix is automatically stripped)"
    echo "  ./release.sh 1.0.0rc1"
    echo "  ./release.sh 1.0.0a1"
    exit 1
fi

# Strip 'v' prefix if present
VERSION="${1#v}"
TAG="v${VERSION}"

echo "📦 Preparing release ${TAG}"
echo ""

# Validate version format (basic check)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(rc[0-9]+|a[0-9]+|b[0-9]+)?$ ]]; then
    echo "❌ Invalid version format: $VERSION"
    echo "Expected format: X.Y.Z, X.Y.Zrc1, X.Y.Za1, or X.Y.Zb1"
    exit 1
fi

# Check if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "❌ Tag $TAG already exists"
    echo "To delete: git tag -d $TAG && git push origin :refs/tags/$TAG"
    exit 1
fi

# Check for uncommitted changes
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ You have uncommitted changes. Commit or stash them first."
    git status --short
    exit 1
fi

# Update version in pyproject.toml
echo "📝 Updating pyproject.toml..."
sed -i '' "s/^version = .*/version = \"$VERSION\"/" pyproject.toml

# Verify the change
echo ""
echo "✅ Version updated:"
grep "^version" pyproject.toml

# Stage and commit
echo ""
echo "📌 Creating commit and tag..."
git add pyproject.toml
git commit -m "Release ${TAG}"
git tag "$TAG"

echo ""
echo "✅ Release ${TAG} ready!"
echo ""
echo "To publish, run:"
echo "  git push origin main"
echo "  git push origin ${TAG}"
echo ""
echo "GitHub Actions will automatically:"
echo "  • Wait for PyPI CDN propagation"
echo "  • Publish to PyPI using trusted publishing"
echo "  • Build and push Docker image to ghcr.io/raw-labs/mxcp"

