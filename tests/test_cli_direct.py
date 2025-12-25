"""
Gemini CLI 命令直接测试
测试模型解析后的实际 CLI 调用
"""

import subprocess
import sys
import json


def run_gemini_test(model: str, prompt: str):
    """直接调用 Gemini CLI 测试"""
    cmd = [
        "gemini",
        "--model", model,
        "--output-format", "json",
        prompt
    ]
    
    print(f"\n{'='*60}")
    print(f"测试模型: {model}")
    print(f"提示词: {prompt}")
    print(f"{'='*60}")
    print(f"命令: {' '.join(cmd)}")
    
    try:
        # Windows 下使用 shell=True 确保 PATH 正确解析
        result = subprocess.run(
            " ".join(cmd),
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            shell=True
        )
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                response = data.get("response", "无响应")
                print(f"✅ 响应: {response[:200]}...")
                return True
            except json.JSONDecodeError:
                print(f"✅ 原始输出: {result.stdout[:200]}...")
                return True
        else:
            print(f"❌ 错误: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ 超时 (60s)")
        return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False


def main():
    print("=" * 60)
    print("Gemini CLI 模型测试")
    print("=" * 60)
    
    # 测试 flash 模型
    test_cases = [
        ("gemini-3-flash-preview", "你好，请用一句话介绍你自己"),
    ]
    
    passed = 0
    for model, prompt in test_cases:
        if run_gemini_test(model, prompt):
            passed += 1
    
    print(f"\n{'='*60}")
    print(f"结果: {passed}/{len(test_cases)} 通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
