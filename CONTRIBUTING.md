# Quy ước cộng tác

## Luồng Git

1. Đồng bộ trước khi làm: `git switch main` và `git pull --ff-only`.
2. Tạo branch theo component, ví dụ `feature/v4-ui`, `data/ctq-sources`, `docs/methodology` hoặc `fix/propagation-queue`.
3. Commit nhỏ, mô tả rõ phạm vi; không trộn thay đổi dữ liệu, UI và refactor không liên quan.
4. Chạy test phù hợp trước khi push.
5. Review diff và merge về `main`; tránh sửa trực tiếp `main` khi hai người đang làm song song.

## Kiểm tra tối thiểu

```bash
python -m unittest discover -s tests
python -m bluesky.v4.demo_v4
```

Nếu thay đổi propagation/Risk, chạy thêm:

```bash
python -m bluesky.v4.demo_v4 --evaluation
```

## Quy ước dữ liệu

- `data/annotations/` là canonical research data; không chỉnh cơ học nếu chưa review provenance.
- Mọi argument/relation/source ID phải ổn định và duy nhất.
- Không back-translate nội dung nguồn tiếng Việt để làm canonical claim.
- Rule không được nguồn hỗ trợ phải để `null`.
- Không suy diễn rằng một tác tử/người ngoài đời đã thấy thông tin; exposure mặc định là `unknown`.

## Tài liệu và outputs

- Kiến trúc đặt tại `docs/architecture/`.
- Phương pháp và kế hoạch nghiên cứu đặt tại `docs/research/`.
- Status/decision/uncertainty/source review đặt tại `docs/project/`.
- Output tái lập của demo đặt tại `bluesky/outputs/`; khi thay đổi code sinh output, cập nhật output tương ứng trong cùng commit.

## Không commit

- `.env`, token, credential;
- `.venv/`, `__pycache__/`, `.pytest_cache/`;
- file editor/OS và file tạm;
- dữ liệu cá nhân hoặc nguồn không có quyền chia sẻ.
