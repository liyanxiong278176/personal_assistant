"""Automatic memory injection for Agent Core.

This module provides intelligent memory injection based on user input,
automatically retrieving relevant memories from semantic memory to
enhance conversation context.

The MemoryInjector extracts keywords from user input and uses them
to search for relevant semantic memories, providing contextual
information to the LLM for better responses.
"""

import logging
import re
from typing import List

from app.core.memory.hierarchy import MemoryHierarchy, MemoryItem

logger = logging.getLogger(__name__)


# Common Chinese stopwords to filter out
CHINESE_STOPWORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "什么", "吗", "呢", "吧", "啊", "哦", "嗯",
    "还", "可以", "这个", "那个", "能", "想", "让", "给", "对", "把", "从",
    "为", "被", "向", "以", "于", "跟", "与", "及", "等", "或", "但是", "因为",
    "所以", "如果", "虽然", "但是", "而且", "然后", "之后", "之前", "的时候",
    "吗呢吧啊哦呀哪", "怎么", "怎样", "如何", "为什么", "哪", "些", "谁", "几",
    "多", "少", "大", "小", "高", "低", "长", "短", "新", "旧", "好", "坏",
    "请", "谢谢", "麻烦", "帮忙", "需要", "希望", "打算", "准备", "正在",
}

# Common English stopwords to filter out
ENGLISH_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "can", "to", "of", "in", "on",
    "at", "by", "for", "with", "from", "about", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just", "i", "you",
    "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "its", "our", "their", "this", "that", "these", "those", "am", "isn't",
    "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't", "don't", "doesn't",
    "didn't", "won't", "wouldn't", "couldn't", "shouldn't", "can't", "couldn't",
    "mustn't", "mightn't", "shan't", "needn't", "daren't", "mayn't", "let's", "that's",
    "who's", "what's", "here's", "there's", "when's", "where's", "why's", "how's",
    "i'm", "you're", "he's", "she's", "it's", "we're", "they're", "i've", "you've",
    "we've", "they've", "i'd", "you'd", "he'd", "she'd", "it'd", "we'd", "they'd",
    "i'll", "you'll", "he'll", "she'll", "it'll", "we'll", "they'll", "isn", "aren",
    "wasn", "weren", "haven", "hasn", "hadn", "don", "doesn", "didn", "won", "wouldn",
    "couldn", "shouldn", "can", "couldn", "mustn", "mightn", "shan", "needn", "daren",
    "mayn", "ll", "ve", "re", "d", "s", "t",
}


