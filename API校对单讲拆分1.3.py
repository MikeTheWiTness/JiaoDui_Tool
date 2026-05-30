import os
import json
import base64
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import requests

CONFIG_FILE = "api_config.json"
PROMPT_FILE = "API_Proofreading_Prompt.json"   # 新增：提示词配置文件
KNOWLEDGE_PROMPT_FILE = "API_Knowledge_Prompt.json"    # 新增：知识校对提示词

# ================== 题目校对 System Prompt ==================
def load_system_prompt():
    """从 JSON 文件加载系统提示词，支持两种格式：
       1. {"system_prompt": "完整字符串"}
       2. {"system_prompt_lines": ["行1", "行2", ...]}
       如果文件不存在则创建默认的数组格式。
    """
    default_lines = [
        "你现在是资深高中物理教研员，需要对高中物理题目进行全方位严格校对，",
        "输入内容包含：题目Markdown文本 + 题目配图（若有），",
        "校对范围：",
        "1. 文字校对：错别字、漏字、语病、标点符号、排版问题",
        "2. 公式符号：物理公式、希腊字母、单位、矢量符号、上下标、格式规范",
        "3. 题干严谨性：物理情景描述、条件完整性、已知量/未知量表述",
        "4. 解析内容：解题逻辑、公式引用、步骤完整性、物理规律适用性",
        "5. 答案校验：计算结果、取值、单位、结论正确性、易错点",
        "6. 格式规范：换行、编号、图文匹配",
        "",
        "忽略的内容（以下问题无需报告）：",
        "1. 转格式产生的无意义空格（如选项前、解答开头的大量连续空格）",
        "2. 明显的年份错误（例如将当前年份错写为其他年份，如“2026山东高考真题”）",
        "3. 题干开头标注的编号（例如“例2”、“练3”、“清北班”、“双一流班1”、“一本班3”、“教师版”等字样）",
        "4. 文档末尾存在的分层标记“目标清北班”、“目标双一流班”、“目标一本班”、“系统班”等字样",
        "5. 图片在文档中的位置标记或图片引用代码（如 `![](image.png)`）",
        "6. 公式中不影响渲染的冗余部分（如 `{a}^{b}`）",
        "",
        "### 强制返回格式（严格遵守，只输出Markdown）",
        "## 题目基础信息",
        "- 题目序号：{题目文件夹名}",
        "- 题干编号：题干开头标注的编号",
        "- 有无配图：有/无",
        "",
        "## 1. 文字内容校对",
        "逐条列出发现的错误及修改建议。若无问题，写“无问题”",
        "",
        "## 2. 公式与符号格式校对",
        "逐条列出公式错误、符号缺失、单位错误、格式不规范问题及修正方案。若无问题，写“无问题”",
        "",
        "## 3. 题干与情景严谨性评估",
        "评估物理情景、条件描述、边界条件是否完整严谨。若无问题，写“无问题”",
        "",
        "## 4. 解析内容审核",
        "分析解析逻辑错误、步骤缺失、规律误用、推导问题。若无问题，写“无问题”",
        "",
        "## 5. 答案正确性校验",
        "判断答案对错，计算错误、结论错误、单位错误等问题。给出你的简要解题过程。",
        "",
        "## 6. 校对总结",
        "简短总结本题整体问题等级：",
        "- 无问题",
        "- 轻微问题（标点、书写习惯，但不影响正确性）",
        "- 一般问题（错字、漏字，描述不精确、表达不严谨）",
        "- 严重错误（解析错误、答案错误）"
    ]
    KNOWLEDGE_PROMPT_FILE = "API_Knowledge_Prompt.json"

    if not os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            json.dump({"system_prompt_lines": default_lines}, f, ensure_ascii=False, indent=2)
        return "\n".join(default_lines)
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "system_prompt_lines" in data and isinstance(data["system_prompt_lines"], list):
            return "\n".join(data["system_prompt_lines"])
        if "system_prompt" in data:
            return data["system_prompt"]
    except Exception:
        pass
    return "\n".join(default_lines)

