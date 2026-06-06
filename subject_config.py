#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学科配置统一加载模块。
目录结构：subjects/{学段}/{学科}/config.json

每个 config.json 管理：
  - 提示词（question_prompt_lines / knowledge_prompt_lines）
  - 讲义拆分规则（lecture_split）
  - 试卷拆分规则（exam_split）

回退顺序：subjects/{学段}/{学科}/config.json → prompts/{学科}.json / title_patterns.json → 内置默认值。
"""

import os, re, json, sys


def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _app_path(rel):
    return os.path.join(_app_dir(), rel)


# ========================= 路径常量 =========================
SUBJECTS_DIR = _app_path("subjects")
PROMPTS_DIR = _app_path("prompts")
TITLE_PATTERNS_FILE = _app_path("title_patterns.json")
LEGACY_QUESTION_PROMPT_FILE = _app_path("API_Proofreading_Prompt.json")
LEGACY_KNOWLEDGE_PROMPT_FILE = _app_path("API_Knowledge_Prompt.json")

# ========================= 学段与学科映射 =========================
LEVELS = ["小学", "初中", "高中"]
DEFAULT_LEVEL = "高中"

LEVEL_SUBJECTS = {
    "小学": ["语文", "数学", "英语", "科学", "道法"],
    "初中": ["语文", "数学", "英语", "物理", "化学", "生物", "科学", "道法", "历史", "地理"],
    "高中": ["语文", "数学", "英语", "物理", "化学", "生物", "政治", "历史", "地理"],
}

# 兼容旧代码：默认高中全学科列表
SUBJECTS = LEVEL_SUBJECTS["高中"]


def get_subjects_for_level(level):
    """返回指定学段的学科列表"""
    return LEVEL_SUBJECTS.get(level, LEVEL_SUBJECTS[DEFAULT_LEVEL])


# ========================= 内置默认值 =========================
_DEFAULT_WRAPPED_PATTERNS = [
    "例\\d+", "练\\d+", "教师版",
    "一本班", "一本班\\d+", "一本班例题", "一本班备用",
    "双一流班", "双一流班\\d+", "双一流班例题", "双一流班备用",
    "清北班", "清北班\\d+", "清北班例题", "清北班备用",
    "A班", "A班\\d+", "A\\+班", "A\\+班\\d+",
    "S班", "S班\\d+",
    "变式\\d+_例\\d+", "变式\\d+",
]


def _load_json(filepath):
    """读取JSON文件，失败返回None"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _load_prompt_lines(filepath, key):
    """从JSON文件读取指定key的list，拼接为字符串"""
    data = _load_json(filepath)
    if data and key in data and isinstance(data[key], list):
        return "\n".join(data[key])
    return None


# ========================= 主加载函数 =========================

def load_subject_config(subject, level=None):
    """
    加载指定学段+学科的完整配置。
    返回 dict，包含所有字段；缺失字段用回退值填充。
    """
    if level is None:
        level = DEFAULT_LEVEL

    config = {}

    # 1. 尝试加载新格式: subjects/{level}/{subject}/config.json
    subject_file = os.path.join(SUBJECTS_DIR, level, subject, "config.json")
    new_data = _load_json(subject_file)

    # 2. 提示词：新格式 → 旧 prompts/*.json（仅高中回退）→ 旧单文件回退
    if new_data and "question_prompt_lines" in new_data:
        config["question_prompt_lines"] = new_data["question_prompt_lines"]
    elif level == DEFAULT_LEVEL:
        old_prompt_file = os.path.join(PROMPTS_DIR, f"{subject}.json")
        lines = _load_prompt_lines(old_prompt_file, "question_prompt_lines")
        if lines is None:
            lines = _load_prompt_lines(LEGACY_QUESTION_PROMPT_FILE, "system_prompt_lines")
        config["question_prompt_lines"] = lines if lines else ""
    else:
        config["question_prompt_lines"] = ""

    if new_data and "knowledge_prompt_lines" in new_data:
        config["knowledge_prompt_lines"] = new_data["knowledge_prompt_lines"]
    elif level == DEFAULT_LEVEL:
        old_prompt_file = os.path.join(PROMPTS_DIR, f"{subject}.json")
        lines = _load_prompt_lines(old_prompt_file, "knowledge_prompt_lines")
        if lines is None:
            lines = _load_prompt_lines(LEGACY_KNOWLEDGE_PROMPT_FILE, "system_prompt_lines")
        config["knowledge_prompt_lines"] = lines if lines else ""
    else:
        config["knowledge_prompt_lines"] = ""

    # 3. lecture_split
    lecture = {}
    if new_data and "lecture_split" in new_data:
        lecture = new_data["lecture_split"]

    config["lecture_split_mode"] = lecture.get("split_mode", "title")
    config["lecture_section_pattern"] = lecture.get("section_pattern", r"^##\s")
    config["lecture_wrapped_patterns"] = lecture.get("wrapped_patterns", [])
    config["lecture_unwrapped_patterns"] = lecture.get("unwrapped_patterns", [])
    config["lecture_section_boundary"] = lecture.get("section_boundary", True)

    # 如果新配置中没有 lecture_split，回退
    if not lecture and not config["lecture_wrapped_patterns"]:
        # 仅高中回退到 title_patterns.json
        if level == DEFAULT_LEVEL:
            tp_data = _load_json(TITLE_PATTERNS_FILE)
            if tp_data and "patterns" in tp_data:
                config["lecture_wrapped_patterns"] = tp_data["patterns"]
            else:
                config["lecture_wrapped_patterns"] = list(_DEFAULT_WRAPPED_PATTERNS)
        else:
            config["lecture_wrapped_patterns"] = list(_DEFAULT_WRAPPED_PATTERNS)

    # 4. exam_split
    exam = {}
    if new_data and "exam_split" in new_data:
        exam = new_data["exam_split"]

    config["exam_question_pattern"] = exam.get("question_pattern", r"^(\d+)．")

    return config


