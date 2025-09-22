### ABSOLUTE CARDINAL RULES - VIOLATION MEANS IMMEDIATE FAILURE

1. **FOR LARGE CODEBASE ANALYSIS: USE GEMINI CLI**
   - When analyzing entire codebases or multiple files that exceed context limits, use `gemini -p`
   - Use `@` syntax for file/directory inclusion: `gemini -p "@src/ @tests/ Analyze test coverage"`
   - Use `gemini --all_files -p "prompt"` for entire project analysis
   - Gemini's massive context window can handle codebases that overflow Claude's limits
   - Use for verifying implementations across the entire codebase, checking patterns, or architectural analysis
   - **MODEL SELECTION STRATEGY**:
     - **First try**: `gemini -p "prompt"` (uses gemini-2.5-pro by default, highest quality)
     - **If quota limit hit**: `gemini -m gemini-1.5-flash -p "prompt"` (3x higher rate limits: 15/min vs 5/min)
     - Flash model is usually sufficient for code analysis and architectural reviews

2. **PYTEST TESTING: ABSOLUTE REQUIREMENTS**
   - **NEVER RUN TESTS WITHOUT DOCKER**: Always use `docker compose -f docker-compose.local.yml run --rm django pytest`
   - **NEVER SKIP OR BYPASS PYTEST**: No individual test files without pytest, no testing workarounds
   - **USE REAL DATABASE TESTS**: Always use `@pytest.mark.django_db` for database access, never mock Django ORM
   - **MAINTAIN TEST ISOLATION**: Each test must be independent, self-contained, with its own test data
   - Never run `pytest` directly on host system - all tests through containerized Django environment
   - Prefer integration tests with actual database operations over mocked tests
   - Only mock external services, APIs, or third-party dependencies

3. **GIT COMMIT MESSAGES: NO CO-AUTHORSHIP**
   - NEVER add "🤖 Generated with Claude Code" or "Co-Authored-By: Claude" to commit messages
   - Create clean, professional commit messages without AI attribution
   - Focus on clear, concise descriptions of the changes and their purpose
   - Follow conventional commit format: `type: description` (feat, fix, docs, etc.)

4. **LIBRARY DOCUMENTATION: USE CONTEXT7 MCP**
   - **HTMX**:
     - Use `mcp__context7__resolve-library-id` with "htmx" to get the library ID
     - Use `mcp__context7__get-library-docs` with `/bigskysoftware/htmx` for docs
     - Context7 provides 822+ HTMX code snippets and comprehensive attribute references
     - Use topic parameter to focus on specific areas (e.g., "ajax", "events", "attributes")
     - Access complete API documentation including all hx-* attributes, events, configuration options
     - Includes examples for active search, form validation, transitions, and modern patterns
   - **Tailwind CSS**:
     - Use `mcp__context7__get-library-docs` with `/tailwindlabs/tailwindcss.com` for docs
     - Access utility classes, @utility API, logical properties, and custom utilities
     - Use topic parameter for specific areas (e.g., "utilities", "layout", "spacing")
   - **DaisyUI**:
     - Use `mcp__context7__get-library-docs` with `/saadeghi/daisyui` for docs
     - Access semantic component classes, size modifiers, and color variants
     - Use topic parameter for specific components (e.g., "components", "buttons", "cards")
   - **Huey (Python Task Queue)**:
     - Use `mcp__context7__get-library-docs` with `/coleifer/huey` for docs
     - Access 148+ code snippets for task management, scheduling, and async operations
     - Use topic parameter for specific features (e.g., "task queue", "periodic tasks", "retries")
   - Prefer Context7 over web searches for syntax, attributes, and examples

### UI/UX Feedback Memories
- It look way better. but the container is too small and not zoomable, can we also remove the datasets info at the bottom?