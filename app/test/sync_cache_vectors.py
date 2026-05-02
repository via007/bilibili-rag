#!/usr/bin/env python
import argparse
import asyncio
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import select

from app.database import get_db_context
from app.models import VideoCache, ContentSource, VideoContent
from app.services.rag import RAGService


def _parse_source(source: Optional[str]) -> ContentSource:
    if not source:
        return ContentSource.BASIC_INFO
    try:
        return ContentSource(source)
    except Exception:
        return ContentSource.BASIC_INFO


def _has_vectors(rag: RAGService, bvid: str) -> bool:
    try:
        collection = rag.vectorstore._collection
        result = collection.get(where={"bvid": bvid}, limit=1)
        ids = result.get("ids") if isinstance(result, dict) else None
        if not ids:
            return False
        if isinstance(ids, list):
            return len(ids) > 0
        return False
    except Exception as e:
        logger.warning(f"[{bvid}] 查询向量失败: {e}")
        return False


async def _load_caches(
    bvids: Optional[Iterable[str]] = None,
) -> list[VideoCache]:
    async with get_db_context() as db:
        stmt = select(VideoCache)
        if bvids:
            stmt = stmt.where(VideoCache.bvid.in_(list(bvids)))
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def _sync_vectors(
    min_length: int,
    rebuild_all: bool,
    bvids: Optional[Iterable[str]],
    dry_run: bool,
) -> dict:
    rag = RAGService()
    caches = await _load_caches(bvids=bvids)

    stats = {
        "checked": 0,
        "skipped_short": 0,
        "skipped_exists": 0,
        "indexed": 0,
        "reindexed": 0,
    }

    async with get_db_context() as db:
        for cache in caches:
            stats["checked"] += 1
            content_text = (cache.content or "").strip()
            if len(content_text) < min_length:
                stats["skipped_short"] += 1
                continue

            exists = _has_vectors(rag, cache.bvid)
            if exists and not rebuild_all:
                stats["skipped_exists"] += 1
                continue

            if dry_run:
                logger.info(
                    f"[{cache.bvid}] 计划写入向量 (rebuild_all={rebuild_all}, exists={exists})"
                )
                continue

            if exists or rebuild_all:
                try:
                    rag.delete_video(cache.bvid)
                except Exception as e:
                    logger.warning(f"[{cache.bvid}] 删除旧向量失败: {e}")

            video = VideoContent(
                bvid=cache.bvid,
                title=cache.title or cache.bvid,
                content=content_text,
                source=_parse_source(cache.content_source),
                outline=cache.outline_json,
            )
            rag.add_video_content(video)

            cache.is_processed = True
            if exists:
                stats["reindexed"] += 1
            else:
                stats["indexed"] += 1

        if not dry_run:
            await db.commit()

    return stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync video_cache content with vector store using cached text only."
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=50,
        help="Minimum content length to index (default: 50).",
    )
    parser.add_argument(
        "--rebuild-all",
        action="store_true",
        help="Rebuild vectors even if they already exist.",
    )
    parser.add_argument(
        "--bvid",
        action="append",
        dest="bvids",
        help="Limit to specific bvid (can be used multiple times).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without writing vectors.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    stats = asyncio.run(
        _sync_vectors(
            min_length=args.min_length,
            rebuild_all=args.rebuild_all,
            bvids=args.bvids,
            dry_run=args.dry_run,
        )
    )
    logger.info(
        "完成: checked={}, skipped_short={}, skipped_exists={}, indexed={}, reindexed={}",
        stats["checked"],
        stats["skipped_short"],
        stats["skipped_exists"],
        stats["indexed"],
        stats["reindexed"],
    )


if __name__ == "__main__":
    main()
