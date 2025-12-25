from typing import Dict, Optional, Any
import os
from .config import ConfigLoader
from .launcher import GeminiLauncher, GeminiLauncherError

class AgentRouter:
    def __init__(self, config_path: str = "agents.yaml"):
        self.config_loader = ConfigLoader(config_path)
    
    def route_request(self, 
                      agent_name: str, 
                      instruction: str, 
                      request_config: Optional[Dict[str, Any]] = None,
                      model: Optional[str] = None) -> str:
        """
        将请求路由到指定的 Agent。
        
        Args:
            agent_name: Agent 名称 (例如 'reviewer')。
            instruction: 针对 Agent 的指令/提示词。
            request_config: 请求级配置 (包含 cwd 和 env_vars)，用于覆盖全局环境而不污染 os.environ。
            model: 可选，覆盖 Agent 默认模型（优先级：调用方 > Agent > Global）。
        
        Returns:
            Agent 的文本响应。
        """
        # 0. 解析上下文
        # 默认上下文
        cwd = None
        env_vars = {}
        
        if request_config:
            cwd = request_config.get("cwd")
            # 提取除 cwd 外的所有配置作为环境变量覆盖
            # 增加类型检查，确保 env_vars 确实是字典 (Fix Point 4)
            ev_data = request_config.get("env_vars")
            if isinstance(ev_data, dict):
                env_vars = ev_data

        # 1. 准备运行时环境 (Base Env + Request Overrides)
        # 这是为了确保 ConfigLoader 能解析出基于当前请求的配置（如模型别名）
        run_env = os.environ.copy()
        run_env.update(env_vars)


        # 2. 加载 Agent 配置 (传入 run_env 以支持动态变量替换)
        try:
            agent_config = self.config_loader.get_agent_config(agent_name, env_overrides=run_env)
        except ValueError as e:
            return f"错误: Agent '{agent_name}' 未定义。{str(e)}"
        
        # 3. 模型优先级: 调用方指定 > Agent 配置
        if model:
            # 同样传入 run_env 以支持动态别名解析
            effective_model = self.config_loader.resolve_model_alias(model, env_overrides=run_env)
        else:
            effective_model = agent_config.model
        
        # 3. 确定最终 CWD
        # 策略：如果有 sub_cwd，始终拼接到基础目录上
        base_cwd = cwd  # 调用方传入的 CWD
        if agent_config.sub_cwd:
            if base_cwd:
                final_cwd = os.path.join(base_cwd, agent_config.sub_cwd)
            else:
                project_root = os.path.dirname(self.config_loader.config_path)
                final_cwd = os.path.join(project_root, agent_config.sub_cwd)
        else:
            final_cwd = base_cwd

        # CWD 校验：如果仍然没有有效的工作目录，向调用方返回明确错误
        if not final_cwd:
            return "[SUB-AGENT ERROR] 未指定工作目录 (CWD)。请在 Header 中设置 SUB_AGENT_CWD 或在环境变量中配置。"

        # 确保目录存在 (自动为 Agent 准备工作区)
        if not os.path.exists(final_cwd):
            try:
                os.makedirs(final_cwd, exist_ok=True)
            except Exception as e:
                return f"[SUB-AGENT ERROR] 无法创建工作目录 '{final_cwd}': {e}"

        # 4. 初始化启动器
        launcher = GeminiLauncher(cwd=final_cwd, env=run_env)
        
        # 5. 执行
        try:
            # 全局设置也支持覆盖
            global_settings = self.config_loader.get_global_settings(env_overrides=run_env)
            global_include_dirs = global_settings.get("include_directories", [])
            timeout_seconds = int(global_settings.get("timeout_seconds", 120))
            
            response = launcher.run(
                prompt=instruction,
                system_prompt=agent_config.system_prompt,
                tools=agent_config.tools,
                model=effective_model,
                include_directories=global_include_dirs,
                output_format="json",
                sandbox=agent_config.sandbox,
                timeout_seconds=timeout_seconds,
                allowed_mcp_servers=agent_config.allowed_mcp_servers
            )
            
            return response

        except GeminiLauncherError as e:
            error_str = str(e)
            # 区分调用方可修复 vs 内部问题
            if "timeout" in error_str.lower():
                return "[SUB-AGENT ERROR] 任务超时，请简化请求或拆分任务。"
            elif "not found" in error_str.lower():
                return "[SUB-AGENT ERROR] 服务配置错误，无需进行二次尝试。"
            else:
                return f"[SUB-AGENT ERROR] 执行失败，请稍后重试。详情: {error_str}"
        except Exception as e:
            from loguru import logger
            logger.exception(f"route_request 发生未预期异常: {e}")
            return "[SUB-AGENT ERROR] 内部错误，请稍后重试。"

# End of file
