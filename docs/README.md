# MXCP Documentation

This directory contains the source documentation for MXCP. The docs are built for [Astro](https://astro.build/) with the [Starlight](https://starlight.astro.build/) documentation theme.

## Structure

```
docs/
├── getting-started/     # Quickstart, introduction, glossary
├── concepts/            # Core concepts (endpoints, types, methodology)
├── tutorials/           # Step-by-step tutorials
├── security/            # Authentication, policies, auditing
├── operations/          # Deployment, configuration, monitoring
├── quality/             # Testing, validation, linting, evals
├── integrations/        # Claude Desktop, dbt, DuckDB
├── reference/           # CLI, API, schema references
├── examples/            # Use case examples
├── contributing/        # Contribution guidelines
├── .archive/            # Deprecated docs (not published)
└── index.md             # Homepage content
```

## Publishing to Website

The docs are synced to the [mxcp-website](https://github.com/raw-labs/mxcp-website) repository:

```bash
# From mxcp-website directory
rsync -av --delete /path/to/mxcp/docs/ ./src/content/docs/
```

The website dev server will automatically pick up changes. If new files don't appear in the sidebar, restart the dev server.

## Writing Documentation

### Frontmatter (Required)

Every markdown file must have YAML frontmatter at the top:

```yaml
---
title: "Page Title"
description: "Brief description for SEO (max 160 chars recommended)"
sidebar:
  order: 2
---
```

#### Required Fields

| Field | Description |
|-------|-------------|
| `title` | Page title displayed in sidebar and browser tab |
| `description` | SEO meta description (appears in search results) |

#### Optional Fields

| Field | Description |
|-------|-------------|
| `sidebar.order` | Number to control position in sidebar (lower = higher) |
| `sidebar.label` | Override sidebar label (defaults to title) |
| `sidebar.badge` | Add badge like `{ text: 'New', variant: 'tip' }` |
| `tableOfContents` | Set to `false` to hide table of contents |
| `pagefind` | Set to `false` to exclude from search |

### Related Topics Banner

Add a related topics banner after frontmatter for cross-referencing:

```markdown
> **Related Topics:** [Topic 1](link1) (brief note) | [Topic 2](link2) (brief note)
```

Example:
```markdown
> **Related Topics:** [Type System](type-system) (parameter types) | [Testing](/quality/testing) (write tests)
```

### Internal Links

Use relative paths for links within the same section:
```markdown
[Type System](type-system)           # Same directory
[Testing](../quality/testing)        # Different directory
```

Use absolute paths for cross-section links:
```markdown
[Testing](/quality/testing)
[CLI Reference](/reference/cli)
```

### Code Blocks

Use fenced code blocks with language identifiers:

````markdown
```yaml
mxcp: 1
tool:
  name: my_tool
```

```python
def my_function():
    pass
```

```bash
mxcp serve --port 8000
```
````

### Admonitions

Starlight supports these admonition types:

```markdown
:::note
General information
:::

:::tip
Helpful suggestions
:::

:::caution
Important warnings
:::

:::danger
Critical warnings
:::
```

### Tables

Use standard markdown tables:

```markdown
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Tool name |
| `description` | string | No | Tool description |
```

### Images

Place images in the same directory as the doc or in a shared assets folder:

```markdown
![Alt text](./image.png)
```

For the website, images should be in `src/assets/` or referenced from public folder.

## SEO Guidelines

### Title
- Keep under 60 characters
- Include primary keyword
- Make it descriptive and unique

### Description
- Keep between 120-160 characters
- Include primary and secondary keywords
- Write compelling copy that encourages clicks
- Each page should have a unique description

### Content
- Use headings hierarchically (h2, h3, h4)
- Include keywords naturally in headings and content
- Add alt text to images
- Use descriptive link text (not "click here")

## Adding New Pages

1. Create a new `.md` file in the appropriate directory
2. Add required frontmatter with title and description
3. Set `sidebar.order` to control position
4. Add Related Topics banner if applicable
5. Write content following the guidelines above
6. Sync to website: `rsync -av --delete docs/ ../mxcp-website/src/content/docs/`

## Adding New Sections

1. Create a new directory under `docs/`
2. Add an `index.md` file with section overview
3. Update `astro.config.mjs` in mxcp-website to add sidebar entry:

```javascript
sidebar: [
  // ... existing sections
  {
    label: 'New Section',
    autogenerate: { directory: 'new-section' },
  },
]
```

## File Naming Conventions

- Use lowercase with hyphens: `my-page.md`
- Keep names short but descriptive
- Use `index.md` for section landing pages
- Match URL structure you want (filename becomes URL slug)

## Sidebar Ordering

The sidebar order is controlled by:

1. `sidebar.order` in frontmatter (lower numbers appear first)
2. Alphabetical order for files without explicit order

Recommended order ranges:
- `1-10`: Core/overview pages
- `11-50`: Main content pages
- `51+`: Reference/appendix pages

## Checking Your Work

Before syncing to website:

1. **Frontmatter**: Ensure title and description are set
2. **Links**: Verify all internal links work
3. **Code**: Check code blocks have language identifiers
4. **Tables**: Ensure tables render correctly
5. **Preview**: Check in the website dev server

## Troubleshooting

### New files not appearing in sidebar
- Restart the Astro dev server
- Check frontmatter is valid YAML
- Verify file is in correct directory

### Broken links
- Use relative paths within sections
- Use absolute paths starting with `/` for cross-section links

### Formatting issues
- Ensure blank lines around code blocks and admonitions
- Check table alignment
- Verify no trailing spaces in frontmatter

## Resources

- [Starlight Documentation](https://starlight.astro.build/)
- [Astro Documentation](https://docs.astro.build/)
- [Markdown Guide](https://www.markdownguide.org/)
