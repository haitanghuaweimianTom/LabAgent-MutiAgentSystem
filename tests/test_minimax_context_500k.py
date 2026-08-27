"""MiniMax-M3 + 500K context + 90% auto-compress 集成测试。

覆盖：
1. ProviderConfig 读 MINIMAX_MAX_CONTEXT_LENGTH / MINIMAX_AUTO_COMPRESS_RATIO 环境变量
2. MiniMaxProvider 默认值（500K / 0.9）
3. TokenBudgetManager 接受 max_context_length + auto_compress_ratio
4. AutoCompressHook 在达到 max_context_length × ratio 时触发压缩
5. Per-agent policy 覆盖
6. 不触发时（<90%）保持原样
"""
from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import patch, AsyncMock


# ==================== Provider 层 ====================


class TestMiniMaxProviderConfig:
    def test_minimax_in_provider_type_enum(self):
        from src.llm.base import ProviderType
        assert ProviderType.MINIMAX.value == "minimax"

    def test_provider_config_reads_env(self):
        from src.llm.base import ProviderConfig, ProviderType
        with patch.dict(
            os.environ,
            {
                "MINIMAX_API_KEY": "sk-test",
                "MINIMAX_API_HOST": "https://api.minimaxi.com",
                "MINIMAX_MODEL": "MiniMax-M3",
                "MINIMAX_MAX_CONTEXT_LENGTH": "500000",
                "MINIMAX_AUTO_COMPRESS_RATIO": "0.9",
            },
        ):
            cfg = ProviderConfig.from_env(ProviderType.MINIMAX)
        assert cfg.api_key == "sk-test"
        assert cfg.api_host == "https://api.minimaxi.com"
        assert cfg.model == "MiniMax-M3"
        assert cfg.max_context_length == 500000
        assert cfg.auto_compress_ratio == 0.9

    def test_minimax_provider_defaults(self):
        """MiniMaxProvider 默认 max_context_length=500K, ratio=0.9."""
        from src.llm.providers.minimax_provider import MiniMaxProvider
        from src.llm.base import ProviderConfig, ProviderType
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "sk-test"}, clear=False):
            cfg = ProviderConfig(
                provider_type=ProviderType.MINIMAX,
                name="minimax",
                api_key="sk-test",
                api_host="https://api.minimaxi.com",
                model="MiniMax-M3",
            )
            p = MiniMaxProvider(cfg)
        assert p.config.max_context_length == 500_000
        assert p.config.auto_compress_ratio == 0.9
        assert p.auto_compress_threshold == 450_000

    def test_factory_registers_minimax(self):
        from src.llm.factory import LLMProviderFactory
        from src.llm.base import ProviderType
        assert ProviderType.MINIMAX in LLMProviderFactory._providers


# ==================== Token Budget 层 ====================


class TestTokenBudgetManagerMiniMax:
    def test_default_window_for_minimax_m3(self):
        from backend.app.core.token_budget import MODEL_CONTEXT_WINDOWS
        assert MODEL_CONTEXT_WINDOWS["MiniMax-M3"] == 500_000
        assert MODEL_CONTEXT_WINDOWS["minimax-m3"] == 500_000
        assert MODEL_CONTEXT_WINDOWS["minimax"] == 500_000

    def test_manager_with_custom_max_context(self):
        from backend.app.core.token_budget import TokenBudgetManager
        mgr = TokenBudgetManager.__new__(TokenBudgetManager)
        mgr.__init__(
            model_key="minimax-m3",
            max_context_length=500_000,
            auto_compress_ratio=0.9,
        )
        assert mgr.max_context_length == 500_000
        assert mgr.auto_compress_threshold == 450_000
        assert mgr.total_budget > 0

    def test_manager_reconfigure(self):
        from backend.app.core.token_budget import TokenBudgetManager
        # Singleton: 必须用新实例。先 reset 状态。
        mgr = TokenBudgetManager.__new__(TokenBudgetManager)
        mgr._initialized = False
        mgr.__init__(model_key="default", max_context_length=128_000, auto_compress_ratio=0.9)
        old_threshold = mgr.auto_compress_threshold
        assert old_threshold == 115_200  # 128K × 0.9

        mgr.reconfigure(
            model_key="minimax-m3",
            max_context_length=500_000,
            auto_compress_ratio=0.9,
        )
        assert mgr.auto_compress_threshold == 450_000
        assert mgr.auto_compress_threshold != old_threshold


