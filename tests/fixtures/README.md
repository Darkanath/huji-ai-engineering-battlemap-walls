# Test fixtures

Small files the tests read. Nothing here costs money to use or comes from a paid run
without being reviewed first.

- **Recorded model responses** (`responses_*.json`): the model's replies as JSON, text and
  tool calls only. No images and never an API key. `tests/conftest.py` loads them into the
  scripted fake client.
- **Golden export** (`golden_result.json`, `golden_export.uvtt`): a fixed trace result and
  the Universal VTT file the exporter must produce from it.
- **Small generated images**, when a test needs a file on disk rather than one made in memory.
- **Single-session guard** (`request_single_session.json`): what the single-session tracer
  sends in its first request on the demo map (system prompt, tools, text, and each image's
  size and SHA-256). `test_single_session_first_request_is_unchanged` compares against it so
  the chunked pass cannot change the existing passes. Regenerate it only for a deliberate
  change to the single session: `REGENERATE_GUARD=1 pytest -k first_request`, then review
  the diff before committing.
