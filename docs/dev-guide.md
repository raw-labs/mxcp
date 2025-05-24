# Development Guide

Welcome to the MXCP development community! This guide will help you get started with contributing to the project.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- A GitHub account
- Basic understanding of SQL and YAML

### Development Setup

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/raw-labs/mxcp.git
   cd mxcp
   ```
3. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
4. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Development Workflow

### 1. Branch Management

- Create a new branch for each feature or bugfix:
  ```bash
  git checkout -b feature/your-feature-name
  # or
  git checkout -b fix/your-bugfix-name
  ```

- Keep your branch up to date with main:
  ```bash
  git fetch origin
  git rebase origin/main
  ```

### 2. Code Style

- Follow PEP 8 guidelines
- Use type hints for all function parameters and return values
- Write docstrings for all public functions and classes
- Keep lines under 100 characters
- Use meaningful variable and function names

### 3. Testing

- Write tests for all new features and bugfixes
- Run the test suite:
  ```bash
  pytest
  ```
- Ensure all tests pass before submitting a PR
- Aim for high test coverage

### 4. Documentation

- Update relevant documentation when adding features
- Add docstrings to new functions and classes
- Update examples if they're affected by your changes
- Follow the existing documentation style

## Pull Request Process

1. **Before Submitting**
   - Ensure your code follows the style guide
   - Run all tests and fix any failures
   - Update documentation as needed
   - Rebase your branch on main

2. **Creating the PR**
   - Use the PR template provided
   - Write a clear title and description
   - Link any related issues
   - Request review from maintainers

3. **During Review**
   - Address review comments promptly
   - Keep the PR up to date with main
   - Squash commits if requested

4. **After Approval**
   - Wait for CI to pass
   - Address any final comments
   - Maintainers will merge your PR

## Project Structure

```
mxcp/
├── src/              # Source code
│   └── mxcp/        # Main package
├── tests/           # Test suite
├── docs/            # Documentation
├── examples/        # Example projects
└── pyproject.toml   # Project configuration
```

## Development Tools

### Code Quality

- Use `black` for code formatting
- Use `isort` for import sorting
- Use `mypy` for type checking
- Use `pylint` for linting

Run all checks:
```bash
make lint
```

### Testing

- Use `pytest` for testing
- Use `pytest-cov` for coverage reports

Run tests with coverage:
```bash
pytest --cov=mxcp
```

## Communication

- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for general questions and ideas
- **Email**: Contact hello@raw-labs.com for private matters
- **Code Review**: Use GitHub PR reviews for code-related discussions

## Release Process

1. Version bump in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release tag
4. Build and publish to PyPI

## Getting Help

- Check the [documentation](docs/)
- Search existing issues and discussions
- Join our community discussions
- Email hello@raw-labs.com for private matters

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md). We aim to maintain a welcoming and inclusive community.

## License

MXCP is released under the Business Source License 1.1. See [LICENSE](../LICENSE) for details. This license allows for non-production use and will convert to MIT after four years from the first public release.

---

Thank you for contributing to MXCP! Your work helps make the project better for everyone. 