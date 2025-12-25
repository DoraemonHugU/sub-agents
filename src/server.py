# ============================================================
# Antigravity Windows Stdio 修复 (必须位于文件最前)
# ============================================================
import sys
import io
import json

if sys.platform == "win32":
    class BinaryCRStripper:
        def __init__(self, stream):
            self.stream = stream
        def write(self, data):
            # 将所有的 \r 剔除，只保留 \n
            return self.stream.write(data.replace(b'\r', b''))
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def flush(self):
            return self.stream.flush()

    # 劫持 stdout，确保输出不含 CR
    sys.stdout = io.TextIOWrapper(
        BinaryCRStripper(sys.stdout.buffer),
        encoding="utf-8", 
        newline="", 
        write_through=True
    )

# ============================================================
# 导入
# ============================================================
from fastmcp import FastMCP
from fastmcp.server.tasks import TaskConfig
from fastmcp.server.dependencies import get_http_headers
from typing import Optional, Dict, Any
import argparse
import os
import signal
import atexit
import anyio
from loguru import logger
from dotenv import load_dotenv
import logging

# 重定向标准 logging 到文件 (防止污染 stdout/stderr)
# 在 STDIO 模式下，保持控制台绝对静默是最佳实践
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "server.log")
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)

# ============================================================
# Loguru 配置
# ============================================================
logger.remove()  # 移除默认的 stderr handler
# 只记录到文件，不记录到 stderr
logger.add(log_file_path, rotation="10 MB", level="DEBUG", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

# 项目路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# ============================================================
# 导入项目模块
# ============================================================
from src.router import AgentRouter
from src.launcher import cleanup_all_processes

# ============================================================
# 进程清理钩子
# ============================================================
def _cleanup_on_exit():
    """Server 退出时清理所有活跃子进程"""
    logger.info("Server 正在退出，清理子进程...")
    cleanup_all_processes()

def _signal_handler(signum, frame):
    """处理 SIGINT/SIGTERM 信号"""
    logger.warning(f"收到信号 {signum}，正在优雅退出...")
    _cleanup_on_exit()
    sys.exit(0)

atexit.register(_cleanup_on_exit)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# ============================================================
# 配置路径解析
# ============================================================
def get_config_path(config_arg: str = "agents.yaml") -> str:
    """智能解析配置文件路径"""
    if os.path.isabs(config_arg):
        return config_arg
    potential_path = os.path.join(project_root, config_arg)
    if os.path.exists(potential_path):
        logger.info(f"已解析配置路径: {potential_path}")
        return potential_path
    return config_arg

# ============================================================
# 全局变量（延迟初始化）
# ============================================================
router: Optional[AgentRouter] = None  # 在 main() 中初始化

# 创建 MCP Server (启用后台任务)
mcp = FastMCP(
    "Sub-Agents",
    instructions="Gemini Sub-Agents Service. Provides specialized AI agents for code review and exploration.",
    tasks=True,  # 启用后台任务支持
)

# ============================================================
# 运行时配置解析 (JSON Header 转 Dict)
# ============================================================
_CONFIG_HEADER_KEY = "x-sub-agent-config"

def _resolve_request_config_dict() -> Dict[str, Any]:
    """
    从 HTTP Headers 解析运行时配置。
    
    返回结构:
    {
        "cwd": "...",
        "env_vars": { "GEMINI_TIMEOUT": "...", ... }
    }
    """

    
    headers = get_http_headers()
    
    # 调试用：记录请求 Header（生产环境可移除）
    logger.debug(f"收到请求 Headers: {dict(headers)}")

    # 1. 默认上下文
    # CWD 不使用 os.getcwd() 作为回退，避免在 MCP 模式下使用不可控的目录
    cwd = os.environ.get("SUB_AGENT_CWD")
    env_vars = {}
    
    # 2. 尝试从 Header 读取 JSON 配置
    config_json_str = headers.get(_CONFIG_HEADER_KEY)
    
    if config_json_str:
        try:
            config_dict = json.loads(config_json_str)
            logger.debug(f"从 Header 加载配置: {list(config_dict.keys())}")
            
            # 提取 CWD
            if "SUB_AGENT_CWD" in config_dict:
                cwd = config_dict["SUB_AGENT_CWD"]
            
            # 剩余所有内容作为环境变量覆盖
            env_vars = {k: str(v) for k, v in config_dict.items() if v is not None}
                    
        except json.JSONDecodeError as e:
            logger.warning(f"Header JSON 解析失败: {e}，使用默认配置")
    
    return {
        "cwd": cwd,
        "env_vars": env_vars
    }

# ============================================================
# Agent 工具定义 (装饰器模式)
# ============================================================

# 加载配置以获取动态描述
try:
    from src.config import ConfigLoader
    _config_loader = ConfigLoader()
    # 注意: 这里使用 os.environ 是为了在 Server 启动时解析尽可能多的默认值
    # 真正的运行时配置会在 route_request 时再次解析
    _reviewer_config = _config_loader.get_agent_config("reviewer", env_overrides=os.environ.copy())
    _explorer_config = _config_loader.get_agent_config("explorer", env_overrides=os.environ.copy())
    _doc_keeper_config = _config_loader.get_agent_config("doc_keeper", env_overrides=os.environ.copy())
    
    _REVIEWER_DESC = _reviewer_config.description
    _EXPLORER_DESC = _explorer_config.description
    _DOC_KEEPER_DESC = _doc_keeper_config.description
except Exception as e:
    logger.warning(f"从 agents.yaml 加载动态描述失败: {e}")
    _REVIEWER_DESC = "审查代码中的缺陷（Bug、逻辑漏洞、安全风险、边界问题）。"
    _EXPLORER_DESC = "理解现有代码结构、追踪逻辑流程或查找定义位置。"
    _DOC_KEEPER_DESC = "外部知识图书管理员，负责获取、整理并存储外部文档。"

@mcp.tool(description=_REVIEWER_DESC, task=TaskConfig(mode="optional"))
async def reviewer(instruction: str) -> str:
    """描述信息从 agents.yaml 动态加载"""
    if not router:
        return "Error: AgentRouter not initialized"

    # 获取当前请求的独立配置
    req_config = _resolve_request_config_dict()
        
    return await anyio.to_thread.run_sync(
        lambda: router.route_request("reviewer", instruction, request_config=req_config)
    )

@mcp.tool(description=_EXPLORER_DESC, task=TaskConfig(mode="optional"))
async def explorer(instruction: str) -> str:
    """描述信息从 agents.yaml 动态加载"""
    if not router:
        return "Error: AgentRouter not initialized"

    req_config = _resolve_request_config_dict()

    return await anyio.to_thread.run_sync(
        lambda: router.route_request("explorer", instruction, request_config=req_config)
    )

@mcp.tool(description=_DOC_KEEPER_DESC, task=TaskConfig(mode="optional"))
async def doc_keeper(instruction: str) -> str:
    """描述信息从 agents.yaml 动态加载"""
    if not router:
        return "Error: AgentRouter not initialized"

    req_config = _resolve_request_config_dict()

    return await anyio.to_thread.run_sync(
        lambda: router.route_request("doc_keeper", instruction, request_config=req_config)
    )


# ============================================================
# 服务器入口
# ============================================================
def main():
    global router
    
    parser = argparse.ArgumentParser(description="Gemini Agent Router MCP Server")
    parser.add_argument("--config", default="agents.yaml", help="agents.yaml 配置文件路径")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "http"], 
                        help="传输协议: stdio (默认) 或 http")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 模式下的主机地址")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 模式下的端口")
    parser.add_argument("-e", "--env-file", default=None, help="指定 .env 文件路径")
    args = parser.parse_args()

    # 加载 .env 环境变量
    load_dotenv(args.env_file)

    config_path = get_config_path(args.config)
    
    # ConfigLoader 已实现单例模式，直接初始化即可
    router = AgentRouter(config_path)
    
    logger.info(f"已注册工具: reviewer, explorer, doc_keeper")
    
    if args.transport == "http":
        logger.info(f"启动 HTTP 传输: {args.host}:{args.port}")
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        # STDIO 模式下禁用 Banner，保持协议纯净
        # 这里的 log_level 会传递给底层 Transport (debug 参数不支持 stdio)
        import warnings
        warnings.simplefilter("ignore")
        mcp.run(show_banner=False, log_level="ERROR")


if __name__ == "__main__":
    main()
