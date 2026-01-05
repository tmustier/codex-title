# Feature List Guide

This guide explains how to write effective feature specifications for the long-task-harness.

## Why Feature Lists Matter

The article "Effective Harnesses for Long-Running Agents" found that open-ended tasks like "build a todo app" lead to poor outcomes. Instead, breaking work into 200+ specific, testable features dramatically improves agent performance.

Key insight: **"It is unacceptable to remove or edit tests because this could lead to missing or buggy outcomes."**

## Feature Structure

Each feature in `features.json` should have:

```json
{
  "id": "feature-001",
  "name": "Short descriptive name",
  "description": "What this feature does and why it matters",
  "steps": [
    "Concrete step 1",
    "Concrete step 2",
    "Concrete step 3"
  ],
  "passes": false,
  "notes": "Any implementation notes or decisions"
}
```

## Writing Good Features

### Be Specific and Testable

❌ Bad: "Add user authentication"
✅ Good: "User can log in with email and password, receiving a JWT token valid for 24 hours"

❌ Bad: "Make the UI responsive"
✅ Good: "Navigation menu collapses to hamburger icon at viewport widths below 768px"

### Include Concrete Steps

Each feature should have steps that can be verified:

```json
{
  "id": "auth-001",
  "name": "Email/password login",
  "description": "Users can authenticate with email and password",
  "steps": [
    "Navigate to /login",
    "Enter valid email and password",
    "Click submit button",
    "Verify redirect to /dashboard",
    "Verify JWT token in localStorage",
    "Verify token expiry is 24 hours from now"
  ],
  "passes": false,
  "notes": ""
}
```

### Granularity Guidelines

- **Too coarse**: "Build the frontend" (too many unknowns)
- **Too fine**: "Add a div element" (not meaningful)
- **Just right**: "Shopping cart displays item count badge on header icon"

Aim for features that can be completed in 15-60 minutes of focused work.

## Feature Categories

Organize features into logical categories:

```json
{
  "features": [
    { "id": "setup-001", "name": "Project scaffolding", ... },
    { "id": "setup-002", "name": "Database schema", ... },
    { "id": "auth-001", "name": "User registration", ... },
    { "id": "auth-002", "name": "User login", ... },
    { "id": "ui-001", "name": "Navigation header", ... }
  ]
}
```

Use prefixes to group related features:
- `setup-*`: Project setup and configuration
- `auth-*`: Authentication and authorization
- `ui-*`: User interface components
- `api-*`: API endpoints
- `test-*`: Test infrastructure
- `docs-*`: Documentation

## Testing Features

### Manual Testing
For each feature, manually verify all steps pass before marking `"passes": true`.

### Automated Testing
When possible, write automated tests that verify the feature steps. Reference the test file in notes:

```json
{
  "id": "auth-001",
  "name": "User login",
  "passes": true,
  "notes": "Tested in tests/auth.test.ts"
}
```

### Browser Automation
For UI features, use browser automation (Puppeteer MCP) for real end-to-end verification rather than just code inspection.

## Common Mistakes

1. **Marking features as passing without testing**: Always verify before updating the `passes` field.

2. **Editing features to make them easier**: If a feature is too hard, break it into smaller features instead of weakening the requirements.

3. **Removing features**: Never remove features. If a feature is no longer needed, mark it in notes and set passes to true with explanation.

4. **Vague acceptance criteria**: Every feature should have clear, binary pass/fail criteria.

## Example: Complete Feature List

See `assets/features_template.json` for a starter template with example features.
