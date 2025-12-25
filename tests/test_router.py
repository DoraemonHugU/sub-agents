"""
AgentRouter 单元测试
测试请求路由、模型覆盖逻辑
"""

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from src.router import AgentRouter
from src.config import AgentConfig


class TestAgentRouter:
    """AgentRouter 单元测试"""
    
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
    tools: [list_directory, read_file]
  
  git_readonly:
    description: "Git 只读"
    tools:
      - "run_shell_command(git status)"

agents:
  - name: reviewer
    description: "代码审查专家"
    permission_set: [file_read, git_readonly]
    model: "flash"
    system_prompt: "prompts/reviewer.md"
"""
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(config_content, encoding='utf-8')
        
        # 创建 prompts 目录和文件
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "reviewer.md").write_text("You are a code reviewer.", encoding='utf-8')
        
        # 切换工作目录到临时目录（因为 system_prompt 是相对路径）
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        yield str(config_file)
        os.chdir(original_cwd)
    
    def test_router_init(self, sample_config):
        """测试 Router 初始化"""
        router = AgentRouter(sample_config)
        assert router.config_loader is not None
    
    def test_route_request_agent_not_found(self, sample_config):
        """测试请求不存在的 Agent"""
        router = AgentRouter(sample_config)
        result = router.route_request("nonexistent", "test instruction")
        assert "未定义" in result or "not found" in result.lower()
    
    @patch('src.router.GeminiLauncher')
    def test_route_request_success(self, mock_launcher_class, sample_config):
        """测试请求成功路由"""
        # 模拟 Launcher
        mock_launcher = MagicMock()
        mock_launcher.run.return_value = "Mock response"
        mock_launcher_class.return_value = mock_launcher
        
        router = AgentRouter(sample_config)
        result = router.route_request("reviewer", "请分析代码")
        
        assert result == "Mock response"
        mock_launcher.run.assert_called_once()
        
        # 验证调用参数
        call_kwargs = mock_launcher.run.call_args.kwargs
        assert call_kwargs["prompt"] == "请分析代码"
        assert call_kwargs["model"] == "gemini-3-flash-preview"  # flash 被解析
    
    @patch('src.router.GeminiLauncher')
    def test_model_override(self, mock_launcher_class, sample_config):
        """测试调用方覆盖模型"""
        mock_launcher = MagicMock()
        mock_launcher.run.return_value = "Mock response"
        mock_launcher_class.return_value = mock_launcher
        
        router = AgentRouter(sample_config)
        # 调用方指定 model="pro"
        result = router.route_request("reviewer", "test", model="pro")
        
        call_kwargs = mock_launcher.run.call_args.kwargs
        # 调用方的 "pro" 应该被解析为 gemini-3-pro-preview (因为 use_preview=true)
        assert call_kwargs["model"] == "gemini-3-pro-preview"
    
    @patch('src.router.GeminiLauncher')
    def test_tools_passed_correctly(self, mock_launcher_class, sample_config):
        """测试工具列表正确传递"""
        mock_launcher = MagicMock()
        mock_launcher.run.return_value = "Mock response"
        mock_launcher_class.return_value = mock_launcher
        
        router = AgentRouter(sample_config)
        router.route_request("reviewer", "test")
        
        call_kwargs = mock_launcher.run.call_args.kwargs
        tools = call_kwargs["tools"]
        
        assert "list_directory" in tools
        assert "read_file" in tools
        assert "run_shell_command(git status)" in tools


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
