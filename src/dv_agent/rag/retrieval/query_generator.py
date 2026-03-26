"""
Multi-Query Generator for RAG-Fusion

使用LLM生成多个查询变体，扩展检索覆盖面。

核心功能：
1. 视角扩展：从不同角度重述问题
2. 关键词提取：提取核心概念
3. 假设文档：生成理想答案的假设描述（HyDE）
"""

import asyncio
import logging
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueryExpansionConfig:
    """查询扩展配置"""
    num_variations: int = 3           # 生成变体数量
    include_original: bool = True      # 是否包含原始查询
    use_hyde: bool = False             # 是否使用HyDE
    max_query_length: int = 200        # 最大查询长度
    language: str = "auto"             # 语言（auto自动检测）
    

class QueryGenerator:
    """
    多查询生成器
    
    支持三种模式：
    1. LLM驱动：使用大模型生成语义变体
    2. 规则驱动：基于规则的简单变换
    3. 混合模式：结合两者
    """
    
    # 查询扩展的Prompt模板
    EXPANSION_PROMPT_CN = """你是一个查询扩展专家。给定一个用户问题，生成{num}个不同角度的相关查询。

原始问题：{query}

要求：
1. 每个变体应从不同视角表达相同意图
2. 保持语义相关但用词多样化
3. 可以分解复杂问题为子问题
4. 每行一个查询，不要编号

生成的查询："""

    EXPANSION_PROMPT_EN = """You are a query expansion expert. Given a user question, generate {num} related queries from different perspectives.

Original question: {query}

Requirements:
1. Each variation should express the same intent from a different angle
2. Keep semantically related but use diverse vocabulary
3. Complex questions can be decomposed into sub-questions
4. One query per line, no numbering

Generated queries:"""

    HYDE_PROMPT_CN = """假设你正在回答以下问题。请写一段简短的假设性答案（50-100字），包含可能出现在真实答案文档中的关键信息。

问题：{query}

假设性答案："""

    HYDE_PROMPT_EN = """Suppose you are answering the following question. Write a brief hypothetical answer (50-100 words) containing key information that might appear in the actual answer document.

Question: {query}

Hypothetical answer:"""
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        config: Optional[QueryExpansionConfig] = None
    ):
        """
        初始化
        
        Args:
            llm_client: LLM客户端（需要有 agenerate 方法）
            config: 扩展配置
        """
        self.llm = llm_client
        self.config = config or QueryExpansionConfig()
        self._cache: Dict[str, List[str]] = {}  # 简单缓存
        
    async def generate(
        self,
        query: str,
        num_variations: Optional[int] = None,
        use_hyde: Optional[bool] = None
    ) -> List[str]:
        """
        生成查询变体
        
        Args:
            query: 原始查询
            num_variations: 变体数量（覆盖配置）
            use_hyde: 是否使用HyDE（覆盖配置）
            
        Returns:
            查询列表（包含原始查询和变体）
        """
        num = num_variations or self.config.num_variations
        hyde = use_hyde if use_hyde is not None else self.config.use_hyde
        
        # 检查缓存
        cache_key = f"{query}_{num}_{hyde}"
        if cache_key in self._cache:
            logger.debug(f"Query expansion cache hit: {query[:50]}")
            return self._cache[cache_key]
        
        queries = []
        
        # 原始查询
        if self.config.include_original:
            queries.append(query)
        
        # LLM驱动扩展
        if self.llm:
            try:
                variations = await self._llm_expand(query, num)
                queries.extend(variations)
            except Exception as e:
                logger.warning(f"LLM expansion failed, falling back to rules: {e}")
                variations = self._rule_based_expand(query, num)
                queries.extend(variations)
        else:
            # 规则驱动扩展
            variations = self._rule_based_expand(query, num)
            queries.extend(variations)
        
        # HyDE扩展
        if hyde and self.llm:
            try:
                hyde_query = await self._hyde_expand(query)
                if hyde_query:
                    queries.append(hyde_query)
            except Exception as e:
                logger.warning(f"HyDE expansion failed: {e}")
        
        # 去重和截断
        queries = self._deduplicate(queries)
        queries = [q[:self.config.max_query_length] for q in queries]
        
        # 缓存结果
        self._cache[cache_key] = queries
        
        logger.info(f"Generated {len(queries)} queries for: {query[:50]}...")
        return queries
    
    async def _llm_expand(self, query: str, num: int) -> List[str]:
        """使用LLM扩展查询"""
        # 检测语言
        is_chinese = self._detect_chinese(query)
        prompt_template = self.EXPANSION_PROMPT_CN if is_chinese else self.EXPANSION_PROMPT_EN
        
        prompt = prompt_template.format(query=query, num=num)
        
        # 调用LLM
        response = await self.llm.agenerate(prompt)
        
        # 解析响应
        lines = response.strip().split('\n')
        variations = []
        
        for line in lines:
            line = line.strip()
            # 移除可能的编号
            line = re.sub(r'^[\d]+[.、)]\s*', '', line)
            if line and line != query and len(line) > 3:
                variations.append(line)
                
        return variations[:num]
    
    async def _hyde_expand(self, query: str) -> Optional[str]:
        """使用HyDE生成假设文档"""
        is_chinese = self._detect_chinese(query)
        prompt_template = self.HYDE_PROMPT_CN if is_chinese else self.HYDE_PROMPT_EN
        
        prompt = prompt_template.format(query=query)
        
        response = await self.llm.agenerate(prompt)
        
        # 清理响应
        hyde_text = response.strip()
        if len(hyde_text) > 20:  # 确保有足够内容
            return hyde_text
        return None
    
    def _rule_based_expand(self, query: str, num: int) -> List[str]:
        """
        基于规则的查询扩展
        
        策略：
        1. 关键词重组
        2. 同义词替换（简化版）
        3. 问句变换
        """
        variations = []
        is_chinese = self._detect_chinese(query)
        
        if is_chinese:
            variations.extend(self._expand_chinese(query))
        else:
            variations.extend(self._expand_english(query))
        
        return variations[:num]
    
    def _expand_chinese(self, query: str) -> List[str]:
        """中文查询扩展规则"""
        variations = []
        
        # 问句变换
        question_words = ['什么', '如何', '怎么', '为什么', '哪些', '哪个']
        for qw in question_words:
            if qw in query:
                # 问题->陈述
                statement = query.replace(qw, '').replace('？', '').replace('?', '')
                if statement.strip():
                    variations.append(statement.strip())
                break
        
        # 添加常见前缀
        prefixes = ['关于', '有关', '介绍']
        for prefix in prefixes:
            if not query.startswith(prefix):
                new_query = f"{prefix}{query}"
                if new_query not in variations:
                    variations.append(new_query)
                break
        
        # 关键词提取（简单版：移除停用词）
        stopwords = {'的', '了', '是', '在', '有', '和', '与', '或', '等'}
        keywords = [w for w in query if w not in stopwords and len(w.strip()) > 0]
        if keywords:
            keyword_query = ''.join(keywords)
            if keyword_query != query and len(keyword_query) > 2:
                variations.append(keyword_query)
        
        return variations
    
    def _expand_english(self, query: str) -> List[str]:
        """英文查询扩展规则"""
        variations = []
        query_lower = query.lower()
        
        # 问句变换
        if query_lower.startswith(('what ', 'how ', 'why ', 'when ', 'where ')):
            # 移除问句词
            words = query.split()[1:]
            if words:
                statement = ' '.join(words).rstrip('?')
                variations.append(statement)
        
        # 添加上下文词
        if not query_lower.startswith(('explain ', 'describe ')):
            variations.append(f"explain {query}")
        
        # 关键词版本（移除常见词）
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'to', 'of', 'and', 'or', 'in', 'on', 'at'}
        words = query.lower().split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        if keywords and len(keywords) < len(words):
            keyword_query = ' '.join(keywords)
            variations.append(keyword_query)
        
        return variations
    
    def _detect_chinese(self, text: str) -> bool:
        """检测是否包含中文"""
        if self.config.language == "zh":
            return True
        elif self.config.language == "en":
            return False
        
        # 自动检测
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        return chinese_chars > len(text) * 0.3
    
    def _deduplicate(self, queries: List[str]) -> List[str]:
        """去重，保持顺序"""
        seen = set()
        result = []
        for q in queries:
            q_normalized = q.lower().strip()
            if q_normalized not in seen:
                seen.add(q_normalized)
                result.append(q)
        return result
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()


# 便捷函数
async def expand_query(
    query: str,
    llm_client: Optional[Any] = None,
    num_variations: int = 3
) -> List[str]:
    """
    快速查询扩展
    
    Args:
        query: 原始查询
        llm_client: LLM客户端（可选）
        num_variations: 变体数量
        
    Returns:
        扩展后的查询列表
    """
    generator = QueryGenerator(llm_client=llm_client)
    return await generator.generate(query, num_variations=num_variations)
