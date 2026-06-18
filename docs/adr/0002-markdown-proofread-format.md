# ADR 0002: Markdown `### 修改 N` Format for LLM Proofreading Output

Replaced the structured JSON proofreading output (ADR 0001) with Markdown `### 修改 N` format parsed by `_parse_proofread_md()`.

## Decision

The LLM outputs proofreading results in Markdown format:

```
### 修改 1
- **类型**: text
- **原文**: ``错误文字``
- **改为**: ``正确文字``
- **原因**: 错别字
```

`_parse_proofread_md()` extracts structured JSON (`_校对数据.json`) from this Markdown, with correction types `text` / `rewrite` / `region`.

## Why

The doubao-seed-2-0-pro model frequently produced malformed JSON (missing brackets, trailing commas, unescaped strings). Markdown output with backtick-delimited fields is naturally tolerant of LLM formatting variance — the parser only needs to match `### 修改 N` boundaries and key-value pairs, not brace-balanced JSON.

Same downstream consumers (LaTeX PDF generator, report aggregator) consume the same `_校对数据.json` structure. Only the LLM output format changed.

## Consequences

- All 24 subject config prompts updated to request `### 修改 N` format (commit `f0143e3`)
- `_parse_proofread_md()` lives in both `校对工具整合版v1.7.py` and `API校对单讲拆分v1.7.py` (duplicated for standalone operation)
- ADR 0001 is superseded
