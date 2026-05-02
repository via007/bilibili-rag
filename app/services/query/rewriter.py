"""
Query Rewriter - Main Service Entry

QueryRewriter 主入口：协调多个改写策略，对用户 query 进行改写。
"""
import re
from typing import List

from app.config import settings
from app.services.query.strategy import RewriteStrategy
from app.services.query.step_back import StepBackStrategy
from app.services.query.sub_query_splitter import SubQuerySplitterStrategy
from app.services.query.types import (
    RewriteResult,
    RewrittenQuery,
    RewriteType,
    CONFIDENCE_THRESHOLD,
)
from loguru import logger


class QueryRewriter:
    """Query 改写服务主入口"""

    def __init__(self):
        from langchain_openai import ChatOpenAI

        self.llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.llm_model,
            temperature=0,  # 改写用 temperature=0 保证稳定
        )

        # 注入改写策略（按优先级排序：后退提示词 > 子查询拆分）
        self.strategies: List[RewriteStrategy] = [
            StepBackStrategy(self.llm),         # 默认策略，优先执行
            SubQuerySplitterStrategy(self.llm),  # 可选增强策略
        ]

    async def rewrite(self, query: str) -> RewriteResult:
        """
        对用户 query 进行改写，返回改写结果。

        策略按顺序串行执行，一旦命中适用策略即返回（不尝试后续策略）。
        """
        # 1. 快速判断是否需要改写（简单 query 跳过）
        if self._is_simple_query(query):
            return RewriteResult(
                original=query,
                rewrites=[],
                suggested_route=self._infer_route(query),
                needs_rewrite=False,
            )

        # 2. 顺序执行策略（遇到第一个适用的策略就返回）
        for strategy in self.strategies:
            if strategy.should_apply(query):
                result = await strategy.apply(query)
                if result and result.confidence >= CONFIDENCE_THRESHOLD:
                    return RewriteResult(
                        original=query,
                        rewrites=[result],
                        suggested_route=self._infer_route(query),
                        needs_rewrite=True,
                    )
                # 命中策略但置信度不足 → 降级为直接检索
                elif result:
                    logger.info(
                        f"[QUERY_REWRITE] strategy={result.type.value} "
                        f"confidence={result.confidence} < {CONFIDENCE_THRESHOLD}, skipping"
                    )

        # 3. 无适用策略或置信度不足 → 降级为直接检索
        return RewriteResult(
            original=query,
            rewrites=[],
            suggested_route=self._infer_route(query),
            needs_rewrite=False,
        )

    def _is_simple_query(self, query: str) -> bool:
        """判断是否为简单 query，不需要改写"""
        if len(query.strip()) < 5:
            return True
        general_terms = ["你好", "嗨", "哈喽", "谢谢", "在吗", "你是谁"]
        return any(term in query for term in general_terms)

    def _infer_route(self, query: str) -> str:
        """根据 query 特征推断建议路由（作为 chat.py 路由的辅助参考）"""
        if self._is_general_question(query):
            return "direct"
        if self._is_list_question(query):
            return "db_list"
        if self._is_summary_question(query):
            return "db_content"
        return "vector"

    def _is_general_question(self, query: str) -> bool:
        """通用闲聊/与收藏无关的问题"""
        general_terms = ["你好", "嗨", "哈喽", "hello", "hi", "在吗", "你是谁", "你能做什么", "谢谢", "晚安", "早安", "早上好"]
        cleaned = re.sub(r"[\W_]+", "", query, flags=re.UNICODE)
        lowered = cleaned.lower()
        residual = lowered
        for term in general_terms:
            residual = residual.replace(term.lower(), "")
        return residual == ""

    def _is_list_question(self, query: str) -> bool:
        """列表/清单类问题"""
        list_terms = ["有哪些", "有什么", "列表", "清单", "目录", "都有哪些", "列出", "罗列", "多少个", "几个"]
        return any(term in query for term in list_terms)

    def _is_summary_question(self, query: str) -> bool:
        """总结/概括类问题"""
        summary_terms = ["总结", "概述", "概括", "分析", "梳理", "提炼", "回顾", "复盘", "要点", "重点", "关键点", "核心", "讲了什么", "讲些什么"]
        return any(term in query for term in summary_terms)

    async def close(self):
        """关闭服务，清理资源（lifespan 关闭时调用）"""
        # 目前无需要清理的资源，保留此接口以便未来扩展
        pass
