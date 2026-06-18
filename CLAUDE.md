# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

K-12 multi-subject content proofreading pipeline — five stages:

1. **源文件输入** — Word `.docx` (组卷网 exam papers or 讲义 lecture materials)
2. **转换与拆分** — Convert `.docx` → Markdown, then split into per-question/section directories (two tools, pick one)
3. **中间标准结构** — Standardised directory layout: `第N题/` or `板块N/` + `知识/`
4. **API 批量校对** — LLM proofreading via doubao model on Volces Ark, subject+level-specific prompts
5. **报告生成** — Auto-save per-exam Markdown report + manual combined export + optional LaTeX PDF

### v1.7 — Multi-subject support with level awareness + LaTeX PDF output

Each subject × level combination (小学/初中/高中) has its own config in `subjects/{学段}/{学科}/config.json`, containing prompts, lecture split rules, and exam split rules. The GUI has two dropdowns: 学段 (小学/初中/高中) and 学科 (subjects vary by level). Subject list updates dynamically when level changes.

## Commands

```bash
# Create and activate venv
python -m venv venv
source venv/Scripts/activate

# Run the integrated multi-subject tool (GUI) — recommended
python 校对工具整合版v1.7.py

# Run the lecture → questions/sections splitter (GUI, standalone)
python 讲义拆分题目和知识转md.py

# Run the exam paper converter + splitter (GUI, standalone)
python 组卷网试卷转md.py

# Run the AI proofreading tool (GUI, standalone)
python API校对单讲拆分v1.7.py

# Run tests
python -m pytest tests/ -v
```

## Pipeline

### 1. 源文件输入

Word `.docx` files — two sources:
- **组卷网 exam papers** — question banks with answers inline or at end
- **讲义 lecture materials** — teaching content with examples and knowledge sections

### 2. 转换与拆分（二选一）

#### 工具一：讲义转换 (`讲义拆分题目和知识转md.py`)

1. Pandoc converts `.docx` → `.md` with LaTeX math preservation (`--mathjax`)
2. `fix_latex_escapes()` remedies Pandoc over-escaping of LaTeX commands
3. `comprehensive_clean()` strips table borders and merges split answer lines
4. `split_md_into_questions()` — two split modes:
   - **title mode**: splits by bold patterns (loaded from config) into `第N题/` subdirectories
   - **section mode**: splits by `##` headers into `板块N/` subdirectories
5. `generate_knowledge_with_images()` — extracts non-question sections into `知识/` (skipped in section mode)

#### 工具二：组卷网转换 (`组卷网试卷转md.py`)

1. Pandoc converts `.docx` → `.md` (no `--mathjax`)
2. Post-processing for Microsoft formula format
3. `detect_answer_mode()` — `"inline"` or `"end"`
4. Parse end-of-document answer tables, auto-inject `【答案】` lines
5. `split_md_into_questions()` splits by `数字．` pattern into `第N题/` subdirectories

### 3. 中间标准结构

```
试卷目录/
  第1题/
    第1题.md
    images/
  第2题/
    第2题.md
    images/
  ...
  知识/                          # lecture mode only (title mode)
    讲义名_知识.md
    images/
```

Section mode uses `板块N/` instead of `第N题/` and skips the `知识/` directory.

### 4. API 批量校对

**`API校对单讲拆分v1.7.py`** / integrated proofreader:

- Scans the exam/section directory for question and knowledge folders
- Distinguishes `第N题/` / `板块N/` (questions) from `知识/` (knowledge)
- Dynamically switches prompts:
  - `question_prompt_lines` for individual questions
  - `knowledge_prompt_lines` for knowledge sections
- Sends content + base64-encoded images to LLM API (doubao model, Volces Ark)
- `call_api_with_retry()` — `reasoning_effort: "high"`, 2 retries, 480s timeout
- Supports interrupt/resume — saves `_校对报告.md` per question immediately after proofreading
- Output format is Markdown (not JSON) with numbered annotation markers

### 5. 报告生成

**自动导出 (per exam):**
- Each exam/section gets a standalone Markdown report: `{name}_校对报告.md`
- Contains per-question proofreading details (original, correction, comments)