# ==================== ContextCompressor 层 ====================


class TestContextCompressorPerCallThreshold:
    def test_threshold_uses_max_context_length_when_set(self):
        from backend.app.core.context_compressor import (
            CompressorConfig,
            ContextCompressor,
        )
        cfg = CompressorConfig(
            max_context_length=500_000,
            auto_compress_ratio=0.9,
            threshold_tokens=30_000,
        )
        c = ContextCompressor(cfg)
        # 触发阈值 = 500K × 0.9 = 450K
        assert c.config.auto_compress_threshold == 450_000

    def test_maybe_compress_respects_per_call_threshold(self):
        """传 max_context_length=500, ratio=0.9 → 450 触发；<450 不触发。"""
        from backend.app.core.context_compressor import (
            CompressorConfig,
            ContextCompressor,
        )
        cfg = CompressorConfig(max_context_length=500, auto_compress_ratio=0.9)
        c = ContextCompressor(cfg)

        # <450 tokens: 不触发
        small = {"a": {"x": "hello world " * 20}}  # ~140 tokens
        stats = c.maybe_compress(
            "t1", small, llm_caller=None, max_context_length=500, auto_compress_ratio=0.9
        )
        assert stats.level_used == "none"

        # >450 tokens: 触发
        big = {
            "a": {"x": "lorem ipsum " * 1000},  # ~11K tokens
        }
        stats = c.maybe_compress(
            "t2", big, llm_caller=None, max_context_length=500, auto_compress_ratio=0.9
        )
        assert stats.level_used != "none"
        assert stats.saved_tokens > 0


# ==================== AutoCompressHook 层 ====================