# ========================= 便捷访问函数 =========================

def get_question_prompt(subject, level=None):
    """返回指定学段+学科的题目校对提示词（字符串）"""
    cfg = load_subject_config(subject, level)
    prompt = cfg["question_prompt_lines"]
    if isinstance(prompt, list):
        prompt = "\n".join(prompt)
    return prompt


def get_knowledge_prompt(subject, level=None):
    """返回指定学段+学科的知识校对提示词（字符串）"""
    cfg = load_subject_config(subject, level)
    prompt = cfg["knowledge_prompt_lines"]
    if isinstance(prompt, list):
        prompt = "\n".join(prompt)
    return prompt


def get_lecture_patterns(subject, level=None):
    r"""
    返回指定学段+学科讲义拆分的 (wrapped_compiled, unwrapped_compiled) 两个正则列表。
    wrapped: 自动包裹为 ^\*\*{pat}\*\*.*$ 后编译
    unwrapped: 原样编译
    """
    cfg = load_subject_config(subject, level)
    wrapped = []
    for pat in cfg["lecture_wrapped_patterns"]:
        try:
            full_pat = r'^\*\*' + pat + r'\*\*.*$'
            wrapped.append(re.compile(full_pat))
        except re.error:
            pass
    unwrapped = []
    for pat in cfg["lecture_unwrapped_patterns"]:
        try:
            unwrapped.append(re.compile(pat))
        except re.error:
            pass
    return wrapped, unwrapped


def get_exam_question_pattern(subject, level=None):
    """返回指定学段+学科试卷拆分的题号正则"""
    cfg = load_subject_config(subject, level)
    try:
        return re.compile(cfg["exam_question_pattern"])
    except re.error:
        return re.compile(r"^(\d+)．")


def get_compiled_title_patterns(subject, level=None):
    """
    返回指定学段+学科讲义拆分的全部 compiled 正则（wrapped + unwrapped 合并）。
    """
    wrapped, unwrapped = get_lecture_patterns(subject, level)
    return wrapped + unwrapped


def get_section_boundary_enabled(subject, level=None):
    """返回指定学段+学科是否使用 # 标题作为题目边界"""
    cfg = load_subject_config(subject, level)
    return cfg.get("lecture_section_boundary", True)


def get_lecture_split_mode(subject, level=None):
    """返回讲义拆分模式: "title" (按题目标记) 或 "section" (按##层级标题)"""
    cfg = load_subject_config(subject, level)
    return cfg.get("lecture_split_mode", "title")


def get_section_pattern(subject, level=None):
    """返回 section 模式下的拆分正则（默认 ^##\\s）"""
    cfg = load_subject_config(subject, level)
    try:
        return re.compile(cfg.get("lecture_section_pattern", r"^##\s"))
    except re.error:
        return re.compile(r"^##\s")
