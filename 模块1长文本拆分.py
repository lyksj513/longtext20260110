import os
import re
import sys
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from typing import List

import tiktoken


# ================== 默认配置 ==================
DEFAULT_CHUNK_SIZE = 2500
DEFAULT_OVERLAP_RATE = 0.05
DEFAULT_MIN_CHUNK_RATIO = 0.2


# ================== 公共函数 ==================
def create_output_folders():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(current_dir, "OUT")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except Exception as e:
        print(f"警告: 无法使用tiktoken计算token，回退到字数统计。错误: {e}")
        return len(text)


def preserve_formatting(text: str) -> str:
    paragraphs = re.split(r'(\n\s*\n)', text)
    cleaned_paragraphs = []
    for para in paragraphs:
        if not para.strip():
            continue
        para = re.sub(r'[ \t]+', ' ', para)
        para = re.sub(r'([。！？.!?,;:；，：、])\s+', r'\1', para)
        para = re.sub(r'\s+([）】」』、。，！？；："\'])', r'\1', para)
        para = re.sub(r'([\(（【「『])\s+', r'\1', para)
        cleaned_paragraphs.append(para.strip())
    return '\n\n'.join([p for p in cleaned_paragraphs if p])


def find_sentence_boundaries(text: str) -> List[int]:
    boundaries = []
    lines = text.split('\n')
    current_pos = 0
    line_positions = []
    for line in lines:
        line_positions.append((current_pos, current_pos + len(line) + 1))
        current_pos += len(line) + 1

    paragraph_boundaries = []
    prev_was_empty = False
    for i, (start_pos, end_pos) in enumerate(line_positions):
        line_content = text[start_pos:end_pos-1]
        is_empty = not line_content.strip()
        if is_empty and not prev_was_empty:
            paragraph_boundaries.append(end_pos)
        prev_was_empty = is_empty

    for match in re.finditer(r'[。．！？\.\!\?]\s*', text):
        end_pos = match.end()
        start_pos = match.start()
        char_before = text[start_pos]
        if char_before == '.' and start_pos > 0:
            prev_char = text[start_pos-1]
            if prev_char.isupper() or prev_char.isdigit():
                if start_pos-2 >= 0 and text[start_pos-2] == '.':
                    continue
                if start_pos-2 < 0 or not text[start_pos-2].isalpha():
                    continue
            if start_pos >= 2 and text[start_pos-2:start_pos+1] in ['...', '…']:
                continue
        boundaries.append(end_pos)

    for pos in paragraph_boundaries:
        if pos not in boundaries:
            boundaries.append(pos)
    if len(text) not in boundaries:
        boundaries.append(len(text))
    return sorted(set(boundaries))


def find_optimal_boundary(text: str, target_pos: int, boundaries: List[int]) -> int:
    if not boundaries:
        return target_pos
    prev_boundaries = [b for b in boundaries if b <= target_pos]
    next_boundaries = [b for b in boundaries if b > target_pos]
    if prev_boundaries:
        return max(prev_boundaries)
    elif next_boundaries:
        return min(next_boundaries)
    else:
        return target_pos


