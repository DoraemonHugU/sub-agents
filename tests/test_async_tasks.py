"""
测试 MCP 后台任务模式 (SEP-1686)

这个脚本验证：
1. Server 端正确配置了 tasks=True
2. Client 可以使用 task=True 进行后台调用
3. 后台调用立即返回 task_id
4. 可以查询任务状态和获取最终结果
"""

import asyncio
import sys
import os

# 添加项目根目录到 sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastmcp import Client


async def test_sync_call(client):
    """测试同步调用（传统模式）"""
    print("\n" + "=" * 60)
    print("测试 1: 同步调用 (不使用 task=True)")
    print("=" * 60)
    
    try:
        result = await client.call_tool(
            "reviewer",
            {"instruction": "简单回答：1+1=?"}
        )
        print(f"✅ 同步调用成功")
        print(f"   返回类型: {type(result)}")
        print(f"   返回内容: {str(result)[:200]}...")
        return True
    except Exception as e:
        print(f"❌ 同步调用失败: {e}")
        return False


async def test_async_call(client):
    """测试后台调用（task=True 模式）"""
    print("\n" + "=" * 60)
    print("测试 2: 后台调用 (使用 task=True)")
    print("=" * 60)
    
    try:
        # 发起后台调用
        print("   正在发起后台调用...")
        task = await client.call_tool(
            "reviewer",
            {"instruction": "简单回答：2+2=?"},
            task=True  # 关键：启用后台任务模式
        )
        
        # 检查是否立即返回
        print(f"✅ 后台调用立即返回")
        print(f"   Task 对象类型: {type(task)}")
        print(f"   Task ID: {getattr(task, 'id', 'N/A')}")
        
        # 检查是否是 Task 对象
        if hasattr(task, 'status'):
            # 查询任务状态
            status = await task.status()
            print(f"   任务状态: {status}")
            
            # 等待结果
            print("   正在等待任务完成...")
            result = await task.result()
            print(f"✅ 任务完成")
            print(f"   返回内容: {str(result)[:200]}...")
            return True
        else:
            # 如果返回的不是 Task 对象，说明 Server 可能自动降级为同步调用
            print(f"⚠️  返回的不是 Task 对象，可能已降级为同步调用")
            print(f"   返回类型: {type(task)}")
            print(f"   返回内容: {str(task)[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ 后台调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_task_capabilities(client):
    """检查 Server 是否声明了任务能力"""
    print("\n" + "=" * 60)
    print("检查 Server 任务能力")
    print("=" * 60)
    
    try:
        # 列出可用工具
        tools = await client.list_tools()
        print(f"   可用工具数量: {len(tools)}")
        
        for tool in tools:
            print(f"   - {tool.name}")
            
        return True
    except Exception as e:
        print(f"❌ 获取工具列表失败: {e}")
        return False


async def main():
    print("=" * 60)
    print("MCP 后台任务模式测试")
    print("=" * 60)
    
    # 使用 in-memory server 进行测试
    # 这样可以直接加载 server.py 而不需要启动子进程
    
    print("\n正在加载 Server...")
    
    try:
        # 导入 server 模块 (装饰器模式：直接使用 mcp 实例)
        from src.server import mcp as server, get_config_path, AgentRouter
        import src.server as server_module
        
        # 手动初始化 router（模拟 main() 的行为）
        server_module.router = AgentRouter(get_config_path())
        
        print(f"✅ Server 加载成功: {server.name}")
        print(f"   tasks 配置: {getattr(server, '_tasks', 'unknown')}")
        
    except Exception as e:
        print(f"❌ Server 加载失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 使用 Client 连接到 in-memory server
    print("\n正在连接到 Server...")
    
    async with Client(server) as client:
        print("✅ Client 连接成功")
        
        # 测试 1: 检查任务能力
        await test_task_capabilities(client)
        
        # 测试 2: 同步调用
        sync_ok = await test_sync_call(client)
        
        # 测试 3: 后台调用
        async_ok = await test_async_call(client)
        
        # 总结
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        print(f"   同步调用: {'✅ 通过' if sync_ok else '❌ 失败'}")
        print(f"   后台调用: {'✅ 通过' if async_ok else '❌ 失败/降级'}")


if __name__ == "__main__":
    asyncio.run(main())