# ================== 知识校对 System Prompt ==================
def load_knowledge_prompt():
    """从 JSON 文件加载知识校对提示词"""
    default_lines = [
            "你现在是资深高中物理教研员，需要对高中物理知识讲解文本进行严格校对。",
            "",
            "输入内容为纯知识讲解的Markdown文本及可能包含的配图。",
            "",
            "# 校对范围：",
            "1. 文字校对：错别字、漏字、语病、标点符号、排版问题",
            "2. 公式符号：物理公式、希腊字母、单位、矢量符号、上下标、格式规范",
            "3. 知识严谨性：物理概念表述是否准确，定理/定律描述是否完整，推导逻辑是否自洽",
            "4. 知识结构：段落条理是否清晰，层级标题是否恰当，有无冗余或缺失",
            "5. 图文匹配：图片是否与文字解说对应，图片引用路径是否正确，有无缺失图片",
            "6. 格式规范：Markdown换行、编号、强调标记等使用是否规范",
            "",
            "# 忽略的内容：",
            "1. 转格式产生的无意义空格（如段落开头的连续空格）",
            "2. 无关的年份表述错误（如“2026高考”等）",
            "3. 图片引用代码本身（如 `![](image.png)`），但需关注配图是否缺失",
            "4. 公式中不影响渲染的冗余部分（如 `{a}^{b}`）",
            "",
            "# 强制返回格式（严格遵守，只输出Markdown）",
            "",
            "请按**原文本行号顺序**（从第1行开始计数，包含空行和Markdown标记行）逐条列出发现的所有问题。每条问题格式如下：",
            "",
            "- **行号**：问题所在行号（若问题跨多行，写起始行号~结束行号）",
            "- **问题类型**：从「文字」「公式符号」「概念逻辑」「结构排版」「图文匹配」「格式规范」中选其一",
            "- **问题描述**：简要说明具体错误（错字、语病、公式缺失、概念不严谨等）",
            "- **修改建议**：给出明确的修正方案",
            "",
            "输出示例：",
            "```markdown",
            "# 校对结果（按行排序）",
            "",
            "- **行号**：12  ",
            "  **问题类型**：文字  ",
            "  **问题描述**：错别字，“做匀束运动”应为“做匀速运动”  ",
            "  **修改建议**：将“束”改为“速”",
            "",
            "- **行号**：24~26  ",
            "  **问题类型**：公式符号  ",
            "  **问题描述**：牛顿第二定律公式中未使用矢量符号，力与加速度应为矢量  ",
            "  **修改建议**：将 `F=ma` 改为 `\\vec{F}=m\\vec{a}`",
            "",
            "- **行号**：41  ",
            "  **问题类型**：图文匹配  ",
            "  **问题描述**：文字提到“如图3所示”，但该位置无图片引用，图片缺失  ",
            "  **修改建议**：插入图3或调整文字描述",
            "",
            "...（按行号递增继续列出）",
            "```",
            "",
            "若全文无任何问题，则输出：",
            "```markdown",
            "## 校对结果（按行排序）",
            "",
            "无问题",
            "```",
            "",
            "在上述问题列表之后，请附加一个简短总结：",
            "",
            "```markdown",
            "# 校对总结",
            "",
            "- **整体问题等级**：无问题 / 轻微问题 / 一般问题 / 严重错误  ",
            "- **简要说明**：（例如：共发现3处问题，均为文字错别字，不影响理解。或：存在1处概念错误，需重点修正）",
            "```"
        ]

    if not os.path.exists(KNOWLEDGE_PROMPT_FILE):
        with open(KNOWLEDGE_PROMPT_FILE, "w", encoding="utf-8") as f:
            json.dump({"system_prompt_lines": default_lines}, f, ensure_ascii=False, indent=2)
        return "\n".join(default_lines)

    try:
        with open(KNOWLEDGE_PROMPT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "system_prompt_lines" in data and isinstance(data["system_prompt_lines"], list):
            return "\n".join(data["system_prompt_lines"])
        if "system_prompt" in data:
            return data["system_prompt"]
    except Exception:
        pass

    return "\n".join(default_lines)

# 全局加载两种提示词
SYSTEM_PROMPT = load_system_prompt()
KNOWLEDGE_SYSTEM_PROMPT = load_knowledge_prompt()   # 新增全局变量

MAX_RETRY = 2
TIME_OUT = 480
QUESTION_INTERVAL = 1
MAX_FILE_SIZE = 10 * 1024 * 1024

class PhysicsProofreadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("高中物理题目批量校对工具【自动导出报告版】")
        self.root.geometry("1250x750")  # 窗口高度750，匹配缩减后的组件高度

        self.task_running = False
        self.task_interrupt = False
        self.paper_list = []
        self.proofread_result = {}      # 全局汇总结果 {题目目录路径: 校对内容}
        self.api_config = self.load_config()
        self.setup_ui()

    def load_config(self):
        default_cfg = {"api_url": "", "api_key": "", "model_name": "", "output_dir": ""}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if "base_url" in loaded and "api_url" not in loaded:
                    loaded["api_url"] = loaded["base_url"]
                if "model" in loaded and "model_name" not in loaded:
                    loaded["model_name"] = loaded["model"]
                for key in default_cfg:
                    if key not in loaded:
                        loaded[key] = default_cfg[key]
                return loaded
            except:
                return default_cfg
        return default_cfg

    def save_config(self):
        self.api_config["api_url"] = self.var_api_url.get().strip()
        self.api_config["api_key"] = self.var_api_key.get().strip()
        self.api_config["model_name"] = self.var_model.get().strip()
        self.api_config["output_dir"] = self.var_output_dir.get().strip()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.api_config, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("提示", "API配置及输出目录保存成功！")

    def reset_config(self):
        self.var_api_url.set("")
        self.var_api_key.set("")
        self.var_model.set("")
        self.var_output_dir.set("")

    def setup_ui(self):
        frame_api = ttk.LabelFrame(self.root, text="API 配置", padding=10)
        frame_api.pack(fill=tk.X, padx=10, pady=5)

        self.var_api_url = tk.StringVar(value=self.api_config["api_url"])
        self.var_api_key = tk.StringVar(value=self.api_config["api_key"])
        self.var_model = tk.StringVar(value=self.api_config["model_name"])
        self.var_output_dir = tk.StringVar(value=self.api_config.get("output_dir", ""))

        ttk.Label(frame_api, text="接口地址：", width=12).grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_api_url, width=60).grid(row=0, column=1, padx=5, pady=3)
        ttk.Label(frame_api, text="API密钥：", width=12).grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_api_key, width=60, show="*").grid(row=1, column=1, padx=5, pady=3)
        ttk.Label(frame_api, text="模型名称：", width=12).grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_model, width=60).grid(row=2, column=1, padx=5, pady=3)

        ttk.Button(frame_api, text="保存配置", command=self.save_config).grid(row=0, column=2, padx=8)
        ttk.Button(frame_api, text="重置", command=self.reset_config).grid(row=1, column=2, padx=8)

        # 新增输出文件夹配置行
        ttk.Label(frame_api, text="报告输出目录：", width=12).grid(row=3, column=0, sticky=tk.W)
        ttk.Entry(frame_api, textvariable=self.var_output_dir, width=60).grid(row=3, column=1, padx=5, pady=3)
        ttk.Button(frame_api, text="浏览", command=self.select_output_dir).grid(row=3, column=2, padx=8)

        frame_top = ttk.Frame(self.root, padding=10)
        frame_top.pack(fill=tk.X)

        ttk.Button(frame_top, text="选择试卷根目录", command=self.select_root_dir).grid(row=0, column=0, padx=5)
        ttk.Button(frame_top, text="选择单个试卷目录", command=self.select_single_paper).grid(row=0, column=1, padx=5)
        self.dir_label = ttk.Label(frame_top, text="未选择目录")
        self.dir_label.grid(row=0, column=2, padx=10)

        frame_mid = ttk.Frame(self.root, padding=10)
        frame_mid.pack(fill=tk.BOTH, expand=True)

        frame_left = ttk.Frame(frame_mid)
        frame_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(frame_left, text="待校对试卷清单").pack(anchor=tk.W)
        self.paper_listbox = tk.Listbox(frame_left, height=9)  # 从18改为9
        self.paper_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        frame_btn = ttk.Frame(frame_left)
        frame_btn.pack(fill=tk.X)
        ttk.Button(frame_btn, text="删除选中", command=self.del_selected).grid(row=0, column=0, padx=2)
        ttk.Button(frame_btn, text="一键清空", command=self.clear_list).grid(row=0, column=1, padx=2)

        frame_right = ttk.Frame(frame_mid)
        frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        ttk.Label(frame_right, text="实时校对日志").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(frame_right, height=9)  # 从18改为9
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)

        frame_bottom = ttk.Frame(self.root, padding=10)
        frame_bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.start_btn = ttk.Button(frame_bottom, text="开始批量校对", command=self.start_proofread)
        self.start_btn.grid(row=0, column=0, padx=5)
        self.stop_btn = ttk.Button(frame_bottom, text="中断任务", command=self.interrupt_task, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)
        ttk.Button(frame_bottom, text="导出校对报告", command=self.export_report).grid(row=0, column=2, padx=5)

    def select_output_dir(self):
        path = filedialog.askdirectory(title="选择校对报告保存目录")
        if path:
            self.var_output_dir.set(path)
            self.log(f"报告输出目录已设置为：{path}")

    def log(self, msg):
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.root.update()

    def select_root_dir(self):
        path = filedialog.askdirectory(title="选择试卷根目录")
        if not path: return
        self.dir_label.config(text=f"根目录：{path}")
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                self.paper_list.append(full_path)
        self.refresh_listbox()
        self.log(f"已加载根目录，共识别 {len(self.paper_list)} 套试卷")

    def select_single_paper(self):
        path = filedialog.askdirectory(title="选择单个试卷文件夹")
        if not path: return
        self.dir_label.config(text=f"单试卷：{path}")
        self.paper_list.append(path)
        self.refresh_listbox()
        self.log(f"已添加试卷：{os.path.basename(path)}")

    def refresh_listbox(self):
        self.paper_listbox.delete(0, tk.END)
        for p in self.paper_list:
            self.paper_listbox.insert(tk.END, os.path.basename(p))

    def del_selected(self):
        idx = self.paper_listbox.curselection()
        if idx:
            self.paper_list.pop(idx[0])
            self.refresh_listbox()

    def clear_list(self):
        self.paper_list.clear()
        self.refresh_listbox()
        self.proofread_result.clear()
        self.log("已清空试卷清单与校对结果")

    def interrupt_task(self):
        if self.task_running:
            self.task_interrupt = True
            self.log("===== 已触发中断，完成当前题目后停止 =====")

    def start_proofread(self):
        api_url = self.var_api_url.get().strip()
        api_key = self.var_api_key.get().strip()
        model = self.var_model.get().strip()
        output_dir = self.var_output_dir.get().strip()

        if not all([api_url, api_key, model]):
            messagebox.showerror("错误", "请先填写并保存完整API配置！")
            return
        if not self.paper_list:
            messagebox.showwarning("提示", "请先添加试卷目录！")
            return
        if self.task_running:
            return

        # 如果设置了输出目录但不存在则尝试创建
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                self.log(f"创建输出目录：{output_dir}")
            except Exception as e:
                self.log(f"创建输出目录失败：{e}")
                messagebox.showerror("错误", f"无法创建输出目录：{e}")
                return

        self.task_running = True
        self.task_interrupt = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        t = threading.Thread(target=self.task_loop, daemon=True)
        t.start()

    def call_api_with_retry(self, api_url, api_key, model, md_text, images, q_title, system_prompt):
        """
        新增 system_prompt 参数，用于动态切换校对提示词
        """
        err_msg = ""
        chat_url = api_url.rstrip("/")
        if not chat_url.endswith("/chat/completions"):
            chat_url += "/chat/completions"
        for retry in range(MAX_RETRY + 1):
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": f"题目编号：{q_title}\n题目内容：\n{md_text}"},
                        *images
                    ]}
                ]
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.3,
                    "reasoning_effort": "high"
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                err_msg = str(e)
                if retry < MAX_RETRY:
                    self.log(f"⚠️ {q_title} 第{retry + 1}次请求超时，正在重试...")
                    time.sleep(2)
        return f"**API调用失败：**\n错误信息：{err_msg}"

    def task_loop(self):
        api_url = self.var_api_url.get().strip()
        api_key = self.var_api_key.get().strip()
        model = self.var_model.get().strip()
        output_dir = self.var_output_dir.get().strip()

        try:
            for paper_path in self.paper_list:
                if self.task_interrupt:
                    break
                paper_name = os.path.basename(paper_path)
                self.log(f"\n>>>>>>>>>> 开始校对试卷：{paper_name} <<<<<<<<<<")

                paper_results = {}

                # 收集题目目录和知识目录
                question_dirs = []
                knowledge_dir = None
                for item in os.listdir(paper_path):
                    full_item = os.path.join(paper_path, item)
                    if not os.path.isdir(full_item):
                        continue
                    if "题" in item:                     # 识别第x题
                        question_dirs.append(full_item)
                    elif item == "知识":                 # 识别知识文件夹
                        knowledge_dir = full_item

                # 按数字排序题目
                question_dirs.sort(key=lambda x: int(''.join([c for c in os.path.basename(x) if c.isdigit()]) or 0))

                # 处理顺序：所有题目 → 知识
                all_dirs = question_dirs[:]
                if knowledge_dir is not None:
                    all_dirs.append(knowledge_dir)

                for q_dir in all_dirs:
                    if self.task_interrupt:
                        break
                    q_name = os.path.basename(q_dir)
                    is_knowledge = (q_name == "知识")
                    task_type = "知识" if is_knowledge else "题目"

                    self.log(f"正在校对{task_type}：{q_name}（超时上限{TIME_OUT}s）")

                    # 读取 md 文件（题目目录和知识目录内都只有一个 .md）
                    md_content = ""
                    for f in os.listdir(q_dir):
                        if f.endswith(".md"):
                            with open(os.path.join(q_dir, f), "r", encoding="utf-8") as f_md:
                                md_content = f_md.read()
                            break

                    # 读取图片（逻辑不变）
                    images_base64 = []
                    img_dir = os.path.join(q_dir, "images")
                    if os.path.exists(img_dir):
                        for img_file in os.listdir(img_dir):
                            if img_file.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                                img_path = os.path.join(img_dir, img_file)
                                file_size = os.path.getsize(img_path)
                                if file_size > MAX_FILE_SIZE:
                                    self.log(f"⚠️ 跳过图片 {img_file}：大小 {file_size / 1024 / 1024:.2f}MB 超过 10MB 限制")
                                    continue
                                try:
                                    with open(img_path, "rb") as f_img:
                                        img_b64 = base64.b64encode(f_img.read()).decode()
                                    ext = img_file.lower().split('.')[-1]
                                    mime = "image/jpeg"
                                    if ext == "png":
                                        mime = "image/png"
                                    elif ext == "gif":
                                        mime = "image/gif"
                                    images_base64.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{mime};base64,{img_b64}"}
                                    })
                                except Exception as e:
                                    self.log(f"❌ 读取图片失败 {img_file}: {str(e)}")

                    # 选择对应的提示词
                    prompt_to_use = KNOWLEDGE_SYSTEM_PROMPT if is_knowledge else SYSTEM_PROMPT

                    # 调用 API（传入动态提示词）
                    res = self.call_api_with_retry(api_url, api_key, model, md_content, images_base64, q_name, prompt_to_use)

                    self.proofread_result[q_dir] = res
                    paper_results[q_dir] = res

                    if "API调用失败" in res:
                        self.log(f"❌ {q_name} {task_type}校对超时/失败")
                    else:
                        self.log(f"✅ {q_name} {task_type}校对完成")

                    time.sleep(QUESTION_INTERVAL)

                # 自动导出试卷报告
                if not self.task_interrupt and paper_results:
                    self.auto_export_paper_report(paper_path, paper_results, output_dir)

            if self.task_interrupt:
                self.log("\n===== 任务已手动中断 =====")
            else:
                self.log("\n===== 全部题目校对完成 =====")

        except Exception as e:
            self.log(f"❌ 任务异常：{str(e)}")
        finally:
            self.task_running = False
            self.task_interrupt = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def auto_export_paper_report(self, paper_path, paper_results, output_dir):
        """自动导出单套试卷的校对报告"""
        if not output_dir:
            self.log("⚠️ 未设置报告输出目录，跳过自动导出")
            return
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                self.log(f"❌ 无法创建输出目录 {output_dir}：{e}")
                return

        paper_name = os.path.basename(paper_path)
        # 替换文件名中的非法字符（简单处理）
        safe_name = "".join(c for c in paper_name if c not in r'\/:*?"<>|')
        report_filename = f"{safe_name}_校对报告.md"
        report_path = os.path.join(output_dir, report_filename)

        report_content = f"# {paper_name} 校对报告\n\n"
        for q_path, content in paper_results.items():
            q_name = os.path.basename(q_path)
            report_content += f"## 题目：{q_name}\n"
            report_content += content
            report_content += "\n\n---\n\n"

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            self.log(f"📄 已自动导出试卷报告：{report_path}")
        except Exception as e:
            self.log(f"❌ 自动导出报告失败：{e}")

    def export_report(self):
        if not self.proofread_result:
            messagebox.showwarning("提示", "暂无校对结果！")
            return
        save_path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown文件", "*.md")],
            title="保存校对报告"
        )
        if not save_path:
            return

        report = "# 高中物理题目批量校对总报告\n\n"
        # 按试卷分组显示（可选，当前按题目逐个展示）
        for q_path, content in self.proofread_result.items():
            paper_name = os.path.basename(os.path.dirname(q_path))
            q_name = os.path.basename(q_path)
            report += f"## {paper_name} - {q_name}\n"
            report += content
            report += "\n\n---\n\n"

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(report)
        messagebox.showinfo("成功", "校对报告导出完成！")
        self.log(f"📄 校对报告已导出")


if __name__ == "__main__":
    root = tk.Tk()
    app = PhysicsProofreadApp(root)
    root.mainloop()