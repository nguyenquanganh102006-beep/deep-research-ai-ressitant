# DeepResearch Lite — Local PDF QA

Ứng dụng local để hỏi đáp trên một paper PDF, có nguồn theo trang. Streamlit cung cấp giao diện; PyMuPDF4LLM giữ Markdown theo trang; multilingual E5 và BM25 chạy trên CPU; Qwen chạy bằng Ollama.

## Yêu cầu

- Windows 10/11 64-bit, Python 3.11 hoặc mới hơn.
- Ollama for Windows và model `qwen3.5:2b`.
- NVIDIA driver đã cài nếu muốn Ollama dùng RTX 2060. Không cần cài CUDA toolkit riêng cho ứng dụng này.
- Kết nối mạng cho lần cài package và lần tải model embedding đầu tiên. Sau khi tải xong dependency, E5 và Ollama model, app có thể chạy offline.

## Cài đặt trên Windows PowerShell

Mở PowerShell tại thư mục project:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

Cài Ollama từ [ollama.com/download](https://ollama.com/download), mở Ollama, sau đó tải model:

```powershell
ollama pull qwen3.5:2b
ollama run qwen3.5:2b
```

Thoát phiên `ollama run` rồi kiểm tra hai prompt code/toán, latency, VRAM và phần trăm xử lý GPU/CPU:

```powershell
nvidia-smi
python smoke_test.py
```

`smoke_test.py` dùng `num_ctx=4096`, nhiệt độ thấp, in kết quả `ollama ps` và bộ nhớ GPU trước/sau. RTX 2060 có thể đang dùng một phần VRAM cho màn hình; nếu Ollama hết bộ nhớ, giảm `DEEPRESEARCH_NUM_CTX` hoặc thử model nhỏ hơn.

## Chạy ứng dụng

```powershell
streamlit run app.py --server.address 127.0.0.1
```

Mở địa chỉ local Streamlit in ra trong terminal. Chọn một file `.pdf`, bấm **Xử lý tài liệu**, rồi hỏi bằng tiếng Việt hoặc tiếng Anh. Một PDF tối đa 50 MB và 50 trang được chấp nhận theo mặc định. File upload được xác thực bằng PyMuPDF, không chỉ dựa vào phần mở rộng.

Lần đầu lập chỉ mục, `sentence-transformers` sẽ tải `intfloat/multilingual-e5-small`. Model embedding được nạp trên CPU và dùng tiền tố `passage:` / `query:`. PDF gốc, trang parse, Markdown, chunks, vectors, metadata và log QA nằm dưới `data/papers/<sha256>/`. Cùng một PDF sẽ dùng lại index đã lưu sau khi mở lại app. Metadata lưu thời gian parse/chunk/embed; log QA ghi latency, citation và RAM/VRAM snapshots nếu hệ thống cung cấp `psutil`/`nvidia-smi`.

## Đánh giá trên paper của bạn

`tests/questions.json` có 15 câu hỏi kiểm tra text/math/code và 3 negative tests. Trang nguồn và đáp án đang để `null`: cần mở một PDF thật, ghi page ground truth/đáp án đã kiểm tra vào JSON, rồi chạy:

```powershell
python -m src.evaluate --document-id <64-character-sha256>
python -m src.evaluate --document-id <64-character-sha256> --answer
```

Runner báo Hit@5 khi đã điền `page_ground_truth`, và lưu chi tiết dưới `data/papers/<sha256>/evaluations/`. Khi bật `--answer`, câu trả lời và cảnh báo citation cũng được lưu. Answer correctness vẫn cần được chấm thủ công; runner không tự xác nhận đáp án model là đúng.

Mục Parser Preview hiển thị Markdown cạnh ảnh trang PDF gốc để spot-check math/code. Mỗi mục trong dataset có dạng:

```json
{
  "id": "math-01",
  "type": "math",
  "question": "Giải thích các ký hiệu trong phương trình ...",
  "answer_ground_truth": "Đáp án đã kiểm tra thủ công",
  "page_ground_truth": [7],
  "notes": "Nguồn cần có equation cụ thể"
}
```

## Cấu hình tùy chọn

Các biến môi trường chính:

| Biến | Mặc định | Mục đích |
| --- | --- | --- |
| `DEEPRESEARCH_MODEL` | `qwen3.5:2b` | Tag Ollama |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama local endpoint |
| `DEEPRESEARCH_NUM_CTX` | `4096` | Context window gửi tới Ollama |
| `DEEPRESEARCH_TEMPERATURE` | `0.15` | Độ ngẫu nhiên khi trả lời |
| `DEEPRESEARCH_MAX_UPLOAD_MB` | `50` | Giới hạn dung lượng PDF |
| `DEEPRESEARCH_MAX_PAGES` | `50` | Giới hạn số trang |
| `DEEPRESEARCH_DATA_DIR` | `<project>/data` | Thư mục dữ liệu |

Để thử model đối chứng 4B trên cùng câu hỏi, đặt biến môi trường trước khi chạy app:

```powershell
$env:DEEPRESEARCH_MODEL = "qwen3.5:4b"
streamlit run app.py
```

Trên máy RTX 2060 6 GB này, bản 4B đã chạy ở context 4096 và dùng GPU 100% trong kiểm tra tổng hợp; hãy so chất lượng trên paper thật trước khi đổi mặc định.

## Giới hạn hiện tại

- Một PDF đang hoạt động tại một thời điểm; ưu tiên PDF digital/text-based.
- PDF scan, thứ tự đọc hai cột, hình/bảng phức tạp, công thức ảnh và indentation code cần được đối chiếu thủ công. UI hiện parser warnings và đoạn nguồn gốc.
- Không chạy code lấy từ PDF. Không có database server, agent, web search, fine-tune hoặc OCR/ MinerU nặng bật mặc định.
- Citation checker phát hiện trang mà model dẫn nhưng không nằm trong context đã truy xuất; đây không phải bộ chứng minh rằng mọi claim đều đúng.
- Không có paper thử trong thư mục ban đầu nên page ground truth, kiểm tra chất lượng text/code/math và benchmark 2B/4B chưa thể điền thay người dùng.

## Cấu trúc

```text
app.py
config.py
smoke_test.py
src/
  chunker.py
  embeddings.py
  evaluate.py
  ingest.py
  llm.py
  parser.py
  retriever.py
  storage.py
tests/questions.json
data/papers/<sha256>/
```
