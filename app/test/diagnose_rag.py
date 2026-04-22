import asyncio
import os
import sys
from app.config import settings
from app.services.rag import RAGService
from langchain_chroma import Chroma
from sqlalchemy import select
from app.models import VideoCache
from app.database import get_db_context
from dotenv import load_dotenv

load_dotenv()

# 强制使用 DashScope
settings.openai_api_key = os.getenv("DASHSCOPE_API_KEY", "")

async def diagnose():
    print("=== 正在诊断向量库状态 ===")
    
    rag = RAGService()
    
    # 1. 检查 Collection 统计
    count = rag.vectorstore._collection.count()
    print(f"向量库总文档数: {count}")
    
    if count == 0:
        print("❌ 向量库是空的！即使你看到'知识库构建完成'，实际上并没有写入向量。")
        print("可能原因：")
        print("1. 视频内容获取失败（没有字幕或摘要）")
        print("2. Embedding 调用静默失败")
    else:
        print("✅ 向量库有数据。")
        
        # 2. 试着搜一下
        query = "AI"
        print(f"\n尝试搜索: '{query}'")
        try:
            results = rag.search(query, k=3)
            print(f"搜索结果数量: {len(results)}")
            for i, doc in enumerate(results):
                print(f"--- 结果 {i+1} ---")
                print(f"标题: {doc.metadata.get('title')}")
                print(f"BVID: {doc.metadata.get('bvid')}")
                print(f"内容片段: {doc.page_content[:50]}...")
        except Exception as e:
            print(f"❌ 搜索报错: {e}")

    print("\n=== 检查数据库 VideoCache ===")
    async with get_db_context() as db:
        result = await db.execute(select(VideoCache.bvid, VideoCache.title, VideoCache.content_source))
        videos = result.fetchall()
        print(f"缓存视频数量: {len(videos)}")
        for v in videos:
            print(f"- [{v.bvid}] {v.title} (来源: {v.content_source})")

if __name__ == "__main__":
    asyncio.run(diagnose())
