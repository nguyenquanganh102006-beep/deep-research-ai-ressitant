"""Streamlit interface for one-paper local PDF question answering."""

from __future__ import annotations

from typing import Any

import streamlit as st

from config import MAX_UPLOAD_BYTES, MODEL_NAME, NUM_CTX, PAPERS_DIR
from src.ingest import IngestionError, ingest_pdf_bytes
from src.llm import answer_question, check_ollama
from src.metrics import capture_resource_metrics
from src.parser import render_page_png
from src.retriever import retrieve
from src.storage import append_jsonl, list_documents, paper_dir, read_json


st.set_page_config(page_title="DeepResearch Lite", page_icon="📄", layout="wide")
st.title("DeepResearch Lite")
st.caption("Hỏi đáp một PDF bằng model local, có đoạn nguồn và số trang.")


@st.cache_data(ttl=30, show_spinner=False)
def _ollama_status() -> tuple[bool, str]:
    return check_ollama()


def _render_sources(sources: list[dict[str, Any]], show_scores: bool = False) -> None:
    with st.expander(f"Sources · {len(sources)} đoạn", expanded=False):
        for item in sources:
            page_start = item.get("page_start", "?")
            page_end = item.get("page_end", page_start)
            page_label = str(page_start) if page_start == page_end else f"{page_start}–{page_end}"
            st.markdown(
                f"**[Trang {page_label}]** · `{item.get('type', 'text')}` · "
                f"{item.get('section') or 'không có tiêu đề'} · `{item.get('chunk_id', '')}`"
            )
            if show_scores:
                st.caption(
                    f"dense={item.get('dense_score', 0):.3f} · "
                    f"BM25={item.get('bm25_score', 0):.3f} · "
                    f"RRF={item.get('rrf_score', 0):.4f}"
                )
            st.markdown(str(item.get("content", "")), unsafe_allow_html=False)
            for warning in item.get("parse_warning", []):
                st.warning(warning)
            st.divider()


with st.sidebar:
    st.subheader("Cấu hình local")
    st.code(f"Model: {MODEL_NAME}\nContext: {NUM_CTX}", language="text")
    reachable, status = _ollama_status()
    if reachable:
        st.success(status)
    else:
        st.warning(status)
    st.caption("Embedding chạy CPU. Ollama là thành phần duy nhất dùng GPU.")

PAPERS_DIR.mkdir(parents=True, exist_ok=True)

