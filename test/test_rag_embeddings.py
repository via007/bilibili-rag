import builtins
import unittest
from unittest.mock import patch

from app.services.rag import RAGService


class FakeDashScopeEmbeddings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class RAGEmbeddingInitializationTest(unittest.TestCase):
    def test_uses_dashscope_embeddings(self):
        with (
            patch(
                "langchain_community.embeddings.DashScopeEmbeddings",
                FakeDashScopeEmbeddings,
            ),
            patch("app.services.rag.Chroma"),
        ):
            rag = RAGService()

        self.assertIsInstance(rag.embeddings, FakeDashScopeEmbeddings)

    def test_missing_langchain_community_fails_explicitly(self):
        real_import = builtins.__import__

        def import_without_community(name, *args, **kwargs):
            if name == "langchain_community.embeddings":
                raise ImportError("simulated missing dependency")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=import_without_community),
            self.assertRaisesRegex(RuntimeError, "pip install -r requirements.txt"),
        ):
            RAGService()


if __name__ == "__main__":
    unittest.main()
