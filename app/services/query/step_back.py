"""
Query Rewriter - Step-Back Prompting Strategy

后退提示词策略：将具体问题泛化为更高层次的概念，
先召回泛化结果，再与原始 query 结果合并。
"""
from typing import Optional

from app.services.query.strategy import RewriteStrategy
from app.services.query.types import (
    RewrittenQuery,
    RewriteType,
    StepBackMetadata,
    StepBackStructuredOutput,
)


class StepBackStrategy(RewriteStrategy):
    """后退提示词策略（默认策略）"""

    def __init__(self, llm):
        """
        Args:
            llm: LangChain LLM 实例
        """
        self.llm = llm

    def should_apply(self, query: str) -> bool:
        """
        后退提示词策略适用于所有非简单 query。
        简单 query 的判断由 QueryRewriter._is_simple_query() 先行处理。
        """
        return True

    async def apply(self, query: str) -> Optional[RewrittenQuery]:
        """
        生成两种不同层次的检索 query：
        1. 高层次抽象：提升到更通用的概念，但必须保留核心实体和关键限定词
        2. 具体完善：补充被省略的主语/宾语

        示例：
        - 输入：如何优化小程序的性能？
        - 高层次抽象：如何提升性能？
        - 具体完善：如何优化小程序开发中的性能问题？
        """
        prompt = f"""你是一个查询改写专家。对于用户的知识库问答问题，生成两种不同层次的检索 query。

## 概念定义

**核心实体**：问题中的名词、专有名词或不可替换的实体
- 人名/人物：例如"王德峰"、"李笑来"
- 技术名词：例如"机器学习"、"深度学习"、"Rust"
- 产品名：例如"小程序"、"iPhone"、"微信"
- 事件/作品：例如"红楼梦"、"三国演义"

**关键限定词**：限定问题范围的重要修饰词，通常是形容词、动词或短语
- 例如："性能优化"、"并发编程"、"哲学思想"、"中国文化"
- 这些词决定了问题的核心方向，不能丢失

## 改写要求

### 1. 高层次抽象
将问题提升到更通用的概念层次，但必须遵循以下规则：

**✅ 必须保留**：
- 所有核心实体（人名、技术名词、产品名等）
- 所有关键限定词（决定问题方向的修饰词）
- **只泛化**动词和通用形容词（如"讲解"→"讨论"，"优化"→"改进"）

**❌ 禁止行为**：
- 禁止删除核心实体（如"小程序"→"软件"是错误的！）
- 禁止过度泛化（如"小程序开发"→"软件开发"丢失了关键限定）
- 禁止替换核心概念

**正确示例**：
- 输入："王德峰讲的中国哲学"
  - ✅ 高层次抽象："王德峰讲的中国哲学核心概念"
  - ❌ 错误泛化："中国哲学"（丢失了王德峰）

- 输入："如何优化小程序的性能？"
  - ✅ 高层次抽象："如何提升性能？"
  - ❌ 错误泛化："如何开发软件？"（丢失了小程序+性能）

- 输入："Rust 所有权规则详解"
  - ✅ 高层次抽象："Rust 编程核心概念"
  - ❌ 错误泛化："编程规则"（丢失了 Rust）

### 2. 具体完善
补充被省略的主语/宾语，使问题更完整具体。但请注意：
- ✅ 只能补充问题中**隐含**的实体（如从上下文可推断）
- ❌ 禁止引入原问题中**完全不存在**的新实体或新主题
- ❌ 禁止改变原问题的否定含义

**正确示例**：
- 输入："所有权规则详解" → "Rust 所有权规则详解"（Rust 是隐含的技术背景）
- 输入："性能怎么调优" → "小程序性能调优方法"（小程序是隐含的产品背景）

**错误示例**：
- 输入："如何学习编程" → "如何学习 Python 编程"（Python 不在原问题中！）
- 输入："不是王德峰讲的" → "王德峰讲的中国哲学"（改变了否定含义！）

### 3. 否定查询处理
如果用户问题包含否定词（"不是"、"除了"、"不包含"、"没有"等）：
- 具体完善时**必须保留否定含义**，禁止把否定改为肯定
- 高层次抽象可以弱化否定，但不得反转语义

**示例**：
- 输入："除了王德峰，我还收藏了哪些讲中国哲学的视频？"
  - ✅ 高层次抽象："讲中国哲学的视频有哪些"
  - ✅ 具体完善："除了王德峰之外，讲中国哲学的视频有哪些"
  - ❌ 错误："王德峰讲的中国哲学视频有哪些"（丢失了否定！）

问题：{query}"""

        try:
            structured_llm = self.llm.with_structured_output(StepBackStructuredOutput)
            result: StepBackStructuredOutput = await structured_llm.ainvoke(prompt)

            # step_back_query 是必填字段
            if not result.step_back_query:
                return None
            return RewrittenQuery(
                type=RewriteType.STEP_BACK,
                query=result.step_back_query,
                confidence=result.confidence,
                reason=result.reason,
                metadata=StepBackMetadata(
                    step_back_query=result.step_back_query,
                    specific_query=result.specific_query or result.step_back_query,
                ),
            )
        except Exception as e:
            # 结构化输出失败时返回 None，由 QueryRewriter 降级为直接检索
            return None
