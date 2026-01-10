"""智能提示词处理器（带API配置界面 + 批量文件夹支持 + 断点续传 + 重试机制 + 提示词管理 + 预设 + 正则后处理 + 进程监控 + JSON格式支持）"""
import os
import json
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from datetime import datetime
import requests
import threading
import sys
import re
from pathlib import Path

# ================== 默认配置 ==================
DEFAULT_CONFIG = {
    "api_url": "http://localhost:11434/api/generate",
    "api_key": "",
    "timeout": 180,
    "selected_model": "",
    "models_list": [],
    "batch_interval": 3
}
CONFIG_FILE = "config.json"
# ===============================================

class ConfigWindow:
    """配置窗口 - 用于设置API参数和测试连接"""
    def __init__(self, root):
        self.root = root
        self.root.title("大模型API配置")
        self.root.geometry("650x550")
        self.root.resizable(False, False)
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Arial', 10))
        style.configure('TLabel', font=('Arial', 10))
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(main_frame, text="大模型API配置", style='Header.TLabel')
        title_label.pack(pady=(0, 15))
        
        # API地址
        api_frame = ttk.Frame(main_frame)
        api_frame.pack(fill=tk.X, pady=5)
        ttk.Label(api_frame, text="API地址:").pack(side=tk.LEFT)
        self.api_url_var = tk.StringVar(value=DEFAULT_CONFIG["api_url"])
        api_entry = ttk.Entry(api_frame, textvariable=self.api_url_var, width=50)
        api_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        # API密钥
        key_frame = ttk.Frame(main_frame)
        key_frame.pack(fill=tk.X, pady=5)
        ttk.Label(key_frame, text="API密钥:").pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar(value=DEFAULT_CONFIG["api_key"])
        key_entry = ttk.Entry(key_frame, textvariable=self.api_key_var, width=50, show="*")
        key_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        # 超时设置
        timeout_frame = ttk.Frame(main_frame)
        timeout_frame.pack(fill=tk.X, pady=5)
        ttk.Label(timeout_frame, text="超时时间(秒):").pack(side=tk.LEFT)
        self.timeout_var = tk.StringVar(value=str(DEFAULT_CONFIG["timeout"]))
        timeout_entry = ttk.Entry(timeout_frame, textvariable=self.timeout_var, width=10)
        timeout_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        # 批量间隔设置
        interval_frame = ttk.Frame(main_frame)
        interval_frame.pack(fill=tk.X, pady=5)
        ttk.Label(interval_frame, text="批量处理间隔(秒):").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value=str(DEFAULT_CONFIG["batch_interval"]))
        interval_entry = ttk.Entry(interval_frame, textvariable=self.interval_var, width=10)
        interval_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)
        self.test_btn = ttk.Button(btn_frame, text="测试连接", command=self.test_connection)
        self.test_btn.pack(side=tk.LEFT, padx=5)
        self.save_btn = ttk.Button(btn_frame, text="保存配置", command=self.save_config, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=5)
        
        # 状态显示
        status_frame = ttk.LabelFrame(main_frame, text="连接状态", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.status_text = scrolledtext.ScrolledText(status_frame, height=8, font=('Consolas', 9))
        self.status_text.pack(fill=tk.BOTH, expand=True)
        self.status_text.config(state=tk.DISABLED)
        
        # 模型选择
        model_frame = ttk.LabelFrame(main_frame, text="可用模型", padding=10)
        model_frame.pack(fill=tk.X, pady=10)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", width=60)
        self.model_combo.pack(fill=tk.X, padx=5, pady=5)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_selected)
        
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def log_status(self, message, clear=False):
        self.status_text.config(state=tk.NORMAL)
        if clear:
            self.status_text.delete(1.0, tk.END)
        self.status_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update()
    
    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.api_url_var.set(config.get("api_url", DEFAULT_CONFIG["api_url"]))
                self.api_key_var.set(config.get("api_key", DEFAULT_CONFIG["api_key"]))
                self.timeout_var.set(str(config.get("timeout", DEFAULT_CONFIG["timeout"])))
                self.interval_var.set(str(config.get("batch_interval", DEFAULT_CONFIG["batch_interval"])))
                models = config.get("models_list", [])
                self.model_combo['values'] = models
                selected = config.get("selected_model", "")
                if selected in models:
                    self.model_var.set(selected)
                self.save_btn.config(state=tk.NORMAL)
                self.log_status("✅ 已加载保存的配置")
            else:
                self.log_status("ℹ️ 未找到配置文件，使用默认设置")
        except Exception as e:
            self.log_status(f"❌ 加载配置失败: {str(e)}")
    
    def test_connection(self):
        self.log_status("⏳ 正在测试连接...", clear=True)
        self.test_btn.config(state=tk.DISABLED)
        self.root.update()
        threading.Thread(target=self._test_connection_thread, daemon=True).start()
    
    def _test_connection_thread(self):
        try:
            api_url = self.api_url_var.get().strip()
            api_key = self.api_key_var.get().strip()
            timeout = int(self.timeout_var.get())
            
            if not api_url:
                self._update_ui_after_test("❌ API地址不能为空")
                return
            
            base_url = api_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url += "/v1"
            models_url = f"{base_url}/models"
            
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            headers["Content-Type"] = "application/json"
            
            self.log_status(f"📡 请求: {models_url}")
            response = requests.get(models_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            models = []
            if "models" in data:
                for model in data["models"]:
                    if isinstance(model, dict) and "name" in model:
                        models.append(model["name"])
                    elif isinstance(model, str):
                        models.append(model)
            elif "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if "id" in item:
                        models.append(item["id"])
            else:
                models = list(data.keys()) if isinstance(data, dict) else [str(data)]
            
            if not models:
                self._update_ui_after_test("⚠️ 未找到可用模型，但连接成功")
                return
            
            self.root.after(0, lambda: self._update_models_list(models))
        except Exception as e:
            error_msg = f"❌ 连接失败: {str(e)}"
            if "Timeout" in str(type(e)):
                error_msg = f"❌ 连接超时 ({timeout}秒)"
            elif "ConnectionError" in str(type(e)):
                error_msg = "❌ 无法连接到服务器，请检查地址"
            self._update_ui_after_test(error_msg)
        finally:
            self.root.after(0, lambda: self.test_btn.config(state=tk.NORMAL))
    
    def _update_ui_after_test(self, message):
        self.log_status(message)
        self.test_btn.config(state=tk.NORMAL)
    
    def _update_models_list(self, models):
        self.model_combo['values'] = models
        if models:
            self.model_var.set(models[0])
            self.save_btn.config(state=tk.NORMAL)
            self.log_status(f"✅ 连接成功! 找到 {len(models)} 个模型")
        else:
            self.log_status("⚠️ 连接成功，但未找到模型")
    
    def on_model_selected(self, event=None):
        self.save_btn.config(state=tk.NORMAL)
    
    def save_config(self):
        try:
            config = {
                "api_url": self.api_url_var.get().strip(),
                "api_key": self.api_key_var.get().strip(),
                "timeout": int(self.timeout_var.get()),
                "batch_interval": int(self.interval_var.get()),
                "selected_model": self.model_var.get(),
                "models_list": list(self.model_combo['values'])
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.log_status("✅ 配置已保存到 config.json")
            messagebox.showinfo("成功", "配置已成功保存！\n点击确定开始处理文件。")
            self.root.destroy()
        except ValueError:
            messagebox.showerror("错误", "超时或间隔时间必须是数字！")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
    
    def on_closing(self):
        if messagebox.askokcancel("退出", "确定要退出程序吗？"):
            self.root.destroy()
            os._exit(0)

class MainApplication:
    def __init__(self, config):
        self.config = config
        self.root = tk.Tk()
        self.root.title("智能提示词处理器")
        self.root.geometry("1000x850")  # 增加宽度
        self.root.minsize(900, 700)
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Arial', 10))
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Success.TButton', background='#4CAF50', foreground='white')
        style.configure('TProgressbar', thickness=20)
        
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(main_frame, text="智能提示词处理器", style='Header.TLabel')
        title_label.pack(pady=(0, 10))
        
        # API信息
        api_info = (
            f"API地址: {config.get('api_url', '未设置')}\n"
            f"使用模型: {config.get('selected_model', '未选择')}\n"
            f"超时时间: {config.get('timeout', 180)} 秒\n"
            f"批量间隔: {config.get('batch_interval', 3)} 秒"
        )
        api_info_frame = ttk.LabelFrame(main_frame, text="当前API配置", padding=8)
        api_info_frame.pack(fill=tk.X, pady=(0, 10))
        api_info_label = ttk.Label(api_info_frame, text=api_info, justify=tk.LEFT)
        api_info_label.pack(padx=5, pady=5)
        
        # =============== 处理模式选择 ===============
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 处理模式选择（左）
        mode_subframe = ttk.Frame(control_frame)
        mode_subframe.pack(side=tk.LEFT)
        ttk.Label(mode_subframe, text="处理模式:").pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value="single")
        single_rb = ttk.Radiobutton(mode_subframe, text="单文件", variable=self.mode_var, value="single", command=self.toggle_mode)
        batch_rb = ttk.Radiobutton(mode_subframe, text="批量文件夹", variable=self.mode_var, value="batch", command=self.toggle_mode)
        single_rb.pack(side=tk.LEFT, padx=(10, 5))
        batch_rb.pack(side=tk.LEFT, padx=(0, 10))
        
        # 初始化批次处理需要的变量
        self.batch_folder_var = tk.StringVar()
        self.batch_files_list = []
        
        # 文件选择控件（右）
        selector_subframe = ttk.Frame(control_frame)
        selector_subframe.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 单文件控件
        self.single_frame = ttk.Frame(selector_subframe)
        ttk.Label(self.single_frame, text="选择文件:").pack(side=tk.LEFT)
        self.file_path_var = tk.StringVar()
        file_entry = ttk.Entry(self.single_frame, textvariable=self.file_path_var, width=40)
        file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        browse_btn = ttk.Button(self.single_frame, text="浏览...", command=self.browse_file)
        browse_btn.pack(side=tk.LEFT, padx=5)
        
        # 批量控件
        self.batch_frame = ttk.Frame(selector_subframe)
        batch_browse_btn = ttk.Button(self.batch_frame, text="选择文件夹", command=self.browse_folder)
        batch_browse_btn.pack(side=tk.LEFT, padx=5)
        self.batch_preview = scrolledtext.ScrolledText(self.batch_frame, height=4, width=50, state=tk.DISABLED)
        self.batch_preview.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 初始显示单文件
        self.single_frame.pack(fill=tk.X)
        self.batch_frame.pack_forget()
        
        # =============== 主布局：左右分栏 ===============
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 左侧配置区域
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3), ipadx=5)
        
        # 右侧进程监控区域
        right_frame = ttk.LabelFrame(content_frame, text="进程监控", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(3, 0), ipadx=5)
        
        # =============== 左侧：提示词输入 ===============
        prompt_frame = ttk.LabelFrame(left_frame, text="输入提示词（批量模式下对所有文件生效）", padding=10)
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # 提示词操作按钮
        prompt_btn_frame = ttk.Frame(prompt_frame)
        prompt_btn_frame.pack(fill=tk.X, pady=(0, 5))
        save_prompt_btn = ttk.Button(prompt_btn_frame, text="保存提示词", command=self.save_prompt)
        save_prompt_btn.pack(side=tk.LEFT, padx=2)
        load_prompt_btn = ttk.Button(prompt_btn_frame, text="加载提示词", command=self.load_prompt)
        load_prompt_btn.pack(side=tk.LEFT, padx=2)
        
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, height=6, font=('Arial', 10))
        self.prompt_text.pack(fill=tk.BOTH, expand=True)
        
        default_prompt = (
            "你是一位专业的内容处理助手。请根据以下要求处理文本：\n"
            "1. 保持内容的核心信息不变\n"
            "2. 优化语言表达，使其更加清晰流畅\n"
            "3. 适当调整结构，增强可读性\n"
            "4. 保留所有关键数据和细节\n\n"
            "需要处理的文本："
        )
        self.prompt_text.insert(tk.END, default_prompt)
        
        # =============== 左侧：系统预设 ===============
        preset_frame = ttk.LabelFrame(left_frame, text="系统预设（可选）", padding=10)
        preset_frame.pack(fill=tk.BOTH, expand=False, pady=5)
        
        preset_btn_frame = ttk.Frame(preset_frame)
        preset_btn_frame.pack(fill=tk.X, pady=(0, 5))
        save_preset_btn = ttk.Button(preset_btn_frame, text="保存预设", command=self.save_preset)
        save_preset_btn.pack(side=tk.LEFT, padx=2)
        load_preset_btn = ttk.Button(preset_btn_frame, text="导入预设", command=self.load_preset_file)
        load_preset_btn.pack(side=tk.LEFT, padx=2)
        
        # 减小高度
        self.preset_text = scrolledtext.ScrolledText(preset_frame, height=2, font=('Arial', 9))
        self.preset_text.pack(fill=tk.BOTH, expand=True)
        self.preset_text.insert(tk.END, "")  # 初始为空
        
        # =============== 左侧：正则规则 ===============
        regex_frame = ttk.LabelFrame(left_frame, text="后处理正则规则（支持纯文本或JSON格式）", padding=10)
        regex_frame.pack(fill=tk.BOTH, expand=False, pady=5)
        
        regex_btn_frame = ttk.Frame(regex_frame)
        regex_btn_frame.pack(fill=tk.X, pady=(0, 5))
        save_regex_btn = ttk.Button(regex_btn_frame, text="保存正则", command=self.save_regex)
        save_regex_btn.pack(side=tk.LEFT, padx=2)
        load_regex_btn = ttk.Button(regex_btn_frame, text="导入正则", command=self.load_regex_file)
        load_regex_btn.pack(side=tk.LEFT, padx=2)
        
        # 减小高度
        self.regex_text = scrolledtext.ScrolledText(regex_frame, height=2, font=('Consolas', 9))
        self.regex_text.pack(fill=tk.BOTH, expand=True)
        self.regex_text.insert(tk.END, (
            "# 纯文本格式: pattern|replacement\n"
            "# JSON格式示例: [{\"pattern\":\"\\\\s+\\\\n\",\"replacement\":\"\\\\n\",\"description\":\"移除多余空白行\"}]\n"
            "# 示例: \\s+\\n|\\n"
        ))
        
        # =============== 右侧：进程监控面板 ===============
        # 总体状态显示
        status_header_frame = ttk.Frame(right_frame)
        status_header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        ttk.Label(status_header_frame, text="总体进度:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
        self.overall_status_var = tk.StringVar(value="等待开始")
        ttk.Label(status_header_frame, textvariable=self.overall_status_var, font=('Arial', 9)).pack(side=tk.LEFT, padx=(5, 0))
        
        # 进度条
        progress_frame = ttk.Frame(right_frame)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_label = ttk.Label(progress_frame, text="0% (0/0)", font=('Arial', 9))
        self.progress_label.pack(pady=(0, 5))
        
        # 当前文件状态
        current_file_frame = ttk.LabelFrame(right_frame, text="当前文件", padding=8)
        current_file_frame.pack(fill=tk.X, padx=10, pady=5)
        self.current_file_var = tk.StringVar(value="无文件")
        ttk.Label(current_file_frame, textvariable=self.current_file_var, wraplength=250).pack(pady=2)
        self.current_status_var = tk.StringVar(value="状态: 等待中")
        ttk.Label(current_file_frame, textvariable=self.current_status_var).pack(pady=2)
        
        # 文件列表
        file_list_frame = ttk.LabelFrame(right_frame, text="文件处理状态", padding=8)
        file_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建Treeview显示文件处理状态
        tree_frame = ttk.Frame(file_list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建Treeview
        self.file_tree = ttk.Treeview(
            tree_frame, 
            columns=('status', 'filename'),
            show='headings',
            yscrollcommand=scrollbar.set,
            height=8
        )
        scrollbar.config(command=self.file_tree.yview)
        
        # 设置列
        self.file_tree.heading('status', text='状态')
        self.file_tree.heading('filename', text='文件名')
        self.file_tree.column('status', width=60, anchor=tk.CENTER)
        self.file_tree.column('filename', width=200, anchor=tk.W)
        
        # 添加标签样式
        self.file_tree.tag_configure('pending', background='#f0f0f0')
        self.file_tree.tag_configure('processing', background='#e6f7ff')
        self.file_tree.tag_configure('success', background='#e6ffe6')
        self.file_tree.tag_configure('error', background='#ffe6e6')
        self.file_tree.pack(fill=tk.BOTH, expand=True)
        
        # =============== 操作按钮区域 ===============
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)
        self.process_btn = ttk.Button(btn_frame, text="开始处理", command=self.process, style='Success.TButton')
        self.process_btn.pack(side=tk.LEFT, padx=10)
        save_profile_btn = ttk.Button(btn_frame, text="保存当前设置", command=self.save_profile)
        save_profile_btn.pack(side=tk.LEFT, padx=10)
        self.config_btn = ttk.Button(btn_frame, text="重新配置API", command=self.reconfigure_api)
        self.config_btn.pack(side=tk.LEFT, padx=10)
        
        # =============== 底部日志区域 ===============
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 创建输出目录
        self.out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OUT")
        os.makedirs(self.out_dir, exist_ok=True)
        
        # 初始化状态
        self.is_processing = False
        self.total_files = 0
        self.processed_files = 0
        self.success_files = 0
        self.error_files = 0
        
        self.log_message("系统已启动，加载配置完成。")
        self.log_message(f"API地址: {config.get('api_url', 'N/A')}")
        self.log_message(f"使用模型: {config.get('selected_model', 'N/A')}")
    
    def toggle_mode(self):
        if self.mode_var.get() == "single":
            self.single_frame.pack(fill=tk.X)
            self.batch_frame.pack_forget()
            self.update_file_list_display([{"name": "单文件模式", "status": "pending"}])
        else:
            self.single_frame.pack_forget()
            self.batch_frame.pack(fill=tk.X)
            self.update_file_list_display([])
    
    def update_file_list_display(self, files):
        """更新文件列表显示"""
        # 清空现有项目
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        # 添加新项目
        for file_info in files:
            status = file_info.get('status', 'pending')
            tag = status if status in ['pending', 'processing', 'success', 'error'] else 'pending'
            self.file_tree.insert('', tk.END, values=(self.get_status_text(status), file_info.get('name', '')), tags=(tag,))
    
    def get_status_text(self, status):
        """获取状态显示文本"""
        status_map = {
            'pending': '⏳',
            'processing': '🔄',
            'success': '✅',
            'error': '❌'
        }
        return status_map.get(status, status)
    
    def update_progress(self, current, total):
        """更新进度条"""
        if total <= 0:
            percent = 0
        else:
            percent = (current / total) * 100
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{percent:.1f}% ({current}/{total})")
        
        # 更新总体状态
        if total == 0:
            self.overall_status_var.set("等待开始")
        elif current < total:
            self.overall_status_var.set(f"处理中 ({current}/{total})")
        else:
            self.overall_status_var.set("完成")
        self.root.update()
    
    def update_current_file(self, filename, status="processing"):
        """更新当前文件显示"""
        self.current_file_var.set(filename)
        status_text = {
            "processing": "状态: 处理中...",
            "success": "状态: 处理成功",
            "error": "状态: 处理失败"
        }.get(status, "状态: 等待中")
        self.current_status_var.set(status_text)
        self.root.update()
    
    def update_file_status(self, filename, status):
        """更新特定文件的状态"""
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
        
        if not hasattr(self, 'temp_logs'):
            self.temp_logs = []
        self.temp_logs.append(formatted)
        
        self.status_var.set(message[:50] + "..." if len(message) > 50 else message)
        self.root.update()
    
    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="选择文本文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.log_message(f"已选择文件: {os.path.basename(file_path)}")
            # 更新文件列表显示
            self.update_file_list_display([{"name": os.path.basename(file_path), "status": "pending"}])
    
    def browse_folder(self):
        folder_path = filedialog.askdirectory(title="选择包含 .txt 文件的文件夹")
        if folder_path:
            self.batch_folder_var.set(folder_path)
            txt_files = sorted([f for f in os.listdir(folder_path) 
                               if f.lower().endswith('.txt') and os.path.isfile(os.path.join(folder_path, f))])
            self.batch_files_list = txt_files
            self.batch_preview.config(state=tk.NORMAL)
            self.batch_preview.delete(1.0, tk.END)
            if txt_files:
                self.batch_preview.insert(tk.END, "\n".join(txt_files))
                self.log_message(f"已选择文件夹: {os.path.basename(folder_path)}，共 {len(txt_files)} 个 .txt 文件")
            else:
                self.batch_preview.insert(tk.END, "⚠️ 该文件夹下没有 .txt 文件")
                self.log_message("⚠️ 该文件夹下没有 .txt 文件")
            self.batch_preview.config(state=tk.DISABLED)
            # 更新文件列表显示
            file_list = [{"name": f, "status": "pending"} for f in txt_files]
            self.update_file_list_display(file_list)
    
    def reconfigure_api(self):
        self.root.destroy()
        new_root = tk.Tk()
        config_window = ConfigWindow(new_root)
        new_root.mainloop()
        os.execl(sys.executable, sys.executable, *sys.argv)
    
    def save_prompt(self):
        """保存提示词，支持JSON和纯文本两种格式"""
        content = self.prompt_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "提示词为空，无法保存。")
            return
            
        file_path = filedialog.asksaveasfilename(
            title="保存提示词",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("提示词文件", "*.prompt"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
            
        try:
            # 检查是否为JSON格式
            is_json_format = file_path.lower().endswith('.json')
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if is_json_format:
                    # 尝试解析现有内容为JSON，如果失败则创建新结构
                    try:
                        json_content = json.loads(content)
                        # 确保基本结构
                        if not isinstance(json_content, dict):
                            raise ValueError("内容不是有效的JSON对象")
                        if "type" not in json_content:
                            json_content["type"] = "prompt"
                        if "content" not in json_content:
                            json_content["content"] = content
                    except (json.JSONDecodeError, ValueError):
                        # 创建标准JSON结构
                        json_content = {
                            "type": "prompt",
                            "version": "1.0",
                            "content": content,
                            "description": "智能提示词模板",
                            "metadata": {
                                "created_at": datetime.now().isoformat(),
                                "last_modified": datetime.now().isoformat()
                            }
                        }
                    json.dump(json_content, f, indent=2, ensure_ascii=False)
                else:
                    # 保存为纯文本
                    f.write(content)
                    
            self.log_message(f"✅ 提示词已保存至: {file_path} ({'JSON' if is_json_format else '文本'}格式)")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def load_prompt(self):
        """加载提示词，支持JSON和纯文本两种格式"""
        file_path = filedialog.askopenfilename(
            title="加载提示词",
            filetypes=[("JSON/提示词/文本文件", "*.json *.prompt *.txt"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 检查是否为JSON格式
            is_json = file_path.lower().endswith('.json') or content.strip().startswith('{')
            
            if is_json:
                try:
                    json_data = json.loads(content)
                    # 从JSON中提取提示词内容
                    if isinstance(json_data, dict):
                        if "content" in json_data:
                            prompt_content = json_data["content"]
                        elif "prompt" in json_data:
                            prompt_content = json_data["prompt"]
                        else:
                            prompt_content = json.dumps(json_data, indent=2, ensure_ascii=False)
                    else:
                        prompt_content = json.dumps(json_data, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    prompt_content = content
            else:
                prompt_content = content
                
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert(tk.END, prompt_content)
            self.log_message(f"✅ 已加载提示词: {os.path.basename(file_path)} ({'JSON' if is_json else '文本'}格式)")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")
    
    def save_preset(self):
        """保存预设，支持JSON和纯文本格式"""
        content = self.preset_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "预设内容为空，无法保存。")
            return
            
        file_path = filedialog.asksaveasfilename(
            title="保存预设",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("预设文件", "*.preset"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
            
        try:
            is_json_format = file_path.lower().endswith('.json')
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if is_json_format:
                    try:
                        # 尝试解析现有内容
                        json_content = json.loads(content)
                        if not isinstance(json_content, dict):
                            raise ValueError("JSON内容格式不正确")
                    except (json.JSONDecodeError, ValueError):
                        # 创建标准JSON结构
                        json_content = {
                            "type": "preset",
                            "version": "1.0",
                            "system_prompt": content,
                            "description": "系统提示预设",
                            "metadata": {
                                "created_at": datetime.now().isoformat(),
                                "last_modified": datetime.now().isoformat()
                            }
                        }
                    
                    json.dump(json_content, f, indent=2, ensure_ascii=False)
                else:
                    # 保存为纯文本
                    f.write(content)
                    
            self.log_message(f"✅ 预设已保存: {file_path} ({'JSON' if is_json_format else '文本'}格式)")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def load_preset_file(self):
        """加载预设，支持JSON和纯文本格式"""
        file_path = filedialog.askopenfilename(
            title="导入预设",
            filetypes=[("JSON/预设/文本文件", "*.json *.preset *.txt"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            is_json = file_path.lower().endswith('.json') or content.strip().startswith('{')
            
            if is_json:
                try:
                    json_data = json.loads(content)
                    # 从JSON提取系统提示
                    if isinstance(json_data, dict):
                        if "system_prompt" in json_data:
                            preset_content = json_data["system_prompt"]
                        elif "content" in json_data:
                            preset_content = json_data["content"]
                        elif "prompt" in json_data:
                            preset_content = json_data["prompt"]
                        else:
                            preset_content = json.dumps(json_data, indent=2, ensure_ascii=False)
                    else:
                        preset_content = json.dumps(json_data, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    preset_content = content
            else:
                preset_content = content
                
            self.preset_text.delete("1.0", tk.END)
            self.preset_text.insert(tk.END, preset_content)
            self.log_message(f"✅ 已加载预设: {os.path.basename(file_path)} ({'JSON' if is_json else '文本'}格式)")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")
    
    def save_regex(self):
        """保存正则规则，支持JSON和纯文本格式"""
        content = self.regex_text.get("1.0", tk.END).strip()
        if not content or all(line.strip().startswith("#") or not line.strip() for line in content.splitlines()):
            messagebox.showwarning("警告", "正则规则为空或仅为注释，无法保存。")
            return
            
        file_path = filedialog.asksaveasfilename(
            title="保存正则规则",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("正则规则", "*.regex"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
            
        try:
            is_json_format = file_path.lower().endswith('.json')
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if is_json_format:
                    try:
                        # 尝试解析现有内容
                        json_content = json.loads(content)
                        if not isinstance(json_content, dict):
                            raise ValueError("JSON内容格式不正确")
                    except (json.JSONDecodeError, ValueError):
                        # 从文本转换为JSON结构
                        rules = []
                        for line_num, line in enumerate(content.splitlines(), 1):
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                                
                            # 处理纯文本格式的规则
                            if "|" in line:
                                parts = line.split("|", 1)
                                pattern = parts[0].strip()
                                replacement = parts[1].strip() if len(parts) > 1 else ""
                                description = f"规则 {line_num}"
                                
                                # 尝试从注释中提取描述
                                if "#" in replacement:
                                    replacement_parts = replacement.split("#", 1)
                                    replacement = replacement_parts[0].strip()
                                    description = replacement_parts[1].strip()
                                
                                rules.append({
                                    "pattern": pattern,
                                    "replacement": replacement,
                                    "description": description,
                                    "enabled": True
                                })
                        
                        json_content = {
                            "type": "regex_rules",
                            "version": "1.0",
                            "rules": rules,
                            "metadata": {
                                "created_at": datetime.now().isoformat(),
                                "source": "converted_from_text"
                            }
                        }
                    
                    json.dump(json_content, f, indent=2, ensure_ascii=False)
                else:
                    # 保存为纯文本
                    f.write(content)
                    
            self.log_message(f"✅ 正则规则已保存: {file_path} ({'JSON' if is_json_format else '文本'}格式)")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def load_regex_file(self):
        """加载正则规则，支持JSON和纯文本格式"""
        file_path = filedialog.askopenfilename(
            title="导入正则规则",
            filetypes=[("JSON/正则规则/文本文件", "*.json *.regex *.txt"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            is_json = file_path.lower().endswith('.json') or content.strip().startswith('{')
            
            if is_json:
                try:
                    json_data = json.loads(content)
                    # 从JSON提取规则
                    if isinstance(json_data, dict) and "rules" in json_data and isinstance(json_data["rules"], list):
                        rules_content = "# 从JSON文件加载的正则规则\n"
                        for rule in json_data["rules"]:
                            if rule.get("enabled", True):
                                pattern = rule.get("pattern", "")
                                replacement = rule.get("replacement", "")
                                description = rule.get("description", "")
                                rule_line = f"{pattern}|{replacement}"
                                if description:
                                    rule_line += f"  # {description}"
                                rules_content += rule_line + "\n"
                    else:
                        rules_content = json.dumps(json_data, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    rules_content = content
            else:
                rules_content = content
                
            self.regex_text.delete("1.0", tk.END)
            self.regex_text.insert(tk.END, rules_content)
            self.log_message(f"✅ 已加载正则规则: {os.path.basename(file_path)} ({'JSON' if is_json else '文本'}格式)")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")
    
    def save_profile(self):
        """保存当前设置配置，使用JSON格式"""
        profile = {
            "type": "profile",
            "version": "1.0",
            "prompt": {
                "content": self.prompt_text.get("1.0", tk.END).strip(),
                "format": "raw"
            },
            "preset": {
                "content": self.preset_text.get("1.0", tk.END).strip(),
                "format": "raw"
            },
            "regex_rules": {
                "content": self.regex_text.get("1.0", tk.END).strip(),
                "format": "raw"
            },
            "mode": self.mode_var.get(),
            "batch_interval": self.config.get("batch_interval", 3),
            "selected_model": self.config.get("selected_model", ""),
            "api_url": self.config.get("api_url", ""),
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "app_version": "3.0"
            }
        }
        
        file_path = filedialog.asksaveasfilename(
            title="保存当前设置（Profile）",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("设置文件", "*.profile"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            self.log_message(f"✅ 当前设置已保存: {file_path} (JSON格式)")
        except Exception as e:
            messagebox.showerror("错误", f"保存设置失败: {str(e)}")
    
    def apply_regex_rules(self, text, log_file=None):
        """应用正则规则进行后处理，支持JSON和纯文本两种格式的规则"""
        rules_content = self.regex_text.get("1.0", tk.END).strip()
        if not rules_content:
            return text
            
        # 尝试解析为JSON格式
        try:
            json_rules = json.loads(rules_content)
            if isinstance(json_rules, dict) and "rules" in json_rules and isinstance(json_rules["rules"], list):
                # 处理JSON格式规则
                processed = text
                for rule_idx, rule in enumerate(json_rules["rules"], 1):
                    if not rule.get("enabled", True):
                        continue
                        
                    pattern = rule.get("pattern", "")
                    replacement = rule.get("replacement", "")
                    description = rule.get("description", f"规则 {rule_idx}")
                    
                    if not pattern:
                        continue
                        
                    try:
                        compiled = re.compile(pattern, re.MULTILINE | re.DOTALL)
                        processed = compiled.sub(replacement, processed)
                        if log_file:
                            with open(log_file, 'a', encoding='utf-8') as lf:
                                lf.write(f"[Regex JSON Rule {rule_idx}] {description}\n")
                                lf.write(f"  Pattern: {pattern}\n")
                                lf.write(f"  Replacement: {replacement}\n")
                    except Exception as e:
                        error_msg = f"JSON正则规则 {rule_idx} ({description}) 错误: {str(e)}"
                        self.root.after(0, lambda msg=error_msg: self.log_message(msg))
                        if log_file:
                            with open(log_file, 'a', encoding='utf-8') as lf:
                                lf.write(f"[Regex JSON Error {rule_idx}] {error_msg}\n")
                return processed
        except (json.JSONDecodeError, ValueError):
            # 不是JSON格式，继续处理纯文本格式
            pass
            
        # 处理纯文本格式规则
        lines = rules_content.splitlines()
        processed = text
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                continue
                
            try:
                pattern, replacement = line.split("|", 1)
                # 处理可能的注释
                if "#" in replacement:
                    replacement_parts = replacement.split("#", 1)
                    replacement = replacement_parts[0].strip()
                    description = replacement_parts[1].strip()
                else:
                    description = f"规则 {line_num}"
                    
                # 处理转义序列
                pattern = pattern.replace(r'\n', '\n').replace(r'\t', '\t').replace(r'\r', '\r')
                replacement = replacement.replace(r'\n', '\n').replace(r'\t', '\t').replace(r'\r', '\r')
                
                compiled = re.compile(pattern, re.MULTILINE | re.DOTALL)
                processed = compiled.sub(replacement, processed)
                if log_file:
                    with open(log_file, 'a', encoding='utf-8') as lf:
                        lf.write(f"[Regex Text Rule {line_num}] {description}\n")
                        lf.write(f"  Pattern: {pattern}\n")
                        lf.write(f"  Replacement: {replacement}\n")
            except Exception as e:
                error_msg = f"正则规则第{line_num}行错误: {str(e)}"
                self.root.after(0, lambda msg=error_msg: self.log_message(msg))
                if log_file:
                    with open(log_file, 'a', encoding='utf-8') as lf:
                        lf.write(f"[Regex Error {line_num}] {error_msg}\n")
                        
        return processed
    
    def process(self):
        # 重置状态
        self.is_processing = True
        self.processed_files = 0
        self.success_files = 0
        self.error_files = 0
        
        mode = self.mode_var.get()
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showerror("错误", "提示词不能为空！")
            return
        
        if mode == "single":
            file_path = self.file_path_var.get().strip()
            if not file_path or not os.path.exists(file_path):
                messagebox.showerror("错误", "请选择有效的文本文件！")
                return
            
            self.process_btn.config(state=tk.DISABLED)
            self.config_btn.config(state=tk.DISABLED)
            
            # 初始化进度
            self.total_files = 1
            self.update_progress(0, self.total_files)
            self.update_current_file(os.path.basename(file_path), "processing")
            self.update_file_status(os.path.basename(file_path), "processing")
            
            threading.Thread(target=self._process_single_thread, args=(file_path, prompt), daemon=True).start()
        else:
            folder_path = self.batch_folder_var.get().strip()
            if not folder_path or not os.path.isdir(folder_path):
                messagebox.showerror("错误", "请选择有效的文件夹！")
                return
            if not self.batch_files_list:
                messagebox.showerror("错误", "文件夹中没有 .txt 文件！")
                return
            
            self.process_btn.config(state=tk.DISABLED)
            self.config_btn.config(state=tk.DISABLED)
            
            # 初始化进度
            self.total_files = len(self.batch_files_list)
            self.update_progress(0, self.total_files)
            
            threading.Thread(target=self._process_batch_thread, args=(folder_path, self.batch_files_list, prompt), daemon=True).start()
    
    def _process_single_thread(self, file_path, prompt):
        try:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_folder = os.path.join(self.out_dir, f"{timestamp}_{base_name}")
            os.makedirs(task_folder, exist_ok=True)
            
            log_file = os.path.join(task_folder, f"{timestamp}_{base_name}_log.txt")
            result_file = os.path.join(task_folder, f"{timestamp}_{base_name}_out.txt")
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("单文件任务日志\n" + "="*50 + "\n")
                for log in getattr(self, 'temp_logs', []):
                    f.write(log + "\n")
            
            self.root.after(0, lambda: self.log_message(f"📂 读取文件: {file_path}"))
            self.root.after(0, lambda: self.update_current_file(os.path.basename(file_path), "processing"))
            
            text_content = self.read_text_file(file_path, log_file)
            if not text_content.strip():
                raise ValueError("文件内容为空")
            
            self.root.after(0, lambda: self.log_message(f"🚀 调用大模型API处理内容 ({len(text_content)} 字符)"))
            result = self.call_llm_api(prompt, text_content, log_file)
            if not result:
                raise Exception("API返回空结果")
            
            final_result = self.apply_regex_rules(result, log_file)
            
            with open(result_file, 'w', encoding='utf-8') as f:
                f.write(final_result)
            
            self.root.after(0, lambda: self.update_progress(1, 1))
            self.root.after(0, lambda: self.update_current_file(os.path.basename(file_path), "success"))
            self.root.after(0, lambda: self.update_file_status(os.path.basename(file_path), "success"))
            self.root.after(0, lambda: self.log_message(f"✅ 处理完成! 结果已保存至:\n{result_file}"))
            self.root.after(0, lambda: messagebox.showinfo("完成", f"处理成功！\n\n结果文件: {result_file}\n\n日志文件: {log_file}"))
            
            try:
                os.startfile(os.path.dirname(result_file))
            except:
                pass
        except Exception as e:
            error_msg = f"❌ 处理失败: {str(e)}"
            self.root.after(0, lambda: self.log_message(error_msg))
            self.root.after(0, lambda: self.update_current_file(os.path.basename(file_path), "error"))
            self.root.after(0, lambda: self.update_file_status(os.path.basename(file_path), "error"))
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.root.after(0, lambda: self.process_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.config_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: setattr(self, 'is_processing', False))
    
    def _process_batch_thread(self, folder_path, file_list, prompt):
        try:
            folder_name = os.path.basename(folder_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_folder = os.path.join(self.out_dir, f"{timestamp}_{folder_name}_批任务")
            os.makedirs(task_folder, exist_ok=True)
            batch_log_file = os.path.join(task_folder, "batch_log.txt")
            
            # 检查已处理的文件（断点续传）
            existing_outputs = set()
            if os.path.exists(task_folder):
                for f in os.listdir(task_folder):
                    if f.endswith('_processed.txt') or f.endswith('_error.txt'):
                        orig_name = f.replace('_processed.txt', '.txt').replace('_error.txt', '.txt')
                        existing_outputs.add(orig_name)
            
            files_to_process = [f for f in file_list if f not in existing_outputs]
            skipped = len(file_list) - len(files_to_process)
            total = len(files_to_process)
            
            self.root.after(0, lambda: self.log_message(
                f"🔍 检测到 {skipped} 个文件已处理，跳过。剩余 {total} 个待处理。"))
            
            with open(batch_log_file, 'a', encoding='utf-8') as log_f:
                if skipped > 0:
                    log_f.write(f"\n[断点续传] 跳过 {skipped} 个已处理文件\n")
                log_f.write(f"批量任务日志 - {total} 个新文件\n")
                log_f.write("="*60 + "\n")
            
            success_count = 0
            for idx, filename in enumerate(files_to_process, 1):
                file_path = os.path.join(folder_path, filename)
                self.root.after(0, lambda f=filename: self.update_current_file(f, "processing"))
                self.root.after(0, lambda f=filename: self.update_file_status(f, "processing"))
                self.root.after(0, lambda i=idx, n=total, f=filename: self.log_message(f"[{i}/{n}] 正在处理: {f}"))
                self.root.after(0, lambda i=idx-1, n=total: self.update_progress(i, total))
                
                processed_successfully = False
                last_error = ""
                max_retries = 3
                retry_delay = 10
                
                for attempt in range(1, max_retries + 1):
                    try:
                        if attempt > 1:
                            self.root.after(0, lambda a=attempt: self.log_message(f" ⏳ 第 {a} 次重试..."))
                            time.sleep(retry_delay)
                        
                        text_content = self.read_text_file(file_path, batch_log_file)
                        if not text_content.strip():
                            raise ValueError("文件内容为空")
                        
                        result = self.call_llm_api(prompt, text_content, batch_log_file)
                        if not result:
                            raise Exception("API 返回空结果")
                        
                        final_result = self.apply_regex_rules(result, batch_log_file)
                        
                        out_filename = filename.replace('.txt', '_processed.txt')
                        result_file = os.path.join(task_folder, out_filename)
                        with open(result_file, 'w', encoding='utf-8') as rf:
                            rf.write(final_result)
                        
                        log_entry = f"[OK] {filename} -> {out_filename}"
                        with open(batch_log_file, 'a', encoding='utf-8') as log_f:
                            log_f.write(log_entry + "\n")
                        
                        processed_successfully = True
                        success_count += 1
                        self.root.after(0, lambda f=out_filename: self.log_message(f"✅ 已保存: {f}"))
                        self.root.after(0, lambda f=filename: self.update_file_status(f, "success"))
                        break
                    except Exception as e:
                        last_error = str(e)
                        error_msg = f" ❌ 尝试 {attempt}/{max_retries} 失败: {last_error}"
                        self.root.after(0, lambda msg=error_msg: self.log_message(msg))
                        with open(batch_log_file, 'a', encoding='utf-8') as log_f:
                            log_f.write(f"[RETRY {attempt}] {filename}: {last_error}\n")
                
                if not processed_successfully:
                    error_filename = filename.replace('.txt', '_error.txt')
                    error_file = os.path.join(task_folder, error_filename)
                    with open(error_file, 'w', encoding='utf-8') as ef:
                        ef.write(f"处理失败（{max_retries} 次重试后仍失败）\n")
                        ef.write(f"最后错误: {last_error}\n")
                        ef.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    with open(batch_log_file, 'a', encoding='utf-8') as log_f:
                        log_f.write(f"[FAILED] {filename} -> {error_filename}\n")
                    self.root.after(0, lambda f=error_filename: self.log_message(f"⚠️ 已生成错误占位文件: {f}"))
                    self.root.after(0, lambda f=filename: self.update_file_status(f, "error"))
                
                # 更新进度
                self.processed_files += 1
                if processed_successfully:
                    self.success_files += 1
                else:
                    self.error_files += 1
                
                # 批量间隔
                if idx < total:
                    interval = self.config.get("batch_interval", 3)
                    self.root.after(0, lambda s=interval: self.log_message(f"⏳ 等待 {s} 秒后再处理下一个文件..."))
                    time.sleep(interval)
            
            # 完成处理
            self.root.after(0, lambda: self.update_progress(total, total))
            final_msg = f"✅ 批量处理完成！成功: {success_count}/{total}（跳过 {skipped} 个），日志: {batch_log_file}"
            self.root.after(0, lambda: self.log_message(final_msg))
            self.root.after(0, lambda: messagebox.showinfo("批量完成", final_msg))
            
            try:
                os.startfile(task_folder)
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"⚠️ 无法自动打开文件夹: {str(e)}"))
        except Exception as e:
            error_msg = f"❌ 批量处理异常: {str(e)}"
            self.root.after(0, lambda: self.log_message(error_msg))
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        finally:
            self.root.after(0, lambda: self.process_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.config_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: setattr(self, 'is_processing', False))
    
    def read_text_file(self, file_path, log_file):
        encodings = ['utf-8', 'gbk', 'shift_jis', 'utf-16', 'latin1']
        with open(log_file, 'a', encoding='utf-8') as lf:
            lf.write(f"\n尝试读取文件: {file_path}\n")
        
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                with open(log_file, 'a', encoding='utf-8') as lf:
                    lf.write(f"✅ 成功使用编码: {enc}\n")
                return content
            except UnicodeDecodeError:
                continue
            except Exception as e:
                with open(log_file, 'a', encoding='utf-8') as lf:
                    lf.write(f"编码 {enc} 出错: {str(e)}\n")
        
        raise Exception(f"无法用支持的编码读取文件: {', '.join(encodings)}")
    
    def call_llm_api(self, prompt, text_content, log_file):
        base_url = self.config["api_url"].rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        generate_url = f"{base_url}/chat/completions"
        
        headers = {"Content-Type": "application/json"}
        if self.config.get("api_key"):
            headers["Authorization"] = f"Bearer {self.config['api_key']}"
        
        # 处理系统预设，支持JSON格式
        preset_content = self.preset_text.get("1.0", tk.END).strip()
        system_prompt = preset_content
        
        try:
            # 尝试解析JSON格式的预设
            preset_json = json.loads(preset_content)
            if isinstance(preset_json, dict) and "system_prompt" in preset_json:
                system_prompt = preset_json["system_prompt"]
        except (json.JSONDecodeError, ValueError):
            pass  # 保持原始内容
        
        # 构建消息
        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt + "\n\n" + text_content})
        
        payload = {
            "model": self.config["selected_model"],
            "messages": messages,
            "stream": False
        }
        
        with open(log_file, 'a', encoding='utf-8') as lf:
            lf.write(f"\n[API Request] 发送请求到 {generate_url}\n")
        
        try:
            response = requests.post(
                generate_url,
                headers=headers,
                json=payload,
                timeout=self.config["timeout"]
            )
            response.raise_for_status()
            data = response.json()
            
            # 支持 OpenAI 格式
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
            else:
                content = str(data)
            
            with open(log_file, 'a', encoding='utf-8') as lf:
                lf.write(f"[API Response] 接收到 {len(content)} 字符\n")
            return content
        except Exception as e:
            with open(log_file, 'a', encoding='utf-8') as lf:
                lf.write(f"[API Error] {str(e)}\n")
            raise

if __name__ == "__main__":
    # 启动配置窗口
    root = tk.Tk()
    app = ConfigWindow(root)
    root.mainloop()
    
    # 加载配置并启动主程序
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        main_app = MainApplication(config)
        main_app.root.mainloop()
    else:
        messagebox.showerror("错误", "未找到配置文件 config.json，请先完成API配置。")