#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多学科题目处理工具 v1.6 —— 整合版
  模式：试卷模式 / 讲义模式
  流程：完整流程 / 仅拆分 / 仅校对
  学科：语数外理化生政史地（各学科独立提示词）
  输出：output/拆题结果/ + output/校对报告/
"""

import os, re, json, base64, time, shutil, subprocess, threading, zipfile, sys
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path
import requests
try:
    from pydantic import BaseModel, Field
    _PYDANTIC_OK = True
except ImportError:
    _PYDANTIC_OK = False
import subject_config

# ========================= 路径工具 =========================
def _extract_json(text: str):
    """从 LLM 返回文本中提取 JSON 对象"""
    if not text:
        return None
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        block = m.group(1).strip()
        if block.startswith("{"):
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _save_proofread_json(res: str, q_dir: str):
    """尝试从 LLM 返回结果中提取 JSON 并保存为 _校对数据.json"""
    data = _extract_json(res)
    if data is None:
        return False
    json_path = os.path.join(q_dir, "_校对数据.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _app_dir():
    """exe 模式返回 exe 所在目录，否则返回脚本所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _app_path(rel):
    return os.path.join(_app_dir(), rel)

# ========================= 符号计算工具集成 =========================
try:
    from sympy_tools.tools import (
        EvaluateExpressionTool, SolveEquationTool, CheckEqualityTool,
        SimplifyExpressionTool, SolvePhysicsFormulaTool, DimensionalAnalysisTool,
        ComputeLimitTool, VectorOperationsTool, CircleFromTwoPointsTool,
        GeometryTool, BalanceChemicalEquationTool, StoichiometryCalcTool,
    )
    _TOOLS_AVAILABLE = True
except ImportError:
    _TOOLS_AVAILABLE = False

try:
    from web_tools import WebFetchTool, WebSearchTool
    _WEB_TOOLS_OK = True
except ImportError:
    _WEB_TOOLS_OK = False

# 学科 → 工具实例映射
def _build_tool_map():
    if not _TOOLS_AVAILABLE:
        return {}
    return {
        "数学": [
            EvaluateExpressionTool(), SolveEquationTool(), CheckEqualityTool(),
            SimplifyExpressionTool(), ComputeLimitTool(),
            GeometryTool(), VectorOperationsTool(), CircleFromTwoPointsTool(),
        ],
        "物理": [
            EvaluateExpressionTool(), SolveEquationTool(), SolvePhysicsFormulaTool(),
            DimensionalAnalysisTool(), VectorOperationsTool(), CircleFromTwoPointsTool(),
        ],
        "化学": [
            EvaluateExpressionTool(), SolveEquationTool(),
            BalanceChemicalEquationTool(), StoichiometryCalcTool(),
        ],
        "生物": [
            EvaluateExpressionTool(), SolveEquationTool(),
        ],
    }

SUBJECT_TOOLS = _build_tool_map()

# 注册联网工具
if _WEB_TOOLS_OK:
    _wf = WebFetchTool()
    _ws = WebSearchTool()
    SUBJECT_TOOLS.setdefault("语文", []).extend([_wf, _ws])
    for _subj in ["数学", "物理", "化学", "生物"]:
        SUBJECT_TOOLS.setdefault(_subj, []).append(_ws)


def _tool_to_openai(tool):
    """将 LangChain BaseTool 转为 OpenAI function-calling 格式"""
    schema = tool.args_schema.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        }
    }

def _execute_tool(tool_instances, tool_name, arguments):
    """根据工具名执行对应工具，返回结果字符串"""
    for t in tool_instances:
        if t.name == tool_name:
            try:
                return t._run(**arguments)
            except Exception as e:
                return f"工具执行错误: {e}"
    return f"未知工具: {tool_name}"

def _get_tool_instructions(subject):
    """生成提示词中的工具使用说明段落"""
    if subject not in SUBJECT_TOOLS or not SUBJECT_TOOLS[subject]:
        return ""
    tools = SUBJECT_TOOLS[subject]
    sympy_tools = [t for t in tools if t.name != "web_search" and t.name != "web_fetch"]
    web_tools = [t for t in tools if t.name == "web_search" or t.name == "web_fetch"]

    lines = []

    if subject == "语文":
        lines.append("## 可用的网页检索工具\n"
            "你在校对语文学科题目时，必须使用以下工具进行**原文联网检索和比对**，不得凭模型自身记忆判断原文准确性：\n")
        lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in web_tools))
        lines.append("\n使用规则：\n"
            "1. 遇到文言文/诗歌原文，必须调用 web_fetch 联网检索原文并逐字比对\n"
            "2. 先调 web_search 搜索'原文句子 site:sou-yun.cn'定位收录站点，再调 web_fetch 抓详情\n"
            "3. 搜索时必须直接用题目中原文的连续2-3句（至少15字）作为检索词，不要搜篇名标题\n"
            "4. 搜韵网 URL 格式：https://sou-yun.cn/QueryPoem.aspx?q=诗句\n"
            "5. 识典古籍搜索 URL 格式：https://www.shidianguji.com/search/原文句子?page_from=home_page\n"
            "6. 如果两次搜索均返回空或失败，标注'无法联网检索'并使用模型自身知识继续校对\n"
            "7. 仅文字类问题（错别字、语病等）不需要调用工具\n")
        return "".join(lines)

    if sympy_tools:
        lines.append("## 可用的符号计算工具\n"
            "你在校对该学科题目时，可以使用以下工具进行**实算验证**，不得凭模型自身估算数值结果：\n")
        lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in sympy_tools))
        lines.append("\n使用规则：对于需要数值计算、方程求解、公式推导验证的步骤，必须调用对应工具获取精确结果。\n")

    if web_tools:
        lines.append("## 可用的联网搜索工具\n"
            "如需查找最新说法、验证专业术语、检索不在训练数据内的信息，可使用：\n")
        lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in web_tools))
        lines.append("\n使用规则：先调 web_search 搜索，若需查看详情页再调 web_fetch 抓取。"
            "搜索失败或超时是正常情况，此时使用模型自身知识继续。\n")

    return "".join(lines)

# ========================= 全局配置 =========================
DEFAULT_OUTPUT = "output"
ENV_FILE = _app_path(".env")

def load_env_config():
    """从 .env 文件读取 API 配置"""
    cfg = {"api_url": "", "api_key": "", "model_name": ""}
    if not os.path.exists(ENV_FILE):
        return cfg
    try:
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key == 'api_url':
                        cfg['api_url'] = val
                    elif key == 'api_key':
                        cfg['api_key'] = val
                    elif key == 'model_name':
                        cfg['model_name'] = val
    except Exception:
        pass
    return cfg

def save_env_config(api_url, api_key, model_name):
    """保存 API 配置到 .env 文件"""
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.write(f"API_URL={api_url}\n")
        f.write(f"API_KEY={api_key}\n")
        f.write(f"MODEL_NAME={model_name}\n")

