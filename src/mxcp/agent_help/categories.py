"""
Category definitions for the MXCP agent help system.
"""

# Available categories in priority order
CATEGORIES = [
    "examples",       # START HERE - working code patterns
    "getting-started", # Basic setup and initialization
    "endpoints",      # Tools, resources, prompts
    "data-sources",   # Database connections and data access
    "testing",        # Validation, testing, debugging
    "troubleshooting", # Common issues and solutions
    "advanced",       # dbt, plugins, performance, security
    "policies",       # Security and access control
    "integration",    # OAuth, MCP clients, external systems
    "deployment",     # Production deployment strategies
    "schemas",        # Type system and validation schemas
]

# Category display names
CATEGORY_NAMES = {
    "examples": "Examples",
    "getting-started": "Getting Started", 
    "endpoints": "Endpoints",
    "data-sources": "Data Sources",
    "testing": "Testing", 
    "troubleshooting": "Troubleshooting",
    "advanced": "Advanced",
    "policies": "Policies",
    "integration": "Integration",
    "deployment": "Deployment", 
    "schemas": "Schemas",
}

# Category descriptions
CATEGORY_DESCRIPTIONS = {
    "examples": "Working examples to get started quickly",
    "getting-started": "Initialize and set up MXCP projects",
    "endpoints": "Create and manage tools, resources, and prompts", 
    "data-sources": "Connect to databases and external data",
    "testing": "Validate, test, and debug your project",
    "troubleshooting": "Common issues and solutions",
    "advanced": "Advanced features and patterns for production deployments",
    "policies": "Security and access control",
    "integration": "OAuth, MCP clients, and external integrations",
    "deployment": "Deploy and serve your MXCP project",
    "schemas": "Type system and validation schemas",
}

def get_categories():
    """Get all available categories."""
    return CATEGORIES

def get_category_description(category):
    """Get description for a specific category."""
    return CATEGORY_DESCRIPTIONS.get(category)

def is_valid_category(category):
    """Check if a category is valid."""
    return category in CATEGORIES 