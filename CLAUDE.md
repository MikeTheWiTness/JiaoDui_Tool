# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

K-12 multi-subject content pipeline — three stages:
1. **Convert** Word `.docx` → Markdown (via Pandoc)
2. **Split** Markdown into per-question/section directories
3. **Proofread** via LLM API (doubao model on Volces Ark) — subject+level-specific prompts for 24 subject-level combos

### v1.6 — Multi-subject support with level awareness

Each subject × level combination (小学/初中/高中) has its own config in `subjects/{学段}/{学科}/config.json`, containing prompts, lecture split rules, and exam split rules. The GUI has two dropdowns: 学段 (小学/初中/高中) and 学科 (subjects vary by level). Subject list updates dynamically when level changes.

### Split modes

Two lecture split strategies, determined by `lecture_split.split_mode` in config:

**`"title"` mode** (default, math/physics/chemistry etc.):
- Splits by bold title patterns like `**例1**`, `**清北班例题**`
- Each problem → `第N题/` directory
- Also generates `知识/` folder with non-problem content

**`"section"` mode** (English lectures):
- Splits by `##` section headers into coherent teaching units
- Each section → `板块N/` directory
- Skip knowledge extraction (sections are self-contained)
- Prompt treats input as a "教学版块" not a single "题目"

## Commands

```bash
# Activate venv
source venv/Scripts/activate

# Run the integrated multi-subject tool (GUI) — recommended
python 校对工具整合版v1.6.py

# Run the lecture → questions/sections splitter (GUI, standalone)
python 讲义拆分题目和知识转md.py

# Run the exam paper converter + splitter (GUI, standalone)
python 组卷网试卷转md.py

# Run the AI proofreading tool (GUI, standalone)
python API校对单讲拆分v1.6.py
```

## Architecture

### Core scripts

**`校对工具整合版v1.6.py`** — Integrated multi-subject tool:
- `IntegratedApp` GUI class with source mode (讲义/试卷), exec mode (完整流程/仅拆分/仅校对), level selector (小学/初中/高中), and subject selector
- Loads subject config from `subjects/{level}/{subject}/config.json` via `subject_config` module
- Raises an error if config is missing (no fallback)
- Split functions accept both `subject` and `level` parameters
- Section mode: auto-skip knowledge extraction, use `板块N/` directory naming

**`讲义拆分题目和知识转md.py`** — Lecture material pipeline:
1. Pandoc converts `.docx` → `.md` with LaTeX math preservation (`--mathjax`)
2. `fix_latex_escapes()` remedies Pandoc over-escaping of LaTeX commands
3. `comprehensive_clean()` strips table borders and merges split answer lines
4. `split_md_into_questions()` — two modes:
   - **title mode**: splits by bold patterns (loaded from config) into `第N题/` subdirectories
   - **section mode**: splits by `##` headers into `板块N/` subdirectories
5. `generate_knowledge_with_images()` — extracts non-question sections into `知识/` (skipped in section mode)
6. GUI has level + subject dropdowns

**`组卷网试卷转md.py`** — Exam paper pipeline (unchanged):
1. Pandoc converts `.docx` → `.md` (no `--mathjax`)
2. Post-processing for Microsoft formula format
3. `detect_answer_mode()` — `"inline"` or `"end"`
4. `split_md_into_questions()` splits by `数字．` pattern

**`API校对单讲拆分v1.6.py`** — AI proofreading (standalone):
- `MultiSubjectProofreadApp` GUI class with level + subject dropdowns
- Reads `.env` for API config (same format as integrated tool)
- Sends content + base64-encoded images to LLM API
- `call_api_with_retry()` with `reasoning_effort: "high"`, 2 retries, 480s timeout

### subject_config.py — Unified config loader

Central module for all subject configuration:
- `load_subject_config(subject, level)` → full config dict
- `get_question_prompt(subject, level)` → joined prompt string
- `get_knowledge_prompt(subject, level)` → joined prompt string
- `get_lecture_split_mode(subject, level)` → `"title"` or `"section"`
- `get_compiled_title_patterns(subject, level)` → compiled regex list
- `get_section_pattern(subject, level)` → section boundary regex

### Config structure

```
subjects/
  小学/                          # 5 subjects
    语文, 数学, 英语, 科学, 道法/config.json
  初中/                          # 10 subjects
    语文, 数学, 英语, 物理, 化学, 生物, 科学, 道法, 历史, 地理/config.json
  高中/                          # 9 subjects
    语文, 数学, 英语, 物理, 化学, 生物, 政治, 历史, 地理/config.json
```

Each `config.json`:
```json
{
  "question_prompt_lines": [...],
  "knowledge_prompt_lines": [...],
  "lecture_split": {
    "split_mode": "title" | "section",
    "section_pattern": "^##\\s",
    "wrapped_patterns": [...],
    "unwrapped_patterns": [...],
    "section_boundary": true
  },
  "exam_split": { "question_pattern": "^(\d+)．" }
}
```

Config file must exist at `subjects/{level}/{subject}/config.json` with `question_prompt_lines` and `knowledge_prompt_lines`. Missing files or fields raise an error.

### Data flow

```
.docx files
  → Pandoc → raw .md (+ _images/media/)
  → fix_latex_escapes / post_process_md
  → comprehensive_clean (lectures only)
  → split:
      title mode  → 第N题/第N题.md + images/ + 知识/
      section mode → 板块N/板块N.md + images/ (no 知识/)
  → AI proofreading (subject+level prompt) → _校对报告.md
```