# ========================= 日志（GUI 注入） =========================
_log_func = None
def log(msg):
    if _log_func:
        _log_func(msg)

# ==================== 工具一：讲义管线 ====================

def compile_title_patterns(subject, level=None):
    """编译指定学科+学段的标题正则（委托 subject_config）"""
    return subject_config.get_compiled_title_patterns(subject, level)

def fix_latex_escapes(md_file):
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    special_chars = r'[\[\]\(\)\$_<>{}$]'
    content = re.sub(r'\\{2,}(?=' + special_chars + r')', r'\\', content)
    content = re.sub(r'\\{2,}([a-zA-Z]+)', r'\\\1', content)
    content = re.sub(r'\\{2,}([^a-zA-Z0-9])', r'\\\1', content)
    content = content.replace(r'\$', r'$')
    content = content.replace(r'\_', '_')
    content = content.replace(r'\<', '<')
    content = content.replace(r'\>', '>')
    content = content.replace(r'\{', '{')
    content = content.replace(r'\}', '}')
    content = content.replace(r'\left\(', r'\left(')
    content = content.replace(r'\right\)', r'\right)')
    content = content.replace(r'\left\[', r'\left[')
    content = content.replace(r'\right\]', r'\right]')
    for esc, orig in [(r'\^','^'), (r'\#','#'), (r'\~','~'), (r'\&','&'),
                       (r'\%','%'), (r'\*','*'), (r'\+','+'), (r'\-','-'),
                       (r'\=','='), (r'\|','|'), (r'\!','!'), (r"\'","'")]:
        content = content.replace(esc, orig)
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(content)

def comprehensive_clean(md_content):
    lines = md_content.splitlines()
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r'^[\|\+\-=\:\.\s\t]*$', stripped) and len(stripped) > 2:
            i += 1; continue
        line = re.sub(r'\|', '', line)
        if '答案:' in line:
            line = re.sub(r'[-=]+', '', line)
            if i + 1 < len(lines):
                nxt = lines[i+1].strip()
                if re.match(r'^[A-Z\s]+$', nxt):
                    line = line.rstrip() + ' ' + nxt
                    i += 1
        cleaned.append(line)
        i += 1
    text = '\n'.join(cleaned)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = '\n'.join(l.strip() for l in text.split('\n'))
    return text.strip()

def clean_md_file(md_file):
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        cleaned = comprehensive_clean(content)
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        return True
    except Exception as e:
        log(f"   清洗失败: {e}")
        return False

def split_by_title_patterns(md_file, output_root, base_name, do_clean, subject=None, level=None):
    """讲义模式：按标题模式拆分题目"""
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # 检查是否启用 section 模式
    split_mode = "title"
    section_pat = None
    if subject:
        split_mode = subject_config.get_lecture_split_mode(subject, level)
        if split_mode == "section":
            section_pat = subject_config.get_section_pattern(subject, level)

    lines = md_content.splitlines()
    questions = []

    if split_mode == "section" and section_pat:
        # ---- Section 模式：按 ## / ### 标题拆分 ----
        current_title = "引言"
        current_content = []
        for line in lines:
            stripped = line.strip()
            if section_pat.match(stripped):
                if current_content:
                    questions.append((current_title, '\n'.join(current_content)))
                current_title = stripped
                current_content = [line]
            else:
                current_content.append(line)
        if current_content:
            questions.append((current_title, '\n'.join(current_content)))
    else:
        # ---- Title 模式：按粗体题目标记拆分（原有逻辑） ----
        title_compiled = compile_title_patterns(subject, level)
        current_title = None
        current_content = []
        in_question = False
        for line in lines:
            stripped = line.strip()
            is_title = any(p.match(stripped) for p in title_compiled)
            is_section = stripped.startswith('#') and not stripped.startswith('**')
            if is_title:
                if current_title is not None:
                    questions.append((current_title, '\n'.join(current_content)))
                current_title = stripped
                current_content = [line]
                in_question = True
            elif is_section and in_question:
                questions.append((current_title, '\n'.join(current_content)))
                current_title = None; current_content = []; in_question = False
            else:
                if in_question:
                    current_content.append(line)
        if current_title is not None:
            questions.append((current_title, '\n'.join(current_content)))

    if not questions:
        log("   ⚠️ 未识别到任何题目，跳过分割")
        return False

    md_dir = Path(md_file).parent
    src_media = md_dir / f"{base_name}_images" / "media"
    log(f"   🔍 图片源目录: {src_media}")
    if not src_media.exists():
        log(f"   ❌ 图片源目录不存在")

    target_root = Path(output_root) / base_name
    target_root.mkdir(parents=True, exist_ok=True)

    def find_img(fname, sdir):
        if not sdir or not sdir.exists(): return None
        c = sdir / fname; return c if c.exists() else None

    unit_prefix = "板块" if split_mode == "section" else "第"
    unit_suffix = "" if split_mode == "section" else "题"

    total_copied = [0]; total_missing = [0]
    img_pat = re.compile(r'!\[(.*?)\]\((.*?)\)')
    for idx, (title, content) in enumerate(questions, start=1):
        q_dir_name = f"{unit_prefix}{idx}{unit_suffix}"
        q_dir = target_root / q_dir_name
        q_dir.mkdir(exist_ok=True)
        img_dir = q_dir / "images"; img_dir.mkdir(exist_ok=True)
        def repl(m):
            alt, src = m.group(1), m.group(2).strip()
            img_name = Path(src).name
            sp = find_img(img_name, src_media)
            if sp:
                dest = img_dir / img_name
                if not dest.exists():
                    shutil.copy2(sp, dest)
                total_copied[0] += 1
                return f"![{alt}](./images/{img_name})"
            else:
                log(f"      ⚠️ 未找到图片: {img_name}")
                total_missing[0] += 1
                return m.group(0)
        new_content = img_pat.sub(repl, content)
        (q_dir / f"{q_dir_name}.md").write_text(new_content, encoding='utf-8')

    log(f"   📂 拆分完成: {len(questions)} 题, 图片 {total_copied[0]} 张")
    return True

