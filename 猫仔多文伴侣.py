"""智能文本处理器增强版
- 核心处理逻辑：基于 vllm_narrative_processor.py
- UI界面和功能：基于文本批处理test - 202601151200.py
- 新增功能：相似度检测、模型选择、批量文件夹处理、一键纠错、循环纠错、优化文档
- 相似度计算排除标点符号
- API配置集成到主界面
- API密钥管理
- 默认配置保存与加载
"""
import os
import json
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from datetime import datetime
import requests
import threading
import concurrent.futures
from difflib import SequenceMatcher
import re
from pathlib import Path

# ================== 默认配置 ==================
DEFAULT_CONFIG = {
    "api_url": "http://127.0.0.1:9093/v1/chat/completions",
    "api_key": "",
    "timeout": 600,
    "selected_model": "",
    "models_list": [],
    "max_workers": 2,
    "max_retries": 3,
    "similarity_threshold": 40,  # 默认相似度阈值（%）
    "max_tokens": 1500,
    "temperature": 0.8,
    "top_p": 0.95,
    "presence_penalty": 1.2,
    "frequency_penalty": 1.2
}
CONFIG_FILE = "config.json"
API_KEYS_FILE = "api_keys.json"  # 存储API密钥的文件
DEFAULT_PROFILE_FILE = "default_profile.json"  # 存储默认配置的文件
# ===============================================

