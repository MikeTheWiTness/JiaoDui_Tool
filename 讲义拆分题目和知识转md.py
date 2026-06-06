#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Word 批量转 Markdown - GUI 版本
- 使用 Pandoc 将 Word 转为 Markdown，自动提取图片到 Word 文件所在目录
- 支持 .docx 文件（.doc 文件 Pandoc 可能无法处理，建议先转为 .docx）
- 可批量处理文件夹（含子目录）
- 修复 Pandoc 对 LaTeX 的多余转义
- 可选：清理表格边框和格式（默认开启）
- 可选：按题目分割成独立子目录（默认开启）
- 分割后的题目输出到用户指定的输出目录，保留原始完整文档在 Word 文件目录
- 新增：转换前检测文件名是否包含 ')'，若包含则报错并终止转换
"""

import os
import re
import time
import json
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path
import subject_config

# ==================== 全局配置 ====================
WORD_SUFFIX = (".docx", ".doc")
IMG_FOLDER_NAME = "images"

# ==================== 日志输出 ====================
def log_print(msg):
    """在 GUI 日志区域输出信息"""
    log_text.insert(tk.END, msg + "\n")
    log_text.see(tk.END)
    root.update_idletasks()

# ==================== Pandoc 检查与转换 ====================
def check_pandoc():
    """检查 Pandoc 是否安装"""
    try:
        result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            log_print("✅ Pandoc 已安装")
            log_print(f"   版本: {result.stdout.split(chr(10))[0]}")
            return True
        else:
            log_print("❌ Pandoc 未安装")
            return False
    except FileNotFoundError:
        log_print("❌ 未找到 Pandoc，请访问 https://pandoc.org/installing.html 安装")
        return False

def convert_with_pandoc(input_path, output_md, output_img_dir):
    """
    使用 Pandoc 转换 Word 文档为 Markdown，图片提取到指定目录。
    输出 Markdown 文件路径为 output_md，图片目录为 output_img_dir。
    """
    try:
        cmd = [
            "pandoc",
            "-f", "docx",
            "-t", "markdown",
            "--mathjax",
            "--extract-media", output_img_dir,
            "--wrap", "none",
            "--markdown-headings", "atx",
            input_path,
            "-o", output_md
        ]
        log_print(f"   执行 Pandoc: pandoc ... -o {os.path.basename(output_md)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return True
        else:
            log_print(f"   Pandoc 转换失败: {result.stderr}")
            return False
    except Exception as e:
        log_print(f"   Pandoc 异常: {e}")
        return False

def fix_latex_escapes(md_file):
    """彻底修复 Pandoc 对 LaTeX 代码的多余转义（包括间距命令、括号、上标等）"""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 处理两个以上反斜杠 + 定界符/特殊字符
    special_chars = r'[\[\]\(\)\$_<>{}$]'
    content = re.sub(r'\\{2,}(?=' + special_chars + r')', r'\\', content)

    # 2. 处理两个以上反斜杠 + 字母序列（LaTeX 命令）
    content = re.sub(r'\\{2,}([a-zA-Z]+)', r'\\\1', content)

    # 3. 处理两个以上反斜杠 + 单个非字母符号（间距、标点等）
    content = re.sub(r'\\{2,}([^a-zA-Z0-9])', r'\\\1', content)

    # 4. 修复可能残留的单个 \$ 转义
    content = content.replace(r'\$', r'$')

    # 5. 修复下划线、尖括号、花括号等
    content = content.replace(r'\_', '_')
    content = content.replace(r'\<', '<')
    content = content.replace(r'\>', '>')
    content = content.replace(r'\{', '{')
    content = content.replace(r'\}', '}')

    # 6. 修复 \left( 和 \right) 的错误转义（不破坏独立的 \( 和 \)）
    content = content.replace(r'\left\(', r'\left(')
    content = content.replace(r'\right\)', r'\right)')

    # 7. 修复 \left[ 和 \right] 的错误转义（不破坏独立的 \[ 和 \]）
    content = content.replace(r'\left\[', r'\left[')
    content = content.replace(r'\right\]', r'\right]')

    # 8. 修复其他常见的单反斜杠转义字符（不影响 LaTeX 命令）
    single_escapes = [
        (r'\^', '^'),   # 上标符
        (r'\#', '#'),   # 井号
        (r'\~', '~'),   # 波浪线
        (r'\&', '&'),   # 和号
        (r'\%', '%'),   # 百分号
        (r'\*', '*'),   # 星号
        (r'\+', '+'),   # 加号
        (r'\-', '-'),   # 减号/连字符
        (r'\=', '='),   # 等号
        (r'\|', '|'),   # 竖线
        (r'\!', '!'),   # 感叹号（可选，Pandoc 有时会转义）

    ]
    for escaped, original in single_escapes:
        content = content.replace(escaped, original)

    # 9. 修复单个撇号转义：将 \' 替换为 '（解决 f_{A}\' → f_{A}'）
    content = content.replace(r"\'", "'")

    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(content)

# ==================== 清洗 Markdown 表格/答案格式 ====================
def comprehensive_clean(md_content):
    """
    安全清洗 Markdown：
    - 只删除表格竖线 |（不影响公式）
    - 删除整行都是表格符号的纯分隔线（如 +---+ 或 |---|）
    - 删除答案行中多余的横线（但不影响公式中的减号）
    - 不删除任何运算符（+、-、= 等）
    """
    lines = md_content.splitlines()
    cleaned_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 1. 删除纯分隔线：整行只包含 | + - = . : 空格 制表符，且长度>2
        if re.match(r'^[\|\+\-\=\.\:\s\t]*$', stripped) and len(stripped) > 2:
            i += 1
            continue

        # 2. 删除表格竖线 |（保留所有其他字符）
        line = re.sub(r'\|', '', line)

        # 3. 处理答案行：删除行内的连续横线（- 或 =），但不影响公式中的减号（因为答案行通常无公式）
        if '答案:' in line:
            line = re.sub(r'[-=]+', '', line)
            # 如果下一行是纯字母（如 C、BD、ABC），合并到当前行
            if i + 1 < len(lines):
                next_line = lines[i+1].strip()
                if re.match(r'^[A-Z\s]+$', next_line):
                    line = line.rstrip() + ' ' + next_line
                    i += 1  # 跳过下一行

        cleaned_lines.append(line)
        i += 1

    final_text = '\n'.join(cleaned_lines)

    # 压缩多余空行（最多两个空行）
    final_text = re.sub(r'\n{3,}', '\n\n', final_text)

    # 去除每行首尾多余空格（保留行内正常空格）
    final_text = '\n'.join(line.strip() for line in final_text.split('\n'))

    return final_text.strip()

def clean_md_file(md_file):
    """读取 md 文件，清洗后写回"""
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        cleaned = comprehensive_clean(content)
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        return True
    except Exception as e:
        log_print(f"   清洗失败: {e}")
        return False

# ==================== 题目分割功能 ====================
def load_title_patterns(config_path=None, subject=None, level=None):
    """
    加载题目标题的正则模式。
    如果指定学科，从 subject_config 加载；否则尝试加载 title_patterns.json。
    如果文件不存在或读取失败，则使用内置默认模式。
    """
    if subject:
        cfg = subject_config.load_subject_config(subject, level)
        return cfg.get("lecture_wrapped_patterns", [])
    default_patterns = [
        r'例\d+',
        r'练\d+',
        r'清北班',
        r'清北班例题',
        r'清北班备用',
        r'教师版',
        r'一本班',
        r'一本班\d+',
        r'双一流班',
        r'双一流班\d+',
        r'A班',
        r'A班\d+',
        r'A\+班',
        r'S班',
    ]
    if config_path is None:
        local_config = Path(__file__).parent / "title_patterns.json"
        if local_config.exists():
            config_path = str(local_config)
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            patterns = config.get('patterns', default_patterns)
            patterns = [str(p) for p in patterns]
            log_print(f"已加载题目标题配置：{config_path}，共 {len(patterns)} 个模式")
            return patterns
        except Exception as e:
            log_print(f"读取配置文件失败：{e}，使用默认模式")
    else:
        log_print("未找到 title_patterns.json，使用内置默认模式")
    return default_patterns

def compile_title_patterns(patterns):
    """
    将字符串模式编译为正则对象，允许标题后面有其他内容。
    注意：不要对模式进行 re.escape，因为模式中可能包含正则特殊字符（如 \\d、+）。
    """
    compiled = []
    for pat in patterns:
        full_pat = r'^\*\*' + pat + r'\*\*.*$'
        compiled.append(re.compile(full_pat))
    return compiled

def generate_knowledge_with_images(cleaned_md, knowledge_dir, basename, src_img_dir, subject=None, level=None):
    """
    从清洗后的 md 生成知识版本，复制涉及图片到 knowledge_dir/images，
    并将 Markdown 保存为 knowledge_dir/{basename}_知识.md
    src_img_dir: 源图片目录（Pandoc 提取的 media 文件夹）
    """
    # 1. 读取全文并过滤题目
    with open(cleaned_md, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.splitlines()

    if subject:
        title_compiled = subject_config.get_compiled_title_patterns(subject, level)
    else:
        patterns = load_title_patterns()
        title_compiled = compile_title_patterns(patterns)

    filtered_lines = []
    in_question = False
    for line in lines:
        stripped = line.strip()
        is_question_title = any(pat.match(stripped) for pat in title_compiled)
        is_section_title = stripped.startswith('#') and not stripped.startswith('**')
        if is_question_title:
            in_question = True
            continue
        elif is_section_title:
            in_question = False
            filtered_lines.append(line)
        else:
            if not in_question:
                filtered_lines.append(line)

    knowledge_text = '\n'.join(filtered_lines)

    # 2. 准备目标目录
    img_dest_dir = knowledge_dir / "images"
    img_dest_dir.mkdir(parents=True, exist_ok=True)

    # 3. 处理图片引用：复制并替换路径
    img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
    copied = 0
    missing = 0

    def replace_img(match):
        nonlocal copied, missing
        alt = match.group(1)
        src = match.group(2).strip()
        img_name = Path(src).name

        src_path = None
        if src_img_dir and src_img_dir.exists():
            candidate = src_img_dir / img_name
            if candidate.exists():
                src_path = candidate

        if src_path:
            dest = img_dest_dir / img_name
            if not dest.exists():
                try:
                    shutil.copy2(src_path, dest)
                    log_print(f"      ✅ 知识图片复制: {img_name}")
                    copied += 1
                except Exception as e:
                    log_print(f"      ❌ 知识图片复制失败: {img_name}, {e}")
                    missing += 1
            return f"![{alt}](./images/{img_name})"
        else:
            log_print(f"      ⚠️ 知识图片未找到: {img_name}")
            missing += 1
            return match.group(0)   # 保留原引用

    new_text = img_pattern.sub(replace_img, knowledge_text)

    # 4. 写入知识 md
    md_path = knowledge_dir / f"{basename}_知识.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(new_text)

    log_print(f"   📘 知识文件已生成: {md_path}")
    if copied > 0:
        log_print(f"      知识图片复制成功: {copied} 张")
    if missing > 0:
        log_print(f"      知识图片缺失: {missing} 张")

def split_md_into_questions(md_file, output_root, base_name, subject=None, level=None):
    """
    将清洗后的 md 文件按题目拆分为多个子目录。
    图片源目录固定为：md_file所在目录 / {base_name}_images / media
    """
    # 读取完整 md 内容
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
        if subject:
            title_compiled = subject_config.get_compiled_title_patterns(subject, level)
        else:
            patterns = load_title_patterns()
            title_compiled = compile_title_patterns(patterns)
        current_title = None
        current_content = []
        in_question = False

        for line in lines:
            stripped = line.strip()
            is_question_title = any(pat.match(stripped) for pat in title_compiled)
            is_section_title = stripped.startswith('#') and not stripped.startswith('**')
            if is_question_title:
                if current_title is not None:
                    questions.append((current_title, '\n'.join(current_content)))
                current_title = stripped
                current_content = [line]
                in_question = True
            elif is_section_title and in_question:
                questions.append((current_title, '\n'.join(current_content)))
                current_title = None
                current_content = []
                in_question = False
            else:
                if in_question:
                    current_content.append(line)

    if current_title is not None:
        questions.append((current_title, '\n'.join(current_content)))

    if not questions:
        log_print("   ⚠️ 未识别到任何题目，跳过分割")
        return False

    # ========== 强制指定图片源目录 ==========
    md_dir = Path(md_file).parent
    src_images_dir = md_dir / f"{base_name}_images" / "media"

    log_print(f"   🔍 图片源目录（硬编码）: {src_images_dir}")
    if not src_images_dir.exists():
        log_print(f"   ❌ 错误：图片源目录不存在！请检查路径是否正确。")
        log_print(f"      期望的路径是: {src_images_dir}")
        # 尝试列出 md_dir 下的内容供调试
        try:
            items = list(md_dir.iterdir())
            log_print(f"      {md_dir} 目录下的内容: {[item.name for item in items]}")
        except:
            pass
        return False
    else:
        # 列出该目录下的图片文件，确认有图片
        img_files = list(src_images_dir.glob("*.*"))
        log_print(f"   📷 图片源目录中共有 {len(img_files)} 个文件")
        if img_files:
            log_print(f"      示例: {[f.name for f in img_files[:5]]}")

    # 创建目标根目录
    target_root = Path(output_root) / base_name
    target_root.mkdir(parents=True, exist_ok=True)

    # 辅助函数：在 src_images_dir 中查找图片（不递归，直接查找）
    def find_image_file(filename, search_dir):
        """在 search_dir 中直接查找 filename，不递归"""
        if not search_dir or not search_dir.exists():
            return None
        candidate = search_dir / filename
        if candidate.exists():
            return candidate
        return None

    # 分割题目
    total_copied = 0
    unit_prefix = "板块" if split_mode == "section" else "第"
    unit_suffix = "" if split_mode == "section" else "题"

    total_missing = 0
    for idx, (title, content) in enumerate(questions, start=1):
        q_dir_name = f"{unit_prefix}{idx}{unit_suffix}"
        q_dir = target_root / q_dir_name
        q_dir.mkdir(exist_ok=True)
        img_dir = q_dir / "images"
        img_dir.mkdir(exist_ok=True)

        # 正则提取图片
        img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
        copied_count = 0
        missing_count = 0

        def replace_img(match):
            nonlocal copied_count, missing_count
            alt = match.group(1)
            src = match.group(2).strip()
            # 提取纯文件名（去掉可能存在的路径）
            img_name = Path(src).name
            log_print(f"      🔎 处理图片引用: {src} -> 文件名: {img_name}")

            src_path = find_image_file(img_name, src_images_dir)
            if src_path:
                dest = img_dir / img_name
                if not dest.exists():
                    try:
                        shutil.copy2(src_path, dest)
                        log_print(f"      ✅ 复制成功: {img_name}")
                        copied_count += 1
                    except Exception as e:
                        log_print(f"      ❌ 复制失败: {img_name}, 错误: {e}")
                        missing_count += 1
                else:
                    log_print(f"      ℹ️ 图片已存在，跳过: {img_name}")
                return f"![{alt}](./images/{img_name})"
            else:
                log_print(f"      ⚠️ 未找到图片: {img_name} (源路径: {src})")
                missing_count += 1
                return f"![{alt}]({src})"

        new_content = img_pattern.sub(replace_img, content)

        # 写入文件
        q_md = q_dir / f"{q_dir_name}.md"
        with open(q_md, 'w', encoding='utf-8') as f:
            f.write(new_content)
        log_print(f"   ✅ 已拆分{unit_prefix}{idx}{unit_suffix}: {title[:50]}... -> {q_dir}")
        if copied_count > 0:
            log_print(f"      成功复制 {copied_count} 张图片")
        if missing_count > 0:
            log_print(f"      缺失 {missing_count} 张图片")
        total_copied += copied_count
        total_missing += missing_count

    log_print(f"   📂 共拆分为 {len(questions)} 道题目")
    log_print(f"   📊 图片复制统计：成功 {total_copied}，失败/缺失 {total_missing}")
    return True

# ==================== 文件扫描 ====================
def scan_word_recursive(folder_path):
    """递归扫描文件夹下的所有 Word 文档"""
    files = []
    for root, _, filenames in os.walk(folder_path):
        for name in filenames:
            if name.lower().endswith(WORD_SUFFIX):
                files.append(os.path.join(root, name))
    return files

# ==================== GUI 逻辑 ====================
file_list = []

def refresh_listbox():
    list_box.delete(0, tk.END)
    for idx, path in enumerate(file_list, 1):
        list_box.insert(tk.END, f"{idx}. {os.path.basename(path)}")

def add_files():
    paths = filedialog.askopenfilenames(
        title="选择 Word 文档",
        filetypes=[("Word 文档", "*.docx;*.doc"), ("所有文件", "*.*")]
    )
    added = 0
    for p in paths:
        if p not in file_list:
            file_list.append(p)
            added += 1
    refresh_listbox()
    log_print(f"📁 已添加 {added} 个文件")

def add_folder():
    folder = filedialog.askdirectory(title="选择包含 Word 文档的文件夹")
    if not folder:
        return
    files = scan_word_recursive(folder)
    added = 0
    for f in files:
        if f not in file_list:
            file_list.append(f)
            added += 1
    refresh_listbox()
    log_print(f"📂 从文件夹添加了 {added} 个文件")

def clear_list():
    global file_list
    file_list = []
    refresh_listbox()
    log_print("🗑️ 已清空文件列表")

def select_output_dir():
    path = filedialog.askdirectory(title="选择 Markdown 输出目录")
    if path:
        out_dir_var.set(path)

def start_conversion():
    if not file_list:
        messagebox.showwarning("提示", "请先添加要转换的 Word 文件")
        return
    out_dir = out_dir_var.get().strip()
    if not out_dir:
        messagebox.showwarning("提示", "请选择输出目录")
        return
    if not os.path.isdir(out_dir):
        messagebox.showerror("错误", "输出目录无效")
        return

    # 检查文件名中是否包含右括号 )
    invalid_files = [f for f in file_list if ')' in os.path.basename(f)]
    if invalid_files:
        msg = "以下文件名包含右括号 )，可能导致 Pandoc 转换异常，请重命名后重新添加：\n\n" + "\n".join(os.path.basename(f) for f in invalid_files)
        messagebox.showerror("文件名错误", msg)
        log_print("❌ 检测到文件名包含 ')'，已取消转换。请移除括号后重试。")
        return

    # 检查依赖
    if not check_pandoc():
        messagebox.showerror("错误", "Pandoc 未安装或不在 PATH 中")
        return

    # 在后台线程中运行转换
    thread = threading.Thread(target=run_conversion, args=(out_dir,), daemon=True)
    thread.start()

def run_conversion(output_root):
    total = len(file_list)
    log_print("=" * 60)
    log_print(f"开始批量转换，共 {total} 个文件")

    success_count = 0
    for idx, word_path in enumerate(file_list, 1):
        fname = os.path.basename(word_path)
        basename = os.path.splitext(fname)[0]
        log_print(f"\n[{idx}/{total}] 处理: {fname}")

        word_dir = os.path.dirname(word_path)
        cleaned_md = os.path.join(word_dir, f"{basename}_cleaned.md")
        img_dir = os.path.join(word_dir, f"{basename}_images")   # Pandoc 提取图片的根目录
        src_media = Path(word_dir) / f"{basename}_images" / "media"  # 实际图片位置

        # 1. Pandoc 转换
        if convert_with_pandoc(word_path, cleaned_md, img_dir):
            # 2. 修复 LaTeX 转义
            fix_latex_escapes(cleaned_md)

            # 3. 可选：清洗表格
            if clean_var.get():
                if clean_md_file(cleaned_md):
                    log_print("   ✅ 表格格式清理完成")
                else:
                    log_print("   ⚠️ 表格格式清理失败")

            # 4. 创建输出根文件夹（与题目同级）
            target_root = Path(output_root) / basename
            target_root.mkdir(parents=True, exist_ok=True)

            # 5. 生成知识文件夹（含图片，section 模式跳过）
            knowledge_dir = target_root / "知识"
            split_mode = subject_config.get_lecture_split_mode(subject_var.get(), level_var.get())
            if split_mode != "section":
                generate_knowledge_with_images(cleaned_md, knowledge_dir, basename, src_media,
                                               subject=subject_var.get(), level=level_var.get())
            else:
                log_print("   📘 section 模式：跳过知识提取（版块即单元）")

            # 6. 可选：按题目分割
            if split_var.get():
                log_print("   ✂️ 开始按题目拆分...")
                split_ok = split_md_into_questions(cleaned_md, output_root, basename,
                                                   subject=subject_var.get(), level=level_var.get())
                if not split_ok:
                    log_print("   ⚠️ 未识别到题目，不进行分割")
            else:
                log_print(f"   📄 完整文档已保存至：{cleaned_md}")

            success_count += 1
            log_print(f"   ✅ 转换成功")
        else:
            log_print(f"   ❌ 转换失败（请确保文档为 .docx 格式，或检查 Pandoc 是否支持 .doc）")

        time.sleep(0.5)

    log_print("=" * 60)
    log_print(f"✅ 批量转换完成！成功: {success_count} / 失败: {total - success_count}")
    messagebox.showinfo("完成", f"转换结束\n成功: {success_count}\n失败: {total - success_count}")

# ==================== 构建 GUI ====================
root = tk.Tk()
root.title("Word 批量转 Markdown")
root.geometry("880x650")
root.minsize(800, 550)

# 顶部：输出目录选择
frame_top = ttk.Frame(root, padding=10)
frame_top.pack(fill=tk.X)
ttk.Label(frame_top, text="输出目录：").pack(side=tk.LEFT)
out_dir_var = tk.StringVar()
ttk.Entry(frame_top, textvariable=out_dir_var, width=60).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
ttk.Button(frame_top, text="选择目录", command=select_output_dir).pack(side=tk.LEFT)

# 操作按钮行（第一行：文件操作）
frame_btn = ttk.Frame(root, padding=10)
frame_btn.pack(fill=tk.X)
ttk.Button(frame_btn, text="📁 添加文件", command=add_files).pack(side=tk.LEFT, padx=4)
ttk.Button(frame_btn, text="📂 添加文件夹", command=add_folder).pack(side=tk.LEFT, padx=4)
ttk.Button(frame_btn, text="🗑️ 清空列表", command=clear_list).pack(side=tk.LEFT, padx=4)

# 选项行（第二行：复选框和转换按钮）
frame_options = ttk.Frame(root, padding=(10, 0, 10, 10))
frame_options.pack(fill=tk.X)
clean_var = tk.BooleanVar(value=True)   # 默认清理表格
split_var = tk.BooleanVar(value=True)   # 默认分割题目
level_var = tk.StringVar(value="高中")
subject_var = tk.StringVar(value="物理")

def on_level_change(event=None):
    subjects = subject_config.get_subjects_for_level(level_var.get())
    subject_combo['values'] = subjects
    if subject_var.get() not in subjects:
        subject_var.set(subjects[0])

ttk.Checkbutton(frame_options, text="清理表格边框和格式", variable=clean_var).pack(side=tk.LEFT, padx=5)
ttk.Checkbutton(frame_options, text="分割题目到子目录", variable=split_var).pack(side=tk.LEFT, padx=5)
ttk.Label(frame_options, text="  学段：").pack(side=tk.LEFT)
level_combo = ttk.Combobox(frame_options, textvariable=level_var, values=subject_config.LEVELS,
                           state="readonly", width=6)
level_combo.pack(side=tk.LEFT)
level_combo.bind("<<ComboboxSelected>>", on_level_change)
ttk.Label(frame_options, text="学科：").pack(side=tk.LEFT)
subject_combo = ttk.Combobox(frame_options, textvariable=subject_var,
                             values=subject_config.get_subjects_for_level("高中"),
                             state="readonly", width=6)
subject_combo.pack(side=tk.LEFT)
ttk.Button(frame_options, text="🚀 开始转换", command=start_conversion).pack(side=tk.RIGHT, padx=4)

# 文件列表标题
ttk.Label(root, text="待转换文档列表：").pack(anchor=tk.W, padx=10)

# 文件列表
list_box = tk.Listbox(root, height=12)
list_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

# 日志标题
ttk.Label(root, text="运行日志：").pack(anchor=tk.W, padx=10)

# 日志区域
log_text = scrolledtext.ScrolledText(root, height=18, wrap=tk.WORD)
log_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

if __name__ == "__main__":
    # 启动时检查 Pandoc
    root.after(200, check_pandoc)
    root.mainloop()