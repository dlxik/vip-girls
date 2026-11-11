# Project Status

## Baseline hiện tại — 2026-11-11

- Source code được tổ chức dưới `src/` với bốn tầng `pipeline`, `core`, `society` và `hierarchy`.
- Entry point chính là CLI `vip-girls`, khai báo trong `pyproject.toml`.
- Dataset CTQ có 56 nguồn, 6 timestamp, 27 lập luận canonical, 82 status record và 31 relation.
- Hệ thống có 27 argument subagent, propagation theo bước logic và 21 risk window.
- Canonical input được hash trước/sau mô phỏng để phát hiện mutation.
- Bộ regression hiện có 39 test; CI chạy lint, test, coverage và demo trên Python 3.11.
- Phạm vi triển khai hiện tại chỉ là case CTQ.

## Đã hoàn thành

- Xây dựng pool 45 candidate và chọn 27 lập luận cuối.
- Chuẩn hóa source taxonomy thành `official_document`, `authority_statement`, `news`, `social`.
- Dựng timeline `t1`–`t6`, status và relation canonical.
- Dựng temporal snapshots và viewpoint layers.
- Triển khai reasoning, interaction, belief revision và society semantics.
- Triển khai hierarchical argument subagents và deterministic message propagation.
- Triển khai conflict, steering, risk ranking và sensitivity evaluation.
- Thêm validation cho duplicate ID, temporal interval, status coverage và accepted reference.
- Sửa propagation để bảo toàn delay dư qua nhiều snapshot.
- Đổi tên các tầng/API lịch sử sang tên chức năng `core`, `society`, `hierarchy`.
- Cho phép một argument thuộc nhiều viewpoint; routing cần một primary owner xác định theo thứ tự mapping.
- Bật runtime split/merge: viewpoint cũ bị retire và overlay viewpoint mới được tạo sau tín hiệu bền vững.
- Chốt policy lưu nguồn, checksum và ranh giới bản quyền/quyền riêng tư.
- Thêm Ruff, coverage, pre-commit và CI.

## Còn mở

- Human review cho 9 source record chưa được xác minh đầy đủ.
- Validation case về household business taxation.
- Quyết định chính sách commit/generated outputs.
- Hiệu chỉnh thực nghiệm cho trọng số reasoning và risk.
- Quyết định license.

## Giới hạn

- Delay là giả định sensitivity theo bước logic, không phải latency ngoài đời thực.
- Viewpoint mapping là thủ công; membership có thể là nhiều-nhiều nhưng action routing hiện dùng primary owner xác định.
- Runtime split/merge thay đổi overlay structure, chưa tự viết ngược vào canonical base mapping.
- Risk score là heuristic có provenance, không phải kết luận pháp lý hoặc nhân quả.
