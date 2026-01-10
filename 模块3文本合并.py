import os
import re
import tkinter as tk
from tkinter import filedialog
from collections import defaultdict
import platform

def extract_info(filename):
    """ 从文件名中提取前缀 AAA、数字 N 和后缀 BBB。
    匹配格式：AAA_chunk_NBBB.txt
    要求：
      - AAA 至少一个字符（非下划线开头？但这里不限制）
      - N 是连续数字
      - BBB 可以是任意字符（包括空），但整个文件名必须以 .txt 结尾
    返回 (prefix, n) 或 None（不匹配则返回 None）
    """
    # 正则解释：
    # ^(.*?) -> 非贪婪匹配前缀 AAA
    # _chunk_ -> 固定字符串
    # (\d+) -> 捕获数字 N
    # (.*?) -> 非贪婪匹配 BBB（可能为空）
    # \.txt$ -> 以 .txt 结尾
    pattern = r'^(.*?)_chunk_(\d+)(.*?)\.txt$'
    match = re.match(pattern, filename)
    if match:
        prefix = match.group(1)
        n = int(match.group(2))
        # 注意：我们不再使用 BBB，只关心 prefix 和 n
        # 但为了区分不同组，应把 AAA + BBB 作为整体前缀？还是仅 AAA？
        # 根据你的描述“AAA 和 BBB 可以是任何内容”，但合并逻辑应基于“同一原始文件拆分”
        # 通常，AAA 是主名，BBB 是附加标识（如时间戳），但若 BBB 不同，可能属于不同批次
        #
        # 然而你要求“所有名字为 AAA_chunk_NBBB.txt 的文件汇总”，
        # 并未说明是否按 AAA 分组。但从原逻辑看，应按“相同 AAA”分组合并。
        #
        # 所以我们只用 AAA 作为分组依据（即 group_key = AAA）
        return prefix, n
    return None

def main():
    # 创建隐藏的主窗口
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 选择文件夹
    folder_path = filedialog.askdirectory(title="请选择包含处理后txt文件的文件夹")
    if not folder_path:
        print("未选择文件夹，程序退出。")
        return

    # 获取所有文件
    files = os.listdir(folder_path)

    # 存储解析成功的文件信息
    file_info_list = []
    prefixes = set()

    for f in files:
        info = extract_info(f)
        if info:
            prefix, n = info
            file_info_list.append((prefix, n, f))
            prefixes.add(prefix)

    if not file_info_list:
        print("未找到符合 AAA_chunk_NBBB.txt 命名规则的文件！")
        return

    # 按前缀（AAA）分组
    grouped = defaultdict(list)
    for prefix, n, filename in file_info_list:
        grouped[prefix].append((n, filename))

    # 对每组进行处理
    for prefix, items in grouped.items():
        # 按 n 排序
        items.sort(key=lambda x: x[0])
        output_lines = []
        for n, filename in items:
            paragraph_num = f"{n:03d}"  # 三位数格式
            filepath = os.path.join(folder_path, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
            except Exception as e:
                print(f"读取文件 {filename} 出错：{e}")
                content = "[读取失败]"
            output_lines.append(f"【段落{paragraph_num}】")
            output_lines.append(content)
            output_lines.append("----")

        # 去掉最后一个分隔符（可选）
        if output_lines and output_lines[-1] == "----":
            output_lines.pop()

        # 写入输出文件
        output_filename = f"{prefix}_zong_out.txt"
        output_path = os.path.join(folder_path, output_filename)
        try:
            with open(output_path, 'w', encoding='utf-8') as out_file:
                out_file.write('\n'.join(output_lines))
            print(f"✅ 已生成合并文件：{output_path}")
        except Exception as e:
            print(f"❌ 无法写入输出文件 {output_filename}：{e}")

    print("处理完成！")

    # >>> 新增：自动打开结果所在文件夹（跨平台）<<<
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

if __name__ == "__main__":
    main()