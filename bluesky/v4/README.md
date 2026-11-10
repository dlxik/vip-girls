# AGORA V4 — Hierarchical Argumentative Agent Society

Subtitle: **Hierarchical Argument Agents with Asynchronous Information Propagation**.

## Từ V1 đến V4

- V1 dựng đồ thị lập luận thời gian và viewpoint phản ứng theo snapshot.
- V2 thêm vòng `observe → reason → act → interact → revise` xác định.
- V3 thêm ngữ nghĩa lập luận, động lực xã hội và Risk Monitoring trên 21 cửa sổ snapshot.
- V4 giữ nguyên V3, nhưng biểu diễn mỗi argument thành một subagent và đặt interaction sau một lớp truyền tin có trạng thái.

Chạy độc lập:

```bash
python -m bluesky.v4.demo_v4
python -m bluesky.v4.demo_v4 --open
python -m bluesky.v4.demo_v4 --evaluation
```

V3 vẫn chạy bằng `python -m bluesky.v3.demo_v3` và không bị V4 ghi đè output.

## Mô hình phân cấp

Mỗi selected argument có đúng một `ArgumentSubAgent` (`CTQ-A011 → ARG-A011`) và giữ nguyên parent trong `viewpoint_mapping.json`. `ViewpointMacroAgent` không bị loại bỏ; nó tổng hợp các subagent thành số accepted/rejected/undecided/retracted, confidence trung bình, số argument active, support/attack nội bộ, phân kỳ và cohesion V3.

Split/merge vẫn chỉ là candidate theo cấu hình V3. Trace V4 bổ sung các argument agent có độ lệch confidence lớn nhất để giải thích candidate; không tự tạo sự kiện.

## Message và propagation

`InformationMessage` lưu source/target agent và argument, loại message, thời điểm gửi/khả dụng/giao/đọc, delay, relation/source IDs và provenance. Queue có thứ tự xác định:

`available_at_t → available_at_k → message_id`.

Observation của argument agent chỉ gồm message đã được giao vào inbox. Message tương lai trong queue không thể được quan sát. Trình tự một bước `k` là:

1. giao message đủ điều kiện;
2. subagent đọc inbox;
3. reasoning xác định dùng lại trọng số observed-action V2;
4. action grounded của V3 tạo message;
5. message zero-delay có thể được giao ngay trong cùng `k`;
6. belief subagent được điều chỉnh;
7. viewpoint macro được tổng hợp;
8. metrics/event xã hội V3 được giữ làm baseline.

Action vẫn phải truy nguyên tới argument/relation/source canonical. V4 không tạo relation ngữ nghĩa mới.

## Giả định delay

`PropagationConfig` hỗ trợ:

- `zero_delay` (mặc định): `δ=0`, gần với giả định đồng bộ của V3;
- `fixed_delay`: mọi message trễ một số bước `k` cố định;
- `action_type_delay`: có thể cấu hình delay theo loại message.

Delay dùng **bước logic k**, không tạo ngày tháng ngoài đời. Nếu `sent_k + delay` vượt số bước của snapshot hiện tại, baseline chuyển message sang `(t_next,k0)` và ghi `crossed_snapshot_boundary=true`. Ở snapshot cuối, message có thể còn pending.

Đây là giả định phân tích độ nhạy, không phải số đo độ trễ thực địa. `real_world_exposure` luôn là `unknown` nếu dữ liệu không chứng minh người/nhóm B thực sự thấy A.

## Steering theo thời điểm đến

V3 dùng publication precedence. V4 thay duy nhất thành:

`T_delta(A,B)=1[arrival_B(A) < formation(B)]`

và:

`I_V4(A,B)=T_delta(A,B) × L(A,B) × P(A,B)`.

L và P tiếp tục dùng implementation V3. Trace theo cặp lưu publication precedence, arrival precedence, snapshot nguồn/đích, delay giả định, mode, bằng chứng delay, `T_delta`, L, P và I. Với `δ=0`, `T_delta` bằng T V3. Delay đủ lớn có thể loại một cạnh influence vì thông tin tới quá muộn.

## Risk Monitoring kế thừa

V4 gọi thẳng `ConflictEvaluator` và `RiskEvaluator` V3:

- `C(x,H)=max c(x,k,H)` không đổi;
- `RS=0.5C+0.2S+0.3CS` không đổi;
- 21 cửa sổ `H=[t_start,t_end]` với biên t1…t6 không đổi;
- chỉ S có thể đổi do `T_delta`.

## Giao diện

Đồ thị viewpoint vẫn là mặc định và mọi node thu gọn. Nút `+` trên viewpoint mở các argument agent con. Node con hiển thị ID, kết luận ngắn, status, confidence và active/historical; canonical support/attack liên quan được hiện có chọn lọc. Click subagent mở inspector message với sent/delay/available/delivered/consumed và provenance. Chế độ propagation luôn hiện nhỏ ở cột trái. Risk Monitoring, snapshot windows và drill-down V3 vẫn còn nguyên.

## Outputs

- `bluesky/outputs/hierarchical_argument_society_v4.html`
- `bluesky/outputs/v4_simulation_trace.json`
- `bluesky/outputs/v4_evaluation_report.json` khi dùng `--evaluation`

## Hạn chế

- Subagent là trạng thái mô hình gắn với argument, không phải cá nhân hoặc nhóm người thật.
- Policy chọn action vẫn kế thừa tầng viewpoint V3; V4 làm rõ local observation/revision và propagation, chưa phải multi-agent planner độc lập.
- Delay chưa được hiệu chỉnh bằng dữ liệu phơi nhiễm thực tế.
- Kết quả Steering/Risk là chỉ báo cấu trúc để phân tích độ nhạy, không chứng minh nhân quả, tác động hay mức nguy hại thực tế.
