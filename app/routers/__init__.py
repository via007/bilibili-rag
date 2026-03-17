"""
Bilibili RAG 知识库系统

路由模块初始化
"""
from app.routers import auth, favorites, knowledge, chat, conversation, correction, config, summary, clustering, learning_path

__all__ = ["auth", "favorites", "knowledge", "chat", "conversation", "correction", "config", "summary", "clustering", "learning_path"]
