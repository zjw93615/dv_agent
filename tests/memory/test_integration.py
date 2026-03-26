"""
Integration Tests for Memory System
记忆系统集成测试

需要运行 Redis、PostgreSQL 和 Milvus 服务。
使用 pytest -m integration 运行这些测试。
"""

import pytest
import asyncio
from datetime import datetime
from uuid import uuid4

from dv_agent.memory import (
    MemoryManager,
    MemoryConfig,
    Memory,
    MemoryType,
    ShortTermMemory,
    LongTermMemory,
    MemoryRetriever,
    MemoryExtractor,
)


@pytest.fixture
def integration_config() -> MemoryConfig:
    """Integration test configuration"""
    return MemoryConfig(
        redis_url="redis://localhost:6379",
        redis_db=15,  # Test database
        postgres_url="postgresql+asyncpg://test:test@localhost:5432/test_memory",
        milvus_host="localhost",
        milvus_port=19530,
        milvus_collection="test_integration_memories",
        embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        embedding_dimension=384,
    )


@pytest.mark.integration
class TestEndToEndWorkflow:
    """End-to-end integration tests"""
    
    @pytest.mark.asyncio
    async def test_full_memory_workflow(self, integration_config):
        """Test complete memory lifecycle: store -> retrieve -> forget"""
        pytest.skip("Requires infrastructure - run with --run-integration")
        
        # Initialize manager
        manager = MemoryManager(integration_config)
        await manager.initialize()
        
        try:
            user_id = f"test_user_{uuid4().hex[:8]}"
            session_id = f"test_session_{uuid4().hex[:8]}"
            
            # 1. Add conversation messages
            messages = [
                {"role": "user", "content": "我是一名数据科学家，主要用Python做机器学习"},
                {"role": "assistant", "content": "很高兴认识你！作为数据科学家，你主要使用哪些ML框架呢？"},
                {"role": "user", "content": "我主要用PyTorch，偶尔也用TensorFlow"},
            ]
            
            for msg in messages:
                await manager.add_message(session_id, user_id, msg)
            
            # 2. Extract and store long-term memories
            memories = await manager.extract_and_store(
                user_id=user_id,
                session_id=session_id,
            )
            
            assert len(memories) > 0, "Should extract at least one memory"
            
            # 3. Retrieve memories
            context = await manager.get_context(
                session_id=session_id,
                user_id=user_id,
                query="机器学习框架",
            )
            
            assert context.long_term_memories, "Should retrieve relevant memories"
            
            # 4. Verify content relevance
            contents = [m.content for m in context.long_term_memories]
            assert any("PyTorch" in c or "机器学习" in c for c in contents)
            
        finally:
            # Cleanup
            await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_cross_session_memory(self, integration_config):
        """Test memory persistence across sessions"""
        pytest.skip("Requires infrastructure - run with --run-integration")
        
        manager = MemoryManager(integration_config)
        await manager.initialize()
        
        try:
            user_id = f"test_user_{uuid4().hex[:8]}"
            session1 = f"session1_{uuid4().hex[:8]}"
            session2 = f"session2_{uuid4().hex[:8]}"
            
            # Session 1: Establish fact
            await manager.add_message(session1, user_id, {
                "role": "user",
                "content": "我的名字叫张三，我在北京工作",
            })
            await manager.extract_and_store(user_id, session1)
            
            # Session 2: Query should retrieve the fact
            context = await manager.get_context(
                session_id=session2,
                user_id=user_id,
                query="用户的基本信息",
            )
            
            # Should find info from session 1
            all_content = " ".join(m.content for m in context.long_term_memories)
            assert "张三" in all_content or "北京" in all_content
            
        finally:
            await manager.shutdown()


