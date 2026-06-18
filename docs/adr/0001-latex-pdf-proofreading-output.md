# ADR 0001: LaTeX PDF as Proofreading Output with Structured JSON Intermediate

## Status

superseded by [ADR 0002](0002-markdown-proofread-format.md)

<!-- The JSON structured-output approach documented below was replaced by Markdown `### 修改 N` format.
     Reason: doubao model frequently produced malformed JSON. Markdown parsing via `_parse_proofread_md()`
     proved significantly more reliable while still extracting the same structured data (`_校对数据.json`). -->

## Decision

Proofreading output transitions from unstructured Markdown reports to dual-output: a structured JSON file (校对数据) containing typed correction items, and a LaTeX-compiled PDF with a two-column paracol layout (left: original content with errors marked in red; right: correction suggestions).

## Context

The current `_校对报告.md` is raw LLM text output — narrative sections with no programmatic structure. Reviewers must read through paragraphs to find what changed. We need a visual, scannable format where errors are highlighted directly on the original content.

## Key Choices

1. **LaTeX engine**: XeLaTeX (via TeX Live 2026) with `ctexart` document class for Chinese support
2. **Layout**: `paracol` package for synchronized two-column parallelism (left = original + red markup, right = corrections)
3. **Fonts**: SimSun (宋体) for CJK, Times New Roman for Latin
4. **Math/chemistry**: `amsmath`, `amssymb`, `mhchem` — formulas embedded verbatim from original `.md`
5. **Images**: Embedded via `\includegraphics`; problematic images get red dashed borders
6. **Correction types**: `text` (inline replacement), `rewrite` (full sentence/paragraph), `region` (image/area-level)
7. **Module structure**: `latex_generator.py` (JSON → .tex), `pdf_compiler.py` (latexmk → PDF), `templates/proofread_template.tex`
8. **Integration**: Dual output — `_校对数据.json` + PDF, while existing `_校对报告.md` preserved unchanged

## Considered Options

- **paracol vs longtable vs tcolorbox**: `longtable` doesn't handle large text blocks well; `tcolorbox` is page-based. `paracol` supports arbitrary-length parallel text with page breaks — best fit for questions of varying length.
- **ctexart vs article+xeCJK**: `ctexart` handles Chinese typography (indentation, line spacing, font switching) out of the box, saving boilerplate. Fallback to `article` + `xeCJK` if compatibility issues arise.
- **Structured JSON vs prompt-only Markdown**: Prompt-only relies entirely on LLM output discipline with no validation. JSON with explicit `type` field enables programmatic parsing, error detection, and reliable LaTeX generation.

## Consequences

- All 24 subject configs must be updated with new prompts requesting structured JSON output
- The `doubao-seed-2-0-pro` model must reliably produce valid JSON with the three correction types
- LaTeX compilation adds a dependency on TeX Live (already available at `C:\Program Files\texlive\2026`)
- Images must be discoverable at compile time (relative paths from output directory)
