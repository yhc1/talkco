# Correctness Log

Record mistakes and correct behavior here to avoid repeating them.

---

## 2026-02-23: Must write tests before delivering code that parses LLM responses

**Error**: Delivered `review.py` with `issue["issue_type"]` (direct dict access) to parse GPT-4o JSON responses. The LLM returned a slightly different structure, causing `KeyError: 'issue_type'` at runtime.

**Correct behavior**:
1. Always use `.get()` with defaults when parsing LLM JSON responses — LLM output is not guaranteed to match the exact schema.
2. Validate required fields exist before using them; skip malformed entries with a warning log.
3. **Write tests with mocked LLM responses** before delivering any code that depends on LLM output parsing. Tests should cover: well-formed responses, malformed/missing fields, empty inputs, and unexpected values.

## 2026-02-23: Drain stale events BEFORE sending new data, not after

**Error**: In `openai_s2s.py`, the stale event queue drain was placed after `response.create()`. This created a race condition where actual response events could be discarded, causing the AI to appear unresponsive on some turns.

**Correct behavior**: Always drain stale events from the queue BEFORE sending new audio/data, so the drain cannot accidentally consume events from the current request.