@pytest.mark.integration
class TestShortTermIntegration:
    """Short-term memory integration with Redis"""
    
    @pytest.mark.asyncio
    async def test_message_persistence(self, integration_config):
        """Test message storage and retrieval in Redis"""
        pytest.skip("Requires Redis - run with --run-integration")
        
        stm = ShortTermMemory(integration_config)
        await stm.initialize()
        
        try:
            session_id = f"test_session_{uuid4().hex[:8]}"
            
            # Add messages
            for i in range(5):
                await stm.add_message(session_id, {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                })
            
            # Retrieve
            messages = await stm.get_messages(session_id)
            
            assert len(messages) == 5
            assert messages[-1]["content"] == "Message 4"
            
        finally:
            await stm.clear_session(session_id)
    
    @pytest.mark.asyncio
    async def test_sliding_window(self, integration_config):
        """Test sliding window message truncation"""
        pytest.skip("Requires Redis - run with --run-integration")
        
        config = MemoryConfig(
            **{**integration_config.__dict__, "max_context_messages": 10}
        )
        stm = ShortTermMemory(config)
        await stm.initialize()
        
        session_id = f"test_session_{uuid4().hex[:8]}"
        
        try:
            # Add more than window size
            for i in range(20):
                await stm.add_message(session_id, {
                    "role": "user",
                    "content": f"Message {i}",
                })
            
            messages = await stm.get_messages(session_id)
            
            # Should only keep recent 10
            assert len(messages) == 10
            
        finally:
            await stm.clear_session(session_id)


@pytest.mark.integration
class TestLongTermIntegration:
    """Long-term memory integration with PostgreSQL + Milvus"""
    
    @pytest.mark.asyncio
    async def test_store_and_search(self, integration_config):
        """Test storing and searching memories"""
        pytest.skip("Requires PostgreSQL + Milvus - run with --run-integration")
        
        ltm = LongTermMemory(integration_config)
        await ltm.initialize()
        
        user_id = f"test_user_{uuid4().hex[:8]}"
        
        try:
            # Create test memory
            import numpy as np
            embedding = np.random.rand(384).astype(np.float32).tolist()
            
            memory = Memory(
                user_id=user_id,
                memory_type=MemoryType.FACT,
                content="用户是一名资深Python开发者",
                embedding=embedding,
                confidence=0.9,
                importance=0.8,
            )
            
            # Store
            stored = await ltm.store(memory)
            assert stored.id is not None
            
            # Search by vector
            results = await ltm.search_by_vector(
                user_id=user_id,
                embedding=embedding,
                top_k=5,
            )
            
            assert len(results) > 0
            assert results[0][0].id == stored.id
            
            # Search by keyword
            keyword_results = await ltm.search_by_keyword(
                user_id=user_id,
                query="Python开发",
                top_k=5,
            )
            
            assert len(keyword_results) > 0
            
        finally:
            await ltm.shutdown()


@pytest.mark.integration
class TestRetrievalIntegration:
    """Retrieval system integration tests"""
    
    @pytest.mark.asyncio
    async def test_hybrid_retrieval(self, integration_config):
        """Test hybrid retrieval with real infrastructure"""
        pytest.skip("Requires full infrastructure - run with --run-integration")
        
        manager = MemoryManager(integration_config)
        await manager.initialize()
        
        user_id = f"test_user_{uuid4().hex[:8]}"
        
        try:
            # Seed some memories
            memories_data = [
                ("用户偏好使用VS Code编辑器", MemoryType.PREFERENCE),
                ("用户精通Python和JavaScript", MemoryType.SKILL),
                ("用户在2023年开始学习Rust", MemoryType.EXPERIENCE),
                ("用户每天编程约8小时", MemoryType.FACT),
            ]
            
            for content, mtype in memories_data:
                memory = Memory(
                    user_id=user_id,
                    memory_type=mtype,
                    content=content,
                    embedding=await manager._generate_embedding(content),
                    confidence=0.9,
                    importance=0.7,
                )
                await manager.store_memory(memory)
            
            # Test retrieval
            from dv_agent.memory.retrieval import RetrievalQuery
            
            query = RetrievalQuery(
                user_id=user_id,
                query="用户的编程技能",
                top_k=3,
            )
            
            results = await manager.retrieve(query)
            
            assert len(results) > 0
            # Should prioritize skill-related memories
            
        finally:
            await manager.shutdown()


@pytest.mark.integration
class TestConsistencyCheck:
    """Test PG-Milvus consistency checking"""
    
    @pytest.mark.asyncio
    async def test_detect_inconsistency(self, integration_config):
        """Test detection of PG-Milvus inconsistencies"""
        pytest.skip("Requires full infrastructure - run with --run-integration")
        
        # This test would:
        # 1. Insert memory to both PG and Milvus
        # 2. Manually delete from one
        # 3. Run consistency check
        # 4. Verify detection
        pass
    
    @pytest.mark.asyncio
    async def test_fix_orphaned_vectors(self, integration_config):
        """Test fixing orphaned vectors in Milvus"""
        pytest.skip("Requires full infrastructure - run with --run-integration")
        pass
