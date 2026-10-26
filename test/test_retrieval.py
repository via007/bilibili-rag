import unittest

from app.services.retrieval import (
    build_snippet,
    build_video_url,
    extract_keywords,
    keyword_score,
    merge_ranked_documents,
)


class FakeDoc:
    def __init__(self, bvid: str, chunk_index: int, doc_type: str = "chunk"):
        self.page_content = f"{bvid}-{doc_type}-{chunk_index}"
        self.metadata = {
            "bvid": bvid,
            "chunk_index": chunk_index,
            "doc_type": doc_type,
        }


class RetrievalHelperTest(unittest.TestCase):
    def test_build_video_url_includes_available_page_and_time(self):
        self.assertEqual(
            build_video_url("BV1", page=2, start_time=83.9),
            "https://www.bilibili.com/video/BV1?p=2&t=83",
        )
        self.assertEqual(
            build_video_url("BV1", page=2),
            "https://www.bilibili.com/video/BV1?p=2",
        )
        self.assertEqual(build_video_url("BV1"), "https://www.bilibili.com/video/BV1")

    def test_extract_keywords_keeps_english_and_chinese_ngrams(self):
        keywords = extract_keywords("RAG 召回率怎么提升，中西方文化差异")

        self.assertIn("RAG", keywords)
        self.assertIn("召回率", keywords)
        self.assertIn("文化差异", keywords)
        self.assertIn("西方文化", keywords)

    def test_keyword_score_boosts_title_matches(self):
        keywords = ["向量检索"]
        title_score = keyword_score(keywords, title="向量检索原理", content="")
        content_score = keyword_score(keywords, title="", content="这一段讲向量检索原理")

        self.assertGreater(title_score, content_score)

    def test_build_snippet_centers_first_keyword(self):
        text = "开头" * 200 + "向量检索很重要" + "结尾" * 200
        snippet = build_snippet(text, ["向量检索"], max_length=80)

        self.assertIn("向量检索", snippet)
        self.assertLessEqual(len(snippet), 86)

    def test_merge_ranked_documents_dedupes_and_limits_per_video(self):
        rankings = {
            "vector": [
                FakeDoc("BV1", 0),
                FakeDoc("BV1", 1),
                FakeDoc("BV1", 2),
                FakeDoc("BV2", 0),
            ],
            "keyword": [
                FakeDoc("BV3", -2, "keyword"),
                FakeDoc("BV1", 0),
            ],
        }

        merged = merge_ranked_documents(
            rankings,
            top_k=4,
            channel_weights={"vector": 1.0, "keyword": 0.9},
            per_video_limit=2,
        )

        identities = [
            f"{doc.metadata['bvid']}:{doc.metadata['doc_type']}:{doc.metadata['chunk_index']}"
            for doc in merged
        ]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertLessEqual(sum(1 for doc in merged if doc.metadata["bvid"] == "BV1"), 2)
        self.assertTrue(any(doc.metadata["bvid"] == "BV3" for doc in merged))


if __name__ == "__main__":
    unittest.main()