**手动导出 (manual):**
- Full aggregated report across all processed exams

**LaTeX PDF (optional):**
- "生成 LaTeX PDF 校对报告" checkbox in integrated GUI (`校对工具整合版v1.7.py`)
- Uses `latex_generator.py` + `pdf_compiler.py` + `templates/proofread_template.tex`
- Produces a combined PDF with paracol two-column layout (left: original, right: correction)
- XeLaTeX compilation with CJK support (`\text{}` wrapping in math mode)

## Split modes

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

## Architecture

### Core scripts

**`校对工具整合版v1.7.py`** — Integrated multi-subject tool:
- `IntegratedApp` GUI class with source mode (讲义/试卷), exec mode (完整流程/仅拆分/仅校对), level selector (小学/初中/高中), and subject selector
- "生成 LaTeX PDF 校对报告" checkbox for optional PDF output
- Loads subject config from `subjects/{level}/{subject}/config.json` via `subject_config` module
- Raises an error if config is missing (no fallback)
- Split functions accept both `subject` and `level` parameters
- Section mode: auto-skip knowledge extraction, use `板块N/` directory naming
- Combined PDF generation via `latex_generator` + `pdf_compiler`

**`讲义拆分题目和知识转md.py`** — Lecture material pipeline (see Pipeline §2 工具一)

**`组卷网试卷转md.py`** — Exam paper pipeline (see Pipeline §2 工具二)

**`API校对单讲拆分v1.7.py`** — AI proofreading (see Pipeline §4)

### Supporting modules

**`subject_config.py`** — Unified config loader:
- `load_subject_config(subject, level)` → full config dict
- `get_question_prompt(subject, level)` → joined prompt string
- `get_knowledge_prompt(subject, level)` → joined prompt string
- `get_lecture_split_mode(subject, level)` → `"title"` or `"section"`
- `get_compiled_title_patterns(subject, level)` → compiled regex list
- `get_section_pattern(subject, level)` → section boundary regex

**`latex_generator.py`** — Markdown → LaTeX conversion:
- Converts proofreading results to LaTeX with paracol two-column layout
- Handles markdown formatting (*italic* → `\textit`, **bold** → `\textbf`, ~~strikethrough~~)
- Image placeholder extraction to prevent LaTeX escaping
- CJK character wrapping in `\text{}` inside math mode
- Numbered annotation markers (circled numbers)

**`pdf_compiler.py`** — XeLaTeX PDF compilation:
- Compiles `.tex` files via `xelatex` subprocess call
- CJK font support via `xeCJK` package
- Combined PDF output from paracol layout

**`web_tools.py`** — Web search/fetch utilities for prompt enhancement

### Templates

**`templates/proofread_template.tex`** — LaTeX template for PDF proofreading reports:
- Paracol two-column layout (original | correction)
- xeCJK for Chinese/Japanese/Korean text
- Configurable geometry and font settings

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

### Tests

```
tests/
  test_json_escape.py        # JSON escape repair for LaTeX commands
  test_latex_generator.py    # LaTeX generator unit tests
  test_latex_template.py     # LaTeX template compilation tests (23)
  test_markdown_to_latex.py  # Markdown→LaTeX format conversion tests (24)
  test_pdf_compiler.py       # PDF compiler unit tests (9)
  test_sympy_tools.py        # SymPy safety/security tests
```

### Data flow

```
.docx files
  → Pandoc → raw .md (+ _images/media/)
  → fix_latex_escapes / post_process_md
  → comprehensive_clean (lectures only)
  → detect_answer_mode + inject 【答案】 (exams only)
  → split:
      title mode  → 第N题/第N题.md + images/ + 知识/
      section mode → 板块N/板块N.md + images/ (no 知识/)
      exam mode  → 第N题/第N题.md + images/
  → AI proofreading (subject+level prompt, Markdown output)
  → _校对报告.md (per question, saved immediately)
  → {name}_校对报告.md (per exam, auto-generated)
  → combined PDF (optional, via latex_generator + pdf_compiler)
```
