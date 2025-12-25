"""
模型解析器单元测试
直接测试 model_resolver.py 的解析逻辑，不依赖 MCP
"""

from src.model_resolver import resolve_model

# 模拟 agents.yaml 中的 model_registry
MOCK_REGISTRY = {
    "preview": {
        "pro": "gemini-3-pro-preview",
        "flash": "gemini-3-flash-preview"
    },
    "stable": {
        "pro": "gemini-2.5-pro",
        "flash": "gemini-2.5-flash",
        "flash_lite": "gemini-2.5-flash-lite"
    },
    "auto": {
        "preview": "auto-gemini-3",
        "stable": "auto-gemini-2.5"
    }
}


def test_resolve_model():
    print("=" * 60)
    print("模型解析器单元测试")
    print("=" * 60)
    
    test_cases = [
        # (alias, use_preview, expected)
        ("auto", True, "auto-gemini-3"),
        ("auto", False, "auto-gemini-2.5"),
        ("pro", True, "gemini-3-pro-preview"),
        ("pro", False, "gemini-2.5-pro"),
        ("flash", True, "gemini-3-flash-preview"),
        ("flash", False, "gemini-2.5-flash"),
        ("flash-lite", True, "gemini-2.5-flash-lite"),  # 无预览版
        ("flash-lite", False, "gemini-2.5-flash-lite"),
        ("gemini-2.5-flash", True, "gemini-2.5-flash"),  # 已是具体名
    ]
    
    passed = 0
    failed = 0
    
    for alias, use_preview, expected in test_cases:
        result = resolve_model(alias, MOCK_REGISTRY, use_preview)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        preview_str = "preview" if use_preview else "stable"
        print(f"{status} resolve_model('{alias}', {preview_str}) = '{result}'")
        if result != expected:
            print(f"   期望: '{expected}'")
    
    print()
    print(f"结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    success = test_resolve_model()
    exit(0 if success else 1)