def generate_knowledge_with_images(cleaned_md, output_root, base_name, subject=None, level=None):
    """讲义模式：提取知识文件夹"""
    with open(cleaned_md, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.splitlines()
    compiled = compile_title_patterns(subject, level)
    filtered = []
    in_question = False
    for line in lines:
        stripped = line.strip()
        is_title = any(p.match(stripped) for p in compiled)
        is_section = stripped.startswith('#') and not stripped.startswith('**')
        if is_title:
            in_question = True; continue
        elif is_section:
            in_question = False; filtered.append(line)
        else:
            if not in_question:
                filtered.append(line)

    knowledge_text = '\n'.join(filtered)
    md_dir = Path(cleaned_md).parent
    src_media = md_dir / f"{base_name}_images" / "media"
    target_root = Path(output_root) / base_name / "知识"
    target_root.mkdir(parents=True, exist_ok=True)
    img_dest = target_root / "images"; img_dest.mkdir(exist_ok=True)

    img_pat = re.compile(r'!\[(.*?)\]\((.*?)\)')
    def repl(m):
        alt, src = m.group(1), m.group(2).strip()
        img_name = Path(src).name
        sp = None
        if src_media.exists():
            c = src_media / img_name
            if c.exists(): sp = c
        if sp:
            dest = img_dest / img_name
            if not dest.exists():
                shutil.copy2(sp, dest)
            return f"![{alt}](./images/{img_name})"
        return m.group(0)
    new_text = img_pat.sub(repl, knowledge_text)
    (target_root / f"{base_name}_知识.md").write_text(new_text, encoding='utf-8')
    log(f"   📘 知识文件已生成")

# ==================== 工具二：组卷网管线 ====================

def fix_pandoc_comment_anomaly(content):
    return content.replace('`<!-- -->`{=html}', '')

def fix_tilde_in_math(content):
    def repl(m):
        return m.group(0).replace(r'\~', r'\sim')
    content = re.sub(r'\$\$.*?\$\$', repl, content, flags=re.DOTALL)
    content = re.sub(r'\$[^$]+\$', repl, content)
    return content

def fix_tilde_in_text(content):
    return content.replace(r'\~', '~')

def convert_italics_to_math(content):
    math_blocks = []
    def save(m):
        math_blocks.append(m.group(0))
        return f'<<<MATHBLOCK{len(math_blocks)-1}>>>'
    content = re.sub(r'\$\$.*?\$\$', save, content, flags=re.DOTALL)
    content = re.sub(r'\$[^$]*\$', save, content)
    def italic_repl(m):
        inner = m.group(1)
        inner = re.sub(r'~(.+?)~', r'_{\1}', inner)
        return f'${inner}$'
    content = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', italic_repl, content)
    for i, block in enumerate(math_blocks):
        content = content.replace(f'<<<MATHBLOCK{i}>>>', block)
    return content

def convert_display_to_inline(content):
    def repl(m):
        formula = m.group(1)
        if '\n' in formula: return m.group(0)
        return f'${formula}$'
    return re.sub(r'\$\$(.+?)\$\$', repl, content, flags=re.DOTALL)

def post_process_md_zw(md_path):
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        log(f"   ❌ 后处理读取失败: {e}")
        return
    original = content
    content = fix_pandoc_comment_anomaly(content)
    content = fix_tilde_in_math(content)
    content = fix_tilde_in_text(content)
    content = convert_italics_to_math(content)
    content = convert_display_to_inline(content)
    if content != original:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(content)
        log("   ✅ 后处理完成")

def find_answer_section(lines):
    ref_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('**') and '参考答案' in stripped:
            ref_idx = i; break
        if '参考答案' in stripped and ('《' in stripped or not stripped.startswith('**')):
            ref_idx = i; break
    if ref_idx is None:
        return None, []
    return ref_idx, lines[ref_idx:]

def detect_answer_mode(lines):
    qs = re.compile(r'^(\d+)．')
    _, ans_lines = find_answer_section(lines)
    search = lines[:lines.index(ans_lines[0])] if ans_lines else lines
    blocks = []
    i = 0
    while i < len(search):
        line = search[i].strip()
        if qs.match(line) and not line.startswith('**'):
            start = i; j = i + 1
            while j < len(search):
                nxt = search[j].strip()
                if qs.match(nxt) and not nxt.startswith('**'): break
                j += 1
            blocks.append(search[start:j]); i = j
        else:
            i += 1
    if not blocks: return "end"
    inline_count = sum(1 for blk in blocks if any('【答案】' in l for l in blk))
    return "inline" if inline_count > len(blocks) / 2 else "end"

def parse_end_answers(answer_lines):
    if not answer_lines: return {}
    qa = re.compile(r'^(\d+)[.．]\s*(.*)')
    start = 0
    while start < len(answer_lines) and not qa.match(answer_lines[start].strip()):
        start += 1
    if start >= len(answer_lines): return {}
    result = {}
    i = start
    while i < len(answer_lines):
        m = qa.match(answer_lines[i].strip())
        if not m: i += 1; continue
        qnum = int(m.group(1))
        ans = m.group(2).strip()
        i += 1
        exp_lines = []
        while i < len(answer_lines):
            if qa.match(answer_lines[i].strip()): break
            exp_lines.append(answer_lines[i]); i += 1
        if not any('【答案】' in l for l in exp_lines):
            exp_lines.insert(0, f'【答案】{ans}')
        result[qnum] = {'answer': ans, 'explanation': exp_lines}
    return result

def split_by_question_numbers(md_file, output_root, base_name):
    """组卷网模式：按题号拆分，自适应答案位置"""
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    lines = md_content.splitlines()
    qs = re.compile(r'^(\d+)．')
    answer_mode = detect_answer_mode(lines)
    log(f"   📋 答案模式: {'随题' if answer_mode == 'inline' else '末尾'}")
    ans_start, ans_lines = find_answer_section(lines)
    main_lines = lines[:ans_start] if ans_start is not None else lines

    blocks = []
    i = 0
    while i < len(main_lines):
        line = main_lines[i].strip()
        if qs.match(line) and not line.startswith('**'):
            start = i; j = i + 1
            while j < len(main_lines):
                nxt = main_lines[j].strip()
                if qs.match(nxt) and not nxt.startswith('**'): break
                j += 1
            blocks.append(main_lines[start:j]); i = j
        else:
            i += 1

    if not blocks:
        log("   ⚠️ 未识别到任何题目"); return False

    end_answers = parse_end_answers(ans_lines) if answer_mode == "end" else None
    md_dir = Path(md_file).parent
    src_media = md_dir / f"{base_name}_images" / "media"
    log(f"   🔍 图片源目录: {src_media}")
    target_root = Path(output_root) / base_name
    target_root.mkdir(parents=True, exist_ok=True)

    def find_img(fname, sdir):
        if not sdir or not sdir.exists(): return None
        c = sdir / fname; return c if c.exists() else None

    total_copied = [0]; total_missing = [0]
    for idx, block in enumerate(blocks, start=1):
        if answer_mode == "inline":
            start_ans = start_exp = None
            for k, ln in enumerate(block):
                if ln.strip() == '【答案】': start_ans = k
                if ln.strip() == '【详解】': start_exp = k
            if start_ans is not None:
                stem = block[:start_ans]
                ans = block[start_ans:start_exp] if start_exp is not None else block[start_ans:]
                exp = block[start_exp:] if start_exp is not None else []
            else:
                stem = block; ans = []; exp = []
            def is_title(l):
                return bool(re.match(r'^\*\*.*\*\*$', l.strip()))
            stem = [l for l in stem if not is_title(l)]
            final_lines = stem + ans + exp
        else:
            stem = block
            def is_title(l):
                return bool(re.match(r'^\*\*.*\*\*$', l.strip()))
            stem = [l for l in stem if not is_title(l)]
            if end_answers and idx in end_answers:
                final_lines = stem + end_answers[idx]['explanation']
            else:
                final_lines = stem

        content_str = '\n'.join(final_lines)
        q_dir = target_root / f"第{idx}题"; q_dir.mkdir(exist_ok=True)
        img_dir = q_dir / "images"; img_dir.mkdir(exist_ok=True)

        img_pat = re.compile(r'!\[(.*?)\]\((.*?)\)')
        def repl(m):
            alt, src = m.group(1), m.group(2).strip()
            img_name = Path(src).name
            sp = find_img(img_name, src_media)
            if sp:
                dest = img_dir / img_name
                if not dest.exists():
                    try:
                        shutil.copy2(sp, dest)
                    except Exception as e:
                        log(f"      ❌ 图片复制失败: {img_name}, {e}")
                total_copied[0] += 1
                return f"![{alt}](./images/{img_name})"
            else:
                log(f"      ⚠️ 未找到图片: {img_name}")
                total_missing[0] += 1
                return m.group(0)

        new_content = img_pat.sub(repl, content_str)
        (q_dir / f"第{idx}题.md").write_text(new_content, encoding='utf-8')

    log(f"   📂 拆分完成: {len(blocks)} 题, 图片 {total_copied[0]} 张")
    return True

# ==================== Pandoc 转换（统一入口） ====================

PANDOC_PATH = None

def find_pandoc():
    """优先使用 exe 同目录下的 pandoc，否则使用 PATH 中的"""
    global PANDOC_PATH
    if PANDOC_PATH:
        return PANDOC_PATH
    import sys
    if getattr(sys, 'frozen', False):
        local = os.path.join(os.path.dirname(sys.executable), "pandoc.exe")
        if os.path.exists(local):
            PANDOC_PATH = local
            return PANDOC_PATH
    PANDOC_PATH = "pandoc"
    return PANDOC_PATH

def check_pandoc():
    pandoc = find_pandoc()
    try:
        r = subprocess.run([pandoc, "--version"], capture_output=True, text=True)
        if r.returncode == 0:
            log(f"✅ Pandoc: {r.stdout.splitlines()[0]}")
            return True
    except FileNotFoundError:
        log("❌ Pandoc 未安装")
    return False

def convert_with_pandoc(input_path, output_md, img_dir, use_mathjax=False):
    """统一 Pandoc 转换入口，use_mathjax 区分讲义/组卷网"""
    pandoc = find_pandoc()
    cmd = [
        pandoc, "-f", "docx", "-t", "markdown",
        "--extract-media", img_dir, "--wrap", "none",
        "--markdown-headings", "atx",
    ]
    if use_mathjax:
        cmd.insert(3, "--mathjax")
    cmd.extend([input_path, "-o", output_md])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0
    except Exception as e:
        log(f"   Pandoc 异常: {e}")
        return False

# ==================== 工具三：API 校对管线 ====================

def _load_prompt_from_file(filepath, key):
    """从JSON文件读取指定key的prompt行列表并拼接为字符串"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if key in data and isinstance(data[key], list):
            return "\n".join(data[key])
    except Exception:
        pass
    return None

def load_subject_question_prompt(subject, level=None):
    """加载指定学科+学段的题目校对提示词（委托 subject_config）"""
    return subject_config.get_question_prompt(subject, level)

def load_subject_knowledge_prompt(subject, level=None):
    """加载指定学科+学段的知识校对提示词（委托 subject_config）"""
    return subject_config.get_knowledge_prompt(subject, level)

def get_full_question_prompt(subject, level=None):
    """获取指定学科+学段的完整题目校对提示词（含工具说明）"""
    base = load_subject_question_prompt(subject, level)
    tool_instructions = _get_tool_instructions(subject)
    return base + "\n" + tool_instructions if tool_instructions else base

def get_full_knowledge_prompt(subject, level=None):
    """获取指定学科+学段的完整知识校对提示词（含工具说明）"""
    base = load_subject_knowledge_prompt(subject, level)
    tool_instructions = _get_tool_instructions(subject)
    return base + "\n" + tool_instructions if tool_instructions else base

# 启动时默认加载高中物理提示词（与默认学段学科一致）
SYSTEM_PROMPT = get_full_question_prompt("物理", "高中")
KNOWLEDGE_SYSTEM_PROMPT = get_full_knowledge_prompt("物理", "高中")
MAX_RETRY = 2; TIME_OUT = 480; QUESTION_INTERVAL = 1; MAX_FILE_SIZE = 10 * 1024 * 1024

def call_api(api_url, api_key, model, md_text, images, q_title, system_prompt, tools=None, subject=None):
    """调用 LLM API，支持可选的符号计算工具调用"""
    err_msg = ""
    tool_instances = tools or []
    openai_tools = [_tool_to_openai(t) for t in tool_instances] if tool_instances else None
    chat_url = api_url.rstrip("/")
    if not chat_url.endswith("/chat/completions"):
        chat_url += "/chat/completions"

    for retry in range(MAX_RETRY + 1):
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": f"编号：{q_title}\n内容：\n{md_text}"},
                    *images
                ]}
            ]
            payload = {
                "model": model, "messages": messages,
                "temperature": 0.3, "reasoning_effort": "high"
            }
            if openai_tools:
                payload["tools"] = openai_tools

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
            resp.raise_for_status()
            choice = resp.json()["choices"][0]

            # 处理 tool calls 循环（理科最多5轮，语文最多10轮——网页搜索可能需要多次尝试）
            max_loops = 10 if subject == "语文" else 5
            loop = 0
            while choice.get("finish_reason") == "tool_calls" or choice["message"].get("tool_calls"):
                if loop >= max_loops:
                    return f"**工具调用超限：** 模型进行了超过{max_loops}轮工具调用，已中止。"
                # 将 assistant 消息（含 tool_calls）加入历史
                messages.append(choice["message"])
                for tc in choice["message"]["tool_calls"]:
                    tool_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    result = _execute_tool(tool_instances, tool_name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result[:4000]  # 限制结果长度
                    })
                    log(f"   🔧 {tool_name}({json.dumps(args, ensure_ascii=False)[:120]})")
                # 继续调用
                resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                loop += 1

            return choice["message"]["content"]
        except Exception as e:
            err_msg = str(e)
            if retry < MAX_RETRY:
                log(f"⚠️ {q_title} 第{retry+1}次重试...")
                time.sleep(2)
    return f"**API调用失败：**\n{err_msg}"

def collect_paper_dirs(base_path):
    """收集指定路径下的试卷子目录"""
    result = []
    base = Path(base_path)
    if not base.exists(): return result
    # 如果路径直接包含 第1题 子目录，则它本身就是一套试卷
    sub_items = [x for x in base.iterdir() if x.is_dir()]
    sub_names = [x.name for x in sub_items]
    def _is_unit_dir(name):
        return '题' in name or name.startswith('板块')
    has_question_dir = any(_is_unit_dir(n) for n in sub_names)
    has_knowledge = any(n == '知识' for n in sub_names)
    if has_question_dir or has_knowledge:
        result.append(str(base))
    else:
        # 扫描下一级
        for d in sub_items:
            inner = [x.name for x in d.iterdir() if x.is_dir()]
            if any(_is_unit_dir(n) for n in inner) or '知识' in inner:
                result.append(str(d))
    return result


# ==================== 整合 GUI ====================

class IntegratedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("多学科题目处理工具 v1.6（整合版）")
        self.root.geometry("1050x750")
        self.root.minsize(900, 650)

        # 状态
        self.source_mode = tk.StringVar(value="讲义")   # 来源：讲义/试卷
        self.exec_mode = tk.StringVar(value="完整流程")  # 执行：完整流程/仅拆分/仅校对
        self.output_dir = tk.StringVar(value="output")
        self.current_level = tk.StringVar(value="高中")
        self.current_subject = tk.StringVar(value="物理")  # 当前学科

        # 讲义选项
        self.clean_enabled = tk.BooleanVar(value=True)
        self.knowledge_enabled = tk.BooleanVar(value=True)

        # 文件列表（转换用）
        self.file_list = []
        # 校对清单
        self.proofread_list = []   # [(dir_path, paper_name)]
        # 校对结果
        self.proofread_result = {}
        # 任务控制
        self.task_running = False
        self.task_interrupt = False
        # API 配置（从 .env 加载）
        self.api_config = load_env_config()

        self.setup_ui()
        self.update_ui_for_mode()

    # ===== API 配置弹窗 =====
    def open_api_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("API 配置")
        dialog.geometry("480x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="接口地址：").grid(row=0, column=0, sticky=tk.W, pady=6)
        e_url = ttk.Entry(frame, width=50)
        e_url.grid(row=0, column=1, padx=6, pady=6)
        e_url.insert(0, self.api_config.get("api_url", ""))

        ttk.Label(frame, text="API 密钥：").grid(row=1, column=0, sticky=tk.W, pady=6)
        e_key = ttk.Entry(frame, width=50, show="*")
        e_key.grid(row=1, column=1, padx=6, pady=6)
        e_key.insert(0, self.api_config.get("api_key", ""))

        ttk.Label(frame, text="模型名称：").grid(row=2, column=0, sticky=tk.W, pady=6)
        e_model = ttk.Entry(frame, width=50)
        e_model.grid(row=2, column=1, padx=6, pady=6)
        e_model.insert(0, self.api_config.get("model_name", ""))

        def do_save():
            url = e_url.get().strip()
            key = e_key.get().strip()
            model = e_model.get().strip()
            if not url or not key or not model:
                messagebox.showwarning("提示", "请填写完整配置", parent=dialog)
                return
            save_env_config(url, key, model)
            self.api_config = {"api_url": url, "api_key": key, "model_name": model}
            log("✅ API 配置已保存到 .env")
            dialog.destroy()

        ttk.Button(frame, text="保存", command=do_save).grid(row=3, column=0, columnspan=2, pady=12)

    # ===== UI =====
    def setup_ui(self):
        # --- 第0行：来源模式 ---
        f0 = ttk.Frame(self.root, padding=10)
        f0.pack(fill=tk.X)
        ttk.Label(f0, text="来源模式：").pack(side=tk.LEFT)
        ttk.Radiobutton(f0, text="讲义模式", variable=self.source_mode, value="讲义",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(f0, text="试卷模式", variable=self.source_mode, value="试卷",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=4)

        # --- 第1行：执行模式 ---
        f1 = ttk.Frame(self.root, padding=10)
        f1.pack(fill=tk.X)
        ttk.Label(f1, text="执行模式：").pack(side=tk.LEFT)
        ttk.Radiobutton(f1, text="完整流程", variable=self.exec_mode, value="完整流程",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(f1, text="仅拆分", variable=self.exec_mode, value="仅拆分",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(f1, text="仅校对", variable=self.exec_mode, value="仅校对",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=4)

        # --- 第2行：学段+学科选择 ---
        f_subj = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        f_subj.pack(fill=tk.X)
        ttk.Label(f_subj, text="学段：").pack(side=tk.LEFT)
        self.level_combo = ttk.Combobox(f_subj, textvariable=self.current_level,
                                        values=subject_config.LEVELS, state="readonly", width=6)
        self.level_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.level_combo.bind("<<ComboboxSelected>>", self.on_level_changed)
        ttk.Label(f_subj, text="校对学科：").pack(side=tk.LEFT)
        self.subject_combo = ttk.Combobox(f_subj, textvariable=self.current_subject,
                                          values=subject_config.get_subjects_for_level(self.current_level.get()),
                                          state="readonly", width=8)
        self.subject_combo.pack(side=tk.LEFT, padx=6)
        self.subject_combo.bind("<<ComboboxSelected>>", self.on_subject_changed)

        # --- 第3行：转换设置区 ---
        self.frame_convert_settings = ttk.Frame(self.root, padding=10)
        self.frame_convert_settings.pack(fill=tk.X)

        f_out = ttk.Frame(self.frame_convert_settings)
        f_out.pack(fill=tk.X)
        ttk.Label(f_out, text="输出根目录：").pack(side=tk.LEFT)
        ttk.Entry(f_out, textvariable=self.output_dir, width=50).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(f_out, text="浏览", command=self.select_output_dir).pack(side=tk.LEFT)

        self.frame_jy_options = ttk.Frame(self.frame_convert_settings)
        self.frame_jy_options.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(self.frame_jy_options, text="清理表格边框", variable=self.clean_enabled).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(self.frame_jy_options, text="提取知识文件夹", variable=self.knowledge_enabled).pack(side=tk.LEFT, padx=4)

        # --- 第3行：文件/目录选择区 ---
        self.frame_file_area = ttk.Frame(self.root, padding=10)
        self.frame_file_area.pack(fill=tk.X)

        # 转换模式的按钮（保存引用以便切换）
        self.btn_add_files = ttk.Button(self.frame_file_area, text="📁 添加文件", command=self.add_files)
        self.btn_add_folder = ttk.Button(self.frame_file_area, text="📂 添加文件夹", command=self.add_folder)
        self.btn_clear = ttk.Button(self.frame_file_area, text="🗑️ 清空列表", command=self.clear_list)
        self.btn_select_papers = ttk.Button(self.frame_file_area, text="🔍 选择试卷目录",
                                            command=self.select_single_paper)
        self.btn_select_root = ttk.Button(self.frame_file_area, text="📂 选择根目录",
                                          command=self.select_root_for_proofread)

        self.btn_add_files.pack(side=tk.LEFT, padx=4)
        self.btn_add_folder.pack(side=tk.LEFT, padx=4)
        self.btn_clear.pack(side=tk.LEFT, padx=4)

        # --- 第4行：待处理清单 ---
        self.frame_list = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        self.frame_list.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.frame_list, text="待处理清单：").pack(anchor=tk.W)
        self.list_box = tk.Listbox(self.frame_list, height=6)
        self.list_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        # --- 第5行：操作按钮 ---
        frame_actions = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        frame_actions.pack(fill=tk.X)

        self.btn_action = ttk.Button(frame_actions, text="🚀 开始转换", command=self.start_conversion)
        self.btn_action.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(frame_actions, text="⏹️ 中断", command=self.interrupt_task, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_actions, text="📄 导出报告", command=self.export_report).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_actions, text="⚙️ API 配置", command=self.open_api_dialog).pack(side=tk.RIGHT, padx=4)

        # --- 第7行：日志 ---
        self.log_text = scrolledtext.ScrolledText(self.root, height=12, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        global _log_func
        _log_func = self._log

    def _log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    # ===== 模式切换 =====
    def on_mode_changed(self):
        self.update_ui_for_mode()

    def on_level_changed(self, event=None):
        """学段切换时更新学科下拉列表并重新加载提示词"""
        level = self.current_level.get()
        subjects = subject_config.get_subjects_for_level(level)
        self.subject_combo['values'] = subjects
        # 当前学科不在新列表中则切换到第一个
        if self.current_subject.get() not in subjects:
            self.current_subject.set(subjects[0])
        self.on_subject_changed()

    def on_subject_changed(self, event=None):
        """学科切换时重新加载对应的提示词"""
        subject = self.current_subject.get()
        level = self.current_level.get()
        global SYSTEM_PROMPT, KNOWLEDGE_SYSTEM_PROMPT
        SYSTEM_PROMPT = get_full_question_prompt(subject, level)
        KNOWLEDGE_SYSTEM_PROMPT = get_full_knowledge_prompt(subject, level)
        tool_count = len(SUBJECT_TOOLS.get(subject, []))
        tool_info = f"，{tool_count}个符号计算工具可用" if tool_count else ""
        log(f"📚 已切换到：{level}{subject}（提示词已更新{tool_info}）")

    def update_ui_for_mode(self):
        exec_mode = self.exec_mode.get()
        source_mode = self.source_mode.get()
        is_proof_only = (exec_mode == "仅校对")

        # 转换设置区：仅校对时隐藏
        if is_proof_only:
            self.frame_convert_settings.pack_forget()
        else:
            self.frame_convert_settings.pack(fill=tk.X, before=self.frame_list)
            if source_mode == "讲义":
                self.frame_jy_options.pack(fill=tk.X, pady=(6, 0))
            else:
                self.frame_jy_options.pack_forget()

        # 文件区按钮
        if is_proof_only:
            self.btn_add_files.pack_forget()
            self.btn_add_folder.pack_forget()
            self.btn_clear.pack_forget()
            self.btn_select_papers.pack(side=tk.LEFT, padx=4)
            self.btn_select_root.pack(side=tk.LEFT, padx=4)
        else:
            self.btn_select_papers.pack_forget()
            self.btn_select_root.pack_forget()
            self.btn_add_files.pack(side=tk.LEFT, padx=4)
            self.btn_add_folder.pack(side=tk.LEFT, padx=4)
            self.btn_clear.pack(side=tk.LEFT, padx=4)

        # 统一操作按钮：根据模式切换文字和命令
        if is_proof_only:
            self.btn_action.config(text="🚀 开始校对", command=self.start_proofread)
        elif exec_mode == "完整流程":
            self.btn_action.config(text="🚀 开始处理", command=self.start_full_pipeline)
        else:
            self.btn_action.config(text="🚀 开始转换", command=self.start_conversion)

        self.refresh_listbox()

    def select_output_dir(self):
        path = filedialog.askdirectory(title="选择输出根目录")
        if path: self.output_dir.set(path)

    # ===== 文件操作 =====
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 Word 文档或压缩包",
            filetypes=[("支持的文件", "*.docx;*.doc;*.zip"), ("Word 文档", "*.docx;*.doc"),
                        ("ZIP 压缩包", "*.zip"), ("所有文件", "*.*")]
        )
        added = 0
        for p in paths:
            if p.lower().endswith('.zip'):
                added += self._extract_zip(p)
            elif p not in self.file_list:
                self.file_list.append(p); added += 1
        self.refresh_listbox()
        log(f"📁 已添加 {added} 个文件")

    def _extract_zip(self, zip_path):
        """解压 zip 并将其中所有 Word 文件加入清单，返回添加数量"""
        try:
            out_dir = self.output_dir.get().strip() or DEFAULT_OUTPUT
            zip_basename = os.path.splitext(os.path.basename(zip_path))[0]
            extract_root = os.path.join(out_dir, "解压缩文件")
            extract_dir = os.path.join(extract_root, zip_basename)
            # 重名处理
            counter = 1
            while os.path.exists(extract_dir):
                extract_dir = os.path.join(extract_root, f"{zip_basename}_{counter}")
                counter += 1
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.infolist():
                    # 防止路径穿越攻击
                    member_path = os.path.normpath(member.filename)
                    if member_path.startswith('..') or os.path.isabs(member_path):
                        log(f"   ⚠️ 跳过可疑条目: {member.filename}")
                        continue
                    zf.extract(member, extract_dir)
            found = 0
            for rt, _, files in os.walk(extract_dir):
                for name in files:
                    if name.lower().endswith((".docx", ".doc")):
                        full = os.path.join(rt, name)
                        if full not in self.file_list:
                            self.file_list.append(full); found += 1
            log(f"   📦 解压到 {extract_dir}，找到 {found} 个 Word 文件")
            return found
        except Exception as e:
            log(f"   ❌ 解压失败 {os.path.basename(zip_path)}: {e}")
            return 0

    def add_folder(self):
        folder = filedialog.askdirectory(title="选择包含 Word 文档的文件夹")
        if not folder: return
        added = 0
        for rt, dirs, files in os.walk(folder):
            for name in files:
                if name.lower().endswith((".docx", ".doc")):
                    full = os.path.join(rt, name)
                    if full not in self.file_list:
                        self.file_list.append(full); added += 1
        self.refresh_listbox()
        log(f"📂 从文件夹添加了 {added} 个文件")

    def clear_list(self):
        if self.exec_mode.get() == "仅校对":
            self.proofread_list = []
            self.proofread_result = {}
            log("🗑️ 已清空试卷清单")
        else:
            self.file_list = []
            log("🗑️ 已清空文件列表")
        self.refresh_listbox()

    @staticmethod
    def _natural_key(s):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

    def refresh_listbox(self):
        self.list_box.delete(0, tk.END)
        exec_mode = self.exec_mode.get()
        if exec_mode == "仅校对":
            for i, (path, name) in enumerate(self.proofread_list, 1):
                self.list_box.insert(tk.END, f"{i}. {name}")
        else:
            sorted_files = sorted(self.file_list, key=lambda p: self._natural_key(os.path.basename(p)))
            for idx, path in enumerate(sorted_files, 1):
                self.list_box.insert(tk.END, f"{idx}. {os.path.basename(path)}")

    # ===== 仅校对：选择试卷目录 =====
    def select_single_paper(self):
        path = filedialog.askdirectory(title="选择单个试卷目录")
        if not path: return
        name = os.path.basename(path)
        entry = (path, name)
        if entry not in self.proofread_list:
            self.proofread_list.append(entry)
            self.refresh_listbox()
            log(f"🔍 已添加：{name}")
        else:
            log(f"   ⚠️ 已存在：{name}")

    def select_root_for_proofread(self):
        path = filedialog.askdirectory(title="选择试卷根目录（批量扫描子目录）")
        if not path: return
        dirs = collect_paper_dirs(path)
        if not dirs:
            messagebox.showwarning("提示", "所选目录下没有识别到试卷结构（需包含第N题/板块N 或 知识 子目录）")
            return
        added = 0
        for d in dirs:
            name = os.path.basename(d)
            entry = (d, name)
            if entry not in self.proofread_list:
                self.proofread_list.append(entry); added += 1
        self.refresh_listbox()
        log(f"📂 已从根目录加载 {added} 套试卷到清单")

    # ===== 转换管线 =====
    def start_full_pipeline(self):
        """完整流程：转换 → 校对"""
        self.start_conversion()

    def start_conversion(self):
        if not self.file_list:
            messagebox.showwarning("提示", "请先添加 Word 文件"); return
        out_dir = self.output_dir.get().strip()
        if not out_dir: out_dir = DEFAULT_OUTPUT
        if not os.path.isdir(out_dir):
            try: os.makedirs(out_dir)
            except Exception as e: messagebox.showerror("错误", f"无法创建输出目录: {e}"); return

        if not check_pandoc():
            messagebox.showerror("错误", "Pandoc 未安装"); return

        invalid = [f for f in self.file_list if ')' in os.path.basename(f)]
        if invalid:
            msg = "以下文件名包含 )，请重命名：\n\n" + "\n".join(os.path.basename(f) for f in invalid)
            messagebox.showerror("文件名错误", msg)
            log("❌ 文件名包含 ')'，已取消")
            return

        self.btn_action.config(state=tk.DISABLED)
        t = threading.Thread(target=self._conversion_thread, args=(out_dir,), daemon=True)
        t.start()

    def _conversion_thread(self, out_root):
        source = self.source_mode.get()
        exec_mode = self.exec_mode.get()
        total = len(self.file_list)
        log("=" * 50)
        log(f"开始转换，模式={source}，共 {total} 个文件")

        split_root = os.path.join(out_root, "拆题结果")
        os.makedirs(split_root, exist_ok=True)

        converted_dirs = []  # 用于完整流程自动衔接校对

        for idx, word_path in enumerate(self.file_list, 1):
            fname = os.path.basename(word_path)
            basename = os.path.splitext(fname)[0]

            # 检查重名
            target_base = basename
            counter = 1
            while os.path.exists(os.path.join(split_root, target_base)):
                target_base = f"{basename}_{counter}"
                counter += 1
            if target_base != basename:
                log(f"   ⚠️ 目录重名：{basename} → {target_base}")
                basename = target_base

            log(f"\n[{idx}/{total}] {fname}")
            word_dir = os.path.dirname(word_path)
            raw_md = os.path.join(word_dir, f"{basename}_raw.md")
            img_dir = os.path.join(word_dir, f"{basename}_images")

            # 1. Pandoc 转换
            use_mathjax = (source == "讲义")
            ok = convert_with_pandoc(word_path, raw_md, img_dir, use_mathjax=use_mathjax)
            if not ok:
                log(f"   ❌ Pandoc 转换失败")
                continue

            # 2. 后处理
            if source == "讲义":
                fix_latex_escapes(raw_md)
                if self.clean_enabled.get():
                    if clean_md_file(raw_md):
                        log("   ✅ 表格清理完成")
                    else:
                        log("   ⚠️ 表格清理失败")
            else:
                post_process_md_zw(raw_md)

            # 3. 拆分题目
            log("   ✂️ 开始拆分题目...")
            subject = self.current_subject.get()
            level = self.current_level.get()
            if source == "讲义":
                split_ok = split_by_title_patterns(raw_md, split_root, basename,
                                                   do_clean=self.clean_enabled.get(),
                                                   subject=subject, level=level)
            else:
                split_ok = split_by_question_numbers(raw_md, split_root, basename)

            if split_ok:
                # 4. 讲义：提取知识（section 模式跳过，版块自成单元）
                if source == "讲义" and self.knowledge_enabled.get():
                    split_mode = subject_config.get_lecture_split_mode(subject, level)
                    if split_mode != "section":
                        generate_knowledge_with_images(raw_md, split_root, basename,
                                                       subject=subject, level=level)
                    else:
                        log("   📘 section 模式：跳过知识提取（版块即单元）")

                converted_dir = os.path.join(split_root, basename)
                converted_dirs.append(converted_dir)
                log(f"   ✅ {fname} 处理完成")

        log("=" * 50)
        log(f"✅ 转换完成，成功 {len(converted_dirs)}/{total}")

        # 完整流程：自动衔接校对
        if exec_mode == "完整流程":
            if converted_dirs:
                log("\n📋 自动加载到校对清单...")
                for d in converted_dirs:
                    name = os.path.basename(d)
                    entry = (d, name)
                    if entry not in self.proofread_list:
                        self.proofread_list.append(entry)
                self.root.after(0, self.refresh_listbox)
                log(f"   已添加 {len(converted_dirs)} 套试卷，即将开始校对...")
                # 自动开始校对（校对结束后恢复按钮）
                self.root.after(500, self.start_proofread)
            else:
                log("   ⚠️ 没有成功转换的文件，无法进入校对")
                self.root.after(0, lambda: self.btn_action.config(state=tk.NORMAL))
        else:
            # 仅拆分模式直接恢复按钮
            self.root.after(0, lambda: self.btn_action.config(state=tk.NORMAL))

    # ===== 校对管线 =====
    def start_proofread(self):
        api_url = self.api_config.get("api_url", "")
        api_key = self.api_config.get("api_key", "")
        model = self.api_config.get("model_name", "")
        if not all([api_url, api_key, model]):
            messagebox.showerror("错误", "请先配置 API（点击 ⚙️ API 配置）"); return
        if not self.proofread_list:
            messagebox.showwarning("提示", "校对清单为空，请先进行转换或选择试卷目录"); return
        if self.task_running: return

        self.task_running = True; self.task_interrupt = False
        self.btn_action.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        t = threading.Thread(target=self._proofread_thread, daemon=True)
        t.start()

    def interrupt_task(self):
        if self.task_running:
            self.task_interrupt = True
            log("===== 已触发中断 =====")

    def _proofread_thread(self):
        api_url = self.api_config.get("api_url", "")
        api_key = self.api_config.get("api_key", "")
        model = self.api_config.get("model_name", "")
        out_root = self.output_dir.get().strip()
        if not out_root: out_root = DEFAULT_OUTPUT
        report_root = os.path.join(out_root, "校对报告")
        os.makedirs(report_root, exist_ok=True)

        try:
            for paper_path, paper_name in self.proofread_list:
                if self.task_interrupt: break
                log(f"\n>>>>>>>>>> 校对试卷：{paper_name} <<<<<<<<<<")
                paper_results = {}

                question_dirs = []
                knowledge_dir = None
                for item in os.listdir(paper_path):
                    full = os.path.join(paper_path, item)
                    if not os.path.isdir(full): continue
                    if "题" in item or item.startswith("板块"):
                        question_dirs.append(full)
                    elif item == "知识":
                        knowledge_dir = full

                question_dirs.sort(key=lambda x: int(''.join(
                    [c for c in os.path.basename(x) if c.isdigit()]) or 0))

                all_dirs = question_dirs[:]
                if knowledge_dir is not None:
                    all_dirs.append(knowledge_dir)

                for q_dir in all_dirs:
                    if self.task_interrupt: break
                    q_name = os.path.basename(q_dir)
                    is_knowledge = (q_name == "知识")
                    task_type = "知识" if is_knowledge else "题目"
                    log(f"校对{task_type}：{q_name}")

                    # 读取 md
                    md_content = ""
                    for f in os.listdir(q_dir):
                        if f.endswith(".md"):
                            with open(os.path.join(q_dir, f), 'r', encoding='utf-8') as fm:
                                md_content = fm.read()
                            break
                    if not md_content:
                        log(f"   ⚠️ 未找到 md 文件，跳过")
                        continue

                    # 读取图片
                    images_b64 = []
                    img_dir = os.path.join(q_dir, "images")
                    if os.path.exists(img_dir):
                        for img_file in os.listdir(img_dir):
                            if img_file.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                                img_path = os.path.join(img_dir, img_file)
                                if os.path.getsize(img_path) > MAX_FILE_SIZE:
                                    log(f"   ⚠️ 跳过图片 {img_file}：>10MB")
                                    continue
                                try:
                                    with open(img_path, "rb") as fi:
                                        b64 = base64.b64encode(fi.read()).decode()
                                    ext = img_file.lower().split('.')[-1]
                                    mime = "image/png" if ext == "png" else "image/jpeg" if ext in ("jpg","jpeg") else "image/gif"
                                    images_b64.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{mime};base64,{b64}"}
                                    })
                                except Exception as e:
                                    log(f"   ❌ 图片读取失败 {img_file}: {e}")

                    prompt = KNOWLEDGE_SYSTEM_PROMPT if is_knowledge else SYSTEM_PROMPT
                    subject = self.current_subject.get()
                    subject_tools = SUBJECT_TOOLS.get(subject, [])
                    res = call_api(api_url, api_key, model, md_content, images_b64, q_name, prompt, tools=subject_tools, subject=subject)
                    self.proofread_result[q_dir] = res
                    paper_results[q_dir] = res

                    if "API调用失败" in res:
                        err_detail = res.replace("**API调用失败：**\n", "").strip()[:200]
                        log(f"   ❌ {q_name} 校对失败：{err_detail}")
                    else:
                        json_saved = _save_proofread_json(res, q_dir)
                        if json_saved:
                            log(f"   ✅ {q_name} 校对完成（JSON 已保存）")
                        else:
                            log(f"   ⚠️ {q_name} 校对完成（JSON 解析失败，仅保留 Markdown）")
                    time.sleep(QUESTION_INTERVAL)

                # 自动导出报告
                if not self.task_interrupt and paper_results:
                    self._export_paper_report(paper_name, paper_results, report_root)

                # 生成汇总 PDF
                if not self.task_interrupt and paper_results:
                    try:
                        from latex_generator import generate_combined_pdf
                        pdf_dir = os.path.join(os.path.dirname(split_root) or os.path.dirname(out_root), "校对PDF")
                        pdf_path = generate_combined_pdf(paper_path, pdf_dir)
                        if pdf_path:
                            log(f"   📄 汇总 PDF：{pdf_path}")
                        else:
                            log(f"   ⚠️ 汇总 PDF 生成失败（无可用的校对数据）")
                    except Exception as e:
                        log(f"   ⚠️ 汇总 PDF 生成异常：{e}")

            if self.task_interrupt:
                log("\n===== 任务已中断 =====")
            else:
                log("\n===== 全部校对完成 =====")
        except Exception as e:
            log(f"❌ 任务异常：{e}")
        finally:
            self.task_running = False; self.task_interrupt = False
            self.root.after(0, lambda: self.btn_action.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))

    def _export_paper_report(self, paper_name, paper_results, report_root):
        safe_name = "".join(c for c in paper_name if c not in r'\/:*?"<>|')
        report_path = os.path.join(report_root, f"{safe_name}_校对报告.md")
        report = f"# {paper_name} 校对报告\n\n"
        for q_path, content in paper_results.items():
            q_name = os.path.basename(q_path)
            report += f"## {q_name}\n{content}\n\n---\n\n"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        log(f"📄 已导出：{report_path}")

    def export_report(self):
        if not self.proofread_result:
            messagebox.showwarning("提示", "暂无校对结果"); return
        path = filedialog.asksaveasfilename(
            defaultextension=".md", filetypes=[("Markdown", "*.md")], title="保存校对报告"
        )
        if not path: return
        report = f"# {self.current_level.get()}{self.current_subject.get()}校对总报告\n\n"
        for q_path, content in self.proofread_result.items():
            paper_name = os.path.basename(os.path.dirname(q_path))
            q_name = os.path.basename(q_path)
            report += f"## {paper_name} - {q_name}\n{content}\n\n---\n\n"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(report)
        messagebox.showinfo("成功", "报告导出完成")


if __name__ == "__main__":
    root = tk.Tk()
    app = IntegratedApp(root)
    root.mainloop()
