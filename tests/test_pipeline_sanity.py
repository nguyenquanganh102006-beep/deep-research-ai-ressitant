import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
import numpy as np
from src.ingest import index_artifacts_valid
from src.storage import write_json
from src.llm import check_ollama

class PipelineSanityTests(unittest.TestCase):
    def test_cache_rejects_corrupt_and_misaligned_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            chunks = [{"chunk_id": "c1", "page_start": 1, "page_end": 1}]
            write_json(directory / "chunks.json", chunks)
            write_json(directory / "pages.json", [{"page_number": 1}])
            metadata = {"page_count": 1, "chunk_count": 1, "embedding_dimensions": 2}
            np.save(directory / "embeddings.npy", np.array([[1, 0]], dtype=np.float32))
            self.assertTrue(index_artifacts_valid(directory, metadata))
            for vectors in [np.array([[1, 0]], dtype=np.float64), np.array([1, 0], dtype=np.float32), np.zeros((1, 0), dtype=np.float32), np.zeros((2, 2), dtype=np.float32), np.array([[float("nan"), 0]], dtype=np.float32), np.zeros((1, 2), dtype=np.float32)]:
                np.save(directory / "embeddings.npy", vectors)
                self.assertFalse(index_artifacts_valid(directory, metadata))
            (directory / "embeddings.npy").write_bytes(b"corrupt")
            self.assertFalse(index_artifacts_valid(directory, metadata))

    def test_missing_model_fails_readiness(self):
        client = SimpleNamespace(list=lambda: SimpleNamespace(models=[]))
        with patch("src.llm.ollama_client", return_value=client):
            self.assertFalse(check_ollama()[0])

    def test_present_model_passes_readiness(self):
        from src.llm import MODEL_NAME
        client = SimpleNamespace(list=lambda: SimpleNamespace(models=[SimpleNamespace(model=MODEL_NAME)]))
        with patch("src.llm.ollama_client", return_value=client):
            self.assertTrue(check_ollama()[0])

    def test_ingest_reuses_valid_cache_and_rebuilds_on_fingerprint_change(self):
        import fitz
        from src.ingest import ingest_pdf_bytes
        document = fitz.open()
        document.new_page().insert_text((72, 72), "Pipeline fixture")
        data = document.tobytes()
        document.close()
        with tempfile.TemporaryDirectory() as tmp, patch("src.storage.PAPERS_DIR", Path(tmp)), patch("src.ingest.parse_pdf", return_value=([{"page_number": 1, "parser_warning": []}], "fixture")) as parse, patch("src.ingest.create_chunks", return_value=[{"chunk_id": "c1", "page_start": 1, "page_end": 1, "content": "fixture"}]), patch("src.ingest.embed_passages", return_value=np.array([[1, 0]], dtype=np.float32)), patch("src.ingest.capture_resource_metrics", return_value={}), patch("src.ingest.embedding_fingerprint", return_value="fp1") as fingerprint:
            first, reused = ingest_pdf_bytes(data, "fixture.pdf")
            self.assertFalse(reused)
            self.assertTrue(ingest_pdf_bytes(data, "fixture.pdf")[1])
            self.assertEqual(parse.call_count, 1)
            fingerprint.return_value = "fp2"
            self.assertFalse(ingest_pdf_bytes(data, "fixture.pdf")[1])
            self.assertEqual(parse.call_count, 2)
            (Path(tmp) / first["document_id"] / "embeddings.npy").write_bytes(b"broken")
            self.assertFalse(ingest_pdf_bytes(data, "fixture.pdf")[1])
            self.assertEqual(parse.call_count, 3)
            fingerprint.return_value = "fp3"
            parse.side_effect = RuntimeError("parser failure")
            from src.ingest import IngestionError
            from src.storage import read_json
            with self.assertRaises(IngestionError): ingest_pdf_bytes(data, "fixture.pdf")
            self.assertEqual(read_json(Path(tmp) / first["document_id"] / "metadata.json")["parse_status"], "error")
            parse.side_effect = None
            self.assertFalse(ingest_pdf_bytes(data, "fixture.pdf")[1])

    def test_ingest_forwards_benchmark_only_page_limit(self):
        import fitz
        from src.ingest import ingest_pdf_bytes
        document = fitz.open()
        for _ in range(51): document.new_page()
        data = document.tobytes()
        document.close()
        validator = Mock(return_value={"page_count": 51, "title": "", "author": ""})
        pages = [{"page_number": i, "parser_warning": []} for i in range(1, 52)]
        with tempfile.TemporaryDirectory() as tmp, \
             patch("src.storage.PAPERS_DIR", Path(tmp)), \
             patch("src.ingest.validate_pdf", validator), \
             patch("src.ingest.parse_pdf", return_value=(pages, "fixture")), \
             patch("src.ingest.create_chunks", return_value=[{"chunk_id": "c1", "page_start": 1, "page_end": 51, "content": "fixture"}]), \
             patch("src.ingest.embed_passages", return_value=np.array([[1, 0]], dtype=np.float32)), \
             patch("src.ingest.capture_resource_metrics", return_value={}), \
             patch("src.ingest.embedding_fingerprint", return_value="fixture-fingerprint"):
            metadata, reused = ingest_pdf_bytes(data, "large.pdf", max_pages=200)
        self.assertFalse(reused)
        self.assertEqual(metadata["page_count"], 51)
        validator.assert_called_once_with(data, "large.pdf", max_pages=200)


    def test_invalid_empty_encrypted_and_oversize_page_pdf(self):
        import fitz
        from src.ingest import ingest_pdf_bytes
        from src.parser import PDFValidationError, validate_pdf
        for data in [b"", b"not a pdf"]:
            with self.assertRaises(PDFValidationError): ingest_pdf_bytes(data, "fake.pdf")
        from config import MAX_UPLOAD_BYTES
        with self.assertRaises(PDFValidationError): ingest_pdf_bytes(b"x" * (MAX_UPLOAD_BYTES + 1), "too-large.pdf")
        document = fitz.open()
        for _ in range(51): document.new_page()
        large_pdf = document.tobytes()
        with self.assertRaises(PDFValidationError): ingest_pdf_bytes(large_pdf, "large.pdf")
        self.assertEqual(validate_pdf(large_pdf, "large.pdf", max_pages=200)["page_count"], 51)
        encrypted = document.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
        with self.assertRaises(PDFValidationError): ingest_pdf_bytes(encrypted, "locked.pdf")
        document.close()

    def test_endpoint_failure_is_explicit(self):
        with patch("src.llm.ollama_client", side_effect=ConnectionError("unavailable")):
            self.assertFalse(check_ollama()[0])

    def test_citations_follow_actual_image_context_and_empty_answer_fails(self):
        from src.llm import answer_question
        response = SimpleNamespace(message=SimpleNamespace(content="claim [Trang 2]"), total_duration=0, prompt_eval_count=0, eval_count=0)
        client = SimpleNamespace(chat=lambda **kwargs: response)
        evidence = [{"page_start": 1, "page_end": 1, "content": "first", "type": "text"}, {"page_start": 2, "page_end": 2, "content": "second", "type": "text"}]
        with patch("src.llm.ollama_client", return_value=client):
            result = answer_question("question", evidence, [(1, b"image")])
            self.assertEqual(result["evidence_pages"], [1])
            self.assertEqual(result["invalid_citations"], [2])
            self.assertFalse(result["citation_page_in_context"])
            response.message.content = " "
            with self.assertRaises(RuntimeError): answer_question("question", evidence)

    def test_retrieval_rejects_invalid_vectors_before_query(self):
        from src.retriever import retrieve, EMBEDDING_MODEL
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_json(directory / "metadata.json", {"embedding_model": EMBEDDING_MODEL, "embedding_fingerprint": "fp"})
            write_json(directory / "chunks.json", [{"chunk_id": "c1", "page_start": 1, "page_end": 1, "content": "test"}])
            np.save(directory / "embeddings.npy", np.array([[float("nan"), 0]], dtype=np.float32))
            with patch("src.retriever.paper_dir", return_value=directory), patch("src.retriever.embedding_fingerprint", return_value="fp"), patch("src.retriever.embed_query") as query:
                with self.assertRaises(RuntimeError): retrieve("id", "test")
                query.assert_not_called()

    def test_ui_handles_incomplete_and_missing_indexes(self):
        from streamlit.testing.v1 import AppTest
        for status in ["processing", "ok"]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                doc = {"document_id": "a" * 64, "filename": "fixture.pdf", "page_count": 1, "chunk_count": 1, "parse_status": status}
                with patch("src.storage.PAPERS_DIR", Path(tmp)), patch("config.PAPERS_DIR", Path(tmp)), patch("src.storage.list_documents", return_value=[doc]), patch("src.llm.check_ollama", return_value=(False, "mock unavailable")):
                    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
                    app.selectbox[0].set_value(doc["document_id"]).run()
                    self.assertFalse(app.exception)
                    if status == "ok": self.assertTrue(app.error)
                    else: self.assertTrue(app.warning)

    def test_evaluator_returns_failure_for_technical_errors(self):
        from src.evaluate import main
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            questions = directory / "questions.json"
            write_json(questions, [{"id": "q1", "question": "test", "page_ground_truth": [1]}])
            argv = ["evaluate", "--document-id", "a" * 64, "--questions", str(questions)]
            with patch("sys.argv", argv), patch("src.evaluate.list_documents", return_value=[]), patch("src.evaluate.paper_dir", return_value=directory), patch("src.evaluate.retrieve", side_effect=RuntimeError("broken index")):
                self.assertEqual(main(), 1)