class TestAutoCompressHook:
    def test_default_minimax_config(self):
        """未传 max_context_length 时用 500K / 0.9 默认值。"""
        from backend.app.core.auto_compress_hook import (
            AutoCompressHook,
            AutoCompressConfig,
            DEFAULT_MAX_CONTEXT_LENGTH,
            DEFAULT_AUTO_COMPRESS_RATIO,
        )
        assert DEFAULT_MAX_CONTEXT_LENGTH == 500_000
        assert DEFAULT_AUTO_COMPRESS_RATIO == 0.9

        hook = AutoCompressHook()
        assert hook.config.max_context_length == 500_000
        assert hook.config.auto_compress_ratio == 0.9
        assert hook.config.threshold_tokens == 450_000

    def test_below_threshold_no_compression(self):
        from backend.app.core.auto_compress_hook import AutoCompressHook, AutoCompressConfig
        hook = AutoCompressHook(AutoCompressConfig(max_context_length=500_000))
        results = {"a": {"x": "hi " * 100}}  # ~50 tokens, 远低于 450K
        stats = hook.before_agent("task1", "a", results)
        assert stats.level_used == "none"
        assert stats.original_tokens < 450_000

    def test_above_threshold_triggers_compression(self):
        from backend.app.core.auto_compress_hook import AutoCompressHook, AutoCompressConfig
        from backend.app.core.context_compressor import estimate_tokens
        hook = AutoCompressHook(
            AutoCompressConfig(max_context_length=1000, auto_compress_ratio=0.9)
        )
        # 用更长的 payload（cl100k_base 下"filler "单 token，字符估 1/3 不准）
        # 用 distinct words 让 tiktoken 编码更接近字符数
        big_text = " ".join(f"word{i}" for i in range(1500))  # ~3000 tokens
        big_payload = {"a": {"x": big_text}}
        results = {"a": big_payload}
        actual_tokens = sum(estimate_tokens(out) for out in results.values())
        assert actual_tokens > 900, f"payload only {actual_tokens} tokens"
        stats = hook.before_agent("task1", "a", results)
        assert stats.level_used != "none"
        assert stats.original_tokens > 900

    def test_per_agent_policy_override(self):
        """特定 Agent 可以单独设置更小的 max_context_length。"""
        from backend.app.core.auto_compress_hook import (
            AutoCompressHook,
            AutoCompressConfig,
            AgentContextPolicy,
        )
        cfg = AutoCompressConfig(
            max_context_length=500_000,
            auto_compress_ratio=0.9,
            agent_policies={
                "writer": AgentContextPolicy(max_context_length=100, auto_compress_ratio=0.9),
            },
        )
        hook = AutoCompressHook(cfg)
        # writer 阈值 = 100 × 0.9 = 90 tokens
        results = {"writer": {"x": "filler " * 100}}  # ~600 tokens
        stats = hook.before_agent("task1", "writer", results)
        assert stats.level_used != "none"  # writer 应该触发

        # 同一 hook 下，普通 agent 默认 500K 阈值，不触发
        results2 = {"other": {"x": "filler " * 100}}
        stats2 = hook.before_agent("task1", "other", results2)
        assert stats2.level_used == "none"

    def test_configure_minimax_helper(self):
        from backend.app.core.auto_compress_hook import AutoCompressHook
        hook = AutoCompressHook()
        hook.configure_minimax()
        assert hook.config.max_context_length == 500_000
        assert hook.config.auto_compress_ratio == 0.9

    def test_protected_fields_preserved(self):
        """压缩时 protected 字段（latex_code / title 等）必须保留原值。"""
        from backend.app.core.auto_compress_hook import (
            AutoCompressHook,
            AutoCompressConfig,
        )
        hook = AutoCompressHook(
            AutoCompressConfig(max_context_length=100, auto_compress_ratio=0.9)
        )
        big_latex = "x" * 50_000
        results = {
            "writer": {
                "latex_code": big_latex,
                "title": "My Paper",
                "raw_response": "y" * 50_000,  # 应被压缩
            }
        }
        stats = hook.before_agent("task1", "writer", results)
        assert results["writer"]["latex_code"] == big_latex  # 保留
        assert results["writer"]["title"] == "My Paper"  # 保留


# ==================== 真实 API 烟雾测试 ====================


@pytest.mark.skipif(
    "sk-cp-sxw2xgI88b" not in os.environ.get("MINIMAX_API_KEY", ""),
    reason="MiniMax API key not set",
)
class TestMiniMaxLiveAPI:
    """真实 API 烟雾测试（需要 key 才跑）。"""

    @pytest.mark.asyncio
    async def test_minimax_generate_async(self):
        from src.llm.providers.minimax_provider import MiniMaxProvider
        from src.llm.base import ProviderConfig, ProviderType

        cfg = ProviderConfig(
            provider_type=ProviderType.MINIMAX,
            name="minimax",
            api_key=os.environ["MINIMAX_API_KEY"],
            api_host="https://api.minimaxi.com",
            model="MiniMax-M3",
            timeout=15,
        )
        provider = MiniMaxProvider(cfg)
        assert provider.auto_compress_threshold == 450_000
        # 注意：M3 是 thinking 模型，max_tokens 必须够 reasoning + 实际输出
        resp = await provider.generate_async(
            prompt="Say 'ok' in one word",
            max_tokens=200,
        )
        assert resp.content, f"empty content, finish_reason={resp.raw_response.get('choices', [{}])[0].get('finish_reason')}"
        assert resp.usage.get("total_tokens", 0) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
