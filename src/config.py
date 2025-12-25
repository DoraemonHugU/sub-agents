import os
import yaml
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .model_resolver import resolve_model

@dataclass
class AgentConfig:
    name: str
    description: str
    tools: List[str]
    system_prompt: str
    model: Optional[str] = None
    sandbox: bool = False
    sub_cwd: Optional[str] = None  # Agent 专属子工作目录
    allowed_mcp_servers: Optional[List[str]] = None


class ConfigLoader:
    _instance = None
    _initialized = False
    
    def __new__(cls, config_path: str = "agents.yaml"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: str = "agents.yaml"):
        # 防止重复初始化
        if ConfigLoader._initialized:
            return
        # 自动定位到项目根目录，解决 STDIO 模式下 CWD 不确定的问题
        if not os.path.isabs(config_path):
            # src/config.py -> src -> project_root
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            self.config_path = os.path.join(project_root, config_path)
        else:
            self.config_path = config_path

        self._config_cache = {}
        self.load_config()
        ConfigLoader._initialized = True

    def load_config(self) -> Dict[str, Any]:
        """加载原始 yaml 配置，不进行变量替换。"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"未找到配置文件: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        try:
            # 只按 YAML 解析结构，不处理 ${VAR}
            # 变量替换推迟到 get_agent_config / get_global_settings 时
            config = yaml.safe_load(content)
            self._config_cache = config
            return config
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 配置解析错误: {e}")

    def _resolve_with_env(self, value: Any, env: Dict[str, str]) -> Any:
        """递归解析配置中的环境变量占位符。"""
        if isinstance(value, str):
            # 正则匹配 ${VAR} 或 ${VAR:default}
            pattern = re.compile(r'\$\{([^}:]+)(:([^}]+))?\}')
            
            def env_sub(match):
                var_name = match.group(1)
                default_value = match.group(3)
                # 优先从传入的 env 查找，没有则回退到 default_value -> ""
                return env.get(var_name, default_value if default_value is not None else "")
            
            return pattern.sub(env_sub, value)
        
        elif isinstance(value, dict):
            return {k: self._resolve_with_env(v, env) for k, v in value.items()}
        
        elif isinstance(value, list):
            return [self._resolve_with_env(v, env) for v in value]
        
        else:
            return value

    def get_global_settings(self, env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """获取全局配置，支持运行时环境覆盖。"""
        raw_global = self._config_cache.get("global", {})
        
        # 合并环境: os.environ (底座) + env_overrides (本次请求)
        run_env = os.environ.copy()
        if env_overrides:
            run_env.update(env_overrides)
            
        return self._resolve_with_env(raw_global, run_env)

    def resolve_model_alias(self, alias: str, env_overrides: Optional[Dict[str, str]] = None) -> str:
        """将模型别名解析为具体模型名称。"""
        global_settings = self.get_global_settings(env_overrides)
        
        model_registry = global_settings.get("model_registry", {})
        use_preview_str = global_settings.get("use_preview_models", "true")
        use_preview = str(use_preview_str).lower() == "true"
        
        return resolve_model(alias, model_registry, use_preview)

    def _resolve_permission_sets(self, set_names, permission_sets: Dict) -> Dict:
        """
        解析权限集，支持组合多个权限集。
        注：权限集通常不包含需要动态替换的变量，所以逻辑不变。
        """
        # 标准化为列表
        if isinstance(set_names, str):
            set_names = [set_names]
        
        combined_tools = []
        sandbox = False
        
        for set_name in set_names:
            if set_name not in permission_sets:
                raise ValueError(f"未找到权限集 '{set_name}'。")
            
            pset = permission_sets[set_name]
            tools = pset.get("tools", [])
            combined_tools.extend(tools)
            
            # 如果任何一个权限集要求沙箱，则启用
            if pset.get("sandbox", False):
                sandbox = True
        
        # 去重并保持顺序
        seen = set()
        unique_tools = []
        for t in combined_tools:
            if t not in seen:
                seen.add(t)
                unique_tools.append(t)
        
        return {"tools": unique_tools, "sandbox": sandbox}

    def get_agent_config(self, agent_name: str, env_overrides: Optional[Dict[str, str]] = None) -> AgentConfig:
        """获取特定 Agent 的配置对象，支持运行时配置覆盖。"""
        # 合并环境
        run_env = os.environ.copy()
        if env_overrides:
            run_env.update(env_overrides)

        agents = self._config_cache.get("agents", [])
        raw_agent_def = next((a for a in agents if a["name"] == agent_name), None)
        
        if not raw_agent_def:
            raise ValueError(f"配置中未找到 Agent '{agent_name}'。")

        # 实时解析 Agent 定义中的变量 (如果 description, model 等包含 ${VAR})
        agent_def = self._resolve_with_env(raw_agent_def, run_env)

        # 解析权限
        permission_sets = self._config_cache.get("permission_sets", {})
        pset_name = agent_def.get("permission_set")
        
        tools = []
        sandbox = False
        
        if pset_name:
            pset = self._resolve_permission_sets(pset_name, permission_sets)
            tools = pset.get("tools", [])
            sandbox = pset.get("sandbox", False)
        
        # 模型解析: 别名 -> 具体模型名
        model_alias = agent_def.get("model") or "auto"
        # 传入 env_overrides 确保 resolve_model_alias 能读到最新配置
        resolved_model = self.resolve_model_alias(model_alias, env_overrides)
        
        return AgentConfig(
            name=agent_def["name"],
            description=agent_def.get("description", ""),
            tools=tools,
            system_prompt=agent_def.get("system_prompt", ""),
            model=resolved_model,
            sandbox=sandbox,
            sub_cwd=agent_def.get("sub_cwd"),  # 解析 sub_cwd
            allowed_mcp_servers=agent_def.get("allowed_mcp_servers")
        )
