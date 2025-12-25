"""
MCP Client Test Script
支持两种模式:
1. STDIO: 从 mcp_config.json 加载 command 配置
2. HTTP:  从 mcp_config.json 加载 url 配置，连接到已运行的 HTTP Server
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# FastMCP Client 支持 HTTP 连接
from fastmcp import Client


def load_mcp_config(config_path: str = "../mcp_config.json", server_name: str = "sub-agents") -> dict:
    """从 MCP JSON 配置文件加载 Server 参数"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    server_config = config.get("mcpServers", {}).get(server_name)
    if not server_config:
        raise ValueError(f"未找到 Server 配置: {server_name}")
    
    return server_config


async def test_mcp_server(config_path: str = "mcp_config.json"):
    print("=" * 80)
    print("MCP Server 测试")
    print("=" * 80)
    
    # 加载配置
    print(f"\n0. 加载配置: {config_path}")
    try:
        server_config = load_mcp_config(config_path)
        
        # 判断模式
        if "url" in server_config:
            mode = "HTTP"
            target = server_config["url"]
        elif "serverUrl" in server_config:
            mode = "HTTP"
            target = server_config["serverUrl"]
            # FastMCP Client expects 'url' parameter
            server_config["url"] = server_config["serverUrl"]
        elif "command" in server_config:
            mode = "STDIO"
            target = f"{server_config['command']} {' '.join(server_config.get('args', []))}"
        else:
            raise ValueError("配置必须包含 'url' 或 'command'")
        
        print(f"   模式: {mode}")
        print(f"   目标: {target}")
        
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return
    
    # 连接 Server
    print(f"\n1. 连接 MCP Server ({mode} 模式)...")
    
    try:
        if mode == "HTTP":
            # HTTP 模式: 连接到已运行的 Server
            async with Client(server_config["url"], timeout=300) as client:
                await run_tests(client)
        else:
            # STDIO 模式: 启动 Server 进程
            # 设置环境变量
            env = os.environ.copy()
            if server_config.get("env"):
                env.update(server_config["env"])
            env.setdefault("PYTHONUTF8", "1")
            env.setdefault("PYTHONIOENCODING", "utf-8")
            
            # 使用 FastMCP Client 的 STDIO 模式
            from fastmcp.client.transports import StdioTransport
            transport = StdioTransport(
                command=server_config["command"],
                args=server_config.get("args", []),
                env=env
            )
            async with Client(transport) as client:
                await run_tests(client)
                
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        import traceback
        traceback.print_exc()


async def run_tests(client):
    """执行测试用例"""
    print("✅ Server 已连接")
    
    # 1. 列出可用工具
    print("\n2. 列出可用工具...")
    tools = await client.list_tools()
    print(f"✅ 发现 {len(tools)} 个工具:")
    for tool in tools:
        print(f"   - {tool.name}: {tool.description[:80]}...")
    
    # 2. 测试调用
    print("\n3. 调用 reviewer (测试同步调用)...")
    # test_instruction = "你支持什么工具,你需要对每个支持的工具进行无害化测试后,列出来真实支持的工具列表"
    test_instruction = "列出你支持的工具名称即可，不要实际执行它们,尤其是`run_shell_command`这个命令支持什么,不实际运行"
    print(f"   指令: '{test_instruction}'")
    
    try:
        result = await client.call_tool(
            "reviewer",
            {"instruction": test_instruction}
        )
        
        print("\n" + "=" * 80)
        print("【返回结果】")
        print("=" * 80)
        print(str(result))
        print("=" * 80)
        print("\n✅ 测试成功！MCP Server 工作正常。")
        
    except Exception as e:
        print(f"\n❌ 调用失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "mcp_config.json"
    print(f"启动 MCP 客户端测试 (配置: {config_file})...")
    asyncio.run(test_mcp_server(config_file))