with st.expander("Thêm PDF", expanded=not bool(list_documents())):
    uploaded = st.file_uploader(
        "Chọn một PDF paper",
        type=["pdf"],
        accept_multiple_files=False,
        max_upload_size=max(1, MAX_UPLOAD_BYTES // (1024 * 1024)),
        help="Mặc định tối đa 50 MB và 50 trang. PDF được lưu cục bộ dưới data/papers/.",
    )
    if st.button("Xử lý tài liệu", type="primary", disabled=uploaded is None):
        try:
            with st.spinner("Đang kiểm tra, trích xuất từng trang và lập chỉ mục trên CPU…"):
                metadata, reused = ingest_pdf_bytes(uploaded.getvalue(), uploaded.name)
            st.session_state.active_document_id = metadata["document_id"]
            st.session_state.chat_messages = []
            if reused:
                st.success("PDF này đã được lập chỉ mục; dùng lại dữ liệu đã lưu.")
            else:
                st.success(
                    f"Đã xử lý {metadata['page_count']} trang, "
                    f"tạo {metadata['chunk_count']} chunk."
                )
            st.rerun()
        except IngestionError as exc:
            st.error(
                f"Không thể hoàn tất parse/index: {exc}. "
                "File gốc đã được lưu cục bộ để có thể thử lại sau khi sửa môi trường."
            )
        except Exception as exc:
            st.error(f"Không xử lý được file: {exc}")

documents = list_documents()
document_by_id = {item["document_id"]: item for item in documents}
document_ids = list(document_by_id)
previous_id = st.session_state.get("active_document_id")
if previous_id not in document_ids:
    previous_id = next(
        (
            item["document_id"]
            for item in documents
            if item.get("parse_status") in {"ok", "warning"}
        ),
        "",
    )

selected_id = st.selectbox(
    "PDF đã lưu",
    options=[""] + document_ids,
    index=([""] + document_ids).index(previous_id or ""),
    format_func=lambda value: (
        "Chọn tài liệu" if not value else
        f"{document_by_id[value].get('filename', 'paper.pdf')} · "
        f"{document_by_id[value].get('page_count', '?')} trang · "
        f"{document_by_id[value].get('parse_status', 'unknown')}"
    ),
)
if selected_id != st.session_state.get("active_document_id"):
    st.session_state.active_document_id = selected_id
    st.session_state.chat_messages = []

if not selected_id:
    st.info("Tải lên PDF ở phía trên để bắt đầu. Tài liệu đã lập chỉ mục sẽ xuất hiện ở đây sau khi mở lại app.")
    st.stop()

metadata = document_by_id[selected_id]
directory = paper_dir(selected_id)
st.header(metadata.get("filename", "Research paper"))
status_col, pages_col, chunks_col, id_col = st.columns([1, 1, 1, 2])
status_col.metric("Trạng thái", metadata.get("parse_status", "unknown"))
pages_col.metric("Số trang", metadata.get("page_count", 0))
chunks_col.metric("Số chunk", metadata.get("chunk_count", 0))
id_col.caption(f"SHA-256: `{selected_id}`")

if metadata.get("parse_status") == "error":
    st.error(metadata.get("parse_error", "Tài liệu chưa được lập chỉ mục hoàn tất."))
    st.stop()

parse_warnings = metadata.get("parse_warnings", [])
if parse_warnings:
    with st.expander(f"Parser warnings ({len(parse_warnings)})", expanded=True):
        for warning in parse_warnings:
            st.warning(f"Trang {warning['page_number']}: {warning['message']}")
st.info("Với công thức hoặc code quan trọng, hãy đối chiếu đoạn trích với trang PDF gốc trước khi sử dụng.")

pages = read_json(directory / "pages.json")
with st.expander("Parser Preview", expanded=False):
    page_numbers = [int(page["page_number"]) for page in pages]
    preview_page_number = st.selectbox(
        "Trang xem trước", options=page_numbers, key=f"preview-{selected_id}"
    )
    preview_page = next(page for page in pages if page["page_number"] == preview_page_number)
    if preview_page.get("parser_warning"):
        for warning in preview_page["parser_warning"]:
            st.warning(warning)
    markdown_col, original_col = st.columns(2)
    with markdown_col:
        st.markdown("**Markdown đã trích xuất**")
        st.markdown(
            preview_page.get("markdown") or "*(Không trích xuất được nội dung văn bản.)*",
            unsafe_allow_html=False,
        )
    with original_col:
        st.markdown("**Trang PDF gốc**")
        st.image(
            render_page_png(directory / "source.pdf", preview_page_number),
            caption=f"PDF gốc · trang {preview_page_number}",
            width="stretch",
        )

st.subheader("Hỏi về paper")
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            if message.get("citation_warning"):
                st.warning(message["citation_warning"])
            if message.get("sources"):
                _render_sources(message["sources"])

question = st.chat_input("Nhập câu hỏi bằng tiếng Việt hoặc tiếng Anh")
if question:
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Đang truy xuất đoạn liên quan…"):
                matches = retrieve(selected_id, question)
            append_jsonl(
                directory / "retrieval_log.jsonl",
                {
                    "question": question,
                    "retrieved_ids": [item["chunk_id"] for item in matches],
                    "pages": sorted({item["page_start"] for item in matches}),
                    "scores": [
                        {
                            "chunk_id": item["chunk_id"],
                            "dense": item["dense_score"],
                            "bm25": item["bm25_score"],
                            "rrf": item["rrf_score"],
                        }
                        for item in matches
                    ],
                },
            )
            with st.spinner("Đang hỏi Ollama local…"):
                resources_before = capture_resource_metrics()
                result = answer_question(question, matches)
                resources_after = capture_resource_metrics()
            st.markdown(result["answer"])
            if result["citation_warning"]:
                st.warning(result["citation_warning"])
            st.caption(f"Thời gian Ollama: {result['latency_seconds']:.2f}s")
            _render_sources(matches)
            assistant_message = {
                "role": "assistant",
                "content": result["answer"],
                "sources": matches,
                "citation_warning": result["citation_warning"],
            }
            append_jsonl(
                directory / "qa_log.jsonl",
                {
                    "question": question,
                    "retrieved_ids": [item["chunk_id"] for item in matches],
                    "answer": result["answer"],
                    "latency_seconds": result["latency_seconds"],
                    "citations": result["citations"],
                    "invalid_citations": result["invalid_citations"],
                    "ollama_total_seconds": result["ollama_total_seconds"],
                    "prompt_eval_count": result["prompt_eval_count"],
                    "eval_count": result["eval_count"],
                    "resources_before": resources_before,
                    "resources_after": resources_after,
                },
            )
        except Exception as exc:
            st.error(f"Không hoàn thành được câu hỏi: {exc}")
            assistant_message = {
                "role": "assistant",
                "content": "Yêu cầu chưa hoàn tất. Kiểm tra trạng thái Ollama/model và log ở terminal.",
                "sources": [],
                "citation_warning": "",
            }
            try:
                append_jsonl(
                    directory / "qa_log.jsonl",
                    {
                        "question": question,
                        "error_class": "model_or_retrieval_error",
                        "error": str(exc),
                    },
                )
            except OSError:
                pass
        st.session_state.chat_messages.append(assistant_message)
