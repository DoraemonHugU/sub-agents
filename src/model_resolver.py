"""
模型别名解析器 (Model Resolver)

将模型别名 (auto, pro, flash, flash-lite) 解析为具体模型名称。
复刻自 Gemini CLI 源码 packages/core/src/models.ts
"""

from typing import Dict, Any


def resolve_model(
    alias: str, 
    registry: Dict[str, Any], 
    use_preview: bool = True
) -> str:
    """
    将模型别名解析为具体模型名称。
    
    Args:
        alias: 别名 ('auto', 'pro', 'flash', 'flash-lite') 或具体模型名
        registry: 来自 agents.yaml 的 model_registry
        use_preview: 是否使用预览模型
    
    Returns:
        具体模型名称，如 'gemini-3-flash-preview'
    """
    tier = 'preview' if use_preview else 'stable'
    
    if alias == 'auto':
        return registry.get('auto', {}).get(tier, 'auto')
    elif alias == 'pro':
        return registry.get(tier, {}).get('pro', 'gemini-2.5-pro')
    elif alias == 'flash':
        return registry.get(tier, {}).get('flash', 'gemini-2.5-flash')
    elif alias == 'flash-lite':
        # flash-lite 没有预览版，始终使用 stable
        return registry.get('stable', {}).get('flash_lite', 'gemini-2.5-flash-lite')
    else:
        # 已经是具体名称，直接返回
        return alias
