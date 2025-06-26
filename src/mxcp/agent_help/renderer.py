"""
Output formatting for the MXCP agent help system.
"""

import json
import click
from typing import Dict, Any, List

class HelpRenderer:
    """Render help content in different formats."""
    
    def __init__(self, json_output: bool = False):
        self.json_output = json_output
    
    def render(self, level: str, content: Dict[str, Any]) -> str:
        """Render help content based on level and format."""
        if level == "error":
            return self._render_error(content)
        
        if self.json_output:
            return json.dumps(content, indent=2)
        
        if level == "root":
            return self._render_root(content)
        elif level == "category":
            return self._render_category(content)
        elif level == "subcategory":
            return self._render_subcategory(content)
        elif level == "topic":
            return self._render_topic(content)
        else:
            return self._render_error({"error": f"Unknown level: {level}"})
    
    def _render_error(self, content: Dict[str, Any]) -> str:
        """Render error message."""
        error_msg = content.get("error", "Unknown error")
        if self.json_output:
            return json.dumps({"error": error_msg}, indent=2)
        
        return f"{click.style('❌ Error:', fg='red', bold=True)} {error_msg}"
    
    def _render_root(self, content: Dict[str, Any]) -> str:
        """Render root level help."""
        lines = []
        
        # Header
        lines.append(click.style(f"🤖 {content['title']}", fg='cyan', bold=True))
        lines.append("")
        lines.append(content['description'])
        lines.append("")
        
        # Security notice
        if content.get('security_notice'):
            lines.append(click.style("🚨 SECURITY-FIRST APPROACH 🚨", fg='white', bold=True, bg='red'))
            lines.append("")
            for line in content['security_notice'].strip().split('\n'):
                if line.strip():
                    if line.startswith('•'):
                        lines.append(click.style(line, fg='red', bold=True))
                    else:
                        lines.append(click.style(line, fg='red'))
            lines.append("")
        
        # Categories
        lines.append(click.style("📚 Available Categories:", fg='yellow', bold=True))
        lines.append("")
        
        for i, cat in enumerate(content['categories'], 1):
            security_priority = cat.get('security_priority', '')
            lines.append(f"{click.style(f'{i:2}.', fg='blue')} {click.style(cat['name'], fg='green', bold=True)} {security_priority}")
            lines.append(f"    {cat['description']}")
            lines.append(f"    {click.style('Command:', fg='cyan')} {cat['command']}")
            lines.append("")
        
        # Usage
        lines.append(click.style("🔧 Usage:", fg='yellow', bold=True))
        for usage in content['usage']:
            lines.append(f"  {usage}")
        lines.append("")
        
        # Examples
        lines.append(click.style("💡 Examples:", fg='yellow', bold=True))
        for example in content['examples']:
            lines.append(f"  {click.style(example, fg='green')}")
        lines.append("")
        
        # Security Quick Start
        if content.get('security_quick_start'):
            lines.append(click.style("🔒 Security Quick Start Guide:", fg='red', bold=True))
            for step in content['security_quick_start']:
                lines.append(f"  {click.style(step, fg='red', bold=True)}")
            lines.append("")

        # Next steps
        lines.append(click.style("🚀 Next Steps:", fg='yellow', bold=True))
        lines.append("  • Choose a category to explore: mxcp agent-help <category>")
        lines.append("  • Get started quickly: mxcp agent-help getting-started")
        lines.append("  • View schemas: mxcp agent-help schemas")
        
        return "\n".join(lines)
    
    def _render_category(self, content: Dict[str, Any]) -> str:
        """Render category level help."""
        lines = []
        current = content['current']
        
        # Header
        lines.append(click.style(f"📂 MXCP Agent Help - {current['name'].title()}", fg='cyan', bold=True))
        lines.append("")
        lines.append(f"{click.style('Description:', fg='yellow')} {current['description']}")
        lines.append("")
        
        # Technical context for AI agents
        if content.get('technical_context'):
            lines.append(click.style("🤖 Technical Context for AI Agents:", fg='blue', bold=True))
            for line in content['technical_context'].strip().split('\n'):
                if line.strip():
                    if line.startswith('External search hints:'):
                        lines.append(click.style(line, fg='cyan', bold=True))
                    elif line.strip().startswith('-'):
                        lines.append(click.style(f"  {line.strip()}", fg='blue'))
                    else:
                        lines.append(click.style(line, fg='blue'))
            lines.append("")
        
        # Security warning for category if present
        if content.get('security_warning'):
            lines.append(click.style("🚨 SECURITY WARNING", fg='red', bold=True, bg='yellow'))
            for line in content['security_warning'].strip().split('\n'):
                if line.strip():
                    lines.append(click.style(line, fg='red', bold=True))
            lines.append("")
        
        # Subcategories
        if content['subcategories']:
            lines.append(click.style("📋 Available Options:", fg='yellow', bold=True))
            lines.append("")
            
            for i, subcat in enumerate(content['subcategories'], 1):
                # Show agent priority if available
                priority_text = ""
                if subcat.get('agent_priority'):
                    priority_color = 'red' if subcat['agent_priority'] == 'high' else 'yellow' if subcat['agent_priority'] == 'medium' else 'green'
                    priority_text = ' ' + click.style(f'[{subcat["agent_priority"].upper()}]', fg=priority_color)
                
                lines.append(f"{click.style(f'{i:2}.', fg='blue')} {click.style(subcat['name'], fg='green', bold=True)}{priority_text}")
                lines.append(f"    {subcat['description']}")
                lines.append(f"    {click.style('Command:', fg='cyan')} {subcat['command']}")
                lines.append("")
        else:
            lines.append(click.style("ℹ️  No subcategories available for this category", fg='blue'))
            lines.append("")
        
        # Related categories
        if content.get('related'):
            lines.append(click.style("🔗 Related Categories:", fg='yellow', bold=True))
            for related in content['related']:
                lines.append(f"  • {click.style(related, fg='green')}: mxcp agent-help {related}")
            lines.append("")
        
        # Navigation
        lines.append(click.style("🧭 Navigation:", fg='yellow', bold=True))
        lines.append(f"  • Back to all categories: {click.style('mxcp agent-help', fg='green')}")
        if content['subcategories']:
            command_text = f"mxcp agent-help {current['name']} <option>"
            lines.append(f"  • Explore an option: {click.style(command_text, fg='green')}")
        
        return "\n".join(lines)
    
    def _render_subcategory(self, content: Dict[str, Any]) -> str:
        """Render subcategory level help."""
        lines = []
        current = content['current']
        parent = content['parent']
        
        # Header with breadcrumb
        breadcrumb = f"{parent['name']} > {current['name']}"
        lines.append(click.style(f"📁 MXCP Agent Help - {breadcrumb.title()}", fg='cyan', bold=True))
        lines.append("")
        lines.append(f"{click.style('Description:', fg='yellow')} {current['description']}")
        lines.append("")
        
        # Topics
        if content['topics']:
            lines.append(click.style("📝 Available Topics:", fg='yellow', bold=True))
            lines.append("")
            
            for i, topic in enumerate(content['topics'], 1):
                lines.append(f"{click.style(f'{i:2}.', fg='blue')} {click.style(topic['name'], fg='green', bold=True)}")
                lines.append(f"    {topic['description']}")
                lines.append(f"    {click.style('Command:', fg='cyan')} {topic['command']}")
                lines.append("")
        else:
            lines.append(click.style("ℹ️  No topics available for this subcategory", fg='blue'))
            lines.append("")
        
        # Navigation
        lines.append(click.style("🧭 Navigation:", fg='yellow', bold=True))
        lines.append(f"  • Back to {parent['name']}: {click.style(parent['command'], fg='green')}")
        lines.append(f"  • Back to all categories: {click.style('mxcp agent-help', fg='green')}")
        if content['topics']:
            path_str = " ".join(content["path"])
            command_text = f"mxcp agent-help {path_str} <topic>"
            lines.append(f"  • View a topic: {click.style(command_text, fg='green')}")
        
        return "\n".join(lines)
    
    def _render_topic(self, content: Dict[str, Any]) -> str:
        """Render topic level help with detailed content."""
        lines = []
        current = content['current']
        
        # Header with breadcrumb
        breadcrumb = " > ".join([item['name'] for item in content['breadcrumb']])
        lines.append(click.style(f"📄 MXCP Agent Help - {breadcrumb.title()}", fg='cyan', bold=True))
        lines.append("")
        
        # Topic content
        topic_content = content['content']
        
        # Security warnings (always first if present)
        if topic_content.get('security_warning'):
            lines.append(click.style("🚨 SECURITY WARNING", fg='red', bold=True, bg='yellow'))
            for line in topic_content['security_warning'].strip().split('\n'):
                if line.strip():
                    lines.append(click.style(line, fg='red', bold=True))
            lines.append("")
        
        if topic_content.get('security_critical'):
            lines.append(click.style("🚨🚨 CRITICAL SECURITY ALERT 🚨🚨", fg='white', bold=True, bg='red'))
            for line in topic_content['security_critical'].strip().split('\n'):
                if line.strip():
                    lines.append(click.style(line, fg='red', bold=True))
            lines.append("")

        # Overview
        if topic_content.get('overview'):
            lines.append(click.style("📖 Overview:", fg='yellow', bold=True))
            lines.append(topic_content['overview'])
            lines.append("")
        
        # Technical requirements (NEW for AI agents)
        if topic_content.get('technical_requirements'):
            lines.append(click.style("🔧 Technical Requirements:", fg='blue', bold=True))
            for req in topic_content['technical_requirements']:
                lines.append(f"  • {req}")
            lines.append("")
        
        # Prerequisites
        if topic_content.get('prerequisites'):
            lines.append(click.style("✅ Prerequisites:", fg='yellow', bold=True))
            for prereq in topic_content['prerequisites']:
                lines.append(f"  • {prereq}")
            lines.append("")
        
        # Code examples (NEW - more structured than steps)
        if topic_content.get('code_examples'):
            lines.append(click.style("💻 Code Examples:", fg='green', bold=True))
            for i, example in enumerate(topic_content['code_examples'], 1):
                if isinstance(example, dict):
                    if example.get('step'):
                        lines.append(f"{click.style(f'{i:2}.', fg='blue')} {click.style(example['step'], fg='green', bold=True)}")
                    elif example.get('file'):
                        lines.append(f"{click.style('📄', fg='blue')} {click.style(example['file'], fg='green', bold=True)}")
                    
                    if example.get('content'):
                        lines.append("    ```yaml")
                        for line in example['content'].strip().split('\n'):
                            lines.append(f"    {line}")
                        lines.append("    ```")
                    
                    if example.get('command'):
                        lines.append(f"    {click.style('Command:', fg='cyan')} {example['command']}")
                    
                    if example.get('expected'):
                        lines.append(f"    {click.style('Expected:', fg='green')} {example['expected']}")
                    
                    if example.get('technical_note'):
                        lines.append(f"    {click.style('🔧 Technical:', fg='blue')} {example['technical_note']}")
                    
                    if example.get('description'):
                        lines.append(f"    {example['description']}")
                    
                    lines.append("")
        
        # Steps (legacy support)
        elif topic_content.get('steps'):
            lines.append(click.style("🔧 Steps:", fg='yellow', bold=True))
            for i, step in enumerate(topic_content['steps'], 1):
                lines.append(f"{click.style(f'{i:2}.', fg='blue')} {click.style(step.get('command', 'Step'), fg='green', bold=True)}")
                if step.get('description'):
                    # Handle multiline descriptions
                    desc_lines = step['description'].strip().split('\n')
                    for desc_line in desc_lines:
                        if desc_line.strip():
                            lines.append(f"    {desc_line}")
                lines.append("")
        
        # Verification commands (NEW for AI agents)
        if topic_content.get('verification_commands'):
            lines.append(click.style("✅ Verification Commands:", fg='green', bold=True))
            for cmd in topic_content['verification_commands']:
                lines.append(f"  • {click.style(cmd, fg='green')}")
            lines.append("")
        
        # Troubleshooting commands (NEW for AI agents)
        if topic_content.get('troubleshooting_commands'):
            lines.append(click.style("🔍 Troubleshooting Commands:", fg='yellow', bold=True))
            for cmd in topic_content['troubleshooting_commands']:
                lines.append(f"  • {click.style(cmd, fg='yellow')}")
            lines.append("")
        
        # External search hints (NEW for AI agents)
        if topic_content.get('external_search_hints'):
            lines.append(click.style("🌐 External Search Hints:", fg='cyan', bold=True))
            for hint in topic_content['external_search_hints']:
                lines.append(f"  • {click.style(hint, fg='cyan')}")
            lines.append("")
        
        # Examples (legacy support)
        if topic_content.get('examples'):
            lines.append(click.style("💡 Examples:", fg='yellow', bold=True))
            for example in topic_content['examples']:
                if isinstance(example, dict):
                    if example.get('type'):
                        lines.append(f"• {click.style(example['type'], fg='green')}: {example.get('description', '')}")
                    if example.get('yaml'):
                        lines.append("  ```yaml")
                        for yaml_line in example['yaml'].strip().split('\n'):
                            lines.append(f"  {yaml_line}")
                        lines.append("  ```")
                else:
                    lines.append(f"  • {example}")
            lines.append("")
        
        # Verification (legacy support)
        if topic_content.get('verification'):
            lines.append(click.style("✅ Verification:", fg='yellow', bold=True))
            for verify in topic_content['verification']:
                lines.append(f"  • {verify}")
            lines.append("")
        
        # Security checklist
        if topic_content.get('security_checklist'):
            lines.append(click.style("🔒 Security Checklist:", fg='red', bold=True))
            for item in topic_content['security_checklist']:
                lines.append(f"  {click.style(item, fg='green' if '✅' in item else 'red')}")
            lines.append("")

        # Common vulnerabilities
        if topic_content.get('common_vulnerabilities'):
            lines.append(click.style("🚨 Common Vulnerabilities:", fg='red', bold=True))
            for vuln in topic_content['common_vulnerabilities']:
                lines.append(f"• {click.style('Vulnerability:', fg='red')} {vuln['vulnerability']}")
                lines.append(f"  {click.style('Test:', fg='yellow')} {vuln['test']}")
                lines.append(f"  {click.style('Prevention:', fg='green')} {vuln['prevention']}")
                lines.append("")

        # Common issues
        if topic_content.get('common_issues'):
            lines.append(click.style("⚠️  Common Issues:", fg='yellow', bold=True))
            for issue in topic_content['common_issues']:
                lines.append(f"• {click.style('Issue:', fg='red')} {issue['issue']}")
                lines.append(f"  {click.style('Solution:', fg='green')} {issue['solution']}")
                if issue.get('security_note'):
                    lines.append(f"  {click.style('🔒 Security Note:', fg='red', bold=True)} {issue['security_note']}")
                if issue.get('technical_note'):
                    lines.append(f"  {click.style('🔧 Technical Note:', fg='blue', bold=True)} {issue['technical_note']}")
                lines.append("")
        
        # What you learn (NEW for AI agents)
        if topic_content.get('what_you_learn'):
            lines.append(click.style("🎓 What You Learn:", fg='magenta', bold=True))
            for item in topic_content['what_you_learn']:
                lines.append(f"  • {item}")
            lines.append("")
        
        # Next steps
        if topic_content.get('next_steps'):
            lines.append(click.style("🚀 Next Steps:", fg='yellow', bold=True))
            for step in topic_content['next_steps']:
                lines.append(f"  • {step}")
            lines.append("")
        
        # Navigation
        lines.append(click.style("🧭 Navigation:", fg='yellow', bold=True))
        parent = content['parent']
        lines.append(f"  • Back to {parent['name']}: {click.style(parent['command'], fg='green')}")
        lines.append(f"  • Back to all categories: {click.style('mxcp agent-help', fg='green')}")
        
        return "\n".join(lines) 