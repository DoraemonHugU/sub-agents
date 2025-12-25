"""
Doc Keeper Integration Test

测试完整链路：
Client -> Agent Server (src/server.py) -> Router -> Gemini Launcher -> Gemini CLI -> Doc MCP Tools

目标：
验证通过 Agent Server 调用 doc_keeper 能正确在用户项目目录(SUB_AGENT_CWD)下创建文档。
"""
import asyncio
import os
import sys
import shutil
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

async def test_doc_keeper_integration():
    print("=" * 80)
    print("Doc Keeper 集成测试")
    print("=" * 80)

    # 1. 准备环境
    # 使用真实项目目录作为 SUB_AGENT_CWD，验证 Router 的路径拼接逻辑
    # 目标: D:/xuexi/projects/subAgent
    real_project_root = "D:/xuexi/projects/subAgent"
    test_cwd = Path(real_project_root)
    
    print(f"测试工作目录 (SUB_AGENT_CWD): {test_cwd}")
    
    # 2. 准备启动参数
    python_exe = sys.executable
    server_script = Path("d:/xuexi/projects/subAgent/src/server.py")
    
    env = os.environ.copy()
    env["SUB_AGENT_CWD"] = str(test_cwd)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    print(f"启动 Server: {server_script}")
    
    transport = StdioTransport(
        command=str(python_exe),
        args=[str(server_script)],
        env=env,
        cwd=str(real_project_root)
    )

    try:
        async with Client(transport) as client:
            print("✅ Agent Server 已连接")
            
            # 3. 列出工具，确认 doc_keeper 存在
            tools = await client.list_tools()
            keeper_tool = next((t for t in tools if t.name == "doc_keeper"), None)
            
            if not keeper_tool:
                print("❌ 未找到 doc_keeper 工具！")
                return
            else:
                print("✅ 找到 doc_keeper 工具")

            # 4. 发送指令
            # 指令包含两个步骤：1. 查目录（会是空的） 2. 创建文档
            # 我们直接发一个明确的创建指令
            instruction = (
                "请帮我在知识库中创建一个关于 'Integration Testing' 的文档。"
                "分类为 'tests'，标签为 'ci, automation'。"
                "描述为 'Documentation for integration testing workflow'。"
                "不需要包含具体内容，创建元数据即可。"
            )
            
            print(f"\n发送指令: {instruction}")
            print("-" * 60)
            
            # 调用 Agent
            # 注意：这可能会花费一些时间，因为涉及 Gemini 调用和工具执行
            result = await client.call_tool("doc_keeper", {"instruction": instruction})
            
            print("-" * 60)
            print("Agent 回复:")
            # result 可能是 TextContent 列表
            print(result)
            print("-" * 60)
            
            # 5. 验证结果
            # 检查 _test_workspace/external_knowledge/tests/integration_testing.md 是否存在
            # 注意：Doc Keeper 的配置 sub_cwd 是 external_knowledge
            # 所以最终路径应该是 test_cwd / external_knowledge / ...
            
            expected_file = test_cwd / "external_knowledge" / "tests" / "integration_testing.md"
            print(f"\n验证文件是否存在: {expected_file}")
            
            if expected_file.exists():
                print("✅ 测试通过！文件已成功创建。")
                print("文件内容预览:")
                print(expected_file.read_text(encoding='utf-8')[:200])
            else:
                print("❌ 测试失败！文件未创建。")
                # 打印目录树帮助调试
                print("\n当前目录结构:")
                for root, dirs, files in os.walk(test_cwd):
                    for file in files:
                        print(os.path.join(root, file))

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理 (可选，为了查看结果暂时保留或注释掉)
        # shutil.rmtree(test_cwd, ignore_errors=True)
        pass

if __name__ == "__main__":
    asyncio.run(test_doc_keeper_integration())
