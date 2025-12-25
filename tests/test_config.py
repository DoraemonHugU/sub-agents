"""
ConfigLoader 单元测试
测试配置加载、环境变量替换、权限集解析
"""

import os
import pytest
import tempfile
from src.config import ConfigLoader, AgentConfig


class TestConfigLoader:
    """ConfigLoader 单元测试"""
    
    @pytest.fixture
    def sample_config(self, tmp_path):
        """创建临时配置文件"""
        config_content = """
global:
  model_registry:
    preview:
      pro: "gemini-3-pro-preview"
      flash: "gemini-3-flash-preview"
    stable:
      pro: "gemini-2.5-pro"
      flash: "gemini-2.5-flash"
      flash_lite: "gemini-2.5-flash-lite"
    auto:
      preview: "auto-gemini-3"
      stable: "auto-gemini-2.5"
  use_preview_models: "true"
  output_format: "json"

permission_sets:
  file_read:
    description: "只读文件系统"
    tools: [list_directory, read_file, search_file_content]
  
  web_access:
    description: "联网搜索"
    tools: [web_fetch, google_web_search]
  
  git_readonly:
    description: "Git 只读"
    tools:
      - "run_shell_command(git diff)"
      - "run_shell_command(git status)"

agents:
  - name: test_agent
    description: "测试用 Agent"
    permission_set: [file_read, web_access]
    model: "flash"
    system_prompt: "prompts/test.md"
"""
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(config_content, encoding='utf-8')
        return str(config_file)
    
    def test_load_config_success(self, sample_config):
        """测试配置加载成功"""
        loader = ConfigLoader(sample_config)
        assert loader._config_cache is not None
        assert "global" in loader._config_cache
        assert "agents" in loader._config_cache
    
    def test_load_config_file_not_found(self):
        """测试配置文件不存在时抛出异常"""
        with pytest.raises(FileNotFoundError):
            ConfigLoader("non_existent.yaml")
    
    def test_get_global_settings(self, sample_config):
        """测试获取全局设置"""
        loader = ConfigLoader(sample_config)
        global_settings = loader.get_global_settings()
        assert global_settings["output_format"] == "json"
        assert "model_registry" in global_settings
    
    def test_env_variable_substitution(self, tmp_path):
        """测试环境变量替换"""
        os.environ["TEST_MODEL_VAR"] = "custom-model"
        
        config_content = """
global:
  model_registry:
    stable:
      flash: "gemini-2.5-flash"
    auto:
      stable: "auto-gemini-2.5"
  test_value: "${TEST_MODEL_VAR}"
  default_value: "${NONEXISTENT_VAR:fallback}"
agents: []
permission_sets: {}
"""
        config_file = tmp_path / "env_test.yaml"
        config_file.write_text(config_content, encoding='utf-8')
        
        loader = ConfigLoader(str(config_file))
        global_settings = loader.get_global_settings()
        
        assert global_settings["test_value"] == "custom-model"
        assert global_settings["default_value"] == "fallback"
        
        del os.environ["TEST_MODEL_VAR"]
    
    def test_get_agent_config(self, sample_config):
        """测试获取 Agent 配置"""
        loader = ConfigLoader(sample_config)
        agent = loader.get_agent_config("test_agent")
        
        assert isinstance(agent, AgentConfig)
        assert agent.name == "test_agent"
        assert agent.description == "测试用 Agent"
        assert "list_directory" in agent.tools
        assert "web_fetch" in agent.tools
        assert agent.model == "gemini-3-flash-preview"  # flash 被解析为具体模型
    
    def test_get_agent_config_not_found(self, sample_config):
        """测试获取不存在的 Agent 时抛出异常"""
        loader = ConfigLoader(sample_config)
        with pytest.raises(ValueError):
            loader.get_agent_config("nonexistent_agent")
    
    def test_permission_set_combination(self, sample_config):
        """测试权限集组合"""
        loader = ConfigLoader(sample_config)
        agent = loader.get_agent_config("test_agent")
        
        # 应该包含 file_read 和 web_access 的所有工具
        assert "list_directory" in agent.tools
        assert "read_file" in agent.tools
        assert "search_file_content" in agent.tools
        assert "web_fetch" in agent.tools
        assert "google_web_search" in agent.tools


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
