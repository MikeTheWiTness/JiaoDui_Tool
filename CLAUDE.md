# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

High school multi-subject content pipeline — three stages:
1. **Convert** Word `.docx` → Markdown (via Pandoc)
2. **Split** Markdown into per-question directories and/or knowledge sections
3. **Proofread** via LLM API (doubao model on Volces Ark) — subject-specific prompts for all 9 subjects

### v1.5 — Multi-subject support

Each subject (语文/数学/英语/物理/化学/生物/政治/历史/地理) has its own proofreading prompt in `prompts/{学科}.json`, containing both `question_prompt_lines` and `knowledge_prompt_lines`. The GUI has a subject selector Combobox that reloads prompts on change.

## Commands

```bash
# Activate venv
source venv/Scripts/activate

# Run the integrated multi-subject tool (GUI) — recommended for v1.5
python 校对工具整合版v1.4.py

# Run the lecture → questions + knowledge splitter (GUI, standalone)
python 讲义拆分题目和知识转md.py

# Run the exam paper converter + splitter (GUI, standalone)
python 组卷网试卷转md.py

# Run the AI proofreading tool (GUI, standalone, physics-only)
python API校对单讲拆分1.3.py
```

## Architecture

### Core scripts

**`校对工具整合版v1.4.py`** — Integrated multi-subject tool (v1.5):
- `IntegratedApp` GUI class with source mode (讲义/试卷), exec mode (完整流程/仅拆分/仅校对), and subject selector
- Loads subject-specific prompts from `prompts/{学科}.json` via `load_subject_question_prompt()` / `load_subject_knowledge_prompt()`
- Falls back to legacy `API_Proofreading_Prompt.json` / `API_Knowledge_Prompt.json` if subject prompt not found
- Default subject: 物理

**`讲义拆分题目和知识转md.py`** — Lecture material pipeline:
1. Pandoc converts `.docx` → `.md` with LaTeX math preservation (`--mathjax`)
2. `fix_latex_escapes()` remedies Pandoc over-escaping of LaTeX commands
3. `comprehensive_clean()` strips table borders and merges split answer lines
4. `split_md_into_questions()` splits by title patterns (loaded from `title_patterns.json`) into `第N题/` subdirectories
5. `generate_knowledge_with_images()` extracts non-question sections into a `知识/` subdirectory with `_知识.md`

Title patterns are bold Markdown headings like `**例1**`, `**清北班例题**`, `**A+班3**`. Questions end at the next section heading (`# ...`). Pattern matching uses `compile_title_patterns()` which wraps patterns as `^\*\*{pat}\*\*.*$`.

**`组卷网试卷转md.py`** — Exam paper pipeline (组卷网 = exam paper site):
1. Pandoc converts `.docx` → `.md` (no `--mathjax` flag here, uses Microsoft formula format)
2. Post-processing: removes Pandoc comment artifacts, converts `\~` to `\sim` in math, `*italic*` to `$inline math$`, `$$...$$` (single-line) to `$...$`
3. `detect_answer_mode()` inspects whether `【答案】` tags appear inline with questions or at end — returns `"inline"` or `"end"`
4. `split_md_into_questions()` splits by `数字．` pattern (`^(\d+)．`), handling both answer modes
5. In "end" mode, `parse_end_answers()` extracts answers from lines matching `^(\d+)[.．]\s*(.*)` and pairs them back to questions

**`API校对单讲拆分1.3.py`** — AI proofreading (standalone, physics-only):
- `PhysicsProofreadApp` GUI class
- Reads split question dirs (`第N题/` containing `.md` + `images/`) and optional `知识/` dir
- Sends content + base64-encoded images to LLM API
- Uses two system prompts: `API_Proofreading_Prompt.json` (questions) and `API_Knowledge_Prompt.json` (knowledge sections)
- Auto-exports per-paper proofread reports to output directory
- `call_api_with_retry()` has 2 retries, 480s timeout, 1s interval between questions

### Config files

- `.env` — API endpoint, key, model name
- `title_patterns.json` — Regex patterns for lecture question title detection
- `API_Proofreading_Prompt.json` — Legacy system prompt for question proofreading (physics, fallback)
- `API_Knowledge_Prompt.json` — Legacy system prompt for knowledge text proofreading (physics, fallback)
- `prompts/{学科}.json` — Per-subject prompts, each with `question_prompt_lines` and `knowledge_prompt_lines`

### Data flow

```
.docx files
  → Pandoc → raw .md (+ _images/media/)
  → fix_latex_escapes / post_process_md
  → comprehensive_clean (lectures only)
  → split into 第N题/第N题.md + 第N题/images/
  → (optional) 知识/知识.md + 知识/images/
  → AI proofreading (subject-specific prompt) → _校对报告.md
```
