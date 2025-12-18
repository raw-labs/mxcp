# MXCP Documentation Guidelines

This directory contains the source documentation for MXCP. These docs are automatically synced to [mxcp.dev](https://mxcp.dev) upon deployment.

## For AI Assistants

This documentation is maintained by both humans and AI assistants. When making changes to the MXCP codebase, you should update the corresponding documentation to keep it accurate and helpful.

### When to Update Documentation

Update docs when:
- Adding new CLI commands or options
- Adding new configuration options
- Changing endpoint schemas or behavior
- Adding new features or capabilities
- Fixing bugs that affect documented behavior
- Deprecating or removing features

### Documentation Principles

1. **Accuracy over completeness** - Only document what exists and works
2. **Examples are essential** - Every feature needs a working example
3. **Keep it current** - Outdated docs are worse than no docs
4. **Cross-reference** - Link related topics to help readers navigate
5. **SEO matters** - Every page should be discoverable via search
6. **Consistency matters** - Follow patterns established in existing docs

### Testing Examples

**All code examples must be tested before adding them to documentation.**

When adding or updating examples:

1. **Create a test environment** - Use a temporary directory (`/tmp/mxcp-test-*`)
2. **Copy the example exactly** - Use the same code that will appear in docs
3. **Run validation** - Execute `mxcp validate` to check for errors
4. **Run tests** - Execute `mxcp test` if the example includes tests
5. **Verify output** - Ensure the example produces the expected results
6. **Clean up** - Remove test directories when done

```bash
# Example testing workflow
mkdir -p /tmp/mxcp-docs-test && cd /tmp/mxcp-docs-test
# Create files from documentation example
mxcp validate
mxcp test
# Verify everything works, then clean up
rm -rf /tmp/mxcp-docs-test
```

**Never add examples that haven't been validated.** Broken examples frustrate users and damage trust.

### Following Existing Patterns

Before writing new documentation, review similar existing pages:

1. **Check the same section** - Look at other pages in the directory for structure and style
2. **Check similar content** - If documenting a tool, look at other tool documentation
3. **Match the tone** - Keep voice and terminology consistent
4. **Reuse patterns** - Use the same table formats, admonition styles, and code block conventions

For example:
- Writing a new endpoint type? Check `concepts/tools.md`, `concepts/resources.md`
- Adding a CLI command? Check `reference/cli.md` for the standard format
- Creating a tutorial? Check existing tutorials for structure and depth
- Adding an example? Check `examples/` for the standard layout

## Directory Structure

```
docs/
├── getting-started/     # First-time users: quickstart, introduction, glossary
├── concepts/            # Core concepts: endpoints, types, methodology
├── tutorials/           # Step-by-step guides for specific tasks
├── security/            # Authentication, policies, auditing
├── operations/          # Deployment, configuration, monitoring
├── quality/             # Testing, validation, linting, evals
├── integrations/        # Claude Desktop, dbt, DuckDB extensions
├── reference/           # CLI commands, API specs, schema reference
├── examples/            # Real-world use case examples
├── contributing/        # How to contribute to MXCP
├── schemas/             # JSON schemas (not markdown)
└── .archive/            # Deprecated docs (not published)
```

### Section Purposes

| Section | Audience | Content Type |
|---------|----------|--------------|
| getting-started | New users | Quick wins, orientation |
| concepts | All users | Understanding how things work |
| tutorials | Developers | Task-focused guides |
| security | DevOps, Security | Security configuration |
| operations | DevOps | Production deployment |
| quality | Developers | Testing and validation |
| integrations | Developers | Third-party connections |
| reference | All users | Complete technical specs |
| examples | All users | Copy-paste solutions |
| contributing | Contributors | Development guidelines |

## SEO Requirements

Every documentation page must be optimized for search engines. Users discover MXCP through Google searches like "MCP server authentication" or "DuckDB API gateway".

### Frontmatter (Required)

Every markdown file MUST have this frontmatter:

```yaml
---
title: "Page Title - Include Primary Keyword"
description: "Compelling 120-160 character description with keywords. Explains what the reader will learn."
sidebar:
  order: 1
---
```

### Title Guidelines

| Rule | Example |
|------|---------|
| Include primary keyword | "Authentication - OAuth & API Keys" ✓ |
| Keep under 60 characters | "Getting Started with MXCP" ✓ |
| Be specific, not generic | "Testing Endpoints" ✓ vs "Testing" ✗ |
| Use title case | "Input Policies" ✓ vs "input policies" ✗ |

### Description Guidelines

The description appears in search results. It must:

1. **Be 120-160 characters** - Google truncates longer descriptions
2. **Include primary keyword** in first 60 characters
3. **Include secondary keywords** naturally
4. **Describe the value** - What will the reader learn/do?
5. **Be unique** - No two pages should have the same description

**Good examples:**
```yaml
description: "Configure OAuth 2.0 and API key authentication for MXCP endpoints. Secure your MCP server with industry-standard auth."
description: "Write automated tests for MXCP endpoints. Validate SQL queries, Python functions, and policy enforcement with the test framework."
description: "Deploy MXCP to production with Docker. Configure environment variables, health checks, and monitoring for enterprise deployments."
```

**Bad examples:**
```yaml
description: "This page covers authentication."  # Too short, no keywords
description: "Learn about testing in MXCP and how to write tests for your endpoints and validate them."  # No specific keywords
description: "Authentication"  # Not a description
```

### Content SEO

1. **Headings hierarchy** - Use H2 → H3 → H4, never skip levels
2. **Keywords in headings** - Include relevant terms in section headers
3. **First paragraph** - Include primary keywords in opening paragraph
4. **Descriptive link text** - Use "see the [Testing Guide](/quality/testing)" not "click [here](/quality/testing)"
5. **Alt text for images** - Describe what the image shows

### Keyword Strategy by Section

| Section | Primary Keywords |
|---------|------------------|
| getting-started | mxcp, mcp server, quickstart, install |
| concepts | endpoints, tools, resources, prompts, mcp protocol |
| security | authentication, oauth, api key, policies, audit |
| operations | deployment, docker, configuration, monitoring |
| quality | testing, validation, linting, evaluations |
| integrations | claude desktop, dbt, duckdb, mcp client |
| reference | cli, api, schema, commands |

## Writing Guidelines

### Page Structure

Every page should follow this structure:

```markdown
---
title: "Feature Name"
description: "SEO-optimized description with keywords."
sidebar:
  order: 1
---

Brief introduction (1-2 sentences) explaining what this page covers.

> **Related Topics:** [Related 1](/path) (context) | [Related 2](/path) (context)

## Main Section

Content...

## Another Section

Content...

## See Also

- [Related Topic](/path) - Brief description
```

### Related Topics Banner

Add a related topics banner after the introduction to help navigation:

```markdown
> **Related Topics:** [Type System](/concepts/type-system) (parameter types) | [Testing](/quality/testing) (write tests)
```

### Code Examples

Always include working examples. Use appropriate language identifiers:

````markdown
```yaml
# YAML for endpoint definitions
mxcp: 1
tool:
  name: get_user
  description: Retrieve user by ID
```

```python
# Python for Python endpoints
def get_user(user_id: int) -> dict:
    return {"id": user_id, "name": "Example"}
```

```bash
# Bash for CLI commands
mxcp validate
mxcp test
mxcp serve --port 8000
```

```sql
-- SQL for queries
SELECT * FROM users WHERE id = $user_id
```
````

### Admonitions

Use sparingly for important callouts:

```markdown
:::note
General helpful information.
:::

:::tip
Best practices or shortcuts.
:::

:::caution
Important warnings about potential issues.
:::

:::danger
Critical warnings about data loss or security.
:::
```

### Tables

Use tables for structured data:

```markdown
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--port` | int | 8000 | Server port |
| `--debug` | flag | false | Enable debug logging |
```

### Internal Links

**Within the same section** - Use relative paths:
```markdown
[Type System](type-system)
[Next Page](./next-page)
```

**Cross-section links** - Use absolute paths:
```markdown
[Testing Guide](/quality/testing)
[CLI Reference](/reference/cli)
```

## Adding New Content

### Adding a New Page

1. Create the file in the appropriate directory
2. Add required frontmatter with SEO-optimized title and description
3. Set `sidebar.order` for positioning (lower = higher in sidebar)
4. Add Related Topics banner if applicable
5. Include working code examples
6. Link to related pages

### Adding a New Section

1. Create a new directory under `docs/`
2. Add an `index.md` with:
   - Overview of the section
   - List of pages in the section
   - When to use this section
3. Note: The website sidebar configuration is managed separately

### File Naming

| Rule | Example |
|------|---------|
| Lowercase with hyphens | `input-policies.md` ✓ |
| Short but descriptive | `testing.md` ✓ |
| Section index | `index.md` for landing pages |
| Match URL slug | `oauth.md` → `/security/oauth` |

### Sidebar Ordering

Control page order with `sidebar.order` in frontmatter:

| Range | Use For |
|-------|---------|
| 1-10 | Section overview and core pages |
| 11-50 | Main content pages |
| 51-99 | Advanced topics |
| 100+ | Reference and appendix |

## Updating Existing Content

### When Code Changes

If you modify MXCP code that affects documentation:

1. **Search for references** - Grep docs for the feature name
2. **Update examples** - Ensure all code examples still work
3. **Update descriptions** - Reflect new behavior accurately
4. **Check cross-references** - Update links if pages move

### Deprecating Content

When deprecating features:

1. Add a deprecation notice at the top:
   ```markdown
   :::caution[Deprecated]
   This feature is deprecated and will be removed in v2.0. Use [New Feature](/path) instead.
   :::
   ```

2. Update any pages that link to the deprecated feature

3. After removal, move the file to `.archive/` (not deleted, for reference)

### Moving Content

When reorganizing documentation:

1. Move the file to the new location
2. Search for all internal links to the old path
3. Update all references to use the new path
4. Consider adding a redirect note in the old location temporarily

## Quality Checklist

Before considering documentation complete, verify:

### Frontmatter
- [ ] Title is under 60 characters with primary keyword
- [ ] Description is 120-160 characters with keywords
- [ ] Description is unique (not duplicated from another page)
- [ ] `sidebar.order` is set appropriately

### Content
- [ ] Introduction explains what the page covers
- [ ] Related Topics banner links to relevant pages
- [ ] All code examples are complete and working
- [ ] Code blocks have language identifiers
- [ ] Headings follow H2 → H3 → H4 hierarchy
- [ ] Tables render correctly
- [ ] No broken internal links

### SEO
- [ ] Primary keyword in title
- [ ] Primary keyword in first paragraph
- [ ] Keywords in headings where natural
- [ ] Descriptive link text (not "click here")
- [ ] Alt text on any images

## Common Patterns

### CLI Command Documentation

```markdown
## command-name

Brief description of what the command does.

### Usage

\`\`\`bash
mxcp command-name [OPTIONS] [ARGUMENTS]
\`\`\`

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--option` | type | default | What it does |

### Examples

\`\`\`bash
# Basic usage
mxcp command-name

# With options
mxcp command-name --option value
\`\`\`
```

### Feature Documentation

```markdown
## Feature Name

Brief explanation of what this feature does and why you'd use it.

### Configuration

\`\`\`yaml
# Example configuration
feature:
  option: value
\`\`\`

### Usage

Step-by-step instructions...

### Examples

Real-world examples...

### See Also

- [Related Feature](/path)
```

### Troubleshooting Sections

```markdown
## Troubleshooting

### Problem: Error message or symptom

**Cause:** Why this happens

**Solution:**
1. Step one
2. Step two

### Problem: Another issue

...
```

## Archive Policy

The `.archive/` directory contains:
- Deprecated documentation (kept for reference)
- Old versions of rewritten pages
- Content that may be restored later

Files in `.archive/` are NOT published to the website.

## Starlight Components

The MXCP documentation website uses [Starlight](https://starlight.astro.build/), which provides built-in components for enhanced documentation. These components are available in `.mdx` files.

### Using Components

Import components at the top of your MDX file:

```mdx
---
title: "My Page"
description: "Page description"
---

import { Tabs, TabItem, Card, Steps } from '@astrojs/starlight/components';

Content here...
```

### Available Components

#### Tabs

Create tabbed interfaces for alternative content (e.g., different languages, platforms):

```mdx
import { Tabs, TabItem } from '@astrojs/starlight/components';

<Tabs>
  <TabItem label="SQL">
    ```sql
    SELECT * FROM users
    ```
  </TabItem>
  <TabItem label="Python">
    ```python
    def get_users():
        return db.query("SELECT * FROM users")
    ```
  </TabItem>
</Tabs>
```

**Props:**
- `syncKey` - Sync tab selection across multiple tab groups on the page

#### Card & CardGrid

Highlight important content in styled boxes:

```mdx
import { Card, CardGrid } from '@astrojs/starlight/components';

<Card title="Quick Start" icon="rocket">
  Get up and running in 5 minutes.
</Card>

<CardGrid>
  <Card title="SQL Endpoints" icon="document">
    Define tools with SQL queries.
  </Card>
  <Card title="Python Endpoints" icon="seti:python">
    Build tools with Python functions.
  </Card>
</CardGrid>
```

**Props:**
- `title` (required) - Card heading
- `icon` - Starlight icon name

#### LinkCard

Create clickable card links:

```mdx
import { LinkCard } from '@astrojs/starlight/components';

<LinkCard
  title="CLI Reference"
  description="Complete command-line documentation"
  href="/reference/cli/"
/>
```

#### Steps

Create numbered step-by-step guides with visual highlighting:

```mdx
import { Steps } from '@astrojs/starlight/components';

<Steps>
1. Install MXCP
   ```bash
   pip install mxcp
   ```

2. Initialize your project
   ```bash
   mxcp init --bootstrap
   ```

3. Start the server
   ```bash
   mxcp serve
   ```
</Steps>
```

#### FileTree

Display directory structures:

```mdx
import { FileTree } from '@astrojs/starlight/components';

<FileTree>
- mxcp-site.yml
- tools/
  - get_users.yml
  - **create_user.yml** (highlighted)
- resources/
  - users.yml
</FileTree>
```

**Features:**
- Append `/` for directories
- Use `**filename**` to highlight files
- Use `...` for omitted content

#### Aside

Callout boxes for notes, tips, warnings (alternative to `:::note` syntax):

```mdx
import { Aside } from '@astrojs/starlight/components';

<Aside type="tip" title="Pro Tip">
  Use `mxcp validate` before committing changes.
</Aside>
```

**Types:** `note` (default), `tip`, `caution`, `danger`

**Props:**
- `type` - Aside variant
- `title` - Custom title (optional)

#### Badge

Display status labels or categories:

```mdx
import { Badge } from '@astrojs/starlight/components';

<Badge text="New" variant="success" />
<Badge text="Deprecated" variant="caution" />
<Badge text="Required" variant="note" />
```

**Variants:** `default`, `note`, `tip`, `success`, `caution`, `danger`

**Props:**
- `text` (required) - Badge content
- `variant` - Color variant
- `size` - `small`, `medium`, or `large`

#### Icon

Render inline icons:

```mdx
import { Icon } from '@astrojs/starlight/components';

<Icon name="star" />
<Icon name="rocket" size="1.5rem" color="var(--sl-color-accent)" />
```

**Props:**
- `name` (required) - Icon name from [Starlight icons](https://starlight.astro.build/reference/icons/)
- `size` - CSS size value
- `color` - CSS color value
- `label` - Accessibility label

#### LinkButton

Call-to-action buttons:

```mdx
import { LinkButton } from '@astrojs/starlight/components';

<LinkButton href="/getting-started/quickstart/">Get Started</LinkButton>
<LinkButton href="/reference/cli/" variant="secondary">CLI Reference</LinkButton>
```

**Props:**
- `href` (required) - Destination URL
- `variant` - `primary` (default), `secondary`, or `minimal`
- `icon` - Starlight icon name
- `iconPlacement` - `start` or `end`

### When to Use Components

| Component | Use Case |
|-----------|----------|
| `Tabs` | Alternative implementations (SQL/Python), platform-specific instructions |
| `Card` | Feature highlights, important callouts |
| `CardGrid` | Landing pages, feature comparisons |
| `LinkCard` | Navigation to related pages |
| `Steps` | Installation guides, tutorials |
| `FileTree` | Project structure, directory layouts |
| `Aside` | Notes, warnings, tips (complex content) |
| `Badge` | Status labels, version indicators |
| `Icon` | Inline visual indicators |
| `LinkButton` | Primary CTAs, important navigation |

### Component vs Markdown

Use **Markdown syntax** for:
- Simple admonitions (`:::note`, `:::tip`, etc.)
- Basic lists and tables
- Code blocks

Use **Components** when you need:
- Interactive elements (tabs)
- Complex layouts (card grids)
- Visual enhancements (badges, icons)
- Structured content (steps, file trees)

For more details, see the [Starlight Components Documentation](https://starlight.astro.build/components/using-components/).

## Resources

- [Starlight Documentation](https://starlight.astro.build/) - Website framework
- [Starlight Components](https://starlight.astro.build/components/using-components/) - Built-in components reference
- [Starlight Icons](https://starlight.astro.build/reference/icons/) - Available icon names
- [Markdown Guide](https://www.markdownguide.org/) - Markdown syntax
- [Google SEO Guide](https://developers.google.com/search/docs) - SEO best practices
