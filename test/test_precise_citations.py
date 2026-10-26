import json
import unittest
from unittest.mock import Mock, patch

from app.models import ContentSource, VideoContent
from app.services.asr import ASRService
from app.services.rag import RAGService
from langchain.text_splitter import RecursiveCharacterTextSplitter


class TranscriptTimestampTest(unittest.TestCase):
    def test_dashscope_millisecond_sentence_times_are_converted_to_seconds(self):
        segment = ASRService._sentence_segment(
            {"text": "带时间的句子", "begin_time": 1250, "end_time": 2875}
        )

        self.assertEqual(segment, {"text": "带时间的句子", "start": 1.25, "end": 2.875})

    def test_transcription_download_prefers_timed_sentences_over_flat_text(self):
        response = Mock()
        response.read.return_value = json.dumps({
            "transcripts": [{
                "text": "整段文字",
                "sentences": [
                    {"text": "第一句", "begin_time": 0, "end_time": 1200},
                    {"text": "第二句", "begin_time": 1200, "end_time": 2500},
                ],
            }],
        }).encode("utf-8")
        service = ASRService()

        with patch("app.services.asr.urlrequest.urlopen", return_value=response):
            result = service._download_transcription("https://example.test/asr.json")

        self.assertEqual(result["text"], "第一句\n第二句")
        self.assertEqual(
            result["segments"],
            [
                {"text": "第一句", "start": 0.0, "end": 1.2},
                {"text": "第二句", "start": 1.2, "end": 2.5},
            ],
        )

    def test_transcript_chunks_keep_page_and_real_time_ranges(self):
        rag = RAGService.__new__(RAGService)
        rag.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=0,
            add_start_index=True,
        )
        video = VideoContent(
            bvid="BV1",
            title="多P测试",
            content="第一句\n第二句\n第三句转写内容",
            source=ContentSource.ASR,
            segments=[
                {"text": "第一句", "start": 1.0, "end": 2.0, "page": 1},
                {"text": "第二句", "start": 2.0, "end": 3.5, "page": 1},
                {"text": "第三句转写内容", "start": 8.0, "end": 9.0, "page": 2},
            ],
        )

        documents = rag._build_transcript_documents(video, video.title)

        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0].metadata["page"], 1)
        self.assertEqual(documents[0].metadata["start_time"], 1.0)
        self.assertEqual(documents[0].metadata["end_time"], 3.5)
        self.assertEqual(documents[1].metadata["page"], 2)
        self.assertEqual(documents[1].metadata["start_time"], 8.0)
        self.assertEqual(documents[1].metadata["end_time"], 9.0)

    def test_page_without_times_does_not_receive_invented_timestamps(self):
        rag = RAGService.__new__(RAGService)
        rag.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=0,
            add_start_index=True,
        )
        video = VideoContent(
            bvid="BV1",
            title="旧ASR",
            content="没有时间戳的转写文本",
            source=ContentSource.ASR,
            segments=[{"text": "没有时间戳的转写文本", "page": 2}],
        )

        documents = rag._build_transcript_documents(video, video.title)

        self.assertEqual(documents[0].metadata["page"], 2)
        self.assertNotIn("start_time", documents[0].metadata)
        self.assertNotIn("end_time", documents[0].metadata)


if __name__ == "__main__":
    unittest.main()
