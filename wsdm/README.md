# WSDM Research Track Project: Evidence Scoring & Frame Uptake Pipeline

For the verified Windows real-data workflow, canonical Parquet adapter, one-command
runner, edge-pilot boundary, and local viewer, see [LOCAL_PIPELINE.md](LOCAL_PIPELINE.md).

Repository này chứa mã nguồn và dữ liệu thực nghiệm cho pipeline đánh giá bằng chứng (evidence scoring) và sự kế thừa khung tranh biện (frame uptake) trên dữ liệu ChangeMyView (CMV) qua các phương pháp trích xuất sử dụng Large Language Models (LLM) và các baseline truyền thống.

---

## 1. Cấu trúc thư mục
wsdm/
├── pilot/
│   ├── items_unlabeled.jsonl       # Dữ liệu ứng viên chưa gán nhãn cho pilot
│   ├── sheet_annotator1.csv        # Bảng gán nhãn của Annotator 1
│   └── sheet_annotator2.csv        # Bảng gán nhãn của Annotator 2
├── toy/
│   ├── results/
│   │   ├── errors.jsonl            # Phân tích lỗi (error analysis)
│   │   ├── predictions.jsonl       # Dự đoán chi tiết của các phương pháp
│   │   ├── results.json            # Kết quả dạng JSON
│   │   └── results.md              # Báo cáo kết quả tổng hợp
│   ├── split/
│   │   ├── dev.jsonl               # Tập phát triển (Development set)
│   │   ├── test.jsonl              # Tập kiểm thử (Test set)
│   │   └── train.jsonl             # Tập huấn luyện (Training set)
│   ├── all.jsonl                   # Tổng hợp toàn bộ item đã gán nhãn
│   ├── extractions.jsonl           # Dữ liệu trích xuất khung/uptake thực tế
│   └── extractions_mock.jsonl      # Dữ liệu trích xuất giả lập (mock) dùng cho kiểm thử
├── build_items.py                  # Script tải dữ liệu CMV và xây dựng cặp ứng viên (hard negatives)
├── evaluate.py                     # Script chia tập dữ liệu, chạy đánh giá và tính metrics
├── llm.py                          # Client LLM hỗ trợ Anthropic, Ollama và Mock mode để trích xuất frame/uptake
├── merge_labels.py                 # Script tính Cohen’s kappa, độ đồng thuận pairwise và hợp nhất nhãn
└── smoke_test.py                   # Script kiểm tra tích hợp toàn bộ pipeline (end-to-end smoke test)
2. Tác dụng của các file chínhbuild_items.py: Tải corpus ChangeMyView từ ConvoKit, trích xuất các thread, xây dựng cặp ứng viên ($A_1, A_2$ đối với phản hồi $B$) dựa trên các tiêu chí hard negatives (cùng nội dung khác nhánh, đổi lens, quote không dùng premise, echo, tổ tiên từ 2 bước) và xuất ra định dạng JSONL/CSV gán nhãn.merge_labels.py: Đọc các file gán nhãn từ độc lập của hai annotator, tính hệ số Cohen’s $\kappa$, độ đồng thuận thô (pairwise agreement), xuất ma trận nhầm lẫn và hỗ trợ hợp nhất nhãn (finalize) để tạo tập dữ liệu huấn luyện/đánh giá chuẩn.llm.py: Cung cấp giao diện gọi LLM (hỗ trợ cả API cloud như Anthropic và local server qua Ollama) để thực hiện trích xuất frame, uptake, span bằng chứng với cơ chế caching (--cache) nhằm tối ưu chi phí và thời gian chạy lại.evaluate.py: Quản lý việc chia tập dữ liệu theo thread (split), thực thi các phương pháp đánh giá (random, cosine, reply_quote, llm, proposed và các biến thể ablation), tính toán Accuracy kèm khoảng tin cậy (CI) bằng bootstrap theo thread, coverage và xuất kết quả ra định dạng markdown/JSON.smoke_test.py: Kiểm thử nhanh toàn bộ nửa sau của pipeline (đánh giá, trích xuất mock) để đảm bảo môi trường hoạt động chính xác.3. Hướng dẫn sử dụngA. Cài đặt môi trường và kiểm tra hệ thốngĐặt các file mã nguồn vào cùng một thư mục làm việc. Thiết lập biến môi trường mã hóa UTF-8 (đặc biệt trên Windows/PowerShell) và cài đặt các thư viện phụ thuộc:PowerShell$env:PYTHONUTF8 = "1"
python --version
python smoke_test.py
pip install numpy convokit
# pip install anthropic                # Chỉ khi gọi LLM cloud thật
# export ANTHROPIC_API_KEY=...         # Chỉ khi gọi LLM cloud thật
Nếu sử dụng mô hình local qua Ollama:PowerShellollama pull qwen2.5:14b                # Khuyến nghị model >= 14B để đảm bảo chất lượng trích xuất
ollama serve
B. Quy trình thực nghiệm từ dữ liệu thôKiểm tra dữ liệu CMV:PowerShellpython build_items.py inspect --n 2
Dựng bộ Pilot (50 cặp):PowerShellpython build_items.py build --n 50 --out pilot --seed 13
Gán nhãn độc lập:Hai annotator tiến hành điền nhãn vào pilot/sheet_annotator1.csv và pilot/sheet_annotator2.csv.Tính toán độ đồng thuận ($\kappa$) và hợp nhất nhãn:PowerShellpython merge_labels.py kappa --sheet1 pilot/sheet_annotator1.csv --sheet2 pilot/sheet_annotator2.csv --out pilot/disagreements.csv
python merge_labels.py finalize --items pilot/items_unlabeled.jsonl --sheet1 pilot/sheet_annotator1.csv --sheet2 pilot/sheet_annotator2.csv --disagreements pilot/disagreements.csv --out pilot/labeled.jsonl
Trích xuất frame/uptake bằng LLM (Ollama):PowerShellpython llm.py extract --items pilot/labeled.jsonl --out pilot/ext.jsonl --model ollama:qwen2.5:14b --cache cache/llm.jsonl
Chạy đánh giá trên tập Pilot (Dev):PowerShellpython evaluate.py eval --items pilot/labeled.jsonl --extractions pilot/ext.jsonl --methods random,cosine,reply_quote,llm,proposed,proposed_u_only,proposed_d_only,proposed_ungated,proposed_dmean --llm-model ollama:qwen2.5:14b --cache cache/llm.jsonl --reference cosine --out results_dev/
Đóng băng cấu hình và tạo tập Test:Khi đã chốt rubric, prompt, ngưỡng và mô hình trên dev, tạo tập test độc lập (sử dụng --exclude để tránh trùng lặp thread):PowerShellpython build_items.py build --n 100 --out test --seed 29 --exclude pilot/items_unlabeled.jsonl
Chạy Test đúng một lần:PowerShellpython llm.py extract --items test/labeled.jsonl --out test/ext.jsonl --model ollama:qwen2.5:14b --cache cache/llm.jsonl
python evaluate.py eval --items test/labeled.jsonl --extractions test/ext.jsonl --fit-items pilot/labeled.jsonl --methods random,cosine,reply_quote,llm,proposed,proposed_u_only,proposed_d_only,proposed_ungated,proposed_dmean --llm-model ollama:qwen2.5:14b --cache cache/llm.jsonl --reference cosine --out results_test/
4. Các lưu ý kỷ luật quan trọngĐóng băng trước khi chạy Test: Rubric ($U$), thang đo độ sâu ($D$), prompt và mô hình LLM phải được cố định hoàn toàn trên tập dev/pilot. Việc tinh chỉnh lại cấu hình sau khi quan sát kết quả trên tập test được xem là rò rỉ dữ liệu (data leakage).Kiểm tra chất lượng trích xuất LLM: Lấy mẫu ngẫu nhiên khoảng 20–30 cặp trích xuất để kiểm tra thủ công tỷ lệ khớp so với nhận định của con người, đặc biệt đối với các mô hình local (như Ollama).Tính độc lập của đặc trưng: Tuyệt đối không sử dụng thông tin delta hoặc success của corpus CMV làm nhãn hoặc đặc trưng phân loại.Xử lý ngữ cảnh LLM: Khi sử dụng mô hình local, client đã được cấu hình sẵn num_ctx=8192 nhằm tránh việc ngữ cảnh dài bị cắt cụt âm thầm. Đảm bảo giữ nguyên tham số temperature=0 và seed=0 để đảm bảo tính tái lập kết quả.Diễn giải kết quả: Khoảng tin cậy (CI) được tính toán bằng bootstrap theo mức độ thread; với số lượng thread nhỏ, CI sẽ có biên rộng, do đó không diễn giải các chênh lệch giá trị nhỏ. Nếu phương pháp đề xuất (proposed) không vượt trội hơn các baseline (reply_quote hoặc llm) trên tập test, cần báo cáo trung thực và tuân thủ quy tắc dừng của nghiên cứu.
