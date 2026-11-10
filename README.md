# AGORA — Shared Research Repository

Kho mã dùng chung của nhóm cho dự án AGORA (Argument Graphs over Official and Real-world Assertions): mô hình hóa đồ thị lập luận thay đổi theo thời gian, xã hội tác tử và giám sát rủi ro lập luận.

Phiên bản hiện tại được nhập từ `dlxik/AGORA`, nhánh `bluesky/v4-hierarchical-argument-agents`, commit `2e1dce0cfe7fb7113c8c720e568f1983efb44a45` vào ngày 10/11/2026. Repo nguồn cũ vẫn được giữ làm lịch sử; repo này là nơi hai thành viên tiếp tục làm việc chung.

## Bản hiện tại

- V1: temporal argument graph và reactive viewpoint agents.
- V2: autonomous argumentative agents với vòng observe/reason/act/revise.
- V3: dynamic agent society và Risk Monitoring trên 21 cửa sổ snapshot.
- V4: argument subagents, viewpoint macro agents, message queue và arrival-aware Steering.

Mở nhanh:

- [Demo V4](bluesky/outputs/hierarchical_argument_society_v4.html)
- [Sơ đồ kiến trúc phân cấp](docs/architecture/hierarchical-multi-agent-argumentation.html)
- [Tài liệu Blue Sky](bluesky/README.md)
- [Tài liệu V4](bluesky/v4/README.md)

## Cấu trúc repository

```text
vip-girls/
├── bluesky/                 # Mã nguồn V1–V4, demo và outputs tái lập
│   ├── src/                 # V1
│   ├── v2/                  # Autonomous agents
│   ├── v3/                  # Dynamic society + Risk Monitoring
│   ├── v4/                  # Hierarchical agents + propagation
│   └── outputs/             # HTML, trace và evaluation đã sinh
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
├── graphs/                  # Snapshot/visualization dành cho graph artifacts
├── tests/                   # Regression tests V2–V4 và Risk Monitoring
└── CONTRIBUTING.md          # Quy ước làm việc chung
```

Xem [chỉ mục tài liệu](docs/README.md) để biết file nào phục vụ mục đích gì.

## Chạy dự án

Tại thư mục gốc repo:

```bash
python -m bluesky.demo
python -m bluesky.v2.demo_v2
python -m bluesky.v3.demo_v3
python -m bluesky.v4.demo_v4
python -m bluesky.v4.demo_v4 --evaluation
python -m unittest discover -s tests
```

V4 mặc định dùng `zero_delay`; delay chỉ là giả định sensitivity theo bước `k`, không phải số đo tiếp xúc thực tế.

## Nguyên tắc nghiên cứu

- Mọi factual claim quan trọng phải truy ngược được tới source ID.
- Không đoán publication date, authority hoặc real-world exposure.
- Không chiếu thông tin ở mốc sau ngược về mốc trước.
- Canonical argument, status và relation chỉ thay đổi khi có review rõ ràng.
- Conflict/Risk V3 và các version cũ phải tiếp tục tái lập được khi phát triển version mới.

## Làm việc chung

Đọc [CONTRIBUTING.md](CONTRIBUTING.md). Mỗi component nên làm trên branch riêng, pull `main` trước khi bắt đầu và chỉ merge sau khi test qua. Không commit secret, cache, virtual environment hoặc file tạm.
