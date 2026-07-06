# AI Function Testing Scripts

This folder contains manual CLI scripts for testing AI-related functions
directly (for example `app.services.ai_service.*`) without going through API
routes.

These scripts are intentionally kept outside `tests/` because they may:

- call external services (OpenAI, internal APIs)
- require credentials and network access
- produce non-deterministic outputs
- be slower and unsuitable for `pytest -q`

Use them for manual verification and prompt tuning.

## Full flow CLI

Use `test_full_flow_cli.py` to run the real end-to-end conversation flow with
the current `.env` configuration, MongoDB, and OpenAI:

```bash
.venv/bin/python scripts/ai_testing/test_full_flow_cli.py \
  --text "Bên mình có gói chụp prewedding ở studio không?" \
  --channel "manual_cli" \
  --customer-name "Test User" \
  --customer-id "test_user_001" \
  --message-mid "m_test_001" \
  --pretty
```
