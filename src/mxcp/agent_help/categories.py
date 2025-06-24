"""
Category definitions for the MXCP agent help system.
"""

# Top-level categories as defined in the implementation guide
CATEGORIES = {
    "examples": "Working examples to get started quickly",
    "getting-started": "Initialize and set up MXCP projects",
    "data-sources": "Connect to databases and data sources", 
    "endpoints": "Create and manage tools, resources, and prompts",
    "testing": "Validate, test, and debug your project",
    "policies": "Access control and data protection policies",
    "deployment": "Deploy and serve your MXCP project",
    "troubleshooting": "Diagnose and fix common issues",
    "integration": "Integrate with MCP clients and AI platforms",
    "advanced": "Advanced features and optimizations",
    "schemas": "YAML file schemas and validation"
}

def get_categories():
    """Get all available categories."""
    return CATEGORIES

def get_category_description(category):
    """Get description for a specific category."""
    return CATEGORIES.get(category)

def is_valid_category(category):
    """Check if a category is valid."""
    return category in CATEGORIES 