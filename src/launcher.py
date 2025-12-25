import subprocess
import json
import os
import sys
import shutil
from typing import List, Dict, Optional, Any, Set
from loguru import logger
import loguru
import psutil
import time


# 全局进程登记册：追踪所有由 launcher 启动的子进程
_active_processes: Set[subprocess.Popen] = set()


def cleanup_all_processes(timeout: int = 5) -> int:
    """
    清理所有已注册的活跃子进程及其子进程树。
    
    使用 psutil 安全地终止进程树，避免 PID 重用导致的误杀。
    
    Args:
        timeout: 等待优雅终止的超时秒数
        
    Returns:
        清理的进程数量
    """
    cleaned_count = 0
    
    for proc in list(_active_processes):
        try:
            # 检查进程是否仍在运行
            if proc.poll() is None:
                try:
                    parent = psutil.Process(proc.pid)
                    children = parent.children(recursive=True)
                    
                    # 先终止子进程
                    for child in children:
                        try:
                            child.terminate()
                            logger.debug(f"终止子进程: {child.pid}")
                        except psutil.NoSuchProcess:
                            pass
                    
                    # 再终止父进程
                    parent.terminate()
                    logger.debug(f"终止父进程: {parent.pid}")
                    
                    # 等待优雅终止
                    gone, alive = psutil.wait_procs([parent] + children, timeout=timeout)
                    
                    # 强制杀死未响应的进程
                    for p in alive:
                        try:
                            p.kill()
                            logger.warning(f"强制杀死进程: {p.pid}")
                        except psutil.NoSuchProcess:
                            pass
                    
                    cleaned_count += 1 + len(children)
                    
                except psutil.NoSuchProcess:
                    # 进程已经不存在了
                    pass
                    
        except Exception as e:
            logger.error(f"清理进程时出错: {e}")
        finally:
            _active_processes.discard(proc)
    
    if cleaned_count > 0:
        logger.info(f"已清理 {cleaned_count} 个进程")
    
    return cleaned_count


class GeminiLauncherError(Exception):
    pass

