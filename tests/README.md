# Bộ test PDF toán và thuật toán

Mỗi paper có 15 câu: 1 nội dung, 6 toán, 5 mã giả và 3 câu bẫy. Mỗi câu có đáp án tham chiếu tiếng Việt. Trang là **số trang PDF tính từ 1**, không phải số equation. Đã đối chiếu công thức Algorithm 1 với ảnh trang gốc của cả hai PDF.

| Paper | PDF cố định phiên bản | Bộ câu hỏi |
| --- | --- | --- |
| Adam: A Method for Stochastic Optimization | `papers/adam-1412.6980v9.pdf` (15 trang) | `adam.questions.json` |
| FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness | `papers/flashattention-2205.14135v2.pdf` (34 trang) | `flashattention.questions.json` |

Nguồn: https://arxiv.org/abs/1412.6980v9 và https://arxiv.org/abs/2205.14135v2. Các PDF chủ yếu chứa **mã giả**, không phải file Python/CUDA chạy trực tiếp. Không dùng source code ngoài paper làm đáp án cho app chỉ đọc PDF.

## Chạy

1. Mở http://127.0.0.1:8502, tải một PDF trong `tests/papers/` và bấm **Xử lý tài liệu**.
2. Lấy SHA-256 hiển thị trong giao diện, thay `<ADAM_ID>` hoặc `<FLASH_ID>` bên dưới. Luôn chỉ rõ ID để tránh chấm nhầm paper.
3. Trong terminal có Python và các thư viện của dự án, chạy từ thư mục gốc:

```powershell
python -m src.evaluate --document-id <ADAM_ID> --questions tests/adam.questions.json --answer
python -m src.evaluate --document-id <FLASH_ID> --questions tests/flashattention.questions.json --answer
```

Bỏ `--answer` nếu chỉ kiểm tra truy xuất. Kết quả nằm ở `data/papers/<ID>/evaluations/`. Nếu lệnh `python` chưa có trong PATH, dùng đường dẫn đầy đủ tới Python đã cài.

## Chấm kết quả

- **Truy xuất:** Hit@5 kiểm tra có ít nhất một trang tham chiếu trong kết quả; không chứng minh đã lấy đủ mọi đoạn cần thiết.
- **Toán:** kiểm tra chỉ số, số mũ, căn, dấu ngoặc, miền biến và kích thước. Không chấp nhận đảo vị trí epsilon hoặc nhầm FLOPs với bộ nhớ.
- **Mã giả:** kiểm tra input/output, thứ tự vòng lặp, khởi tạo và điều kiện. Không gọi code tự viết là code nguyên bản.
- **Câu bẫy:** sửa tiền đề sai hoặc nói không có thông tin, không bịa benchmark/code. Các câu thiếu nguồn dùng `page_ground_truth: null` có chủ ý và không được tính Hit@5.
- **Ngôn ngữ và nguồn:** giải thích bằng tiếng Việt, giữ ký hiệu/code; dẫn đúng `[Trang N]` cho thông tin được nguồn hỗ trợ.

Đáp án tham chiếu là các ý cần có, không yêu cầu khớp chuỗi tuyệt đối. Runner chỉ tự đo truy xuất và cảnh báo citation; độ đúng của đáp án cần chấm thủ công. Các câu hỏi chưa được chạy benchmark trên toàn bộ pipeline. `tests/questions.json` được giữ làm mẫu chung.
