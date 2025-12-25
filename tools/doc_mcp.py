"""
Doc Keeper MCP Tools (V2.0)

核心理念:
- 结构化管理: 基于 DOM 树而非纯文本行号。
- 职责分离: 元数据与内容分离，读写分离。
- 安全优先: 双重锁验证，强制快照，禁止隐式覆盖。

Author: Antigravity Agent
"""
import os
import shutil
import difflib
import yaml
import json
import re
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# 初始化 FastMCP 服务器
mcp = FastMCP("DocKeeperTools")

# 基础配置
# CWD 由 Router 设置为目标知识库目录，直接使用当前目录
KNOWLEDGE_ROOT = "."
HISTORY_DIR = os.path.join(KNOWLEDGE_ROOT, ".history")

# --- 内部辅助函数 ---

def _validate_path(path: str) -> str:
    """验证路径安全性并返回绝对路径。"""
    # 移除可能的前导斜杠和空白
    clean_path = path.strip().lstrip("/\\")
    
    # 防止路径遍历
    if ".." in clean_path:
        raise ValueError(f"拒绝访问: 路径包含非法字符 '..' ({clean_path})")
    
    abs_root = os.path.abspath(KNOWLEDGE_ROOT)
    abs_target = os.path.abspath(os.path.join(KNOWLEDGE_ROOT, clean_path))
    
    if not abs_target.startswith(abs_root):
        raise ValueError(f"拒绝访问: 路径 '{clean_path}' 超出知识库范围。")
    
    return abs_target

def _ensure_history_dir(file_path: str):
    """确保指定文件的 .history 目录存在。"""
    safe_name = file_path.replace("/", "_").replace("\\", "_")
    target_dir = os.path.join(HISTORY_DIR, safe_name)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir

