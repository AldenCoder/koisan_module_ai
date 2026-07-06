# Codex Agent Guidelines

The project is a small FastAPI service with a lightweight test suite. To keep
Codex iterations quick:

- Skip running `pre-commit` when performing tasks.
- Use Python 3.11.
- Run tests with `pytest -q` to verify changes. The tests do not require any
  external services.
