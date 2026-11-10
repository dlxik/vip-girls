# AGORA — Shared Research Repository

Kho mã dùng chung của nhóm cho AGORA (Argument Graphs over Official and Real-world Assertions): mô hình hóa đồ thị lập luận theo thời gian, xã hội tác tử phân cấp và giám sát rủi ro lập luận.

Repository này chỉ chứa hệ thống AGORA hiện hành. Các tầng `pipeline`, `core`, `society` và `hierarchy` là các thành phần của cùng một sản phẩm, không phải các phiên bản độc lập.

## Mở nhanh

- [Demo AGORA](outputs/agora.html)
- [Sơ đồ kiến trúc phân cấp](docs/architecture/hierarchical-multi-agent-argumentation.html)
- [Chỉ mục tài liệu](docs/README.md)

## Cấu trúc repository

```text
vip-girls/
├── agora/
│   ├── pipeline/            # Nạp dữ liệu và dựng snapshot thời gian
│   ├── core/                # Belief, reasoning, interaction và revision
│   ├── society/             # Động lực xã hội, semantics và Risk Monitoring
│   ├── hierarchy/           # Argument subagents, propagation và điều phối
│   ├── resources/           # Cấu hình/mapping đi kèm hệ thống
│   └── demo.py              # Entry point duy nhất
├── data/
│   ├── raw/                 # Nguồn thô theo case
│   ├── sources/             # Danh mục và metadata nguồn
│   ├── timelines/           # Timeline availability t1–t6
│   ├── annotations/         # Argument, status và relation canonical
│   └── processed/           # Dữ liệu dẫn xuất
├── docs/
│   ├── architecture/        # Kiến trúc hệ thống và sơ đồ HTML
│   ├── research/            # Câu hỏi, phương pháp, kế hoạch dữ liệu
│   ├── project/             # Status, quyết định, bất định, source review
│   └── meeting_notes/       # Biên bản làm việc
├── outputs/                 # Demo, simulation trace và evaluation hiện tại
├── graphs/                  # Graph artifacts phục vụ nghiên cứu
├── tests/                   # Regression tests của hệ thống hiện tại
└── CONTRIBUTING.md          # Quy ước làm việc chung
```

## Chạy dự án

Tại thư mục gốc repository:

```bash
python -m agora.demo
python -m agora.demo --evaluation
python -m unittest discover -s tests
```

Mô phỏng mặc định dùng `zero_delay`; delay là giả định sensitivity theo bước `k`, không phải số đo tiếp xúc thực tế.

## Nguyên tắc nghiên cứu

- Mọi factual claim quan trọng phải truy ngược được tới source ID.
- Không đoán publication date, authority hoặc real-world exposure.
- Không chiếu thông tin ở mốc sau ngược về mốc trước.
- Canonical argument, status và relation chỉ thay đổi khi có review rõ ràng.
- Rule không được nguồn hỗ trợ phải để `null`.

## Làm việc chung

Đọc [CONTRIBUTING.md](CONTRIBUTING.md). Mỗi component nên làm trên branch riêng, pull `main` trước khi bắt đầu và chỉ merge sau khi test qua. Không commit secret, cache, virtual environment hoặc file tạm.
