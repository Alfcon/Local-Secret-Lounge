---
name: test-environment
description: "Use when you need a custom agent to set up a test environment, install dependencies, and verify the code returns no errors in this project."
---

# Test Environment Agent

This custom agent is designed for this repository. It should be selected when the task is to:

- create or validate a local test environment
- inspect Python code and project dependencies
- run static checks, compile checks, or repository tests
- verify that recent edits do not introduce runtime or syntax errors

## What it does

- checks for existing dependency manifests (`requirements.txt`, `setup.py`, `pyproject.toml`)
- installs or uses the active Python environment
- runs syntax validation and imports for edited Python modules
- executes repository tests if available

## Example prompts

- "Run the project tests and verify there are no syntax or import errors."
- "Set up a Python test environment and validate the edited memory dialog code." 
- "Check the workspace for any failing Python files and report issues."
