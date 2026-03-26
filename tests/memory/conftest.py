"""
Pytest Fixtures for Memory System Tests
"""

import asyncio
from datetime import datetime
from typing import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from dv_agent.memory.config import MemoryConfig
from dv_agent.memory.models import Memory, MemoryType, MemoryRelation, RelationType


# ========== Event Loop Fixture ==========

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ========== Configuration Fixtures ==========

@pytest.fixture
def memory_config() -> MemoryConfig:
    """Test configuration"""
    return MemoryConfig(
        # Redis
        redis_url="redis://localhost:6379",
        redis_db=15,  # Use test database
        
        # PostgreSQL
        postgres_url="postgresql+asyncpg://test:test@localhost:5432/test_memory",
        
        # Milvus
        milvus_host="localhost",
        milvus_port=19530,
        milvus_collection="test_memories",
        
        # 短期记忆
        short_term_ttl=60,
        max_context_messages=10,
        
        # 长期记忆
        embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        embedding_dimension=384,
        
        # 生命周期
        importance_decay_lambda=0.1,
        soft_forget_days=3,
        archive_days=7,
        hard_delete_days=14,
    )


# ========== Mock Fixtures ==========

@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = AsyncMock()
    redis.lpush = AsyncMock(return_value=1)
    redis.lrange = AsyncMock(return_value=[])
    redis.ltrim = AsyncMock()
    redis.expire = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.pipeline = MagicMock()
    redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=redis)
    redis.pipeline.return_value.__aexit__ = AsyncMock()
    return redis


@pytest.fixture
def mock_postgres_session():
    """Mock PostgreSQL async session"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_milvus():
    """Mock Milvus client"""
    milvus = MagicMock()
    milvus.insert = MagicMock(return_value=MagicMock(primary_keys=[1, 2, 3]))
    milvus.search = MagicMock(return_value=[[]])
    milvus.delete = MagicMock()
    milvus.flush = MagicMock()
    return milvus


@pytest.fixture
def mock_embedding_model():
    """Mock sentence transformer"""
    import numpy as np
    
    model = MagicMock()
    model.encode = MagicMock(
        return_value=np.random.rand(384).astype(np.float32)
    )
    return model


@pytest.fixture
def mock_llm():
    """Mock LLM for extraction"""
    llm = AsyncMock()
    llm.acomplete = AsyncMock(
        return_value=MagicMock(
            text='[{"content": "用户喜欢Python", "type": "preference", "confidence": 0.9}]'
        )
    )
    return llm


# ========== Sample Data Fixtures ==========

@pytest.fixture
def sample_memory() -> Memory:
    """Sample memory object"""
    return Memory(
        id=uuid4(),
        user_id="test_user",
        memory_type=MemoryType.FACT,
        content="用户是一名软件工程师",
        embedding=[0.1] * 384,
        confidence=0.95,
        importance=0.8,
        source_session_id="session_001",
        access_count=5,
        metadata={"extracted_from": "user_profile"},
    )


@pytest.fixture
def sample_memories() -> list[Memory]:
    """Multiple sample memories"""
    base_time = datetime.utcnow()
    return [
        Memory(
            id=uuid4(),
            user_id="test_user",
            memory_type=MemoryType.FACT,
            content="用户是一名Python开发者",
            embedding=[0.1] * 384,
            confidence=0.9,
            importance=0.85,
        ),
        Memory(
            id=uuid4(),
            user_id="test_user",
            memory_type=MemoryType.PREFERENCE,
            content="用户偏好使用VS Code编辑器",
            embedding=[0.2] * 384,
            confidence=0.85,
            importance=0.7,
        ),
        Memory(
            id=uuid4(),
            user_id="test_user",
            memory_type=MemoryType.EXPERIENCE,
            content="用户曾参与过大型分布式系统开发",
            embedding=[0.3] * 384,
            confidence=0.8,
            importance=0.9,
        ),
        Memory(
            id=uuid4(),
            user_id="test_user",
            memory_type=MemoryType.SKILL,
            content="用户精通异步编程和并发处理",
            embedding=[0.4] * 384,
            confidence=0.88,
            importance=0.75,
        ),
    ]


@pytest.fixture
def sample_relations(sample_memories) -> list[MemoryRelation]:
    """Sample memory relations"""
    return [
        MemoryRelation(
            source_id=sample_memories[0].id,
            target_id=sample_memories[2].id,
            relation_type=RelationType.SUPPORTS,
            strength=0.8,
        ),
        MemoryRelation(
            source_id=sample_memories[1].id,
            target_id=sample_memories[0].id,
            relation_type=RelationType.RELATED,
            strength=0.6,
        ),
    ]


@pytest.fixture
def sample_messages() -> list[dict]:
    """Sample conversation messages"""
    return [
        {
            "role": "user",
            "content": "你好，我是一名Python开发者",
            "timestamp": datetime.utcnow().isoformat(),
        },
        {
            "role": "assistant",
            "content": "你好！很高兴认识你。作为Python开发者，你主要从事什么方向的开发呢？",
            "timestamp": datetime.utcnow().isoformat(),
        },
        {
            "role": "user",
            "content": "我主要做后端开发，喜欢用FastAPI",
            "timestamp": datetime.utcnow().isoformat(),
        },
        {
            "role": "assistant",
            "content": "FastAPI是个很好的选择！异步支持和类型提示做得很好。",
            "timestamp": datetime.utcnow().isoformat(),
        },
    ]


# ========== Integration Test Markers ==========

def pytest_configure(config):
    """Configure custom markers"""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (need infrastructure)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


# ========== Test Helpers ==========

class MemoryTestHelper:
    """Helper class for memory tests"""
    
    @staticmethod
    def create_memory(
        user_id: str = "test_user",
        memory_type: MemoryType = MemoryType.FACT,
        content: str = "Test memory",
        importance: float = 0.5,
        **kwargs
    ) -> Memory:
        """Create a memory with defaults"""
        return Memory(
            id=kwargs.get("id", uuid4()),
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            embedding=kwargs.get("embedding", [0.0] * 384),
            confidence=kwargs.get("confidence", 0.8),
            importance=importance,
            **{k: v for k, v in kwargs.items() if k not in ["id", "embedding", "confidence"]}
        )
    
    @staticmethod
    async def populate_memories(storage, memories: list[Memory]):
        """Bulk insert memories for testing"""
        for memory in memories:
            await storage.store(memory)


@pytest.fixture
def memory_helper() -> MemoryTestHelper:
    """Provide test helper"""
    return MemoryTestHelper()
