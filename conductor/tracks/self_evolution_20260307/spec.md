# Track Specification: Implement Code Generation and Sandbox Execution for Self-Evolution

## Overview
This track implements the "Self-Evolution" capability of GenieBot (Bridge-03). It enables the system to autonomously generate new Python agent code from natural language instructions, verify the code for safety, and execute it within a restricted sandbox.

## Functional Requirements
- **Dynamic Code Generation:** A specialized `CodeGenAgent` that uses Gemini Pro to output valid `BaseAgent` subclasses.
- **Restricted Sandbox:** Execution environment using `RestrictedPython` to prevent malicious or accidental system damage.
- **Safety Auditing:** Static and dynamic checks to ensure generated code adheres to security whitelists (e.g., restricted imports, no shell access).
- **Hot-Reloading:** Ability to load and register new agents into the `registry` without restarting the primary bot process.
- **Human-in-the-Loop:** A review flow where generated code must be approved via Telegram before deployment.

## Technical Requirements
- Language: Python 3.12+
- Sandbox: `RestrictedPython`
- AI Model: Gemini Pro (via `google-genai`)
- Framework: `aiogram 3.x` for interaction

## Acceptance Criteria
- [ ] `CodeGenAgent` can produce a working "Simple Search Agent" from a prompt.
- [ ] Generated code cannot access `.env` or run `os.system`.
- [ ] New agents can be registered and called via the main Telegram bridge.
- [ ] User can view and approve code snippets via Telegram.
