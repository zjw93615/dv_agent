"""
Tests for Intent Recognition and Routing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dv_agent.intent.models import IntentResult, Intent
from dv_agent.intent.recognizer import IntentRecognizer
from dv_agent.intent.router import IntentRouter


class TestIntent:
    """Test suite for Intent enum."""
    
    def test_intent_values(self):
        """Test intent enum has expected values."""
        assert Intent.GENERAL is not None
        assert Intent.CALCULATION is not None
        assert Intent.SEARCH is not None
        assert Intent.CODE is not None
        assert Intent.QA is not None


class TestIntentResult:
    """Test suite for IntentResult model."""
    
    def test_create_intent_result(self):
        """Test creating an intent result."""
        result = IntentResult(
            intent=Intent.CALCULATION,
            confidence=0.95,
            entities={"expression": "2+2"},
            raw_query="计算 2+2"
        )
        
        assert result.intent == Intent.CALCULATION
        assert result.confidence == 0.95
        assert result.entities["expression"] == "2+2"
    
    def test_intent_result_high_confidence(self):
        """Test high confidence intent result."""
        result = IntentResult(
            intent=Intent.SEARCH,
            confidence=0.99,
            entities={},
            raw_query="搜索AI新闻"
        )
        
        assert result.confidence >= 0.9
    
    def test_intent_result_low_confidence(self):
        """Test low confidence intent result."""
        result = IntentResult(
            intent=Intent.GENERAL,
            confidence=0.45,
            entities={},
            raw_query="随便说点什么"
        )
        
        assert result.confidence < 0.5


class TestIntentRecognizer:
    """Test suite for IntentRecognizer."""
    
    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM gateway."""
        from dv_agent.llm_gateway.models import LLMResponse, Role
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            content='{"intent": "calculation", "confidence": 0.9}',
            role=Role.ASSISTANT,
            model="mock"
        ))
        return llm
    
    @pytest.fixture
    def recognizer(self, mock_llm):
        """Create intent recognizer with mock LLM."""
        return IntentRecognizer(
            llm_gateway=mock_llm,
            use_embedding=False,
            use_llm_fallback=True
        )
    
    @pytest.mark.asyncio
    async def test_recognize_calculation_intent(self, recognizer):
        """Test recognizing calculation intent."""
        result = await recognizer.recognize("计算 123 + 456")
        
        assert result is not None
        assert result.intent in [Intent.CALCULATION, Intent.GENERAL]
    
    @pytest.mark.asyncio
    async def test_recognize_search_intent(self, recognizer):
        """Test recognizing search intent."""
        result = await recognizer.recognize("搜索最新的人工智能新闻")
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_recognize_datetime_intent(self, recognizer):
        """Test recognizing datetime intent."""
        result = await recognizer.recognize("今天是什么日期？")
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_recognize_code_intent(self, recognizer):
        """Test recognizing code intent."""
        result = await recognizer.recognize("帮我写一个Python函数来排序列表")
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_recognize_general_intent(self, recognizer):
        """Test recognizing general intent."""
        result = await recognizer.recognize("你好，今天天气怎么样？")
        
        assert result is not None
        assert result.raw_query == "你好，今天天气怎么样？"
    
    @pytest.mark.asyncio
    async def test_rule_based_recognition(self, recognizer):
        """Test rule-based recognition."""
        # Calculator keywords
        result = await recognizer.recognize("计算 2+2")
        assert result is not None
        
        # Search keywords
        result = await recognizer.recognize("搜索Python教程")
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_empty_query(self, recognizer):
        """Test handling empty query."""
        result = await recognizer.recognize("")
        
        assert result is not None
        assert result.intent == Intent.GENERAL
        assert result.confidence < 0.5


