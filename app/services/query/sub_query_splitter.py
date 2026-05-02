"""
Query Rewriter - Sub-Query Splitter Strategy

子查询拆分策略：识别多主题查询，拆分为独立子 query，
并发检索后合并去重。
"""
from typing import Optional

from app.services.query.strategy import RewriteStrategy
from app.services.query.types import (
    RewrittenQuery,
    RewriteType,
    SubQueryMetadata,
    SubQueryStructuredOutput,
)


class SubQuerySplitterStrategy(RewriteStrategy):
    """子查询拆分策略（可选增强策略）"""

    def __init__(self, llm):
        """
        Args:
            llm: LangChain LLM 实例
        """
        self.llm = llm

    def should_apply(self, query: str) -> bool:
        """
        子查询拆分策略适用于包含多个并列主题的 query。
        关键词：和、与、以及、或者、还是、分别
        """
        splitter_terms = ["和", "与", "以及", "或者", "还是", "分别"]
        return any(term in query for term in splitter_terms)

    async def apply(self, query: str) -> Optional[RewrittenQuery]:
        """
        识别多主题查询，拆分为独立子 query。

        示例："王德峰和哲学的关系" → sub_queries=["王德峰", "哲学", "王德峰和哲学的关系"]
        """
        prompt = f"""分析以下用户问题，判断是否包含多个子主题或子问题，如有则拆分。

要求：
1. 如果是多主题问题，输出拆分结果
2. 拆分子主题要独立、完整，且必须与原始问题语义相关
3. 保留原始问题作为最后一个子 query

## 严格约束（违反将导致检索结果严重污染）

**❌ 禁止生成过于宽泛的子 query**：
- 禁止生成单字或双字的子 query（如 "王德峰"、"哲学"）
- 禁止生成与原始问题没有直接语义关联的子 query
- 每个子 query 必须是一个完整的问句或检索意图，能够独立检索到相关内容

**正确示例**：
- 输入："王德峰和西方哲学的关系是什么"
  - ✅ sub_queries=["王德峰对西方哲学的观点", "王德峰讲的中国哲学与西方哲学的对比", "王德峰和西方哲学的关系是什么"]
  - ❌ 错误：sub_queries=["王德峰", "西方哲学", "王德峰和西方哲学的关系是什么"]（前两个过于宽泛！）

- 输入："Rust 和 Go 在并发编程上有什么区别"
  - ✅ sub_queries=["Rust 并发编程的特点", "Go 并发编程的特点", "Rust 和 Go 在并发编程上有什么区别"]
  - ❌ 错误：sub_queries=["Rust", "Go", "并发编程", "Rust 和 Go 在并发编程上有什么区别"]（前三个过于宽泛！）

问题：{query}"""

        try:
            structured_llm = self.llm.with_structured_output(SubQueryStructuredOutput)
            result: SubQueryStructuredOutput = await structured_llm.ainvoke(prompt)
            is_multi_topic = result.is_multi_topic
            sub_queries = result.sub_queries

            # 后处理：过滤过于宽泛的子 query
            filtered_queries: list[str] = []
            for sq in sub_queries:
                sq = sq.strip()
                if len(sq) < 5:
                    # 单字/双字/过短的子 query 过于宽泛，跳过
                    continue
                if sq == query:
                    # 保留原始问题
                    filtered_queries.append(sq)
                    continue
                # 检查子 query 是否与原始问题有语义关联（共享关键词）
                original_keywords = set(query.split())
                sub_keywords = set(sq.split())
                if not original_keywords & sub_keywords:
                    # 无公共关键词，可能是无关子 query，跳过
                    continue
                filtered_queries.append(sq)

            # 去重并保持顺序
            seen: set[str] = set()
            unique_queries: list[str] = []
            for sq in filtered_queries:
                if sq not in seen:
                    seen.add(sq)
                    unique_queries.append(sq)

            # 只有多主题且有效子查询数量 >= 2 才应用此策略
            if not is_multi_topic or len(unique_queries) < 2:
                return None

            return RewrittenQuery(
                type=RewriteType.SUB_QUERIES,
                query=query,  # 保留原始 query 作为主检索 query
                confidence=result.confidence,
                reason=result.reason,
                metadata=SubQueryMetadata(
                    is_multi_topic=is_multi_topic,
                    sub_queries=unique_queries,
                    main_topic=result.main_topic,
                ),
            )
        except Exception:
            # 结构化输出失败时返回 None，由 QueryRewriter 降级为直接检索
            return None
