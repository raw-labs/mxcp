"""
Help navigation logic for the MXCP agent help system.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from .categories import get_categories, is_valid_category

class HelpNavigator:
    """Navigate through the hierarchical help structure."""
    
    def __init__(self):
        self.content_dir = Path(__file__).parent / "content"
        self._content_cache: Dict[str, Any] = {}
    
    def _load_content(self, category: str) -> Dict[str, Any]:
        """Load content for a category from YAML file."""
        if category in self._content_cache:
            return self._content_cache[category]
        
        content_file = self.content_dir / f"{category}.yaml"
        if not content_file.exists():
            # Return empty structure for missing content files
            return {
                "category": category,
                "description": get_categories().get(category, "No description available"),
                "subcategories": []
            }
        
        try:
            with open(content_file, 'r') as f:
                content = yaml.safe_load(f)
            self._content_cache[category] = content
            return content
        except Exception as e:
            # Return error structure if file is malformed
            return {
                "category": category,
                "description": f"Error loading content: {e}",
                "subcategories": []
            }
    
    def get_help_content(self, path: List[str]) -> Tuple[str, Dict[str, Any]]:
        """
        Get help content for the given path.
        Returns (level, content) where level is 'root', 'category', 'subcategory', or 'topic'.
        """
        if not path:
            return self._get_root_help()
        
        category = path[0]
        if not is_valid_category(category):
            return "error", {"error": f"Unknown category: {category}"}
        
        if len(path) == 1:
            return self._get_category_help(category)
        
        if len(path) == 2:
            return self._get_subcategory_help(category, path[1])
        
        if len(path) == 3:
            return self._get_topic_help(category, path[1], path[2])
        
        return "error", {"error": "Too many path components"}
    
    def _get_root_help(self) -> Tuple[str, Dict[str, Any]]:
        """Get root level help showing all categories."""
        categories = get_categories()
        
        return "root", {
            "level": "root",
            "title": "MXCP Agent Help",
            "description": "Hierarchical help system for AI agents to understand and use MXCP",
            "security_notice": """
🚨 SECURITY-FIRST APPROACH 🚨

MXCP requires careful attention to security to prevent:
• Data breaches through misconfigured endpoints
• Secret leakage via hardcoded credentials  
• SQL injection through improper parameter handling
• Unauthorized access without proper authentication
• Policy bypass leading to data exposure