# ================== 模式 A：Token 分块（v1）==================
def split_text_file_v1(file_path: str, output_folder: str, base_name: str, CHUNK_SIZE, OVERLAP_RATE, MIN_CHUNK_RATIO):
    encodings = ['utf-8', 'gbk', 'shift_jis', 'utf-16', 'latin1']
    text = None
    used_encoding = None
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                text = f.read()
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("无法用任何支持的编码读取文件")
    if not text.strip():
        raise ValueError("文件内容为空")

    text = preserve_formatting(text)
    total_tokens = count_tokens(text)
    chunks_dir = os.path.join(output_folder, f"{base_name}_chunks")
    metadata_dir = os.path.join(output_folder, "metadata")
    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(metadata_dir, exist_ok=True)

    boundaries = find_sentence_boundaries(text)
    overlap_tokens = int(CHUNK_SIZE * OVERLAP_RATE)
    min_chunk_tokens = max(200, int(CHUNK_SIZE * MIN_CHUNK_RATIO))
    chars_per_token = len(text) / (total_tokens or 1)

    current_pos = 0
    current_token_pos = 0
    chunk_num = 1
    chunks = []
    metadata = {
        'file_path': file_path,
        'chunk_size': CHUNK_SIZE,
        'overlap_rate': OVERLAP_RATE,
        'total_tokens': total_tokens,
        'total_chunks': 0,
        'chunks': []
    }

    while current_token_pos < total_tokens:
        target_end_token_pos = min(current_token_pos + CHUNK_SIZE, total_tokens)
        target_end_char_pos = int(target_end_token_pos * chars_per_token)
        optimal_end_pos = find_optimal_boundary(text, target_end_char_pos, boundaries)
        chunk_text = text[current_pos:optimal_end_pos]
        chunk_tokens = count_tokens(chunk_text)

        if chunk_tokens < min_chunk_tokens and chunk_num > 1:
            next_boundaries = [b for b in boundaries if b > optimal_end_pos]
            if next_boundaries:
                next_boundary = min(next_boundaries)
                chunk_text = text[current_pos:next_boundary]
                chunk_tokens = count_tokens(chunk_text)
                optimal_end_pos = next_boundary

        chunk_info = {
            'chunk_num': chunk_num,
            'start_pos': current_pos,
            'end_pos': optimal_end_pos,
            'text': chunk_text,
            'token_count': chunk_tokens,
        }
        chunks.append(chunk_info)

        chunk_file = os.path.join(chunks_dir, f"{base_name}_{chunk_num}.txt")
        with open(chunk_file, 'w', encoding='utf-8') as f:
            f.write(chunk_text)

        metadata['chunks'].append({
            'chunk_num': chunk_num,
            'file_path': os.path.relpath(chunk_file, output_folder),
            'token_count': chunk_tokens,
            'char_range': [chunk_info['start_pos'], chunk_info['end_pos']]
        })

        overlap_start_char = current_pos + int(max(0, (target_end_token_pos - overlap_tokens - current_token_pos)) * chars_per_token)
        next_start_boundary = find_optimal_boundary(text, overlap_start_char, boundaries)
        next_start_pos = max(optimal_end_pos, next_start_boundary)
        current_pos = next_start_pos
        current_token_pos = int(current_pos / chars_per_token)

        remaining_tokens = total_tokens - current_token_pos
        if remaining_tokens < min_chunk_tokens and remaining_tokens > 0:
            if chunks:
                remaining_text = text[current_pos:]
                chunks[-1]['text'] += "\n\n[合并的剩余内容]\n" + remaining_text
                chunks[-1]['end_pos'] = len(text)
                chunks[-1]['token_count'] = count_tokens(chunks[-1]['text'])
                chunk_file = os.path.join(chunks_dir, f"{base_name}_{chunk_num}.txt")
                with open(chunk_file, 'w', encoding='utf-8') as f:
                    f.write(chunks[-1]['text'])
                break

        chunk_num += 1

    metadata['total_chunks'] = len(chunks)
    metadata_file = os.path.join(metadata_dir, f"{base_name}_metadata.json")
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return chunks_dir, len(chunks)


# ================== 模式 B：章节分块（v2）==================
def detect_chapters(text):
    chapter_patterns = [
        r'^\s*(第?[零一二三四五六七八九十百\d]+[章节回篇幕场])\s*[:：\-—]?\s*.*$',
        r'^\s*(Chapter|Scene|Part|Act|Prologue|Epilogue|Appendix)\s+\d*[A-Za-z]?\s*:?.*$',
        r'^\s*(序幕|尾声|楔子|终章|后记|前言|引子|附录)\s*:?.*$',
        r'^\s*#{1,3}\s+(.+)$',
    ]
    lines = text.splitlines(keepends=True)
    chapters = []
    current_lines = []
    for line in lines:
        stripped = line.strip()
        is_chapter_start = any(re.match(pattern, stripped, re.IGNORECASE) for pattern in chapter_patterns)
        if is_chapter_start:
            if current_lines:
                chapters.append(''.join(current_lines))
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        chapters.append(''.join(current_lines))
    return chapters


