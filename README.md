# VIP Girls — Temporal Argument Research System

Repository nghiên cứu dùng để mô hình hóa đồ thị lập luận theo thời gian, xã hội tác tử phân cấp và giám sát rủi ro lập luận. Case hiện tại là THPT Chuyên Tuyên Quang (CTQ).

## Cấu trúc

```text
vip-girls/
├── src/
│   ├── pipeline/            # Nạp, kiểm tra dữ liệu và dựng snapshot
│   ├── core/                # Belief, reasoning, interaction và revision
│   ├── society/             # Semantics, động lực xã hội và risk monitoring
│   ├── hierarchy/           # Argument subagent và message propagation
│   ├── resources/           # Viewpoint mapping
│   └── demo.py              # Entry point
├── data/                    # Dữ liệu canonical và source metadata
├── docs/                    # Kiến trúc, phương pháp và project records
├── graphs/                  # Graph artifacts khi được sinh
├── outputs/                 # Trace, evaluation và HTML hiện tại
├── tests/                   # Regression và data-validation tests
└── pyproject.toml           # Packaging và CLI
```

## Cài đặt và chạy

Yêu cầu Python 3.10 trở lên.

```bash
python -m pip install -e .
vip-girls
vip-girls --evaluation
python -m unittest discover -s tests -v
```

Tooling phát triển:

```bash
python -m pip install -e ".[dev]"
ruff check src tests
coverage run -m unittest discover -s tests -v
coverage report
```

Không cài package vẫn có thể chạy demo trực tiếp:

```bash
python src/demo.py
```

Output chính được sinh tại:

- `outputs/index.html`
- `outputs/simulation-trace.json`
- `outputs/evaluation-report.json` khi dùng `--evaluation`

## Dữ liệu và mô hình

- 56 nguồn CTQ và 6 trạng thái thông tin `t1`–`t6`.
- 27 lập luận canonical, 31 quan hệ support/attack và 9 viewpoint.
- Mỗi lập luận canonical có một argument subagent.
- Một lập luận có thể thuộc nhiều viewpoint; action routing dùng primary owner xác định theo thứ tự mapping.
- Split/merge retire viewpoint runtime cũ và tạo overlay viewpoint mới, không sửa canonical base mapping.
- Delay propagation được đo bằng bước logic `k`, không phải thời gian hoặc exposure ngoài đời thực.
- Trọng số reasoning/risk là heuristic có cấu hình, chưa phải tham số đã hiệu chỉnh thực nghiệm.

## Nguyên tắc nghiên cứu

- Mọi factual claim quan trọng phải truy ngược được tới source ID.
- Không đoán publication date, authority hoặc real-world exposure.
- Không dùng thông tin ở mốc sau để mô tả trạng thái thông tin ở mốc trước.
- Dữ liệu canonical chỉ thay đổi sau review rõ ràng.
- Rule không được nguồn hỗ trợ phải để `null`.
- Tệp nguồn chỉ được commit theo [source preservation policy](docs/research/source-preservation-policy.md).

Xem [chỉ mục tài liệu](docs/README.md) và [quy ước cộng tác](CONTRIBUTING.md).