Always follow security best practices and test thoroughly before production deployment.
""",
            "categories": [
                {
                    "name": name,
                    "description": desc,
                    "command": f"mxcp agent-help {name}",
                    "security_priority": "🔒 HIGH" if name in ["policies", "advanced", "integration"] else "🔒 MEDIUM" if name in ["testing", "deployment"] else "🔒 BASIC"
                }
                for name, desc in categories.items()
            ],
            "usage": [
                "mxcp agent-help <category>",
                "mxcp agent-help <category> <subcategory>",
                "mxcp agent-help <category> <subcategory> <topic>"
            ],
            "examples": [
                "mxcp agent-help getting-started",
                "mxcp agent-help policies access-control",
                "mxcp agent-help testing security-testing",
                "mxcp agent-help advanced secrets"
            ],
            "security_quick_start": [
                "1. Start with: mxcp agent-help getting-started",
                "2. Secure secrets: mxcp agent-help advanced secrets",
                "3. Set up policies: mxcp agent-help policies",
                "4. Security testing: mxcp agent-help testing security-testing",
                "5. Deploy securely: mxcp agent-help deployment"
            ]
        }
    
    def _get_category_help(self, category: str) -> Tuple[str, Dict[str, Any]]:
        """Get category level help showing subcategories."""
        content = self._load_content(category)
        
        result = {
            "level": "category",
            "path": [category],
            "current": {
                "name": category,
                "description": content.get("description", "No description available")
            },
            "subcategories": [],
            "related": self._get_related_categories(category),
            "security_warning": content.get("security_warning"),
            "technical_context": content.get("technical_context")
        }
        
        for subcat in content.get("subcategories", []):
            if subcat and isinstance(subcat, dict):  # Safety check for None values and type
                result["subcategories"].append({
                    "name": subcat.get("name", ""),
                    "description": subcat.get("description", ""),
                    "command": f"mxcp agent-help {category} {subcat.get('name', '')}",
                    "agent_priority": subcat.get("agent_priority")
                })
        
        return "category", result
    
    def _get_subcategory_help(self, category: str, subcategory: str) -> Tuple[str, Dict[str, Any]]:
        """Get subcategory level help showing topics."""
        content = self._load_content(category)
        
        # Find the subcategory
        subcat_content = None
        for subcat in content.get("subcategories", []):
            if subcat["name"] == subcategory:
                subcat_content = subcat
                break
        
        if not subcat_content:
            return "error", {"error": f"Subcategory '{subcategory}' not found in '{category}'"}
        
        result = {
            "level": "subcategory",
            "path": [category, subcategory],
            "current": {
                "name": subcategory,
                "description": subcat_content.get("description", "No description available")
            },
            "parent": {
                "name": category,
                "description": content.get("description", ""),
                "command": f"mxcp agent-help {category}"
            },
            "topics": [],
            "related": self._get_related_subcategories(category, subcategory)
        }
        
        for topic in subcat_content.get("topics", []):
            result["topics"].append({
                "name": topic["name"],
                "description": topic.get("description", ""),
                "command": f"mxcp agent-help {category} {subcategory} {topic['name']}"
            })
        
        return "subcategory", result
    
    def _get_topic_help(self, category: str, subcategory: str, topic: str) -> Tuple[str, Dict[str, Any]]:
        """Get topic level help with detailed content."""
        content = self._load_content(category)
        
        # Find the subcategory and topic
        topic_content = None
        subcat_content = None
        
        for subcat in content.get("subcategories", []):
            if subcat["name"] == subcategory:
                subcat_content = subcat
                for topic_item in subcat.get("topics", []):
                    if topic_item["name"] == topic:
                        topic_content = topic_item
                        break
                break
        
        if not topic_content:
            return "error", {"error": f"Topic '{topic}' not found in '{category}/{subcategory}'"}
        
        result = {
            "level": "topic",
            "path": [category, subcategory, topic],
            "current": {
                "name": topic,
                "description": topic_content.get("description", "No description available")
            },
            "parent": {
                "name": subcategory,
                "description": subcat_content.get("description", ""),
                "command": f"mxcp agent-help {category} {subcategory}"
            },
            "breadcrumb": [
                {"name": category, "command": f"mxcp agent-help {category}"},
                {"name": subcategory, "command": f"mxcp agent-help {category} {subcategory}"},
                {"name": topic}
            ],
            "content": topic_content.get("content", {}),
            "related": self._get_related_topics(category, subcategory, topic)
        }
        
        return "topic", result
    
    def _get_related_categories(self, category: str) -> List[str]:
        """Get related categories for cross-references."""
        # Simple heuristic for related categories
        relations = {
            "getting-started": ["data-sources", "endpoints", "testing"],
            "data-sources": ["getting-started", "endpoints", "schemas"],
            "endpoints": ["getting-started", "testing", "schemas"],
            "testing": ["endpoints", "troubleshooting"],
            "troubleshooting": ["testing", "schemas"],
            "schemas": ["endpoints", "troubleshooting"],
            "integration": ["deployment", "troubleshooting"],
            "deployment": ["integration", "advanced"],
            "advanced": ["deployment", "schemas"]
        }
        return relations.get(category, [])
    
    def _get_related_subcategories(self, category: str, subcategory: str) -> List[str]:
        """Get related subcategories within the same category."""
        # This could be enhanced with more sophisticated relations
        return []
    
    def _get_related_topics(self, category: str, subcategory: str, topic: str) -> List[str]:
        """Get related topics for cross-references."""
        # This could be enhanced with more sophisticated relations
        return []
    
    def validate_path(self, path: List[str]) -> Tuple[bool, str]:
        """Validate if a help path exists."""
        try:
            level, content = self.get_help_content(path)
            if level == "error":
                return False, content.get("error", "Unknown error")
            return True, ""
        except Exception as e:
            return False, str(e) 