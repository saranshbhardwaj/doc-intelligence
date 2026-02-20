# API Response Fixtures

This directory contains recorded API responses for record/replay testing.

## File Naming Convention

Test cassettes are named after the test function:
- `test_auto_map_fields.json` - Response for `test_auto_map_fields()` test

## Recording Mode

To record new API responses:
1. Set `PYTEST_RECORD_MODE=record` environment variable
2. Ensure `ANTHROPIC_API_KEY` is set with valid key
3. Run the test - it will make real API call and save response
4. Commit the cassette file to version control

## Replay Mode (Default)

By default, tests use saved responses without making real API calls.
This ensures:
- Fast test execution
- No API costs during testing
- Deterministic test results
- Works without network connection

## Updating Cassettes

If the API contract changes, delete the cassette file and re-record.
