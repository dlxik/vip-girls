# Quy ước cộng tác

## Thiết lập

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
vip-girls
```

Nếu thay đổi propagation hoặc risk, chạy thêm:

```bash
vip-girls --evaluation
```

## Luồng Git

1. Đồng bộ `main` bằng `git pull --ff-only`.
2. Tạo branch theo component, ví dụ `fix/propagation-queue` hoặc `data/ctq-sources`.
3. Giữ commit nhỏ; không trộn thay đổi dữ liệu canonical với refactor không liên quan.
4. Chạy test và xem diff trước khi push.
5. Không sửa trực tiếp `main` khi nhiều người đang làm song song.

## Quy ước source code

- Mã Python nằm trong `src/`; không tạo thêm package bọc bên ngoài.
- `pipeline`, `core`, `society` và `hierarchy` là các tầng của cùng một hệ thống.
- Thay đổi schema, propagation hoặc risk phải có regression test.
- Không tạo factual claim, relation hoặc source mới trong simulation.

## Quy ước dữ liệu

- `data/annotations/` là canonical research data; không chỉnh cơ học khi chưa review provenance.
- Argument, relation và source ID phải ổn định và duy nhất.
- Không back-translate nội dung nguồn tiếng Việt để tạo canonical claim.
- Rule không được nguồn hỗ trợ phải để `null`.
- Exposure mặc định là `unknown` nếu không có dữ liệu chứng minh.

## Không commit

- `.env`, token hoặc credential;
- virtual environment, cache, coverage và build artifact;
- file editor/OS và file tạm;
- dữ liệu cá nhân hoặc nguồn không có quyền chia sẻ.
