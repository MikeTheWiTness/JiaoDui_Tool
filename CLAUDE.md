# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

High school physics content pipeline — three stages:
1. **Convert** Word `.docx` → Markdown (via Pandoc)
2. **Split** Markdown into per-question directories and/or knowledge sections
3. **Proofread** via LLM API (doubao model on Volces Ark)

## Commands

```bash
# Activate venv
source venv/Scripts/activate

# Run the lecture → questions + knowledge splitter (GUI)
python 讲义拆分题目和知识转md.py

# Run the exam paper converter + splitter (GUI)
python 组卷网试卷转md.py

# Run the AI proofreading tool (GUI)
python API校对单讲拆分1.3.py
```

## Architecture

### Core scripts

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

**`API校对单讲拆分1.3.py`** — AI proofreading:
- `PhysicsProofreadApp` GUI class
- Reads split question dirs (`第N题/` containing `.md` + `images/`) and optional `知识/` dir
- Sends content + base64-encoded images to LLM API
- Uses two system prompts: `API_Proofreading_Prompt.json` (questions) and `API_Knowledge_Prompt.json` (knowledge sections)
- Auto-exports per-paper proofread reports to output directory
- `call_api_with_retry()` has 2 retries, 480s timeout, 1s interval between questions

### Config files

- `api_config.json` — API endpoint, key, model name, output directory
- `title_patterns.json` — Regex patterns for lecture question title detection
- `API_Proofreading_Prompt.json` — System prompt for question proofreading (supports `system_prompt` string or `system_prompt_lines` array formats)
- `API_Knowledge_Prompt.json` — System prompt for knowledge text proofreading

### Data flow

```
.docx files
  → Pandoc → raw .md (+ _images/media/)
  → fix_latex_escapes / post_process_md
  → comprehensive_clean (lectures only)
  → split into 第N题/第N题.md + 第N题/images/
  → (optional) 知识/知识.md + 知识/images/
  → AI proofreading → _校对报告.md
```
