# Task 6 report — trigger regression matrix

## Coverage

- Direct-mode configured keywords remain `keyword` with the command prefix disabled and enabled.
- `随机语音` remains a direct `random_all` trigger when the prefix is enabled.
- Prefix-enabled random filters require exactly one leading slash; unprefixed and double-slash forms are ignored, while `/随机关键词` returns `random_filter` with `关键词`.
- Legacy `#voice 关键词` handling remains confined to prefix mode.
- Direct, prefix, and LLM trigger modes remain distinct.

## Verification

- `pytest tests/test_trigger_matrix.py -q`: 7 passed.
- `pytest -q`: 42 passed.
- `python -m py_compile main.py web_api.py voice_catalog.py request_parser.py`: passed.
- `git diff --check`: passed.

## Parser changes

None. The new parser-only regression matrix passed against the existing parser integration. No chat-platform manual verification was performed.
