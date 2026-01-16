import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from collections import defaultdict
import platform

def detect_pattern(filename):
    """ 
    从文件名中智能检测命名模式并提取信息。
    支持任意格式：aaaNbbb.txt，其中：
      - aaa: 前缀（任意内容）
      - N: 连续数字
      - bbb: 后缀（任意内容）
      - 必须以 .txt 结尾
    
    返回: (pattern_key, prefix, number, suffix) 或 None
    其中 pattern_key 用于区分不同的命名规则组
    """
    # 去掉 .txt 扩展名
    if not filename.endswith('.txt'):
        return None
    
    name_without_ext = filename[:-4]
    
    # 查找所有连续数字的位置
    # 使用正则找出所有数字序列
    digit_matches = list(re.finditer(r'\d+', name_without_ext))
    
    if not digit_matches:
        return None
    
    # 尝试每个数字序列作为分隔符
    # 优先使用最后一个数字序列（更符合常见命名习惯）
    for match in reversed(digit_matches):
        start, end = match.span()
        number = int(match.group())
        
        prefix = name_without_ext[:start]
        suffix = name_without_ext[end:]
        
        # 如果前缀为空，跳过这个数字（数字不能在开头）
        if not prefix:
            continue
        
        # pattern_key 是前缀和后缀的组合模板，用于识别同一命名规则的文件
        # 例如：AAA_chunk_{}BBB 或 test{}_result
        pattern_key = f"{prefix}{{N}}{suffix}"
        
        return pattern_key, prefix, number, suffix
    
    return None

def main():
    # 创建隐藏的主窗口
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 第一个提示：开源信息
    messagebox.showinfo("猫仔一键合并工具", "猫仔一键合并工具由lovelycateman/www.52pojie.cn开源，人人为我，我为人人")
    
    # 第二个提示：选择文件夹说明
    messagebox.showinfo("提示", "请选择你需要合并文件的文件夹")

    # 选择文件夹
    folder_path = filedialog.askdirectory(title="请选择包含处理后txt文件的文件夹")
    if not folder_path:
        print("未选择文件夹，程序退出。")
        return

    # 获取所有文件
    files = os.listdir(folder_path)

    # 存储解析成功的文件信息
    # 格式：{pattern_key: [(number, filename, prefix, suffix), ...]}
    pattern_groups = defaultdict(list)

    for f in files:
        result = detect_pattern(f)
        if result:
            pattern_key, prefix, number, suffix = result
            pattern_groups[pattern_key].append((number, f, prefix, suffix))

    if not pattern_groups:
        print("未找到符合命名规则的 .txt 文件！")
        print("支持的格式示例：")
        print("  - AAA_chunk_001BBB.txt")
        print("  - test1result.txt, test2result.txt")
        print("  - file_1.txt, file_2.txt")
        print("  - 任何包含数字的 .txt 文件")
        return

    print(f"\n检测到 {len(pattern_groups)} 种不同的命名模式：\n")
    
    # 对每种命名模式分别处理
    for pattern_idx, (pattern_key, items) in enumerate(pattern_groups.items(), 1):
        # 按数字排序
        items.sort(key=lambda x: x[0])
        
        # 获取该组的统一前缀和后缀（从第一个文件获取）
        _, _, group_prefix, group_suffix = items[0]
        
        print(f"模式 {pattern_idx}: {pattern_key}")
        print(f"  文件数量: {len(items)}")
        print(f"  编号范围: {items[0][0]} - {items[-1][0]}")
        
        # 构建输出内容
        output_lines = []
        for number, filename, prefix, suffix in items:
            paragraph_num = f"{number:03d}"  # 三位数格式
            filepath = os.path.join(folder_path, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
            except Exception as e:
                print(f"  ⚠️  读取文件 {filename} 出错：{e}")
                content = "[读取失败]"
            
            output_lines.append(f"【段落{paragraph_num}】")
            output_lines.append(content)
            output_lines.append("----")

        # 去掉最后一个分隔符
        if output_lines and output_lines[-1] == "----":
            output_lines.pop()

        # 生成输出文件名
        # 保持原来的命名规则，只在末尾添加 _zong
        output_filename = f"{group_prefix}{group_suffix}_zong.txt"
        
        output_path = os.path.join(folder_path, output_filename)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as out_file:
                out_file.write('\n'.join(output_lines))
            
            file_numbers = [num for num, _, _, _ in items]
            print(f"  ✅ 已生成: {output_filename}")
            
            if len(items) != (max(file_numbers) - min(file_numbers) + 1):
                print(f"  ℹ️  注意：编号不连续，实际合并 {len(items)} 个文件")
        except Exception as e:
            print(f"  ❌ 无法写入输出文件 {output_filename}：{e}")
        
        print()  # 空行分隔不同模式

    print("=" * 50)
    print("处理完成！")

    # 自动打开结果所在文件夹（跨平台）
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(folder_path)
        elif system == "Darwin":  # macOS
            os.system(f'open "{folder_path}"')
        else:  # Linux
            os.system(f'xdg-open "{folder_path}"')
    except Exception as e:
        print(f"未能自动打开文件夹：{e}")
    
    print("\n" + "=" * 50)
    print("程序继续运行中，可以继续处理其他文件夹...")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    # 循环运行，允许用户持续处理多个文件夹
    while True:
        main()
        print("\n按 Enter 键继续处理其他文件夹，或输入 'q' 退出程序...")
        user_input = input().strip().lower()
        if user_input == 'q':
            print("程序已退出。")
            break
        print("\n" + "=" * 50 + "\n")
