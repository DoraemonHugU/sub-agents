# 示例配置文件

本目录包含 MCP 配置示例，帮助你快速配置 Sub-Agents 服务。

## 文件说明

| 文件 | 说明 |
|------|------|
| `mcp_config.stdio.example.json` | **STDIO 模式配置**（推荐）<br>通过标准输入输出通信，配置简单 |
| `mcp_config.sse.example.json` | **SSE 模式配置**<br>通过 HTTP 通信，适用于远程部署或多客户端场景 |

## 使用方法

### STDIO 模式

1. 复制 `mcp_config.stdio.example.json` 到你的 IDE 配置目录
2. 修改以下路径：
   - `command`: Python 解释器路径
   - `args[0]`: `server.py` 的绝对路径
   - `SUB_AGENT_CWD`: 你的项目工作目录

### SSE 模式

1. 先启动 HTTP 服务器：
   ```bash
   python src/server.py --transport http --host 127.0.0.1 --port 8000
   ```

2. 复制 `mcp_config.sse.example.json` 到你的 IDE 配置目录

3. 修改 `X-Sub-Agent-Config` Header 中的 JSON 配置

## 注意事项

- **路径分隔符**: Windows 下建议使用正斜杠 `/` 或双反斜杠 `\\`
- **SSE 模式需要转义**: Header 中的 JSON 需要转义双引号 (`\"`)
- **IDE 兼容性**: 详见主目录 README.md 中的 IDE 兼容性说明
