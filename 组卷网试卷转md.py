#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Word → Markdown 转换器（GUI）+ 后处理 + 智能题目分割
- 自动检测答案位置（随题 / 末尾）
- 随题模式：按题号分割，保留题干+答案+解析
- 末尾模式：跳过答案表格，从“题号．答案”行提取解析，匹配回各题
- 图片自动复制到题目子目录，路径转为相对路径
"""

import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path

# ==================== 后处理函数 ====================
def fix_pandoc_comment_anomaly(content: str) -> str:
    """删除 Pandoc 插入的 `<!-- -->`{=html} 标记"""
    return content.replace('`<!-- -->`{=html}', '')

def fix_tilde_in_math(content: str) -> str:
    r"""将数学模式内的 \~ 替换为 \sim"""
    def replace_inner(m):
        return m.group(0).replace(r'\~', r'\sim')
    content = re.sub(r'\$\$.*?\$\$', replace_inner, content, flags=re.DOTALL)
    content = re.sub(r'\$[^$]+\$', replace_inner, content)
    return content

def fix_tilde_in_text(content: str) -> str:
    r"""将正文中的 \~ 替换为普通波浪号 ~"""
    return content.replace(r'\~', '~')

def convert_italics_to_math(content: str) -> str:
    """单星号斜体 *...* 转为 $...$，下标 ~...~ 转为 _..._，保护加粗"""
    math_blocks = []
    def save_math(m):
        math_blocks.append(m.group(0))
        return f'<<<MATHBLOCK{len(math_blocks)-1}>>>'
    content = re.sub(r'\$\$.*?\$\$', save_math, content, flags=re.DOTALL)
    content = re.sub(r'\$[^$]*\$', save_math, content)

    def italic_repl(m):
        inner = m.group(1)
        inner = re.sub(r'~(.+?)~', r'_{\1}', inner)
        return f'${inner}$'
    content = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', italic_repl, content)
    for i, block in enumerate(math_blocks):
        content = content.replace(f'<<<MATHBLOCK{i}>>>', block)
    return content

def convert_display_to_inline(content: str) -> str:
    """单行 $$...$$ 转为 $...$，保留有换行的跨行公式"""
    def repl(m):
        formula = m.group(1)
        if '\n' in formula:
            return m.group(0)
        return f'${formula}$'
    content = re.sub(r'\$\$(.+?)\$\$', repl, content, flags=re.DOTALL)
    return content

def post_process_md(md_path: str):
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

# ==================== 模式检测 ====================
def find_answer_section(lines):
    """
    找到“参考答案”部分，返回 (answer_start_idx, answer_lines)
    如果找不到，返回 (None, [])
    """
    ref_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('**') and '参考答案' in stripped:
            ref_idx = i
            break
        if '参考答案' in stripped and ('《' in stripped or not stripped.startswith('**')):
            ref_idx = i
            break
    if ref_idx is None:
        return None, []
    return ref_idx, lines[ref_idx:]

def detect_answer_mode(lines) -> str:
    """
    仅对参考答案之前的题目块进行检测
    如果大多数块内包含【答案】，返回 "inline"，否则 "end"
    """
    question_start = re.compile(r'^(\d+)．')
    _, answer_lines = find_answer_section(lines)
    if answer_lines:
        search_lines = lines[:lines.index(answer_lines[0])]
    else:
        search_lines = lines

    blocks = []
    i = 0
    while i < len(search_lines):
        line = search_lines[i].strip()
        if question_start.match(line) and not line.startswith('**'):
            start = i
            j = i + 1
            while j < len(search_lines):
                nxt = search_lines[j].strip()
                if question_start.match(nxt) and not nxt.startswith('**'):
                    break
                j += 1
            blocks.append(search_lines[start:j])
            i = j
        else:
            i += 1
    if not blocks:
        return "end"
    inline_count = sum(1 for blk in blocks if any('【答案】' in l for l in blk))
    return "inline" if inline_count > len(blocks) / 2 else "end"

# ==================== 末尾模式解析（跳过表格） ====================
def parse_end_answers(answer_lines):
    if not answer_lines:
        return {}
    # 匹配行首的“数字．”或“数字.”，并捕获之后的全部内容作为答案文本
    question_answer = re.compile(r'^(\d+)[.．]\s*(.*)')
    start = 0
    while start < len(answer_lines) and not question_answer.match(answer_lines[start].strip()):
        start += 1
    if start >= len(answer_lines):
        return {}

    result = {}
    i = start
    while i < len(answer_lines):
        m = question_answer.match(answer_lines[i].strip())
        if not m:
            i += 1
            continue
        qnum = int(m.group(1))
        ans = m.group(2).strip()  # 完整答案文本
        i += 1
        exp_lines = []
        while i < len(answer_lines):
            if question_answer.match(answer_lines[i].strip()):
                break
            exp_lines.append(answer_lines[i])
            i += 1
        # 若解析中没有【答案】行，则插入
        if not any('【答案】' in l for l in exp_lines):
            exp_lines.insert(0, f'【答案】{ans}')
        result[qnum] = {'answer': ans, 'explanation': exp_lines}
    return result

# ==================== 分割函数 ====================
def split_md_into_questions(md_file, output_root, base_name):
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    lines = md_content.splitlines()

    question_start = re.compile(r'^(\d+)．')

    # 检测答案模式
    answer_mode = detect_answer_mode(lines)
    log(f"   📋 检测到答案模式: {'随题' if answer_mode == 'inline' else '末尾'}")

    # 分离参考答案区域
    answer_start_idx, answer_lines = find_answer_section(lines)
    if answer_start_idx is not None:
        main_lines = lines[:answer_start_idx]
    else:
        main_lines = lines

    # 在题目区域中分割题目块
    blocks = []
    i = 0
    while i < len(main_lines):
        line = main_lines[i].strip()
        if question_start.match(line) and not line.startswith('**'):
            start = i
            j = i + 1
            while j < len(main_lines):
                nxt = main_lines[j].strip()
                if question_start.match(nxt) and not nxt.startswith('**'):
                    break
                j += 1
            blocks.append(main_lines[start:j])
            i = j
        else:
            i += 1

    if not blocks:
        log("   ⚠️ 未识别到任何题目，跳过分割")
        return False

    total_questions = len(blocks)
    # 若为末尾模式，提前提取答案映射
    end_answers = parse_end_answers(answer_lines) if answer_mode == "end" else None

    # 图片源目录
    md_dir = Path(md_file).parent
    src_images_dir = md_dir / f"{base_name}_images" / "media"
    log(f"   🔍 图片源目录: {src_images_dir}")
    if not src_images_dir.exists():
        log("   ❌ 图片源目录不存在")
    else:
        log(f"   📷 源目录图片数量: {len(list(src_images_dir.glob('*.*')))}")

    target_root = Path(output_root) / base_name
    target_root.mkdir(parents=True, exist_ok=True)

    def find_image_file(filename, search_dir):
        if not search_dir or not search_dir.exists():
            return None
        candidate = search_dir / filename
        return candidate if candidate.exists() else None

    total_copied = 0
    total_missing = 0

    for idx, block in enumerate(blocks, start=1):
        if answer_mode == "inline":
            # 随题模式：原有逻辑
            start_ans = None
            start_exp = None
            for k, ln in enumerate(block):
                if ln.strip() == '【答案】':
                    start_ans = k
                if ln.strip() == '【详解】':
                    start_exp = k
            if start_ans is not None:
                stem_lines = block[:start_ans]
                ans_lines = block[start_ans:start_exp] if start_exp is not None else block[start_ans:]
                exp_lines = block[start_exp:] if start_exp is not None else []
            else:
                stem_lines = block
                ans_lines = []
                exp_lines = []
            def is_title_line(l):
                return bool(re.match(r'^\*\*.*\*\*$', l.strip()))
            stem_lines = [l for l in stem_lines if not is_title_line(l)]
            final_lines = stem_lines + ans_lines + exp_lines
        else:
            # 末尾模式：从解析字典获取
            stem_lines = block
            def is_title_line(l):
                return bool(re.match(r'^\*\*.*\*\*$', l.strip()))
            stem_lines = [l for l in stem_lines if not is_title_line(l)]
            if end_answers and idx in end_answers:
                ans_data = end_answers[idx]
                # ans_data['explanation'] 已包含【答案】行
                final_lines = stem_lines + ans_data['explanation']
            else:
                final_lines = stem_lines

        content_str = '\n'.join(final_lines)

        # 创建题目目录
        q_dir = target_root / f"第{idx}题"
        q_dir.mkdir(exist_ok=True)
        img_dir = q_dir / "images"
        img_dir.mkdir(exist_ok=True)

        # 处理图片引用
        img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
        copied_count = 0
        missing_count = 0

        def replace_img(match):
            nonlocal copied_count, missing_count
            alt = match.group(1)
            src = match.group(2).strip()
            img_name = Path(src).name
            src_path = find_image_file(img_name, src_images_dir)
            if src_path:
                dest = img_dir / img_name
                if not dest.exists():
                    try:
                        shutil.copy2(src_path, dest)
                        copied_count += 1
                    except Exception as e:
                        log(f"      ❌ 图片复制失败: {img_name}, {e}")
                        missing_count += 1
                return f"![{alt}](./images/{img_name})"
            else:
                log(f"      ⚠️ 未找到图片: {img_name}")
                missing_count += 1
                return match.group(0)

        new_content = img_pattern.sub(replace_img, content_str)

        q_md = q_dir / f"第{idx}题.md"
        with open(q_md, 'w', encoding='utf-8') as f:
            f.write(new_content)
        log(f"   ✅ 第 {idx} 题 -> {q_dir}")
        total_copied += copied_count
        total_missing += missing_count

    log(f"   📂 拆分完成: {total_questions} 题, 图片复制 {total_copied} 张, 缺失 {total_missing}")
    return True

# ==================== Pandoc 转换 ====================
def check_pandoc():
    try:
        result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version_line = result.stdout.splitlines()[0]
            log(f"✅ Pandoc 已安装：{version_line}"
                f"\n 必须使用在组卷网上下载的，公式格式为微软公式的docx文件")
            return True
        else:
            log("❌ Pandoc 返回异常")
            return False
    except FileNotFoundError:
        log("❌ 未找到 Pandoc，请访问 https://pandoc.org/installing.html 安装")
        return False

def convert_file(word_path):
    fname = os.path.basename(word_path)
    basename = os.path.splitext(fname)[0]
    word_dir = os.path.dirname(word_path)
    output_md = os.path.join(word_dir, f"{basename}.md")
    img_dir = os.path.join(word_dir, f"{basename}_images")

    cmd = [
        "pandoc",
        "-f", "docx",
        "-t", "markdown",
        "--extract-media", img_dir,
        "--wrap", "none",
        "--markdown-headings", "atx",
        word_path,
        "-o", output_md,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            post_process_md(output_md)
            return True, output_md, basename
        else:
            return False, result.stderr, None
    except Exception as e:
        return False, str(e), None

# ==================== GUI 逻辑 ====================
file_list = []

def log(msg):
    log_text.insert(tk.END, msg + "\n")
    log_text.see(tk.END)
    root.update_idletasks()

def add_files():
    paths = filedialog.askopenfilenames(
        title="选择 Word 文档",
        filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")]
    )
    added = 0
    for p in paths:
        if p not in file_list:
            file_list.append(p)
            added += 1
    refresh_list()
    log(f"📁 已添加 {added} 个文件")

def add_folder():
    folder = filedialog.askdirectory(title="选择包含 Word 文档的文件夹")
    if not folder:
        return
    added = 0
    for root, dirs, files in os.walk(folder):
        for name in files:
            if name.lower().endswith(".docx"):
                full = os.path.join(root, name)
                if full not in file_list:
                    file_list.append(full)
                    added += 1
    refresh_list()
    log(f"📂 从文件夹添加了 {added} 个文件")

def clear_list():
    global file_list
    file_list = []
    refresh_list()
    log("🗑️ 已清空文件列表")

def refresh_list():
    list_box.delete(0, tk.END)
    for idx, path in enumerate(file_list, 1):
        list_box.insert(tk.END, f"{idx}. {os.path.basename(path)}")

def select_output_dir():
    path = filedialog.askdirectory(title="选择题目分割输出目录")
    if path:
        out_dir_var.set(path)

def start_conversion():
    if not file_list:
        messagebox.showwarning("提示", "请先添加 Word 文件")
        return
    out_dir = out_dir_var.get().strip()
    if not out_dir:
        messagebox.showwarning("提示", "请选择题目输出目录")
        return
    if not os.path.isdir(out_dir):
        messagebox.showerror("错误", "输出目录无效")
        return
    if not check_pandoc():
        messagebox.showerror("错误", "Pandoc 未安装")
        return
    thread = threading.Thread(target=run_conversion, args=(out_dir,), daemon=True)
    thread.start()

def run_conversion(output_root):
    total = len(file_list)
    success = 0
    log("=" * 50)
    log(f"开始批量转换，共 {total} 个文件")
    for idx, path in enumerate(file_list, 1):
        fname = os.path.basename(path)
        log(f"\n[{idx}/{total}] 处理: {fname}")
        ok, msg_or_md, basename = convert_file(path)
        if ok:
            log(f"   ✅ 转换成功，进行题目分割...")
            split_ok = split_md_into_questions(msg_or_md, output_root, basename)
            if not split_ok:
                log("   ⚠️ 未识别到题目")
            success += 1
        else:
            log(f"   ❌ 转换失败: {msg_or_md}")
    log("=" * 50)
    log(f"✅ 批量转换完成！成功: {success} / 失败: {total - success}")
    messagebox.showinfo("完成", f"转换结束\n成功: {success}\n失败: {total - success}")

# ==================== 界面 ====================
root = tk.Tk()
root.title("Word → Markdown 转换+智能题目分割")
root.geometry("850x600")
root.minsize(650, 450)

frame_top = ttk.Frame(root, padding=10)
frame_top.pack(fill=tk.X)
ttk.Label(frame_top, text="题目拆分输出目录：").pack(side=tk.LEFT)
out_dir_var = tk.StringVar()
ttk.Entry(frame_top, textvariable=out_dir_var, width=60).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
ttk.Button(frame_top, text="选择目录", command=select_output_dir).pack(side=tk.LEFT)

frame_btn = ttk.Frame(root, padding=10)
frame_btn.pack(fill=tk.X)
ttk.Button(frame_btn, text="📁 添加文件", command=add_files).pack(side=tk.LEFT, padx=4)
ttk.Button(frame_btn, text="📂 添加文件夹", command=add_folder).pack(side=tk.LEFT, padx=4)
ttk.Button(frame_btn, text="🗑️ 清空列表", command=clear_list).pack(side=tk.LEFT, padx=4)
ttk.Button(frame_btn, text="🚀 开始转换", command=start_conversion).pack(side=tk.RIGHT, padx=4)

ttk.Label(root, text="待转换文档列表：").pack(anchor=tk.W, padx=10)
list_box = tk.Listbox(root, height=10)
list_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

ttk.Label(root, text="运行日志：").pack(anchor=tk.W, padx=10)
log_text = scrolledtext.ScrolledText(root, height=14, wrap=tk.WORD)
log_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

if __name__ == "__main__":
    root.after(200, check_pandoc)
    root.mainloop()