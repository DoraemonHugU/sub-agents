import json

# ============================================================
# 在这里配置你想要的参数
# ============================================================
config = {
    "SUB_AGENT_CWD": "D:/xuexi/projects/deeplearn/shujishibie",
    "USE_PREVIEW_MODELS": "true",
    "GEMINI_MODEL_ALIAS_AUTO": "auto",
    "GEMINI_MODEL_ALIAS_PRO": "pro",
    "GEMINI_MODEL_ALIAS_FLASH": "flash",
    "GEMINI_MODEL_ALIAS_FLASH_LITE": "flash-lite",
    "GEMINI_TIMEOUT": "360"
}
# ============================================================

def generate_header_string(config_dict):
    # 第一步：转成 JSON 字符串
    json_str = json.dumps(config_dict, ensure_ascii=False)
    
    # 第二步：再次转 JSON (这次是为了转义引号)
    # 也可以手动 replace('"', '\\"')，但 json.dumps 最稳
    escaped_json_str = json.dumps(json_str) 
    
    # 去掉最外层的引号（因为 json.dumps 会加上）
    # 我们只需要里面的内容： \"key\": \"value\"...
    inner_content = escaped_json_str[1:-1]
    
    print("\n请复制以下内容到 mcp_config.json 的 headers 中：\n")
    print(f'"X-Sub-Agent-Config": "{inner_content}"')
    
    print("\n或者直接复制这一行 Value：\n")
    print(inner_content)

if __name__ == "__main__":
    generate_header_string(config)
