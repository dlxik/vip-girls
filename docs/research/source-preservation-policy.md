# Source preservation policy

## Mục tiêu

Chính sách này cân bằng khả năng tái lập nghiên cứu với bản quyền, quyền riêng tư và an toàn dữ liệu. Mọi nguồn dùng cho CTQ phải có hồ sơ provenance ngay cả khi nội dung đầy đủ không được đưa vào Git.

## Metadata bắt buộc

Mỗi nguồn phải có mã ổn định, URL chuẩn, đơn vị phát hành, loại nguồn, tiêu đề/ngôn ngữ gốc, thời điểm công bố (nếu xác minh được), thời điểm truy cập, trạng thái xác minh và ghi chú về phạm vi áp dụng. Không đoán metadata còn thiếu.

Nếu có bản lưu cục bộ hoặc trong kho riêng, manifest phải ghi tên tệp, định dạng, kích thước và SHA-256. Checksum xác nhận đúng bản đã dùng; nó không chứng minh nội dung là thật hay có giá trị pháp lý.

## Nội dung được đưa vào repository

- Chỉ commit toàn văn/tệp gốc khi nguồn cho phép lưu và chia sẻ lại rõ ràng hoặc thuộc phạm vi pháp lý cho phép.
- Với nội dung có bản quyền, nội dung mạng xã hội hoặc tài liệu chứa dữ liệu cá nhân, mặc định chỉ commit metadata, claim đã trừu tượng hóa và checksum của bản lưu riêng.
- Không commit cookie, token, thông tin đăng nhập, dữ liệu cá nhân không cần thiết hoặc nội dung công kích không phục vụ trực tiếp cho lập luận nghiên cứu.
- Giữ nguyên ngôn ngữ nguồn. Không dùng bản dịch ngược làm dữ liệu canonical.

## Nguồn mạng xã hội

Khi điều khoản nền tảng cho phép, ghi URL cấp bài đăng, thời điểm đăng/truy cập và trạng thái còn truy cập được. Chỉ trích phần tối thiểu cần thiết; ưu tiên diễn giải claim và đánh dấu đây là diễn giải. Nếu bài bị sửa/xóa, cập nhật trạng thái thay vì tái xuất bản nội dung riêng tư hoặc gây hại.

## Lưu trữ và mất liên kết

Tệp không phù hợp để commit được giữ trong kho riêng có kiểm soát truy cập; repository chỉ giữ manifest/checksum. Khi URL chết, ghi ngày phát hiện, thử nguồn chính thức hoặc bản sao hợp pháp, và không tự động nâng bản sao thứ cấp thành nguồn chính thức.

## Kiểm tra con người

Con người vẫn phải xác minh tính xác thực, thẩm quyền, hiệu lực thời gian, phạm vi áp dụng và quyền lưu trữ. Pipeline chỉ kiểm tra tính đầy đủ/cấu trúc, không thay thế đánh giá đó.