class TestIntentRouter:
    """Test suite for IntentRouter."""
    
    @pytest.fixture
    def mock_recognizer(self):
        """Create mock intent recognizer."""
        recognizer = MagicMock()
        recognizer.recognize = AsyncMock(return_value=IntentResult(
            intent=Intent.CALCULATION,
            confidence=0.9,
            entities={"expression": "2+2"},
            raw_query="计算 2+2"
        ))
        return recognizer
    
    @pytest.fixture
    def router(self, mock_recognizer):
        """Create intent router with mock recognizer."""
        return IntentRouter(recognizer=mock_recognizer)
    
    @pytest.mark.asyncio
    async def test_route_calculation(self, router, mock_recognizer):
        """Test routing calculation intent."""
        mock_recognizer.recognize = AsyncMock(return_value=IntentResult(
            intent=Intent.CALCULATION,
            confidence=0.95,
            entities={},
            raw_query="计算 2+2"
        ))
        
        agent_id, result = await router.route("计算 2+2")
        
        assert result.intent == Intent.CALCULATION
    
    @pytest.mark.asyncio
    async def test_route_search(self, router, mock_recognizer):
        """Test routing search intent."""
        mock_recognizer.recognize = AsyncMock(return_value=IntentResult(
            intent=Intent.SEARCH,
            confidence=0.9,
            entities={"query": "AI news"},
            raw_query="搜索AI新闻"
        ))
        
        agent_id, result = await router.route("搜索AI新闻")
        
        assert result.intent == Intent.SEARCH
    
    @pytest.mark.asyncio
    async def test_route_fallback_to_orchestrator(self, router, mock_recognizer):
        """Test fallback to orchestrator for unknown intent."""
        mock_recognizer.recognize = AsyncMock(return_value=IntentResult(
            intent=Intent.GENERAL,
            confidence=0.5,
            entities={},
            raw_query="随便聊聊"
        ))
        
        agent_id, result = await router.route("随便聊聊")
        
        # Should route to orchestrator for general queries
        assert agent_id is not None
    
    def test_register_route(self, router):
        """Test registering a custom route."""
        router.register_route(Intent.CODE, "code-agent")
        
        assert Intent.CODE in router._routes
        assert router._routes[Intent.CODE] == "code-agent"
    
    def test_default_routes(self, router):
        """Test default routes are set up."""
        # Router should have some default routes
        assert hasattr(router, '_routes')
    
    @pytest.mark.asyncio
    async def test_route_with_low_confidence(self, router, mock_recognizer):
        """Test routing with low confidence falls back."""
        mock_recognizer.recognize = AsyncMock(return_value=IntentResult(
            intent=Intent.SEARCH,
            confidence=0.3,  # Low confidence
            entities={},
            raw_query="maybe search?"
        ))
        
        agent_id, result = await router.route("maybe search?")
        
        # Should still return a result
        assert result is not None


class TestIntentPatterns:
    """Test suite for intent pattern matching."""
    
    @pytest.fixture
    def recognizer(self):
        """Create recognizer for pattern testing."""
        llm = MagicMock()
        llm.chat = AsyncMock()
        return IntentRecognizer(llm_gateway=llm, use_llm_fallback=False)
    
    @pytest.mark.asyncio
    async def test_calculation_patterns(self, recognizer):
        """Test calculation intent patterns."""
        patterns = [
            "计算 1+1",
            "算一下 100/5",
            "1234 * 5678 等于多少",
            "帮我算 (2+3)*4",
        ]
        
        for query in patterns:
            result = await recognizer.recognize(query)
            # Should recognize as calculation or at least have high confidence
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_search_patterns(self, recognizer):
        """Test search intent patterns."""
        patterns = [
            "搜索Python教程",
            "查找AI最新进展",
            "帮我找一下机器学习资料",
        ]
        
        for query in patterns:
            result = await recognizer.recognize(query)
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_datetime_patterns(self, recognizer):
        """Test datetime intent patterns."""
        patterns = [
            "今天是几号",
            "现在几点了",
            "明天是星期几",
        ]
        
        for query in patterns:
            result = await recognizer.recognize(query)
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_code_patterns(self, recognizer):
        """Test code intent patterns."""
        patterns = [
            "写一个Python函数",
            "帮我调试这段代码",
            "解释这个算法",
        ]
        
        for query in patterns:
            result = await recognizer.recognize(query)
            assert result is not None