class APIKeyManagerDialog:
    """API密钥管理对话框"""
    def __init__(self, parent, current_url="", current_key=""):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("API密钥管理")
        self.dialog.geometry("700x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 加载已保存的API密钥
        self.api_keys = self.load_api_keys()
        
        # 标题
        title_label = ttk.Label(self.dialog, text="API密钥管理", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # 说明
        info_label = ttk.Label(self.dialog, text="选择已保存的API配置，或删除不需要的配置", 
                              font=('Arial', 9))
        info_label.pack(pady=5)
        
        # 列表框架
        list_frame = ttk.Frame(self.dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox
        self.listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, 
                                  yscrollcommand=scrollbar.set, font=('Arial', 10))
        scrollbar.config(command=self.listbox.yview)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 填充API密钥列表
        self.refresh_list()
        
        # 按钮框架
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="加载选中", command=self.load_selected, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除选中", command=self.delete_selected, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.cancel, width=12).pack(side=tk.LEFT, padx=5)
        
        # 居中显示
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def load_api_keys(self):
        """加载已保存的API密钥"""
        if os.path.exists(API_KEYS_FILE):
            try:
                with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_api_keys(self):
        """保存API密钥到文件"""
        with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.api_keys, f, indent=2, ensure_ascii=False)
    
    def refresh_list(self):
        """刷新列表显示"""
        self.listbox.delete(0, tk.END)
        for url, keys in self.api_keys.items():
            for key in keys:
                # 显示格式: URL | Key (隐藏部分)
                masked_key = key[:8] + "..." + key[-4:] if len(key) > 12 else key
                display_text = f"{url} | {masked_key}"
                self.listbox.insert(tk.END, display_text)
    
    def load_selected(self):
        """加载选中的API配置"""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个API配置！")
            return
        
        # 解析选中项
        idx = selection[0]
        count = 0
        for url, keys in self.api_keys.items():
            for key in keys:
                if count == idx:
                    self.result = {"url": url, "key": key}
                    self.dialog.destroy()
                    return
                count += 1
    
    def delete_selected(self):
        """删除选中的API配置"""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个API配置！")
            return
        
        result = messagebox.askyesno("确认", "确定要删除选中的API配置吗？")
        if not result:
            return
        
        # 解析并删除选中项
        idx = selection[0]
        count = 0
        for url in list(self.api_keys.keys()):
            keys = self.api_keys[url]
            for i, key in enumerate(keys):
                if count == idx:
                    keys.pop(i)
                    if not keys:  # 如果该URL下没有密钥了，删除URL
                        del self.api_keys[url]
                    self.save_api_keys()
                    self.refresh_list()
                    messagebox.showinfo("成功", "API配置已删除！")
                    return
                count += 1
    
    def cancel(self):
        """取消"""
        self.result = None
        self.dialog.destroy()

class FileSelectionDialog:
    """文件选择对话框 - 用于优化文档功能"""
    def __init__(self, parent, file_items):
        self.result = []
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("选择要优化的文档")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 标题
        title_label = ttk.Label(self.dialog, text="请选择要重新处理的文档", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # 说明
        info_label = ttk.Label(self.dialog, text="勾选需要优化的文档，将使用当前配置重新处理", 
                              font=('Arial', 9))
        info_label.pack(pady=5)
        
        # 列表框架
        list_frame = ttk.Frame(self.dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox
        self.listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, 
                                  yscrollcommand=scrollbar.set, font=('Arial', 10))
        scrollbar.config(command=self.listbox.yview)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 填充文件列表
        self.file_items = file_items
        for item in file_items:
            status_icon = self.get_status_icon(item['status'])
            display_text = f"{status_icon} {item['name']}"
            self.listbox.insert(tk.END, display_text)
        
        # 选择按钮
        select_frame = ttk.Frame(self.dialog)
        select_frame.pack(pady=10)
        
        ttk.Button(select_frame, text="全选", command=self.select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(select_frame, text="取消全选", command=self.deselect_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(select_frame, text="反选", command=self.invert_selection).pack(side=tk.LEFT, padx=5)
        
        # 确认按钮
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="确定", command=self.ok, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.cancel, width=12).pack(side=tk.LEFT, padx=5)
        
        # 居中显示
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def get_status_icon(self, status):
        return {'pending': '⏳', 'processing': '🔄', 'success': '✅', 'error': '❌'}.get(status, '❓')
    
    def select_all(self):
        self.listbox.select_set(0, tk.END)
    
    def deselect_all(self):
        self.listbox.select_clear(0, tk.END)
    
    def invert_selection(self):
        for i in range(self.listbox.size()):
            if self.listbox.selection_includes(i):
                self.listbox.selection_clear(i)
            else:
                self.listbox.selection_set(i)
    
    def ok(self):
        selected_indices = self.listbox.curselection()
        self.result = [self.file_items[i]['name'] for i in selected_indices]
        self.dialog.destroy()
    
    def cancel(self):
        self.result = []
        self.dialog.destroy()

class MainApplication:
    def __init__(self):
        self.config = self.load_or_create_config()
        self.root = tk.Tk()
        self.root.title("猫仔多文伴侣 V2.0")
        self.root.geometry("1200x850")
        self.root.resizable(False, False)
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Arial', 10))
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Success.TButton', background='#4CAF50', foreground='white')
        
        # 创建主容器框架（包含Canvas和Scrollbar）
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)
        
        # 创建Canvas
        canvas = tk.Canvas(container, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 创建垂直滚动条
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 配置Canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 在Canvas中创建Frame来放置所有内容
        main_frame = ttk.Frame(canvas, padding="15")
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor=tk.NW)
        
        # 配置Canvas滚动区域
        def configure_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        main_frame.bind("<Configure>", configure_scroll_region)
        
        # 配置Canvas窗口宽度以适应Canvas宽度
        def configure_canvas_width(event):
            canvas.itemconfig(canvas_window, width=event.width)
        
        canvas.bind("<Configure>", configure_canvas_width)
        
        # 绑定鼠标滚轮事件
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # 标题和作者信息
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(pady=(0, 10))
        
        title_label = ttk.Label(title_frame, text="猫仔多文伴侣 V2.0", style='Header.TLabel')
        title_label.pack()
        
        author_label = ttk.Label(title_frame, text="该作品由 lovelycateman/www.52pojie.cn 开源，人人为我，我为人人", 
                                font=('Arial', 10, 'bold'), foreground='black')
        author_label.pack(pady=(2, 0))
        
        # ======== API配置区域 (集成到主界面) ========
        api_config_frame = ttk.LabelFrame(main_frame, text="API配置", padding=10)
        api_config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # API地址和密钥
        api_row1 = ttk.Frame(api_config_frame)
        api_row1.pack(fill=tk.X, pady=2)
        ttk.Label(api_row1, text="API地址:", width=12).pack(side=tk.LEFT)
        self.api_url_var = tk.StringVar(value=self.config.get("api_url", DEFAULT_CONFIG["api_url"]))
        ttk.Entry(api_row1, textvariable=self.api_url_var, width=45).pack(side=tk.LEFT, padx=5)
        ttk.Label(api_row1, text="密钥:", width=8).pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar(value=self.config.get("api_key", DEFAULT_CONFIG["api_key"]))
        ttk.Entry(api_row1, textvariable=self.api_key_var, width=20, show="*").pack(side=tk.LEFT, padx=5)
        ttk.Button(api_row1, text="加载", command=self.load_api_key, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(api_row1, text="删除", command=self.delete_api_key, width=8).pack(side=tk.LEFT, padx=2)
        
        # 模型选择和测试连接
        api_row2 = ttk.Frame(api_config_frame)
        api_row2.pack(fill=tk.X, pady=2)
        ttk.Label(api_row2, text="模型:", width=12).pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value=self.config.get("selected_model", ""))
        self.model_combo = ttk.Combobox(api_row2, textvariable=self.model_var, width=42, state="readonly")
        self.model_combo['values'] = self.config.get("models_list", [])
        self.model_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(api_row2, text="测试连接", command=self.test_api_connection, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(api_row2, text="保存配置", command=self.save_api_config, width=12).pack(side=tk.LEFT, padx=5)
        
        # 参数配置
        api_row3 = ttk.Frame(api_config_frame)
        api_row3.pack(fill=tk.X, pady=2)
        ttk.Label(api_row3, text="超时(秒):", width=12).pack(side=tk.LEFT)
        self.timeout_var = tk.StringVar(value=str(self.config.get("timeout", 600)))
        ttk.Entry(api_row3, textvariable=self.timeout_var, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(api_row3, text="并发数:", width=8).pack(side=tk.LEFT)
        self.max_workers_var = tk.StringVar(value=str(self.config.get("max_workers", 2)))
        ttk.Entry(api_row3, textvariable=self.max_workers_var, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(api_row3, text="重试次数:", width=10).pack(side=tk.LEFT)
        self.max_retries_var = tk.StringVar(value=str(self.config.get("max_retries", 3)))
        ttk.Entry(api_row3, textvariable=self.max_retries_var, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(api_row3, text="相似度阈值(%):", width=14).pack(side=tk.LEFT)
        self.similarity_var = tk.StringVar(value=str(self.config.get("similarity_threshold", 40)))
        ttk.Entry(api_row3, textvariable=self.similarity_var, width=8).pack(side=tk.LEFT, padx=5)
        
        # 文件夹/文档选择区域
        folder_frame = ttk.LabelFrame(main_frame, text="选择处理文件夹/文档", padding=10)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 模式选择
        mode_frame = ttk.Frame(folder_frame)
        mode_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(mode_frame, text="输入模式:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        self.input_mode = tk.StringVar(value="folder")  # folder 或 file
        folder_mode_radio = ttk.Radiobutton(mode_frame, text="文件夹模式", variable=self.input_mode, value="folder")
        folder_mode_radio.pack(side=tk.LEFT, padx=5)
        file_mode_radio = ttk.Radiobutton(mode_frame, text="文档模式", variable=self.input_mode, value="file")
        file_mode_radio.pack(side=tk.LEFT, padx=5)
        
        folder_select_frame = ttk.Frame(folder_frame)
        folder_select_frame.pack(fill=tk.X, pady=5)
        ttk.Label(folder_select_frame, text="路径:").pack(side=tk.LEFT)
        self.folder_path_var = tk.StringVar()
        folder_entry = ttk.Entry(folder_select_frame, textvariable=self.folder_path_var, width=55)
        folder_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        browse_btn = ttk.Button(folder_select_frame, text="选择输入文档/文件夹", command=self.browse_input)
        browse_btn.pack(side=tk.LEFT, padx=5)
        open_input_btn = ttk.Button(folder_select_frame, text="打开输入文件夹", command=self.open_input_folder)
        open_input_btn.pack(side=tk.LEFT, padx=5)
        
        # 文件预览
        self.folder_preview = scrolledtext.ScrolledText(folder_frame, height=4, state=tk.DISABLED, font=('Consolas', 9))
        self.folder_preview.pack(fill=tk.X, padx=5, pady=5)
        
        # 主布局：左右分栏
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 左侧配置区域
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # 提示词输入
        prompt_frame = ttk.LabelFrame(left_frame, text="系统提示词（将应用于所有文件）", padding=10)
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        prompt_btn_frame = ttk.Frame(prompt_frame)
        prompt_btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(prompt_btn_frame, text="保存提示词", command=self.save_prompt).pack(side=tk.LEFT, padx=2)
        ttk.Button(prompt_btn_frame, text="加载提示词", command=self.load_prompt).pack(side=tk.LEFT, padx=2)
        
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, height=8, font=('Arial', 10), wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.BOTH, expand=True)
        
        # 默认提示词
        default_prompt = """核心原则：1.仅输出结果，不要展示任何分析或思维过程。凡原文出现的情节，一律视为可保留内容，除非纯属重复抒情或无任何功能的环境描写；尤其不得省略以下类型的情节：配角的猜测、议论、误判（如"其他法师认为召唤失败了"）；情绪驱动的即时行为（如"朱迪愤怒掌掴质疑者"）；群体反应（如"众人噤声""侍从跪地发抖"）；象征性姿态（如"撕信""摔杯""冷笑不语"）；对话中的语气与态度（如"讥讽道""颤抖着恳求"）；任何展现人物性格、权力关系或局势氛围的具体互动。2.结构要求：每个关键情节（如一次冲突、一场仪式、一段对峙）应组织为约四句话，分别承担：起——情境或导火索（如"召唤仪式结束，法阵无光"）；承——他人反应或初步行动（如"几名法师低声议论仪式已失败"）；转——主角介入或局势突变（如"朱迪怒斥'谁敢妄言？'并一掌掴倒说话者"）；合——即时后果或氛围变化（如"全场死寂，无人再敢出声"）。若情节简单，可为2–3句；若复杂，可拆为多个四句单元。严禁将多层互动压缩为单句结论（如不得写"朱迪镇压了质疑"，而要写出"谁说了什么→她如何反应→结果如何"）。3.具体操作规范：对话必须转述，保留说话人、内容、意图及语气效果（如"老法师怯懦地提出仪式可能失败，朱迪暴怒掌掴，令其踉跄倒地"）；动作需具象化：用"掌掴""踹翻桌案""攥紧至指节发白"等，而非"她很生气"；可删内容仅限：纯氛围渲染且无剧情作用的环境描写（如"夜色深沉"）；连续重复的情绪形容（保留最强烈的一次）；与所有角色行为、反应、对话完全无关的内心独白。4.禁止行为：跳过配角反应直接写主角结果，将"多人互动"简化为"众人反对"， 用抽象概括替代具体事件（如"她展现了威严" → 必须写"她掌掴质疑者，全场噤声"），添加原文未有的解释、评价或心理分析。5.输出格式：单一连贯段落（可自然分段，但不用标题）；语言精炼，但每个塑造性细节都以行为化方式呈现；保持原作的节奏感、冲突密度与人物鲜明度。6.质检自检清单（输出前必须满足）：✓ 所有原文出现的具体事件（包括配角言行、微小冲突、情绪爆发）均已保留；✓ 每个重大或典型互动都包含：触发者 + 言行 + 主角/关键人反应 + 即时后果；✓ 无人物性格靠"告诉"（如"她很强势"），全部靠"展示"（如"她一掌掴倒质疑者"）；✓ 无因果跳跃，无群体模糊化（如"大家觉得…" → 必须写"某人说…，引发…"）。7.输出格式：所有的输出内容，必须严格包裹在 <content> 与 </content> 标签之间。"""
        self.prompt_text.insert(tk.END, default_prompt)
        
        # 预设
        preset_frame = ttk.LabelFrame(left_frame, text="系统预设（可选）", padding=10)
        preset_frame.pack(fill=tk.X, pady=5)
        
        preset_btn_frame = ttk.Frame(preset_frame)
        preset_btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(preset_btn_frame, text="保存预设", command=self.save_preset).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_btn_frame, text="加载预设", command=self.load_preset).pack(side=tk.LEFT, padx=2)
        
        self.preset_text = scrolledtext.ScrolledText(preset_frame, height=3, font=('Arial', 9))
        self.preset_text.pack(fill=tk.BOTH, expand=True)
        
        # 正则规则
        regex_frame = ttk.LabelFrame(left_frame, text="后处理正则规则（可选）", padding=10)
        regex_frame.pack(fill=tk.X, pady=5)
        
        regex_btn_frame = ttk.Frame(regex_frame)
        regex_btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(regex_btn_frame, text="保存正则", command=self.save_regex).pack(side=tk.LEFT, padx=2)
        ttk.Button(regex_btn_frame, text="加载正则", command=self.load_regex).pack(side=tk.LEFT, padx=2)
        
        self.regex_text = scrolledtext.ScrolledText(regex_frame, height=3, font=('Consolas', 9))
        self.regex_text.pack(fill=tk.BOTH, expand=True)
        self.regex_text.insert(tk.END, ".*?<content>|\n</content>.*|")
        
        # 右侧进程监控区域
        right_frame = ttk.LabelFrame(content_frame, text="处理进度监控", width=400, padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        
        # 总体进度
        status_header_frame = ttk.Frame(right_frame)
        status_header_frame.pack(fill=tk.X, pady=5)
        ttk.Label(status_header_frame, text="总体进度:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        self.overall_status_var = tk.StringVar(value="等待开始")
        ttk.Label(status_header_frame, textvariable=self.overall_status_var, font=('Arial', 10)).pack(side=tk.LEFT, padx=(5, 0))
        
        # 进度条
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(right_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_label = ttk.Label(right_frame, text="0% (0/0)", font=('Arial', 9))
        self.progress_label.pack(pady=(0, 10))
        
        # 当前文件状态
        current_file_frame = ttk.LabelFrame(right_frame, text="当前处理", padding=8)
        current_file_frame.pack(fill=tk.X, pady=5)
        self.current_file_var = tk.StringVar(value="无文件")
        ttk.Label(current_file_frame, textvariable=self.current_file_var, wraplength=350, font=('Arial', 9)).pack(pady=2)
        self.current_status_var = tk.StringVar(value="状态: 等待中")
        ttk.Label(current_file_frame, textvariable=self.current_status_var, font=('Arial', 9)).pack(pady=2)
        
        # 文件列表
        file_list_frame = ttk.LabelFrame(right_frame, text="文件处理状态", padding=8)
        file_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        tree_frame = ttk.Frame(file_list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar_tree = ttk.Scrollbar(tree_frame)
        scrollbar_tree.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_tree = ttk.Treeview(
            tree_frame,
            columns=('status', 'filename'),
            show='headings',
            yscrollcommand=scrollbar_tree.set,
            height=12
        )
        scrollbar_tree.config(command=self.file_tree.yview)
        
        self.file_tree.heading('status', text='状态')
        self.file_tree.heading('filename', text='文件名')
        self.file_tree.column('status', width=60, anchor=tk.CENTER)
        self.file_tree.column('filename', width=300, anchor=tk.W)
        
        self.file_tree.tag_configure('pending', background='#f0f0f0')
        self.file_tree.tag_configure('processing', background='#e6f7ff')
        self.file_tree.tag_configure('success', background='#e6ffe6')
        self.file_tree.tag_configure('error', background='#ffe6e6')
        self.file_tree.pack(fill=tk.BOTH, expand=True)
        
        # 操作按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)
        
        # 第一行按钮
        btn_row1 = ttk.Frame(btn_frame)
        btn_row1.pack(pady=5)
        
        self.start_btn = ttk.Button(btn_row1, text="▶ 开始", command=self.start_processing, style='Success.TButton', width=12)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = ttk.Button(btn_row1, text="⏸ 暂停", command=self.toggle_pause, state=tk.DISABLED, width=12)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_row1, text="设为默认配置", command=self.save_as_default_profile).pack(side=tk.LEFT, padx=10)
        
        # 第二行按钮（纠错和优化）
        btn_row2 = ttk.Frame(btn_frame)
        btn_row2.pack(pady=5)
        
        self.fix_errors_btn = ttk.Button(btn_row2, text="🔧 一键纠错", command=self.fix_errors, 
                                         state=tk.DISABLED, width=15)
        self.fix_errors_btn.pack(side=tk.LEFT, padx=5)
        
        self.loop_fix_btn = ttk.Button(btn_row2, text="🔄 循环纠错开始", command=self.toggle_loop_fix, 
                                       state=tk.DISABLED, width=15)
        self.loop_fix_btn.pack(side=tk.LEFT, padx=5)
        
        self.optimize_docs_btn = ttk.Button(btn_row2, text="✨ 优化文档", command=self.optimize_docs, 
                                           state=tk.DISABLED, width=15)
        self.optimize_docs_btn.pack(side=tk.LEFT, padx=5)
        
        self.view_result_btn = ttk.Button(btn_row2, text="📁 查看输出文件夹", command=self.view_result_folder, 
                                         state=tk.DISABLED, width=15)
        self.view_result_btn.pack(side=tk.LEFT, padx=5)
        
        self.merge_result_btn = ttk.Button(btn_row2, text="📋 汇总输出结果", command=self.merge_output_results, 
                                          state=tk.DISABLED, width=15)
        self.merge_result_btn.pack(side=tk.LEFT, padx=5)
        
        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 创建输出目录
        self.out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OUT")
        os.makedirs(self.out_dir, exist_ok=True)
        
        # 初始化状态
        self.batch_files_list = []
        self.is_processing = False
        self.is_paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.processing_completed = False
        self.current_task_folder = None
        self.file_status_map = {}
        self.loop_fix_running = False  # 循环纠错运行标志
        self.loop_fix_stop_flag = False  # 循环纠错停止标志
        self.current_input_folder = None  # 记录当前输入文件夹（用于单文档模式）
        
        self.log_message("系统已启动，加载配置完成。")
        self.log_message(f"API地址: {self.config.get('api_url', 'N/A')}")
        self.log_message(f"使用模型: {self.config.get('selected_model', 'N/A')}")
        self.log_message(f"相似度阈值: {self.config.get('similarity_threshold', 40)}%")
        
        # 加载默认配置（如果存在）
        self.load_default_profile()
    
    def load_or_create_config(self):
        """加载或创建配置文件"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return DEFAULT_CONFIG.copy()
    
    def load_api_key(self):
        """加载已保存的API密钥"""
        dialog = APIKeyManagerDialog(self.root)
        self.root.wait_window(dialog.dialog)
        
        if dialog.result:
            self.api_url_var.set(dialog.result["url"])
            self.api_key_var.set(dialog.result["key"])
            self.log_message(f"✅ 已加载API配置: {dialog.result['url']}")
    
    def delete_api_key(self):
        """删除API密钥"""
        dialog = APIKeyManagerDialog(self.root)
        self.root.wait_window(dialog.dialog)
    
    def save_api_key(self, url, key):
        """保存API密钥"""
        if not url or not key:
            return
        
        # 加载现有密钥
        api_keys = {}
        if os.path.exists(API_KEYS_FILE):
            try:
                with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                    api_keys = json.load(f)
            except:
                api_keys = {}
        
        # 添加新密钥（如果不存在）
        if url not in api_keys:
            api_keys[url] = []
        
        if key not in api_keys[url]:
            api_keys[url].append(key)
            
            # 保存到文件
            with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
                json.dump(api_keys, f, indent=2, ensure_ascii=False)
            
            self.log_message(f"✅ API密钥已自动保存")
    
    def test_api_connection(self):
        """测试API连接"""
        def test_thread():
            try:
                api_url = self.api_url_var.get().strip()
                api_key = self.api_key_var.get().strip()
                timeout = int(self.timeout_var.get())
                
                if not api_url:
                    self.root.after(0, lambda: messagebox.showerror("错误", "API地址不能为空"))
                    return
                
                base_url = api_url.rstrip("/")
                if "/v1/chat/completions" in base_url:
                    base_url = base_url.replace("/v1/chat/completions", "")
                if not base_url.endswith("/v1"):
                    base_url += "/v1"
                models_url = f"{base_url}/models"
                
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                
                self.root.after(0, lambda: self.log_message(f"📡 测试连接: {models_url}"))
                response = requests.get(models_url, headers=headers, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                
                models = []
                if "data" in data and isinstance(data["data"], list):
                    for item in data["data"]:
                        if "id" in item:
                            models.append(item["id"])
                elif "models" in data:
                    for model in data["models"]:
                        if isinstance(model, dict) and "name" in model:
                            models.append(model["name"])
                        elif isinstance(model, str):
                            models.append(model)
                
                if models:
                    self.root.after(0, lambda: self.model_combo.config(values=models))
                    if models:
                        self.root.after(0, lambda: self.model_var.set(models[0]))
                    self.root.after(0, lambda: self.log_message(f"✅ 连接成功! 找到 {len(models)} 个模型"))
                    self.root.after(0, lambda: messagebox.showinfo("成功", f"连接成功!\n找到 {len(models)} 个模型"))
                    # 连接成功后自动保存API密钥
                    self.save_api_key(api_url, api_key)
                else:
                    self.root.after(0, lambda: messagebox.showwarning("警告", "连接成功，但未找到模型"))
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"❌ 连接失败: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("错误", f"连接失败:\n{str(e)}"))
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def save_api_config(self):
        """保存API配置"""
        try:
            similarity = int(self.similarity_var.get())
            if similarity < 30 or similarity > 100:
                messagebox.showerror("错误", "相似度阈值必须在30-100之间！")
                return
            
            self.config = {
                "api_url": self.api_url_var.get().strip(),
                "api_key": self.api_key_var.get().strip(),
                "timeout": int(self.timeout_var.get()),
                "selected_model": self.model_var.get(),
                "models_list": list(self.model_combo['values']),
                "max_workers": int(self.max_workers_var.get()),
                "max_retries": int(self.max_retries_var.get()),
                "similarity_threshold": similarity,
                "max_tokens": self.config.get("max_tokens", 1500),
                "temperature": self.config.get("temperature", 0.8),
                "top_p": self.config.get("top_p", 0.95),
                "presence_penalty": self.config.get("presence_penalty", 1.2),
                "frequency_penalty": self.config.get("frequency_penalty", 1.2)
            }
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            
            self.log_message("✅ API配置已保存")
            messagebox.showinfo("成功", "API配置已成功保存！")
        except ValueError:
            messagebox.showerror("错误", "请确保所有数值参数输入正确！")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
    
    def save_as_default_profile(self):
        """保存为默认配置"""
        try:
            profile = {
                "api_url": self.api_url_var.get().strip(),
                "api_key": self.api_key_var.get().strip(),
                "timeout": int(self.timeout_var.get()),
                "selected_model": self.model_var.get(),
                "models_list": list(self.model_combo['values']),
                "max_workers": int(self.max_workers_var.get()),
                "max_retries": int(self.max_retries_var.get()),
                "similarity_threshold": int(self.similarity_var.get()),
                "max_tokens": self.config.get("max_tokens", 1500),
                "temperature": self.config.get("temperature", 0.8),
                "top_p": self.config.get("top_p", 0.95),
                "presence_penalty": self.config.get("presence_penalty", 1.2),
                "frequency_penalty": self.config.get("frequency_penalty", 1.2),
                "prompt": self.prompt_text.get("1.0", tk.END).strip(),
                "preset": self.preset_text.get("1.0", tk.END).strip(),
                "regex": self.regex_text.get("1.0", tk.END).strip()
            }
            
            with open(DEFAULT_PROFILE_FILE, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            
            # 同时更新config.json
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                config_data = {k: v for k, v in profile.items() if k not in ["prompt", "preset", "regex"]}
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            self.log_message("✅ 默认配置已保存")
            messagebox.showinfo("成功", "默认配置已保存！\n下次启动将自动加载此配置。")
        except Exception as e:
            self.log_message(f"❌ 保存默认配置失败: {str(e)}")
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def load_default_profile(self):
        """加载默认配置"""
        if not os.path.exists(DEFAULT_PROFILE_FILE):
            return
        
        try:
            with open(DEFAULT_PROFILE_FILE, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            
            # 加载API配置
            if "api_url" in profile:
                self.api_url_var.set(profile["api_url"])
            if "api_key" in profile:
                self.api_key_var.set(profile["api_key"])
            if "timeout" in profile:
                self.timeout_var.set(str(profile["timeout"]))
            if "max_workers" in profile:
                self.max_workers_var.set(str(profile["max_workers"]))
            if "max_retries" in profile:
                self.max_retries_var.set(str(profile["max_retries"]))
            if "similarity_threshold" in profile:
                self.similarity_var.set(str(profile["similarity_threshold"]))
            if "selected_model" in profile:
                self.model_var.set(profile["selected_model"])
            if "models_list" in profile:
                self.model_combo['values'] = profile["models_list"]
            
            # 加载提示词、预设和正则
            if "prompt" in profile and profile["prompt"]:
                self.prompt_text.delete("1.0", tk.END)
                self.prompt_text.insert(tk.END, profile["prompt"])
            if "preset" in profile and profile["preset"]:
                self.preset_text.delete("1.0", tk.END)
                self.preset_text.insert(tk.END, profile["preset"])
            if "regex" in profile and profile["regex"]:
                self.regex_text.delete("1.0", tk.END)
                self.regex_text.insert(tk.END, profile["regex"])
            
            self.log_message("✅ 已加载默认配置")
        except Exception as e:
            self.log_message(f"⚠️ 加载默认配置失败: {str(e)}")
    
    def browse_input(self):
        """根据模式选择文件或文件夹"""
        mode = self.input_mode.get()
        
        if mode == "folder":
            # 文件夹模式
            folder_path = filedialog.askdirectory(title="选择包含 .txt 文件的文件夹")
            if folder_path:
                self.current_input_folder = folder_path
                self.folder_path_var.set(folder_path)
                txt_files = sorted([f for f in os.listdir(folder_path)
                                   if f.lower().endswith('.txt') and os.path.isfile(os.path.join(folder_path, f))])
                self.batch_files_list = txt_files
                
                self.folder_preview.config(state=tk.NORMAL)
                self.folder_preview.delete(1.0, tk.END)
                if txt_files:
                    self.folder_preview.insert(tk.END, f"[文件夹模式] 找到 {len(txt_files)} 个 .txt 文件:\n")
                    self.folder_preview.insert(tk.END, "\n".join(txt_files[:20]))
                    if len(txt_files) > 20:
                        self.folder_preview.insert(tk.END, f"\n... 及其他 {len(txt_files)-20} 个文件")
                    self.log_message(f"[文件夹模式] 已选择文件夹: {os.path.basename(folder_path)}，共 {len(txt_files)} 个文件")
                else:
                    self.folder_preview.insert(tk.END, "⚠️ 该文件夹下没有 .txt 文件")
                    self.log_message("⚠️ 该文件夹下没有 .txt 文件")
                self.folder_preview.config(state=tk.DISABLED)
                
                file_list = [{"name": f, "status": "pending"} for f in txt_files]
                self.update_file_list_display(file_list)
                self.file_status_map = {f: "pending" for f in txt_files}
        else:
            # 文档模式
            file_path = filedialog.askopenfilename(
                title="选择要处理的 .txt 文件",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
            )
            if file_path:
                self.current_input_folder = os.path.dirname(file_path)
                filename = os.path.basename(file_path)
                self.folder_path_var.set(file_path)
                self.batch_files_list = [filename]
                
                self.folder_preview.config(state=tk.NORMAL)
                self.folder_preview.delete(1.0, tk.END)
                self.folder_preview.insert(tk.END, f"[文档模式] 已选择文件:\n{filename}")
                self.folder_preview.config(state=tk.DISABLED)
                
                self.log_message(f"[文档模式] 已选择文件: {filename}")
                
                file_list = [{"name": filename, "status": "pending"}]
                self.update_file_list_display(file_list)
                self.file_status_map = {filename: "pending"}
    
    def update_file_list_display(self, files):
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        for file_info in files:
            status = file_info.get('status', 'pending')
            self.file_tree.insert('', tk.END, values=(self.get_status_text(status), file_info.get('name', '')), tags=(status,))
    
    def get_status_text(self, status):
        status_map = {'pending': '⏳', 'processing': '🔄', 'success': '✅', 'error': '❌'}
        return status_map.get(status, status)
    
    def update_progress(self, current, total):
        if total <= 0:
            percent = 0
        else:
            percent = (current / total) * 100
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{percent:.1f}% ({current}/{total})")
        
        if total == 0:
            self.overall_status_var.set("等待开始")
        elif current < total:
            self.overall_status_var.set(f"处理中 ({current}/{total})")
        else:
            self.overall_status_var.set("完成")
        self.root.update()
    
    def update_current_file(self, filename, status="processing"):
        self.current_file_var.set(filename)
        status_text = {
            "processing": "状态: 处理中...",
            "success": "状态: 处理成功",
            "error": "状态: 处理失败"
        }.get(status, "状态: 等待中")
        self.current_status_var.set(status_text)
        self.root.update()
    
    def update_file_status(self, filename, status):
        self.file_status_map[filename] = status
        for item in self.file_tree.get_children():
            values = self.file_tree.item(item, 'values')
            if values and len(values) > 1 and values[1] == filename:
                self.file_tree.item(item, values=(self.get_status_text(status), filename), tags=(status,))
                break
        self.root.update()
    
    def log_message(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, formatted + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.status_var.set(message[:80] + "..." if len(message) > 80 else message)
        self.root.update()
    
    def save_prompt(self):
        content = self.prompt_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "提示词为空")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            if file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({"prompt": content}, f, indent=2, ensure_ascii=False)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            self.log_message(f"✅ 提示词已保存: {file_path}")
    
    def load_prompt(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.endswith('.json'):
                        data = json.load(f)
                        content = data.get("prompt", "")
                    else:
                        content = f.read()
                self.prompt_text.delete("1.0", tk.END)
                self.prompt_text.insert(tk.END, content)
                self.log_message(f"✅ 已加载提示词: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("错误", f"加载失败: {str(e)}")
    
    def save_preset(self):
        content = self.preset_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "预设为空")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            if file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({"preset": content}, f, indent=2, ensure_ascii=False)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            self.log_message(f"✅ 预设已保存: {file_path}")
    
    def load_preset(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.endswith('.json'):
                        data = json.load(f)
                        content = data.get("preset", "")
                    else:
                        content = f.read()
                self.preset_text.delete("1.0", tk.END)
                self.preset_text.insert(tk.END, content)
                self.log_message(f"✅ 已加载预设: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("错误", f"加载失败: {str(e)}")
    
    def save_regex(self):
        content = self.regex_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "正则规则为空")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            if file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({"regex": content}, f, indent=2, ensure_ascii=False)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            self.log_message(f"✅ 正则规则已保存: {file_path}")
    
    def load_regex(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON文件", "*.json"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.endswith('.json'):
                        data = json.load(f)
                        content = data.get("regex", "")
                    else:
                        content = f.read()
                self.regex_text.delete("1.0", tk.END)
                self.regex_text.insert(tk.END, content)
                self.log_message(f"✅ 已加载正则规则: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("错误", f"加载失败: {str(e)}")
    
    def open_input_folder(self):
        """打开输入文件夹"""
        # 优先使用 current_input_folder
        folder_path = self.current_input_folder
        if not folder_path:
            # 如果是文件夹模式，使用 folder_path_var
            path = self.folder_path_var.get().strip()
            if os.path.isdir(path):
                folder_path = path
            elif os.path.isfile(path):
                folder_path = os.path.dirname(path)
        
        if folder_path and os.path.exists(folder_path):
            try:
                os.startfile(folder_path)
                self.log_message(f"📁 已打开输入文件夹: {folder_path}")
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件夹: {str(e)}")
        else:
            messagebox.showwarning("警告", "输入文件夹不存在！请先选择文件或文件夹。")
    
    def view_result_folder(self):
        """查看输出文件夹"""
        if self.current_task_folder and os.path.exists(self.current_task_folder):
            try:
                os.startfile(self.current_task_folder)
                self.log_message(f"📁 已打开输出文件夹: {self.current_task_folder}")
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件夹: {str(e)}")
        else:
            messagebox.showwarning("警告", "输出文件夹不存在！请先完成处理。")
    
    def detect_pattern(self, filename):
        """从文件名中智能检测命名模式并提取信息"""
        if not filename.endswith('.txt'):
            return None
        
        name_without_ext = filename[:-4]
        digit_matches = list(re.finditer(r'\d+', name_without_ext))
        
        if not digit_matches:
            return None
        
        for match in reversed(digit_matches):
            start, end = match.span()
            number = int(match.group())
            
            prefix = name_without_ext[:start]
            suffix = name_without_ext[end:]
            
            if not prefix:
                continue
            
            pattern_key = f"{prefix}{{N}}{suffix}"
            return pattern_key, prefix, number, suffix
        
        return None
    
    def merge_output_results(self):
        """汇总输出结果"""
        if not self.current_task_folder or not os.path.exists(self.current_task_folder):
            messagebox.showwarning("警告", "输出文件夹不存在！请先完成处理。")
            return
        
        try:
            # 1. 删除带有error的文件
            files = os.listdir(self.current_task_folder)
            error_files = [f for f in files if 'error' in f.lower() and f.endswith('.txt')]
            
            if error_files:
                for error_file in error_files:
                    error_path = os.path.join(self.current_task_folder, error_file)
                    os.remove(error_path)
                    self.log_message(f"🗑️ 已删除错误文件: {error_file}")
            
            # 2. 检测是否已存在汇总结果
            files = os.listdir(self.current_task_folder)
            existing_merge = [f for f in files if '_zong.txt' in f]
            
            if existing_merge:
                result = messagebox.askyesno(
                    "确认",
                    f"检测到已存在汇总结果：\n{', '.join(existing_merge)}\n\n继续会覆盖原结果，是否继续？"
                )
                if not result:
                    self.log_message("⚠️ 用户取消汇总操作")
                    return
                
                # 删除旧的汇总文件
                for merge_file in existing_merge:
                    merge_path = os.path.join(self.current_task_folder, merge_file)
                    os.remove(merge_path)
                    self.log_message(f"🗑️ 已删除旧汇总文件: {merge_file}")
            
            # 3. 执行汇总逻辑
            files = os.listdir(self.current_task_folder)
            txt_files = [f for f in files if f.endswith('.txt')]
            
            if not txt_files:
                messagebox.showwarning("警告", "输出文件夹中没有可汇总的txt文件！")
                return
            
            # 存储解析成功的文件信息
            from collections import defaultdict
            pattern_groups = defaultdict(list)
            
            for f in txt_files:
                result = self.detect_pattern(f)
                if result:
                    pattern_key, prefix, number, suffix = result
                    pattern_groups[pattern_key].append((number, f, prefix, suffix))
            
            if not pattern_groups:
                messagebox.showwarning("警告", "未找到符合命名规则的文件！")
                return
            
            self.log_message(f"📋 开始汇总，检测到 {len(pattern_groups)} 种命名模式")
            
            # 对每种命名模式分别处理
            merge_count = 0
            for pattern_key, items in pattern_groups.items():
                items.sort(key=lambda x: x[0])
                _, _, group_prefix, group_suffix = items[0]
                
                self.log_message(f"  处理模式: {pattern_key} ({len(items)} 个文件)")
                
                # 构建输出内容
                output_lines = []
                for number, filename, prefix, suffix in items:
                    paragraph_num = f"{number:03d}"
                    filepath = os.path.join(self.current_task_folder, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                    except Exception as e:
                        self.log_message(f"  ⚠️ 读取文件 {filename} 出错：{e}")
                        content = "[读取失败]"
                    
                    output_lines.append(f"【段落{paragraph_num}】")
                    output_lines.append(content)
                    output_lines.append("----")
                
                # 去掉最后一个分隔符
                if output_lines and output_lines[-1] == "----":
                    output_lines.pop()
                
                # 生成输出文件名
                output_filename = f"{group_prefix}{group_suffix}_zong.txt"
                output_path = os.path.join(self.current_task_folder, output_filename)
                
                try:
                    with open(output_path, 'w', encoding='utf-8') as out_file:
                        out_file.write('\n'.join(output_lines))
                    
                    self.log_message(f"  ✅ 已生成: {output_filename}")
                    merge_count += 1
                except Exception as e:
                    self.log_message(f"  ❌ 写入文件 {output_filename} 失败：{e}")
            
            if merge_count > 0:
                messagebox.showinfo("完成", f"汇总完成！\n成功生成 {merge_count} 个汇总文件。")
                self.log_message(f"📋 汇总完成，共生成 {merge_count} 个文件")
            else:
                messagebox.showwarning("警告", "未能生成任何汇总文件！")
                
        except Exception as e:
            error_msg = f"汇总过程出错: {str(e)}"
            self.log_message(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)
    
    def apply_regex_rules(self, text):
        """应用正则规则进行后处理"""
        rules_content = self.regex_text.get("1.0", tk.END).strip()
        if not rules_content:
            return text
        
        processed = text
        for line in rules_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                continue
            try:
                pattern, replacement = line.split("|", 1)
                pattern = pattern.replace(r'\n', '\n').replace(r'\t', '\t')
                replacement = replacement.replace(r'\n', '\n').replace(r'\t', '\t')
                processed = re.sub(pattern, replacement, processed, flags=re.MULTILINE | re.DOTALL)
            except Exception as e:
                self.log_message(f"⚠️ 正则规则错误: {str(e)}")
        return processed
    
    def remove_punctuation(self, text):
        """移除文本中的标点符号，用于相似度计算"""
        # 中文和英文标点符号
        punctuation = r'[，。！？；：""''（）《》【】、,.!?;:\'"()\[\]{}<>]'
        return re.sub(punctuation, '', text)
    
    def get_similarity(self, a, b):
        """计算文本相似度（排除标点符号）"""
        # 移除标点符号后再计算相似度
        a_no_punct = self.remove_punctuation(a)
        b_no_punct = self.remove_punctuation(b)
        return SequenceMatcher(None, a_no_punct, b_no_punct).ratio()
    
    def post_process_format(self, text):
        """格式修正与标点优化"""
        text = text.strip()
        text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
        text = text.replace(',', '，').replace('!', '！').replace('?', '？').replace(':', '：')
        if text and text[-1] not in "。！？】：\"":
            text += "。"
        return text
    
    def fix_errors(self):
        """一键纠错：自动重新处理所有失败的文件"""
        if not self.processing_completed:
            messagebox.showwarning("警告", "请先完成一次文件批处理方可使用此功能！")
            return
        
        failed_files = [fname for fname, status in self.file_status_map.items() if status == 'error']
        
        if not failed_files:
            messagebox.showinfo("提示", "没有失败的文件需要处理！")
            return
        
        result = messagebox.askyesno("确认", 
                                     f"检测到 {len(failed_files)} 个失败的文件\n是否重新处理这些文件？")
        if not result:
            return
        
        self.log_message(f"🔧 开始一键纠错，共 {len(failed_files)} 个失败文件")
        
        folder_path = self.folder_path_var.get().strip()
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        
        threading.Thread(target=self._reprocess_files_thread, 
                        args=(folder_path, failed_files, prompt, "一键纠错"), 
                        daemon=True).start()
    
    def toggle_loop_fix(self):
        """切换循环纠错状态"""
        if not self.processing_completed:
            messagebox.showwarning("警告", "请先完成一次文件批处理方可使用此功能！")
            return
        
        if self.loop_fix_running:
            # 停止循环纠错
            self.loop_fix_stop_flag = True
            self.log_message("🛑 正在停止循环纠错...")
        else:
            # 开始循环纠错
            failed_files = [fname for fname, status in self.file_status_map.items() if status == 'error']
            
            if not failed_files:
                messagebox.showinfo("提示", "没有失败的文件需要处理！")
                return
            
            result = messagebox.askyesno("确认", 
                                         f"检测到 {len(failed_files)} 个失败的文件\n将循环处理直到全部成功，是否开始？")
            if not result:
                return
            
            self.loop_fix_stop_flag = False
            self.loop_fix_running = True
            self.loop_fix_btn.config(text="🛑 循环纠错停止")
            self.log_message(f"🔄 开始循环纠错，共 {len(failed_files)} 个失败文件")
            
            folder_path = self.folder_path_var.get().strip()
            prompt = self.prompt_text.get("1.0", tk.END).strip()
            
            threading.Thread(target=self._loop_fix_thread, 
                            args=(folder_path, prompt), 
                            daemon=True).start()
    
    def _loop_fix_thread(self, folder_path, prompt):
        """循环纠错线程"""
        try:
            cycle = 1
            while not self.loop_fix_stop_flag:
                # 获取当前失败的文件
                failed_files = [fname for fname, status in self.file_status_map.items() if status == 'error']
                
                if not failed_files:
                    self.root.after(0, lambda: self.log_message("✅ 所有文件处理成功！循环纠错完成���"))
                    self.root.after(0, lambda: messagebox.showinfo("完成", "所有文件已成功处理！"))
                    break
                
                self.root.after(0, lambda c=cycle, n=len(failed_files): 
                              self.log_message(f"🔄 第 {c} 轮循环纠错，处理 {n} 个失败文件"))
                
                # 处理失败的文件
                self._reprocess_files_sync(folder_path, failed_files, prompt, f"循环纠错-第{cycle}轮")
                
                cycle += 1
                
                # 检查是否需要停止
                if self.loop_fix_stop_flag:
                    self.root.after(0, lambda: self.log_message("🛑 循环纠错已停止"))
                    break
                
                # 短暂延迟，避免过于频繁
                time.sleep(1)
        
        finally:
            self.loop_fix_running = False
            self.loop_fix_stop_flag = False
            self.root.after(0, lambda: self.loop_fix_btn.config(text="🔄 循环纠错开始"))
    
    def optimize_docs(self):
        """优化文档：允许用户选择特定文件重新处理"""
        if not self.processing_completed:
            messagebox.showwarning("警告", "请先完成一次文件批处理方可使用此功能！")
            return
        
        file_items = [{"name": fname, "status": status} 
                     for fname, status in self.file_status_map.items()]
        
        if not file_items:
            messagebox.showwarning("警告", "没有可优化的文件！")
            return
        
        dialog = FileSelectionDialog(self.root, file_items)
        self.root.wait_window(dialog.dialog)
        
        selected_files = dialog.result
        if not selected_files:
            self.log_message("⚠️ 未选择任何文件")
            return
        
        self.log_message(f"✨ 开始优化文档，共选择 {len(selected_files)} 个文件")
        
        folder_path = self.folder_path_var.get().strip()
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        
        threading.Thread(target=self._reprocess_files_thread, 
                        args=(folder_path, selected_files, prompt, "优化文档"), 
                        daemon=True).start()
    
    def _reprocess_files_sync(self, folder_path, file_list, prompt, operation_name):
        """同步重新处理指定文件（用于循环纠错）"""
        max_workers = self.config.get("max_workers", 2)
        success_count = 0
        error_count = 0
        
        def process_single_file(filename):
            if self.loop_fix_stop_flag:
                return {"status": "stopped", "filename": filename}
            
            file_path = os.path.join(folder_path, filename)
            self.root.after(0, lambda: self.update_current_file(filename, "processing"))
            self.root.after(0, lambda: self.update_file_status(filename, "processing"))
            
            for attempt in range(1, self.config.get("max_retries", 3) + 1):
                if self.loop_fix_stop_flag:
                    return {"status": "stopped", "filename": filename}
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        source_text = f.read().strip()
                    
                    if not source_text:
                        raise ValueError("文件内容为空")
                    
                    result = self.call_llm_api(prompt, source_text)
                    processed_output = self.post_process_format(result)
                    
                    similarity_threshold = self.config.get("similarity_threshold", 40) / 100.0
                    sim_ratio = self.get_similarity(source_text, processed_output)
                    
                    if sim_ratio > similarity_threshold:
                        self.root.after(0, lambda f=filename, a=attempt, s=sim_ratio: 
                                      self.log_message(f"⚠️ [{operation_name}][{f}] 第{a}次失败：相似度{s:.2%}过高"))
                        if attempt < self.config.get("max_retries", 3):
                            time.sleep(2)
                            continue
                        else:
                            raise Exception(f"相似度过高（{sim_ratio:.2%}），疑似复读原文")
                    
                    final_result = self.apply_regex_rules(processed_output)
                    
                    out_filename = filename.replace('.txt', '_processed.txt')
                    result_file = os.path.join(self.current_task_folder, out_filename)
                    with open(result_file, 'w', encoding='utf-8') as f:
                        f.write(final_result)
                    
                    self.root.after(0, lambda f=filename, s=sim_ratio: 
                                  self.log_message(f"✅ [{operation_name}][{f}] 处理成功！相似度: {s:.2%}"))
                    self.root.after(0, lambda f=filename: self.update_file_status(f, "success"))
                    return {"status": "success", "filename": filename}
                
                except Exception as e:
                    if attempt < self.config.get("max_retries", 3):
                        self.root.after(0, lambda f=filename, a=attempt, err=str(e): 
                                      self.log_message(f"❌ [{operation_name}][{f}] 第{a}次失败: {err}"))
                        time.sleep(2)
                    else:
                        self.root.after(0, lambda f=filename, err=str(e): 
                                      self.log_message(f"🚫 [{operation_name}][{f}] 处理失败: {err}"))
                        self.root.after(0, lambda f=filename: self.update_file_status(f, "error"))
                        
                        error_file = os.path.join(self.current_task_folder, filename.replace('.txt', '_error.txt'))
                        with open(error_file, 'w', encoding='utf-8') as f:
                            f.write(f"处理失败\n错误: {str(e)}\n时间: {datetime.now()}")
                        return {"status": "error", "filename": filename}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_single_file, f) for f in file_list]
            
            for future in concurrent.futures.as_completed(futures):
                if self.loop_fix_stop_flag:
                    break
                result = future.result()
                if result and result["status"] == "success":
                    success_count += 1
                elif result and result["status"] == "error":
                    error_count += 1
        
        self.root.after(0, lambda s=success_count, e=error_count: 
                      self.log_message(f"📊 [{operation_name}] 本轮完成: 成功 {s}, 失败 {e}"))
    
    def _reprocess_files_thread(self, folder_path, file_list, prompt, operation_name):
        """重新处理指定文件的线程函数"""
        try:
            self.root.after(0, lambda: self.start_btn.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.fix_errors_btn.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.loop_fix_btn.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.optimize_docs_btn.config(state=tk.DISABLED))
            
            self.root.after(0, lambda: self.update_progress(0, len(file_list)))
            
            max_workers = self.config.get("max_workers", 2)
            success_count = 0
            error_count = 0
            
            def process_single_file(filename):
                file_path = os.path.join(folder_path, filename)
                self.root.after(0, lambda: self.update_current_file(filename, "processing"))
                self.root.after(0, lambda: self.update_file_status(filename, "processing"))
                
                for attempt in range(1, self.config.get("max_retries", 3) + 1):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            source_text = f.read().strip()
                        
                        if not source_text:
                            raise ValueError("文件内容为空")
                        
                        result = self.call_llm_api(prompt, source_text)
                        processed_output = self.post_process_format(result)
                        
                        similarity_threshold = self.config.get("similarity_threshold", 40) / 100.0
                        sim_ratio = self.get_similarity(source_text, processed_output)
                        
                        if sim_ratio > similarity_threshold:
                            self.root.after(0, lambda f=filename, a=attempt, s=sim_ratio: 
                                          self.log_message(f"⚠️ [{operation_name}][{f}] 第{a}次失败：相似度{s:.2%}过高"))
                            if attempt < self.config.get("max_retries", 3):
                                time.sleep(2)
                                continue
                            else:
                                raise Exception(f"相似度过高（{sim_ratio:.2%}），疑似复读原文")
                        
                        final_result = self.apply_regex_rules(processed_output)
                        
                        out_filename = filename.replace('.txt', '_processed.txt')
                        result_file = os.path.join(self.current_task_folder, out_filename)
                        with open(result_file, 'w', encoding='utf-8') as f:
                            f.write(final_result)
                        
                        self.root.after(0, lambda f=filename, s=sim_ratio: 
                                      self.log_message(f"✅ [{operation_name}][{f}] 处理成功！相似度: {s:.2%}"))
                        self.root.after(0, lambda f=filename: self.update_file_status(f, "success"))
                        return {"status": "success", "filename": filename}
                    
                    except Exception as e:
                        if attempt < self.config.get("max_retries", 3):
                            self.root.after(0, lambda f=filename, a=attempt, err=str(e): 
                                          self.log_message(f"❌ [{operation_name}][{f}] 第{a}次失败: {err}"))
                            time.sleep(2)
                        else:
                            self.root.after(0, lambda f=filename, err=str(e): 
                                          self.log_message(f"🚫 [{operation_name}][{f}] 处理失败: {err}"))
                            self.root.after(0, lambda f=filename: self.update_file_status(f, "error"))
                            
                            error_file = os.path.join(self.current_task_folder, filename.replace('.txt', '_error.txt'))
                            with open(error_file, 'w', encoding='utf-8') as f:
                                f.write(f"处理失败\n错误: {str(e)}\n时间: {datetime.now()}")
                            return {"status": "error", "filename": filename}
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(process_single_file, f) for f in file_list]
                
                for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                    result = future.result()
                    if result and result["status"] == "success":
                        success_count += 1
                    else:
                        error_count += 1
                    self.root.after(0, lambda c=i, t=len(file_list): self.update_progress(c, t))
            
            final_msg = f"✅ {operation_name}完成！成功: {success_count}, 失败: {error_count}, 总计: {len(file_list)}"
            self.root.after(0, lambda: self.log_message(final_msg))
            self.root.after(0, lambda msg=final_msg: messagebox.showinfo("完成", msg))
        
        except Exception as e:
            error_msg = f"❌ {operation_name}异常: {str(e)}"
            self.root.after(0, lambda: self.log_message(error_msg))
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.fix_errors_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.loop_fix_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.optimize_docs_btn.config(state=tk.NORMAL))
    
    def start_processing(self):
        """开始处理"""
        if not self.current_input_folder or not os.path.exists(self.current_input_folder):
            messagebox.showerror("错误", "请先选择有效的文件或文件夹！")
            return
        if not self.batch_files_list:
            messagebox.showerror("错误", "没有可处理的 .txt 文件！")
            return
        
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showerror("错误", "提示词不能为空！")
            return
        
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.is_processing = True
        self.is_paused = False
        self.pause_event.set()
        
        threading.Thread(target=self._process_batch_thread, args=(self.current_input_folder, self.batch_files_list, prompt), daemon=True).start()
    
    def toggle_pause(self):
        """切换暂停/继续状态"""
        if self.is_paused:
            self.is_paused = False
            self.pause_event.set()
            self.pause_btn.config(text="⏸ 暂停")
            self.log_message("▶ 恢复处理...")
            self.overall_status_var.set("处理中")
        else:
            self.is_paused = True
            self.pause_event.clear()
            self.pause_btn.config(text="▶ 继续")
            self.log_message("⏸ 已暂停，等待当前文件处理完成...")
            self.overall_status_var.set("已暂停")
    
    def _process_batch_thread(self, folder_path, file_list, prompt):
        try:
            folder_name = os.path.basename(folder_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_folder = os.path.join(self.out_dir, f"{timestamp}_{folder_name}")
            os.makedirs(task_folder, exist_ok=True)
            self.current_task_folder = task_folder
            
            self.root.after(0, lambda: self.log_message(f"🚀 开始批量处理 {len(file_list)} 个文件"))
            self.root.after(0, lambda: self.update_progress(0, len(file_list)))
            
            max_workers = self.config.get("max_workers", 2)
            success_count = 0
            error_count = 0
            
            def process_single_file(filename):
                file_path = os.path.join(folder_path, filename)
                self.root.after(0, lambda: self.update_current_file(filename, "processing"))
                self.root.after(0, lambda: self.update_file_status(filename, "processing"))
                
                for attempt in range(1, self.config.get("max_retries", 3) + 1):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            source_text = f.read().strip()
                        
                        if not source_text:
                            raise ValueError("文件内容为空")
                        
                        result = self.call_llm_api(prompt, source_text)
                        processed_output = self.post_process_format(result)
                        
                        similarity_threshold = self.config.get("similarity_threshold", 40) / 100.0
                        sim_ratio = self.get_similarity(source_text, processed_output)
                        
                        if sim_ratio > similarity_threshold:
                            self.root.after(0, lambda f=filename, a=attempt, s=sim_ratio: 
                                          self.log_message(f"⚠️ [{f}] 第{a}次失败：相似度{s:.2%}过高"))
                            if attempt < self.config.get("max_retries", 3):
                                time.sleep(2)
                                continue
                            else:
                                raise Exception(f"相似度过高（{sim_ratio:.2%}），疑似复读原文")
                        
                        final_result = self.apply_regex_rules(processed_output)
                        
                        out_filename = filename.replace('.txt', '_processed.txt')
                        result_file = os.path.join(task_folder, out_filename)
                        with open(result_file, 'w', encoding='utf-8') as f:
                            f.write(final_result)
                        
                        self.root.after(0, lambda f=filename, s=sim_ratio: 
                                      self.log_message(f"✅ [{f}] 处理成功！相似度: {s:.2%}"))
                        self.root.after(0, lambda f=filename: self.update_file_status(f, "success"))
                        return {"status": "success", "filename": filename}
                    
                    except Exception as e:
                        if attempt < self.config.get("max_retries", 3):
                            self.root.after(0, lambda f=filename, a=attempt, err=str(e): 
                                          self.log_message(f"❌ [{f}] 第{a}次失败: {err}"))
                            time.sleep(2)
                        else:
                            self.root.after(0, lambda f=filename, err=str(e): 
                                          self.log_message(f"🚫 [{f}] 处理失败: {err}"))
                            self.root.after(0, lambda f=filename: self.update_file_status(f, "error"))
                            
                            error_file = os.path.join(task_folder, filename.replace('.txt', '_error.txt'))
                            with open(error_file, 'w', encoding='utf-8') as f:
                                f.write(f"处理失败\n错误: {str(e)}\n时间: {datetime.now()}")
                            return {"status": "error", "filename": filename}
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                
                for idx, f in enumerate(file_list):
                    self.pause_event.wait()
                    future = executor.submit(process_single_file, f)
                    futures.append((idx, future))
                
                for i, (idx, future) in enumerate(futures, 1):
                    result = future.result()
                    if result and result["status"] == "success":
                        success_count += 1
                    else:
                        error_count += 1
                    self.root.after(0, lambda c=i, t=len(file_list): self.update_progress(c, t))
            
            self.processing_completed = True
            
            self.root.after(0, lambda: self.fix_errors_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.loop_fix_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.optimize_docs_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.view_result_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.merge_result_btn.config(state=tk.NORMAL))
            
            final_msg = f"✅ 批量处理完成！成功: {success_count}, 失败: {error_count}, 总计: {len(file_list)}"
            self.root.after(0, lambda: self.log_message(final_msg))
            result_msg = final_msg + f"\n\n结果保存在:\n{task_folder}"
            self.root.after(0, lambda msg=result_msg: messagebox.showinfo("完成", msg))
        
        except Exception as e:
            error_msg = f"❌ 批量处理异常: {str(e)}"
            self.root.after(0, lambda: self.log_message(error_msg))
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.pause_btn.config(state=tk.DISABLED, text="⏸ 暂停"))
            self.root.after(0, lambda: setattr(self, 'is_processing', False))
            self.root.after(0, lambda: setattr(self, 'is_paused', False))
            self.root.after(0, lambda: self.pause_event.set())
    
    def call_llm_api(self, prompt, text_content):
        """调用大模型API处理文本"""
        base_url = self.config["api_url"].rstrip("/")
        if "/v1/chat/completions" in base_url:
            api_url = base_url
        else:
            if not base_url.endswith("/v1"):
                base_url += "/v1"
            api_url = f"{base_url}/chat/completions"
        
        headers = {"Content-Type": "application/json"}
        if self.config.get("api_key"):
            headers["Authorization"] = f"Bearer {self.config['api_key']}"
        
        preset_content = self.preset_text.get("1.0", tk.END).strip()
        messages = []
        if preset_content:
            messages.append({"role": "system", "content": preset_content})
        
        user_content = (
            f"【绝对指令：禁止复读原文，必须进行处理转写】\n"
            f"任务要求：{prompt}\n\n"
            f"--- 待处理原文 START ---\n{text_content}\n--- 待处理原文 END ---\n\n"
            f"【再次强调】请立即开始转写。仅输出转写后的内容，严禁直接粘贴原文。"
        )
        messages.append({"role": "user", "content": user_content})
        
        payload = {
            "model": self.config["selected_model"],
            "messages": messages,
            "max_tokens": self.config.get("max_tokens", 1500),
            "temperature": self.config.get("temperature", 0.8),
            "top_p": self.config.get("top_p", 0.95),
            "presence_penalty": self.config.get("presence_penalty", 1.2),
            "frequency_penalty": self.config.get("frequency_penalty", 1.2)
        }
        
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=self.config["timeout"]
        )
        response.raise_for_status()
        data = response.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        else:
            raise Exception("API返回格式错误")

if __name__ == "__main__":
    app = MainApplication()
    app.root.mainloop()