class GeminiLauncher:
    def __init__(self, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None):
        """
        初始化启动器。
        
        Args:
            cwd: Gemini 进程的当前工作目录（必须显式提供）。
            env: 传递给进程的环境变量。
        """
        # CWD 必须由调用方显式提供，不使用 os.getcwd() 回退
        if not cwd:
            raise ValueError("GeminiLauncher 要求显式提供 cwd 参数")
        self.cwd = cwd
        self.env = env or os.environ.copy()
        self._gemini_executable = self._find_gemini_executable()

    def _find_gemini_executable(self) -> str:
        """
        查找 gemini 可执行文件路径。
        
        优先级：环境变量 > PATH > 默认命令名
        """
        # 1. 用户通过环境变量显式指定
        if "GEMINI_EXECUTABLE" in self.env:
            return self.env["GEMINI_EXECUTABLE"]

        # 2. 从 PATH 中查找
        executable = shutil.which("gemini") or shutil.which("gemini.cmd") or shutil.which("gemini.ps1")
        if executable:
            return executable

        # 3. 回退到默认命令名（需确保 gemini 在 PATH 中）
        return "gemini"

    def run(self, 
            prompt: str, 
            system_prompt: Optional[str] = None,
            tools: Optional[List[str]] = None,
            model: Optional[str] = None,
            include_directories: Optional[List[str]] = None,
            output_format: str = "json",
            sandbox: bool = False,
            timeout_seconds: int = 120,
            allowed_mcp_servers: Optional[List[str]] = None
           ) -> str:
        """
        运行 Gemini CLI。
        
        Args:
            prompt: 主提示词
            system_prompt: System Prompt 文件路径 (通过 GEMINI_SYSTEM_MD 传递)
            tools: 允许的工具列表 (通过 --allowed-tools 传递)
            model: 模型名称
            include_directories: 额外包含的目录列表
            output_format: 输出格式 (json/text/stream-json)
            sandbox: 是否启用沙箱模式
        """
        
        cmd = [self._gemini_executable]
        
        # 模型
        if model:
            cmd.extend(["--model", model])
            
        # MCP Access Control
        if allowed_mcp_servers:
            for server in allowed_mcp_servers:
                cmd.extend(["--allowed-mcp-server-names", server])
        
        # 沙箱模式
        if sandbox:
            cmd.append("--sandbox")
        
        # System Prompt: 通过 GEMINI_SYSTEM_MD 环境变量传递
        # 配置与数据分离，Prompt 由独立 MD 文件管理
        
        final_prompt = prompt
        
        # 关键修复：创建环境副本，避免并发请求修改同一个 self.env 导致竞争条件
        run_env = self.env.copy()
        
        if system_prompt:
            # 此时 system_prompt 应该是一个文件路径
            sys_prompt_path = os.path.abspath(system_prompt)
            
            if os.path.exists(sys_prompt_path):
                logger.debug(f"使用 System Prompt 文件: {sys_prompt_path}")
                # 设置局部的环境变量指向该文件，不影响其他并发请求
                run_env["GEMINI_SYSTEM_MD"] = sys_prompt_path
            else:
                logger.warning(f"未找到 System Prompt 文件: {sys_prompt_path}. 忽略。")
        
        # 工具白名单: 通过 --allowed-tools 传递 (无需 settings.json)
        # 这些工具将被允许静默执行，其他工具会被拒绝（非交互模式）
        if tools:
            for tool in tools:
                cmd.extend(["--allowed-tools", tool])
            # 使用 default 模式：仅允许白名单中的工具，其他工具需确认（非交互模式被拒绝）
            cmd.extend(["--approval-mode", "default"])
            logger.debug(f"工具白名单: {tools}")
        
        if include_directories:
            for d in include_directories:
                cmd.extend(["--include-directories", d])

        # 强制输出格式
        cmd.extend(["--output-format", output_format])
        
        # 添加主提示词 (使用位置参数而非 --prompt，避免 deprecated 警告)
        cmd.append(final_prompt)
        
        try:
            # ============================================================
            # 日志 - 执行前
            # ============================================================
            start_time = time.time()
            
            logger.info("=" * 60)
            logger.info("开始执行 Gemini CLI")
            logger.debug(f"工作目录: {self.cwd}")
            logger.debug(f"可执行文件: {self._gemini_executable}")
            logger.debug(f"完整命令: {' '.join(cmd)}")
            logger.debug(f"模型: {model or 'default'}")
            logger.debug(f"输出格式: {output_format}")
            logger.debug(f"沙箱模式: {sandbox}")
            logger.debug(f"超时设置: {timeout_seconds}s")
            logger.debug(f"Prompt 长度: {len(final_prompt)} 字符")
            logger.debug(f"工具白名单数量: {len(tools) if tools else 0}")
            logger.debug(f"环境变量覆盖: {list(run_env.keys() - os.environ.keys())}")
            
            # 使用 Popen 替代 run，以便手动管理超时和进程树杀死
            process = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                env=run_env,  # 关键修复：使用包含特定 SystemPrompt 的局部环境副本
                stdin=subprocess.DEVNULL,  # 关键：不继承父进程的 stdin，防止 MCP 管道冲突
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                # Windows: 创建新进程组，方便后续整棵树杀死
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )
            
            logger.debug(f"进程已启动 (PID: {process.pid})")
            
            # 注册进程到全局登记册
            _active_processes.add(process)
            
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
                elapsed_time = time.time() - start_time
            except subprocess.TimeoutExpired:
                elapsed_time = time.time() - start_time
                logger.error(f"❌ 超时失败 ({elapsed_time:.2f}s / {timeout_seconds}s)")
                logger.error("正在强制终止进程树...")
                # 使用 psutil 安全地杀死进程树
                try:
                    parent = psutil.Process(process.pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                    parent.kill()
                    logger.info(f"已杀死父进程 PID {process.pid}")
                except psutil.NoSuchProcess:
                    pass
                except Exception as kill_err:
                    logger.warning(f"无法杀死进程树: {kill_err}")
                    process.kill()  # Fallback
                
                # 清理残留的 communicate
                try:
                    process.communicate(timeout=2)
                except:
                    pass
                
                raise GeminiLauncherError(f"Gemini CLI timeout ({timeout_seconds}s). Process tree terminated.")
            
            # ============================================================
            # 日志 - 执行后
            # ============================================================
            logger.info(f"✅ CLI 执行完成 (耗时: {elapsed_time:.2f}s, 退出码: {process.returncode})")
            
            # 详细记录 stdout 和 stderr（即使成功也记录）
            if stdout:
                logger.debug(f"STDOUT 长度: {len(stdout)} 字符")
                logger.debug(f"STDOUT 内容:\n{stdout[:1000]}")  # 记录前 1000 字符
                if len(stdout) > 1000:
                    logger.debug(f"... (STDOUT 已截断，完整长度: {len(stdout)})")
            else:
                logger.warning("⚠️  STDOUT 为空！")
            
            if stderr:
                logger.debug(f"STDERR 长度: {len(stderr)} 字符")
                logger.warning(f"STDERR 内容:\n{stderr[:1000]}")  # 警告级别，因为通常 stderr 有内容就需要关注
                if len(stderr) > 1000:
                    logger.debug(f"... (STDERR 已截断，完整长度: {len(stderr)})")
            
            if process.returncode != 0:
                error_msg = stderr.strip() or stdout.strip()
                logger.error(f"❌ CLI 执行失败 (退出码: {process.returncode})")
                logger.error(f"错误信息: {error_msg[:500]}")
                raise GeminiLauncherError(f"Gemini CLI exited with code {process.returncode}: {error_msg}")
            
            stdout = stdout.strip()
            
            if output_format == "json":
                try:
                    if not stdout:
                        logger.error("❌ JSON 解析失败: stdout 为空字符串")
                        logger.error(f"完整 STDERR: {stderr}")
                        raise GeminiLauncherError("Gemini CLI returned empty output. Check stderr for details.")
                    
                    data = json.loads(stdout)
                    if "error" in data:
                        raise GeminiLauncherError(f"Gemini API Error: {data['error'].get('message', 'Unknown error')}")
                    response_text = data.get("response", "")
                    logger.success(f"✅ 解析成功: 响应长度 {len(response_text)} 字符")
                    return response_text
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON 解析错误: {e}")
                    logger.error(f"原始输出 (前 500 字符): {stdout[:500]}")
                    raise GeminiLauncherError(f"Failed to parse JSON output.\nRaw: {stdout[:500]}...\nError: {e}")
            
            return stdout

        except GeminiLauncherError:
            raise  # Re-raise our own errors
        except FileNotFoundError:
             raise GeminiLauncherError(f"Executable '{self._gemini_executable}' not found.")
        except Exception as e:
            raise GeminiLauncherError(f"Unexpected error: {str(e)}")
        finally:
            # 无论成功失败，都从登记册移除进程
            if 'process' in locals():
                _active_processes.discard(process)

# End of file