def _create_snapshot(file_path: str, abs_path: str):
    """创建文件快照。"""
    if os.path.exists(abs_path):
        history_dir = _ensure_history_dir(file_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_path = os.path.join(history_dir, f"{timestamp}.snap")
        shutil.copy2(abs_path, snap_path)
        return snap_path
    return None

def _parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """解析 Frontmatter，返回 (meta, body)。"""
    if content.startswith("---"):
        try:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                yaml_content = parts[1]
                body = parts[2]
                meta = yaml.safe_load(yaml_content) or {}
                return meta, body
        except Exception:
            pass
    return {}, content

def _build_frontmatter(meta: Dict) -> str:
    """构建 Frontmatter 字符串。"""
    # 确保 last_updated 存在
    if "last_updated" not in meta:
        meta["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    
    yaml_str = yaml.dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{yaml_str}\n---\n"

def _smart_resolve_path(path_query: str) -> str:
    """
    智能路径解析。
    1. 优先尝试精确匹配。
    2. 如果失败，扫描所有子目录寻找同名文件。
    """
    # 1. 精确匹配
    try:
        abs_path = _validate_path(path_query)
        if os.path.exists(abs_path):
            return path_query
    except ValueError:
        pass # 可能会因为 .. 报错，这里忽略
        
    # 2. 模糊查找 (只匹配文件名)
    target_name = os.path.basename(path_query)
    candidates = []
    
    for root, _, files in os.walk(KNOWLEDGE_ROOT):
        # 跳过 .history
        if ".history" in root:
            continue
            
        if target_name in files:
            rel_dir = os.path.relpath(root, KNOWLEDGE_ROOT)
            if rel_dir == ".":
                candidates.append(target_name)
            else:
                candidates.append(os.path.join(rel_dir, target_name).replace("\\", "/"))
    
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        # 存在歧义，抛出详细错误供模型选择
        msg = f"路径 '{path_query}' 不明确，找到多个匹配项:\n"
        for c in candidates:
            # 尝试读取 Description 增强信息 (这里简单处理，实际可复用 list 逻辑)
            msg += f"- {c}\n"
        raise ValueError(msg)
        
    # 没找到，如果是创建操作，可能就是新路径；如果是读取，抛出不存在
    # 这里我们返回原值，交给调用者判断是否存在
    return path_query

def _get_outline_tree(content: str) -> List[Dict]:
    """
    解析 Markdown 标题树。
    返回: [{"id": "1", "title": "Overview", "level": 1, "children": []}, ...]
    这里为了简单，返回扁平列表，但包含 level 信息供逻辑处理。
    """
    lines = content.splitlines()
    outline = []
    counters = [0] * 7 # H1-H6 计数器
    
    for i, line in enumerate(lines):
        match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            
            # 更新计数器
            counters[level] += 1
            # 重置子级计数器
            for j in range(level + 1, 7):
                counters[j] = 0
                
            # 生成 ID (如 1.2.1)
            # 只取有效层级
            current_id_parts = [str(c) for c in counters[1:level+1]]
            node_id = ".".join(current_id_parts)
            
            outline.append({
                "id": node_id,
                "title": title,
                "level": level,
                "line_start": i + 1 # 1-based line number for internal ref (not exposed)
            })
            
    return outline

# --- MCP Tools ---

@mcp.tool()
def list_knowledge_catalog(category: Optional[str] = None, detail: bool = False) -> str:
    """
    列出知识库目录结构。
    
    Args:
        category: (可选) 按分类过滤，如 'libs', 'python'。
        detail: (可选) 是否返回 Description，默认为 False (极简模式)。
    """
    catalog = []
    
    for root, dirs, files in os.walk(KNOWLEDGE_ROOT):
        # 过滤隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if not file.endswith('.md'):
                continue
                
            rel_path = os.path.join(root, file)
            display_path = os.path.relpath(rel_path, KNOWLEDGE_ROOT).replace("\\", "/")
            
            # 读取元数据
            meta = {}
            try:
                with open(rel_path, 'r', encoding='utf-8') as f:
                    # 安全读取前 50 行
                    lines = f.readlines()[:50]
                    meta, _ = _parse_frontmatter("".join(lines))
            except Exception:
                pass
            
            # 过滤
            file_cat = meta.get('category', 'unknown')
            if category and category.lower() not in file_cat.lower():
                continue
                
            item = {
                "path": display_path,
                "title": meta.get('title', file),
                "category": file_cat
            }
            
            if detail:
                item['description'] = meta.get('description', 'No description.')
                item['tags'] = meta.get('tags', [])
                
            catalog.append(item)
            
    return json.dumps(catalog, indent=2, ensure_ascii=False)

@mcp.tool()
def get_file_outline(path: str) -> str:
    """
    获取指定文件的大纲结构和元数据。
    这是修改文件前的必经之路。
    
    Args:
        path: 文件路径或文件名 (支持智能查找)。
    """
    try:
        resolved_path = _smart_resolve_path(path)
        abs_path = _validate_path(resolved_path)
        
        if not os.path.exists(abs_path):
            return f"错误: 文件 '{resolved_path}' 不存在。"
            
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        meta, _ = _parse_frontmatter(content)
        structure = _get_outline_tree(content)
        
        result = {
            "path": resolved_path,
            "metadata": meta,
            "structure": structure
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
        
    except ValueError as e:
        return f"路径错误: {str(e)}"
    except Exception as e:
        return f"读取失败: {str(e)}"

@mcp.tool()
def create_knowledge(title: str, category: str, tags: str, description: str, name: Optional[str] = None) -> str:
    """
    创建新文档（仅元数据骨架，内容为空）。
    
    ⚠️ 重要：每个用户请求只应调用此工具 **一次**。重复调用会创建多个文件！
    
    Args:
        title: 文档标题（会成为 H1 标题）。
        category: 分类目录（如 libs, tools, tests）。决定文件存放的子目录。
        tags: 标签，逗号分隔（如 "react, hooks"）。
        description: 一句话描述文档内容。
        name: 文件名（可选，不含路径和后缀）。
              - 若不传：自动从 title 生成 slug
              - 若传入：直接使用该名称
    
    路径规则（简化版）：
        最终路径 = {category}/{name}.md
        
        示例：
        - category="libs", name=None, title="React Hooks" → libs/react_hooks.md
        - category="tests", name="api" → tests/api.md
        - category="tools", name="docker" → tools/docker.md
    
    Returns:
        成功消息或错误信息。
    """
    try:
        # 处理标签列表
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        
        # 确定文件名
        if name:
            # 清理：移除可能的路径分隔符和后缀
            clean_name = name.strip().replace("/", "_").replace("\\", "_")
            if clean_name.endswith(".md"):
                clean_name = clean_name[:-3]
        else:
            # 从 title 生成 slug
            clean_name = title.lower().replace(" ", "_").replace("/", "_")
        
        # 构建路径：category/name.md
        target_path = f"{category}/{clean_name}.md"
            
        abs_path = _validate_path(target_path)
        
        if os.path.exists(abs_path):
            return f"错误: 文件 '{target_path}' 已存在。请使用 update_knowledge_section 更新。"
            
        # 构建标准元数据
        meta = {
            "title": title,
            "category": category,
            "tags": tag_list,
            "description": description,
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }
        
        content = _build_frontmatter(meta)
        content += f"\n# {title}\n\n"
        
        # 写入文件
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return f"成功创建文档: {target_path}\n接下来请使用 get_file_outline 查看结构，并使用 update_knowledge_section 填充内容。"
        
    except Exception as e:
        return f"创建失败: {str(e)}"

@mcp.tool()
def update_knowledge_section(path: str, node_id: str, expected_title: str, new_content: str) -> str:
    """
    更新文档的特定章节。
    
    Args:
        path: 文件路径。
        node_id: 目标章节的 ID (例如 "2.1")。如果要追加到文末，使用 "APPEND"。
                 如果要更新正文(Frontmatter和第一个标题之间)，可尝试使用 "0" (实验性)。
        expected_title: 双重锁验证，必须匹配目标章节的标题。
        new_content: 新的 Markdown 内容 (包含该标题及其子内容)。
    """
    try:
        resolved_path = _smart_resolve_path(path)
        abs_path = _validate_path(resolved_path)
        
        if not os.path.exists(abs_path):
            return f"错误: 文件 '{resolved_path}' 不存在。"
            
        # 1. 创建快照
        _create_snapshot(resolved_path, abs_path)
        
        # 2. 读取并解析
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 3. 处理 APPEND 模式
        if node_id == "APPEND":
            with open(abs_path, 'a', encoding='utf-8') as f:
                f.write("\n\n" + new_content)
            return "成功追加内容到文档末尾。"

        # 4. 解析结构进行定位
        # 这里我们需要更精细的行号定位，所以不仅要有 ID，还要有行范围
        lines = content.splitlines()
        update_start = -1
        update_end = -1
        
        # 简易的大纲解析器 (复用逻辑但需要行号)
        counters = [0] * 7
        target_found = False
        current_level = 0
        
        for i, line in enumerate(lines):
            match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                
                # 如果已经找到了目标，且当前标题级别 <= 目标级别，说明目标块结束了
                if target_found:
                    if level <= current_level:
                        update_end = i
                        break
                
                # 更新计数器
                counters[level] += 1
                for j in range(level + 1, 7): counters[j] = 0
                
                # 生成 ID
                current_id = ".".join([str(c) for c in counters[1:level+1]])
                
                # 检查匹配
                if current_id == node_id:
                    # 双重锁验证 (忽略大小写和空格)
                    if expected_title.lower().strip() not in title.lower().strip():
                        return f"双重锁验证失败: ID {node_id} 处的标题是 '{title}'，与期望的 '{expected_title}' 不符。请重新检查大纲。"
                    
                    target_found = True
                    current_level = level
                    update_start = i
        
        if not target_found:
            return f"未找到 ID 为 {node_id} 的章节。"
            
        if update_end == -1: # 目标是最后一个章节
            update_end = len(lines)
            
        # 5. 执行替换
        # 保留 update_start 之前的，替换 update_start 到 update_end，保留 update_end 之后的
        new_lines = new_content.splitlines()
        final_lines = lines[:update_start] + new_lines + lines[update_end:]
        
        final_content = "\n".join(final_lines)
        if content.endswith("\n") and not final_content.endswith("\n"):
            final_content += "\n"
            
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
            
        return f"成功更新章节 {node_id} ({expected_title})。\n影响行数: {update_end - update_start} -> {len(new_lines)}"
        
    except ValueError as e:
        return f"路径错误: {str(e)}"
    except Exception as e:
        import traceback
        return f"更新失败: {str(e)}\n{traceback.format_exc()}"

@mcp.tool()
def view_doc_changes(path: str) -> str:
    """查看文档的最近变更 (Diff)。"""
    try:
        resolved_path = _smart_resolve_path(path)
        abs_path = _validate_path(resolved_path)
        
        history_dir = _ensure_history_dir(resolved_path)
        snaps = sorted([f for f in os.listdir(history_dir) if f.endswith('.snap')])
        
        if not snaps:
            return "未找到历史快照 (初始版本)。"
            
        latest_snap = os.path.join(history_dir, snaps[-1])
        
        with open(latest_snap, 'r', encoding='utf-8') as f:
            old_lines = f.readlines()
        with open(abs_path, 'r', encoding='utf-8') as f:
            new_lines = f.readlines()
            
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"快照 ({snaps[-1]})",
            tofile="当前版本",
            lineterm=""
        )
        
        return "".join(diff)
        
    except Exception as e:
        return f"查看变更失败: {str(e)}"

if __name__ == "__main__":
    mcp.run()