def extract_title(chapter_text):
    first_line = chapter_text.split('\n')[0].strip()
    patterns = [
        r'^(第?[零一二三四五六七八九十百\d]+[章节回篇幕场]).*',
        r'^(Chapter|Scene|Part|Act|Prologue|Epilogue|Appendix)\s+\d*[A-Za-z]?.*',
        r'^(序幕|尾声|楔子|终章|后记|前言|引子|附录).*',
        r'^#{1,3}\s+(.+)',
    ]
    for pat in patterns:
        m = re.match(pat, first_line, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return "Unknown"


def sanitize_filename(s):
    return "".join(c for c in s if c.isalnum() or c in " _-").rstrip()


def split_text_file_v2(file_path: str, output_folder: str, base_name: str, max_tokens: int):
    # 尝试多种编码
    encodings = ['utf-8', 'gbk', 'shift_jis', 'utf-16', 'latin1']
    content = None
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        raise ValueError("无法用任何支持的编码读取文件")

    enc = tiktoken.get_encoding("cl100k_base")
    chapters = detect_chapters(content)
    titles = [extract_title(ch) for ch in chapters]

    chunks = []
    chunk_ranges = []
    current_chunk = []
    current_tokens = 0
    start_i = 0

    for i, chapter in enumerate(chapters):
        tok = len(enc.encode(chapter))
        if tok > max_tokens:
            if current_chunk:
                chunks.append(''.join(current_chunk))
                chunk_ranges.append((titles[start_i], titles[i-1]))
                current_chunk = []
                current_tokens = 0
            chunks.append(chapter)
            chunk_ranges.append((titles[i], titles[i]))
            start_i = i + 1
        else:
            if current_tokens + tok <= max_tokens:
                if not current_chunk:
                    start_i = i
                current_chunk.append(chapter)
                current_tokens += tok
            else:
                chunks.append(''.join(current_chunk))
                chunk_ranges.append((titles[start_i], titles[i-1]))
                current_chunk = [chapter]
                current_tokens = tok
                start_i = i

    if current_chunk:
        chunks.append(''.join(current_chunk))
        chunk_ranges.append((titles[start_i], titles[-1]))

    # 保存
    for i, (chunk, (start, end)) in enumerate(zip(chunks, chunk_ranges), 1):
        safe_start = sanitize_filename(str(start))
        safe_end = sanitize_filename(str(end))
        range_str = safe_start if start == end else f"{safe_start}-{safe_end}"
        filename = f"{base_name}_chunk_{i:02d}({range_str}).txt"
        with open(os.path.join(output_folder, filename), 'w', encoding='utf-8') as f:
            f.write(chunk)

    return output_folder, len(chunks)


# ================== GUI 主程序 ==================
class UnifiedSplitGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("文本分块工具 -作者lovelycateman/www.52pojie.cn")
        self.root.geometry("520x460")  # 增加高度以容纳两行信息
        self.root.resizable(False, False)

        self.file_path = None
        self.mode = tk.StringVar(value="v1")  # "v1" 或 "v2"

        # 使用 grid 布局
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 文件选择
        tk.Label(root, text="请选择要分块的文本文件：").grid(row=0, column=0, sticky='w', padx=20, pady=(15, 5))
        self.btn_select = tk.Button(root, text="选择文件", command=self.select_file, width=15)
        self.btn_select.grid(row=1, column=0, sticky='w', padx=20, pady=5)

        # 文件名标签（可换行）
        self.label_file = tk.Label(root, text="未选择文件", fg="gray", wraplength=480, justify='left')
        self.label_file.grid(row=2, column=0, sticky='w', padx=20, pady=2)

        # Token 数量标签（单独一行）
        self.label_token = tk.Label(root, text="", fg="gray")
        self.label_token.grid(row=3, column=0, sticky='w', padx=20, pady=(0, 10))

        # 模式选择
        tk.Label(root, text="请选择分块模式：").grid(row=4, column=0, sticky='w', padx=20, pady=(5, 5))
        mode_frame = tk.Frame(root)
        mode_frame.grid(row=5, column=0, sticky='w', padx=20, pady=5)
        tk.Radiobutton(mode_frame, text="模式 A：Token 精细分块（保留句子边界）", variable=self.mode, value="v1", command=self.toggle_mode).pack(anchor='w')
        tk.Radiobutton(mode_frame, text="模式 B：按章节分块（保持章节完整）", variable=self.mode, value="v2", command=self.toggle_mode).pack(anchor='w')

        # 参数容器
        self.param_frame = tk.Frame(root)
        self.param_frame.grid(row=6, column=0, sticky='w', padx=20, pady=10)

        self.create_v1_params()

        # 开始按钮（始终存在）
        self.btn_start = tk.Button(root, text="开始分块", command=self.start_split, state='disabled', width=15)
        self.btn_start.grid(row=7, column=0, sticky='w', padx=20, pady=15)

    def select_file(self):
        path = filedialog.askopenfilename(
            title="请选择要处理的文本文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if path:
            self.file_path = path
            filename = os.path.basename(path)

            try:
                encodings = ['utf-8', 'gbk', 'shift_jis', 'utf-16', 'latin1']
                text = None
                for encoding in encodings:
                    try:
                        with open(path, 'r', encoding=encoding) as f:
                            text = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                if text is None:
                    raise ValueError("无法用任何支持的编码读取文件")

                # 更新文件名（允许换行）
                self.label_file.config(text=filename, fg="black")

                # 尝试计算 token
                try:
                    total_tokens = count_tokens(text)
                    self.label_token.config(text=f"总 Token 数量: {total_tokens:,}", fg="black")
                except Exception as e:
                    self.label_token.config(text=f"Token 计算失败: {e}", fg="orange")

                self.btn_start.config(state='normal')

            except Exception as e:
                self.label_file.config(text=filename, fg="red")
                self.label_token.config(text=f"文件读取失败: {e}", fg="red")
                self.btn_start.config(state='normal')  # 仍启用按钮，便于重试或强制处理

    def toggle_mode(self):
        for widget in self.param_frame.winfo_children():
            widget.destroy()
        if self.mode.get() == "v1":
            self.create_v1_params()
        else:
            self.create_v2_params()

    def create_v1_params(self):
        frame = self.param_frame
        tk.Label(frame, text="目标 Token 大小:").grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.entry_chunk = tk.Entry(frame, width=12)
        self.entry_chunk.insert(0, str(DEFAULT_CHUNK_SIZE))
        self.entry_chunk.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(frame, text="重叠率 (0～1):").grid(row=1, column=0, sticky='e', padx=5, pady=3)
        self.entry_overlap = tk.Entry(frame, width=12)
        self.entry_overlap.insert(0, str(DEFAULT_OVERLAP_RATE))
        self.entry_overlap.grid(row=1, column=1, padx=5, pady=3)

        tk.Label(frame, text="最小区块比例 (0～1):").grid(row=2, column=0, sticky='e', padx=5, pady=3)
        self.entry_min_ratio = tk.Entry(frame, width=12)
        self.entry_min_ratio.insert(0, str(DEFAULT_MIN_CHUNK_RATIO))
        self.entry_min_ratio.grid(row=2, column=1, padx=5, pady=3)

    def create_v2_params(self):
        frame = self.param_frame
        tk.Label(frame, text="最大 Token 上限:").grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.entry_max_tok = tk.Entry(frame, width=12)
        self.entry_max_tok.insert(0, "5000")
        self.entry_max_tok.grid(row=0, column=1, padx=5, pady=3)

    def validate_inputs(self):
        mode = self.mode.get()
        if mode == "v1":
            try:
                chunk = int(self.entry_chunk.get())
                overlap = float(self.entry_overlap.get())
                min_ratio = float(self.entry_min_ratio.get())
                if chunk <= 0:
                    raise ValueError("Chunk size 必须 > 0")
                if not (0 <= overlap < 1):
                    raise ValueError("重叠率应在 [0, 1) 范围内")
                if not (0 < min_ratio <= 1):
                    raise ValueError("最小区块比例应在 (0, 1] 范围内")
                return {"mode": "v1", "params": (chunk, overlap, min_ratio)}
            except ValueError as e:
                messagebox.showerror("输入错误", f"参数格式错误：{e}")
                return None
        else:
            try:
                max_tok = int(self.entry_max_tok.get())
                if max_tok <= 0:
                    raise ValueError("最大 Token 数必须 > 0")
                return {"mode": "v2", "params": (max_tok,)}
            except ValueError as e:
                messagebox.showerror("输入错误", f"参数格式错误：{e}")
                return None

    def start_split(self):
        if not self.file_path:
            messagebox.showwarning("警告", "请先选择文件！")
            return
        config = self.validate_inputs()
        if not config:
            return

        self.root.destroy()

        try:
            out_dir = create_output_folders()
            base_name = os.path.splitext(os.path.basename(self.file_path))[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_folder = os.path.join(out_dir, f"{timestamp}_{base_name}")
            os.makedirs(task_folder, exist_ok=True)

            if config["mode"] == "v1":
                CHUNK_SIZE, OVERLAP_RATE, MIN_CHUNK_RATIO = config["params"]
                chunks_dir, total_chunks = split_text_file_v1(
                    self.file_path, task_folder, base_name,
                    CHUNK_SIZE, OVERLAP_RATE, MIN_CHUNK_RATIO
                )
            else:
                max_tokens, = config["params"]
                chunks_dir, total_chunks = split_text_file_v2(
                    self.file_path, task_folder, base_name, max_tokens
                )

            messagebox.showinfo("完成", f"✅ 分块成功！\n共 {total_chunks} 个区块\n保存于:\n{task_folder}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("错误", f"分块失败：\n{str(e)}")


def main():
    root = tk.Tk()
    app = UnifiedSplitGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
