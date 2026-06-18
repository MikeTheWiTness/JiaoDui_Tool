#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学科配置统一加载模块。
目录结构：subjects/{学段}/{学科}/config.json

每个 config.json 管理：
  - 提示词（question_prompt_lines / knowledge_prompt_lines）
  - 讲义拆分规则（lecture_split）
  - 试卷拆分规则（exam_split）
"""

import os, re, json, sys, logging

_log = logging.getLogger(__name__)


def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _app_path(rel):
    return os.path.join(_app_dir(), rel)


# ========================= 路径常量 =========================
SUBJECTS_DIR = _app_path("subjects")

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


# ========================= 主加载函数 =========================

_config_cache = {}


def clear_config_cache():
    """清空配置缓存（用于测试或强制重载）"""
    _config_cache.clear()


def load_subject_config(subject, level=None):
    """
    加载指定学段+学科的完整配置。
    返回 dict，包含所有字段。
    若配置文件不存在或缺少必需字段则直接报错。
    结果会被缓存，避免重复读取 JSON 文件。
    """
    if level is None:
        level = DEFAULT_LEVEL

    cache_key = (subject, level)
    cached = _config_cache.get(cache_key)
    if cached is not None:
        return cached

    # 加载 config.json
    subject_file = os.path.join(SUBJECTS_DIR, level, subject, "config.json")
    if not os.path.exists(subject_file):
        raise FileNotFoundError(f"学科配置文件不存在: {subject_file}")

    with open(subject_file, 'r', encoding='utf-8') as f:
        new_data = json.load(f)

    # 提示词 — 必需字段，缺失直接报错
    if "question_prompt_lines" not in new_data:
        raise ValueError(f"配置文件缺少 question_prompt_lines: {subject_file}")
    if "knowledge_prompt_lines" not in new_data:
        raise ValueError(f"配置文件缺少 knowledge_prompt_lines: {subject_file}")

    config = {}
    config["question_prompt_lines"] = new_data["question_prompt_lines"]
    config["knowledge_prompt_lines"] = new_data["knowledge_prompt_lines"]

    # lecture_split — 可选，缺失用空默认
    lecture = new_data.get("lecture_split", {})
    config["lecture_split_mode"] = lecture.get("split_mode", "title")
    config["lecture_section_pattern"] = lecture.get("section_pattern", r"^##\s")
    config["lecture_wrapped_patterns"] = lecture.get("wrapped_patterns", [])
    config["lecture_unwrapped_patterns"] = lecture.get("unwrapped_patterns", [])
    config["lecture_section_boundary"] = lecture.get("section_boundary", True)

    # exam_split — 可选，缺失用默认
    exam = new_data.get("exam_split", {})
    config["exam_question_pattern"] = exam.get("question_pattern", r"^(\d+)．")

    _config_cache[cache_key] = config
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
            _log.warning("[subject_config] 无效正则（%s/%s wrapped）: %r", subject, level or '默认', pat)
    unwrapped = []
    for pat in cfg["lecture_unwrapped_patterns"]:
        try:
            unwrapped.append(re.compile(pat))
        except re.error:
            _log.warning("[subject_config] 无效正则（%s/%s unwrapped）: %r", subject, level or '默认', pat)
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
