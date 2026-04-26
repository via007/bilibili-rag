"""
Query Rewriter - Strategy Interface

改写策略抽象基类，所有策略必须实现此接口。
"""
from abc import ABC, abstractmethod
from typing import Optional

from app.services.query.types import RewrittenQuery


class RewriteStrategy(ABC):
    """改写策略抽象基类"""

    @abstractmethod
    async def apply(self, query: str) -> Optional[RewrittenQuery]:
        """
        对 query 应用改写策略，返回 None 表示不适用。

        Args:
            query: 用户原始 query

        Returns:
            RewrittenQuery if strategy applies, None otherwise
        """
        pass

    @abstractmethod
    def should_apply(self, query: str) -> bool:
        """
        判断当前 query 是否应该应用此策略。

        Args:
            query: 用户原始 query

        Returns:
            True if strategy should be applied, False otherwise
        """
        pass