class MemoryInjector:
    """Automatic memory injection based on user input keywords.

    This class analyzes user input to extract relevant keywords and
    retrieves related memories from semantic memory, building context
    for the LLM to provide more personalized responses.

    Example usage:
        ```python
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        # Add some semantic memories
        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.PREFERENCE
        ))

        # Inject relevant memories
        context = injector.build_memory_context("我想去北京旅游")
        # context will contain information about user's Beijing preference
        ```
    """

    def __init__(self, hierarchy: MemoryHierarchy):
        """Initialize the memory injector.

        Args:
            hierarchy: MemoryHierarchy instance to retrieve memories from
        """
        self._hierarchy = hierarchy
        # Chinese word pattern: match consecutive Chinese characters (2+ chars)
        # We'll split the text into individual words in extract_keywords
        self._chinese_char_pattern = re.compile(r'[\u4e00-\u9fff]+')
        self._english_pattern = re.compile(r'\b[a-zA-Z]{3,}\b')
        self._number_pattern = re.compile(r'\d+')

    def extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for memory retrieval.

        Extracts Chinese words (2+ characters) and English words (3+ characters)
        while filtering out common stopwords.

        Args:
            text: Input text to extract keywords from

        Returns:
            List of extracted keywords (lowercase, deduplicated)

        Examples:
            >>> injector.extract_keywords("我想去北京旅游")
            ['北京', '旅游']
            >>> injector.extract_keywords("I want to visit Beijing")
            ['want', 'visit', 'beijing']
        """
        if not text:
            return []

        keywords = set()

        # Extract Chinese words
        chinese_matches = self._chinese_char_pattern.findall(text)
        for word in chinese_matches:
            if word not in CHINESE_STOPWORDS:
                keywords.add(word)

        # Extract English words
        english_matches = self._english_pattern.findall(text)
        for word in english_matches:
            word_lower = word.lower()
            if word_lower not in ENGLISH_STOPWORDS:
                keywords.add(word_lower)

        # Extract numbers (dates, budgets, etc.)
        number_matches = self._number_pattern.findall(text)
        for number in number_matches:
            keywords.add(number)

        result = sorted(list(keywords))

        logger.debug(
            f"[MemoryInjector] Extracted {len(result)} keywords from '{text[:50]}...': {result}"
        )

        return result

    def get_relevant_memories(
        self,
        user_input: str,
        max_memories: int = 3,
        min_importance: float = 0.3,
    ) -> List[str]:
        """Get relevant semantic memories based on user input.

        Searches semantic memory for items matching keywords extracted
        from the user input. Returns the most relevant memories up to
        the specified limit.

        Args:
            user_input: User's input text
            max_memories: Maximum number of memories to return
            min_importance: Minimum importance score for memories

        Returns:
            List of memory content strings (most relevant first)

        Examples:
            >>> injector.get_relevant_memories("我想去北京旅游")
            ['用户喜欢北京的自然景观', '用户预算充足']
        """
        keywords = self.extract_keywords(user_input)

        if not keywords:
            logger.debug("[MemoryInjector] No keywords extracted, returning no memories")
            return []

        # Get all semantic memories
        all_memories = self._hierarchy.get_semantic(
            limit=100,  # Get more to filter
            min_importance=min_importance,
        )

        if not all_memories:
            logger.debug("[MemoryInjector] No semantic memories available")
            return []

        # Score memories by keyword matching
        scored_memories = []
        for memory in all_memories:
            score = self._calculate_relevance_score(memory, keywords)
            if score > 0:
                scored_memories.append((score, memory))

        # Sort by relevance score (descending)
        scored_memories.sort(key=lambda x: x[0], reverse=True)

        # Return top memories
        top_memories = [m.content for _, m in scored_memories[:max_memories]]

        logger.debug(
            f"[MemoryInjector] Found {len(top_memories)} relevant memories "
            f"from {len(all_memories)} total semantic memories"
        )

        return top_memories

    def build_memory_context(
        self,
        user_input: str,
        max_memories: int = 3,
        include_empty: bool = False,
    ) -> str:
        """Build memory context string for LLM injection.

        Creates a formatted string containing relevant memories that
        can be injected into the LLM context for personalized responses.

        Args:
            user_input: User's input text
            max_memories: Maximum number of memories to include
            include_empty: If True, include empty context message when no memories found

        Returns:
            Formatted memory context string

        Examples:
            >>> injector.build_memory_context("我想去北京旅游")
            '用户偏好记忆：\\n- 用户喜欢北京的自然景观\\n- 用户预算充足'
        """
        memories = self.get_relevant_memories(user_input, max_memories)

        if not memories:
            if include_empty:
                return "用户偏好记忆：暂无相关记忆"
            return ""

        # Build formatted context
        context_lines = ["用户偏好记忆："]
        for i, memory in enumerate(memories, 1):
            context_lines.append(f"  {i}. {memory}")

        context = "\n".join(context_lines)

        logger.debug(
            f"[MemoryInjector] Built context with {len(memories)} memories for input: "
            f"'{user_input[:50]}...'"
        )

        return context

    def _calculate_relevance_score(self, memory: MemoryItem, keywords: List[str]) -> float:
        """Calculate relevance score for a memory based on keywords.

        Higher scores indicate more relevant memories. Scoring considers:
        - Exact keyword matches
        - Partial matches (substring)
        - Memory importance weight

        Args:
            memory: MemoryItem to score
            keywords: List of keywords to match against

        Returns:
            Relevance score (0.0 to 1.0+)
        """
        score = 0.0
        content_lower = memory.content.lower()

        # Check each keyword
        for keyword in keywords:
            keyword_lower = keyword.lower()

            # Exact match bonus
            if keyword_lower in content_lower:
                score += 0.5

                # Longer matches get higher scores
                match_count = content_lower.count(keyword_lower)
                score += match_count * 0.2

            # Check metadata for matches
            if memory.metadata:
                metadata_str = str(memory.metadata).lower()
                if keyword_lower in metadata_str:
                    score += 0.3

        # Apply importance weight
        score *= (0.5 + memory.importance)

        return score

    def get_memory_injection_prompt(
        self,
        user_input: str,
        max_memories: int = 3,
    ) -> str:
        """Get full prompt with memory context for LLM.

        Builds a complete prompt that includes both the user input
        and relevant memory context in a structured format.

        Args:
            user_input: User's input text
            max_memories: Maximum number of memories to include

        Returns:
            Complete prompt string with memory context

        Examples:
            >>> injector.get_memory_injection_prompt("我想去北京旅游")
            '''用户偏好记忆：
              1. 用户喜欢北京的自然景观

            用户输入：我想去北京旅游'''
        """
        context = self.build_memory_context(user_input, max_memories, include_empty=False)

        if context:
            return f"{context}\n\n用户输入：{user_input}"
        else:
            return f"用户输入：{user_input}"

    def find_memories_by_type(
        self,
        user_input: str,
        memory_type: str,
        max_memories: int = 3,
    ) -> List[str]:
        """Find relevant memories of a specific type.

        Args:
            user_input: User's input text for keyword extraction
            memory_type: Memory type to filter by
            max_memories: Maximum number of memories to return

        Returns:
            List of memory content strings
        """
        from app.core.memory.hierarchy import MemoryType

        try:
            mem_type = MemoryType(memory_type)
        except ValueError:
            logger.warning(f"[MemoryInjector] Invalid memory type: {memory_type}")
            return []

        keywords = self.extract_keywords(user_input)

        if not keywords:
            return []

        # Get memories of specific type
        memories = self._hierarchy.get_semantic(
            limit=100,
            memory_type=mem_type,
        )

        if not memories:
            return []

        # Score and filter
        scored_memories = []
        for memory in memories:
            score = self._calculate_relevance_score(memory, keywords)
            if score > 0:
                scored_memories.append((score, memory))

        scored_memories.sort(key=lambda x: x[0], reverse=True)

        return [m.content for _, m in scored_memories[:max_memories]]
