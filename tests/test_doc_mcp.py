"""
Doc MCP 工具测试脚本 (V2.0)

测试新版工具集：
1. create_knowledge (元数据插值, 自动路径)
2. get_file_outline (结构化解析)
3. update_knowledge_section (块级更新, 双重锁)
4. list_knowledge_catalog (detail 参数)
"""
import asyncio
import os
import sys
import shutil
import tempfile
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def run_doc_mcp_tests(client, test_dir: str):
    """执行 V2 工具集测试"""
    print("✅ doc_mcp Server 已连接")
    
    # 1. 测试 create_knowledge
    print("\n" + "=" * 60)
    print("1. 测试 create_knowledge (多种路径策略)")
    print("=" * 60)
    
    # 1.1 自动生成路径 (category/slug.md)
    res1 = await client.call_tool(
        "create_knowledge",
        {
            "title": "React Hooks",
            "category": "libs",
            "tags": "react, frontend",
            "description": "Introduction to React Hooks."
        }
    )
    print(f"1.1 自动生成: {res1}")
    
    # 1.2 指定文件名 (category/filename)
    res2 = await client.call_tool(
        "create_knowledge",
        {
            "title": "FastAPI Guide",
            "category": "backend", 
            "tags": "python, api", 
            "description": "FastAPI basics.",
            "filename": "fastapi_guide.md"
        }
    )
    print(f"1.2 指定文件名: {res2}")
    
    # 1.3 指定完整路径
    res3 = await client.call_tool(
        "create_knowledge",
        {
            "title": "Project Config",
            "category": "config", 
            "tags": "settings", 
            "description": "Global settings.",
            "filename": "core/settings.md"
        }
    )
    print(f"1.3 指定完整路径: {res3}")

    # 1.4 测试重复创建 (应失败)
    res4 = await client.call_tool(
        "create_knowledge",
        {
            "title": "React Hooks", 
            "category": "libs", 
            "tags": "retry", 
            "description": "Retry..."
        }
    )
    print(f"1.4 重复创建: {res4}") # 期望：错误提示

    # 2. 测试 update_knowledge_section (填充内容)
    print("\n" + "=" * 60)
    print("2. 测试 update_knowledge_section (块级更新)")
    print("=" * 60)
    
    # 先填充初始内容 (使用 APPEND)
    initial_content = """## Core Hooks
### useState
State management.
### useEffect
Side effects.
"""
    await client.call_tool(
        "update_knowledge_section",
        {
            "path": "libs/react_hooks.md",
            "node_id": "APPEND",
            "expected_title": "APPEND",
            "new_content": initial_content
        }
    )
    print("2.1 已追加初始内容")
    
    # 3. 测试 get_file_outline
    print("\n" + "=" * 60)
    print("3. 测试 get_file_outline (结构解析)")
    print("=" * 60)
    outline = {}
    try:
        outline_json = await client.call_tool("get_file_outline", {"path": "libs/react_hooks.md"})
        outline = json.loads(outline_json)
        print("3.1 结构树:")
        for node in outline.get("structure", []):
            print(f"    {node['id']}: {node['title']} (L{node.get('level')})")
    except:
        print(f"解析失败: {outline_json}")

    # 4. 测试 update_knowledge_section (修改特定块)
    print("\n" + "=" * 60)
    print("4. 测试 update_knowledge_section (双重锁修改)")
    print("=" * 60)
    
    # 4.1 修改 2.1 (useState) -> 期望成功
    # 注意: 根据前面 APPEND 的内容，Core Hooks 是 H2 (ID可能为 1)，useState 是 H3 (ID可能为 1.1)
    # 具体 ID 取决于 get_file_outline 的结果。根据上面生成的 markdown:
    # # React Hooks (H1) -> ID 1
    # ## Core Hooks (H2) -> ID 1.1 ? 不对，create 生成了 # Title
    # 让我们假设 create 生成了 # Title。APPEND 追加了 ## Core Hooks。
    # 结构应该是:
    # 1: React Hooks (H1)
    # 1.1: Core Hooks (H2)
    # 1.1.1: useState (H3)
    # 1.1.2: useEffect (H3)
    
    # 我们尝试更新 useState (需先确认 ID，这里模拟盲猜，可能会失败，真实场景 Agent 会先读 Outline)
    # 为了自动化测试，我们解析刚才的 output
    target_id = None
    if isinstance(outline, dict):
        for node in outline.get("structure", []):
            if "useState" in node["title"]:
                target_id = node["id"]
                break
    
    if target_id:
        print(f"4.1 尝试更新 ID {target_id} (useState)...")
        res_update = await client.call_tool(
            "update_knowledge_section",
            {
                "path": "libs/react_hooks.md", 
                "node_id": target_id,
                "expected_title": "useState",
                "new_content": "### useState\n**Updated** state management content."
            }
        )
        print(f"结果: {res_update}")
    else:
        print("❌ 未找到目标节点 ID，跳过更新测试")

    # 4.2 双重锁失败测试
    print("\n4.2 测试双重锁拦截:")
    res_lock = await client.call_tool(
        "update_knowledge_section",
        {
            "path": "libs/react_hooks.md", 
            "node_id": target_id if target_id else "1.1.1",
            "expected_title": "WRONG TITLE",
            "new_content": "### Hack\n..."
        }
    )
    print(f"结果: {res_lock}")

    # 5. 测试 view_doc_changes
    print("\n" + "=" * 60)
    print("5. 测试 view_doc_changes")
    print("=" * 60)
    res_diff = await client.call_tool("view_doc_changes", {"path": "libs/react_hooks.md"})
    print(f"变更: \n{res_diff}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


async def test_doc_mcp():
    """主测试入口"""
    print("=" * 80)
    print("Doc MCP V2 工具测试")
    print("=" * 80)
    
    test_dir = tempfile.mkdtemp(prefix="doc_mcp_v2_test_")
    
    # 定位 doc_mcp.py
    script_dir = Path(__file__).parent.parent
    doc_mcp_path = script_dir / "tools" / "doc_mcp.py"
    python_exe = script_dir / ".venv" / "Scripts" / "python.exe"
    
    try:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        
        transport = StdioTransport(
            command=str(python_exe),
            args=[str(doc_mcp_path)],
            env=env,
            cwd=test_dir 
        )
        
        async with Client(transport) as client:
            await run_doc_mcp_tests(client, test_dir)
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n清理测试目录: {test_dir}")
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(test_doc_mcp())
