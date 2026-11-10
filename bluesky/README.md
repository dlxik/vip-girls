# AGORA Blue Sky: Temporal Argument Graph and Viewpoint Agents

## Phiên bản

- **V1 — reactive viewpoint agents:** demo và tài liệu hiện tại trong `bluesky/src/`, chạy bằng `python -m bluesky.demo`.
- **V2 — autonomous argumentative agents:** package và tài liệu tại [`bluesky/v2/`](v2/README.md), chạy bằng `python -m bluesky.v2.demo_v2`. V2 giữ riêng real time `t` và deliberation step `k`, có symbolic reasoning, action policy, interaction protocol và belief revision xác định.
- **V3 — dynamic agent society:** package và tài liệu tại [`bluesky/v3/`](v3/README.md), chạy bằng `python -m bluesky.v3.demo_v3`. V3 tái sử dụng V1/V2, có cả `Agent Society` và manager-facing `Risk Monitoring`, đồng thời bổ sung argumentation semantics, dynamic-viewpoint candidates, structural prevalence, institutional protocol và society events.
- **V4 — hierarchical argumentative agent society:** package và tài liệu tại [`bluesky/v4/`](v4/README.md), chạy bằng `python -m bluesky.v4.demo_v4`. V4 giữ viewpoint macro-agent, thêm một argument subagent cho mỗi selected argument, message queue với delay theo `k`, Steering theo thời điểm đến và kế thừa nguyên Conflict/Risk Monitoring V3.

V1, V2 và V3 vẫn được giữ nguyên; mỗi version sinh package, trace và visualization độc lập.

## Tầm nhìn

Blue Sky mở rộng lõi nghiên cứu AGORA theo chuỗi:

`Arguments -> Temporal Argument Graph -> Viewpoint Clusters -> Viewpoint Agents -> Agentic Public Deliberation`

Mục tiêu của bản proof-of-concept là cho thấy lập luận có provenance có thể tạo thành đồ thị biến đổi theo thông tin sẵn có, rồi được tổng hợp thành các agent quan điểm tập thể. Đây không phải chatbot tranh luận, LLM role-play hay hệ thống tối ưu thuyết phục.

## Quan hệ với lõi AGORA

Lõi AGORA vẫn là lập luận: trích xuất, nguồn, thời gian, trạng thái và quan hệ support/attack. Lớp agent không thay thế dữ liệu này. Mọi node agent và cạnh agent trong demo đều truy ngược được về argument ID, relation ID và source ID.

## Sáu trạng thái CTQ

`t1 ... t6` là các trạng thái thông tin theo thời gian, **không phải các vòng tương tác agent nhân tạo**.

| Mốc | Khoảng ngày | Trọng tâm |
| --- | --- | --- |
| `t1` | 2026-07-01 đến 2026-07-02 | Bất thường điểm và các giải thích cạnh tranh; chưa kết luận sai phạm. |
| `t2` | 2026-07-05 đến 2026-07-07 | Chuyển từ nghi vấn thống kê sang chứng cứ sai phạm coi thi. |
| `t3` | 2026-07-09 | Đề xuất thi lại Toán và các biện pháp cạnh tranh. |
| `t4` | 2026-08-04 đến 2026-08-05 | Hủy kết quả ban đầu và quyết định thi lại tất cả môn. |
| `t5` | 2026-08-19 | Kết quả thi lại và các diễn giải có giới hạn. |
| `t6` | 2026-10-01 | Điều tra mở rộng tới tất cả phòng và tất cả môn. |

Mỗi snapshot tuân theo `G_t = (A_t, E_t, state_t)`. Argument chỉ xuất hiện sau `introduced_at`; sau `active_until`, nó được giữ như node lịch sử nếu cần làm đích của quan hệ thời gian. Hai chiều được tách rõ:

- `semantic_status`: `accepted`, `rejected` hoặc `undecided`; node lịch sử giữ status gần nhất đã được ghi trong CSV, kèm `status_basis=carried_forward` và `status_timestamp`, không biến thành null;
- `activity`: `active` hoặc `historical`, điều khiển độ mờ trực quan nhưng không thay đổi ý nghĩa semantic.

Relation chỉ xuất hiện khi đã được giới thiệu, còn hiệu lực và cả hai đầu đã tồn tại. Loader báo lỗi nếu một argument active thiếu status, hoặc node lịch sử không có status trước đó để truy nguyên.

## Đồ thị lập luận thời gian

Chế độ **Argument Graph** hiển thị:

- node argument với P/R/C, loại `A_K`/`A_D`, nguồn, vai trò thời gian, semantic status và activity;
- màu riêng cho `accepted`, `rejected`, `undecided`;
- halo nét đứt cho argument mới, độ mờ cho node lịch sử và badge nhỏ cho nhóm nguồn;
- cạnh có hướng `source_arg -> target_arg`, phân biệt support và attack;
- detail panel chứa conflict type, confidence, evidence sources và khối `WHY THIS CHANGED` dựa trên status reason/quan hệ có thật.

Rule null được giữ null và hiển thị rõ; demo không tạo lại các quy tắc ngầm định đã bị loại khỏi canonical data.

## Phân cụm quan điểm và viewpoint agents

Mapping thủ công nằm tại `bluesky/data/viewpoint_mapping.json`. Tám viewpoint tập thể và một lớp bối cảnh/thể chế phủ đúng 27 lập luận, không trùng nhau. Phân nhóm dựa trên kết luận, vai trò thời gian và quy tắc bao gồm được ghi tường minh; không thay đổi nội dung hay trạng thái của argument. Các argument `A_K` đặt nền thẩm quyền/thủ tục được tách vào `CTX01` thay vì bị diễn giải như một quan điểm công chúng đồng nhất.

Trong **Agent Society View**, một node xuất hiện khi cụm đã có ít nhất một argument khả dụng. Đây là các **argument-grounded reactive viewpoint agents**, chưa phải agent tự trị. State gồm argument active/lịch sử, phân bố semantic status, thành phần nguồn và số quan hệ support/attack vào/ra. State diff ghi argument mới active, argument chuyển lịch sử, thay đổi phân bố status và thay đổi quan hệ. Thành phần nguồn được tính trực tiếp từ source IDs; không có công thức strength ẩn.

Quan hệ liên cụm được tổng hợp khi relation nền nối hai argument thuộc hai cụm khác nhau. Độ dày cạnh phản ánh số relation nền; click/hover hiện đầy đủ relation ID, cặp argument, evidence source và relation mới tại mốc đó.

Mỗi snapshot có `transition_events` được sinh theo thứ tự ba giai đoạn:

1. thông tin mới: argument được giới thiệu, đổi status hoặc chuyển historical;
2. tương tác agent: relation mới được tổng hợp thành support/attack giữa viewpoint, vẫn giữ relation ID, cặp argument và evidence source;
3. cập nhật state: before/after của argument counts, status counts và quan hệ vào/ra.

Event không phải hội thoại hay hành động tự phát. Tất cả đều được suy ra xác định từ snapshot diff, relation diff, mapping và viewpoint state diff.

Không có institutional agent giả. Nội dung thể chế chỉ xuất hiện qua argument thật có `official_document` hoặc `authority_statement`, được nhận diện bằng viền node và metadata nguồn.

## Điều khiển visualization

- desktop dùng workspace ba cột: tiêu đề ở trái, graph ở giữa, inspector `Hoạt động`/`Chi tiết` ở phải; trang không cuộn và chỉ inspector cuộn nội dung;
- timeline cùng metadata mốc và transition summary trải phía trên graph + inspector; slider luôn hiển thị, còn `Chi tiết mốc và thay đổi` có thể mở/đóng;
- inspector bên phải dùng hai tab `Hoạt động` và `Chi tiết`; click node/cạnh tự chuyển sang tab Chi tiết, không xếp hai panel cuộn chồng lên nhau;
- trên màn hình hẹp, layout chuyển về một cột và dùng một luồng cuộn trang thông thường;
- slider sáu vị trí, nút Trước/Sau và Phát/Dừng;
- chuyển giữa Argument Graph và Agent Society View;
- lọc tất cả, `A_K`, `A_D`;
- bật/tắt support, attack, rejected, undecided hoặc chỉ node mới;
- kéo node, kéo nền để pan, cuộn chuột để zoom;
- hover argument để xem premise/rule/conclusion, thời gian, status và nguồn;
- hover viewpoint agent để xem argument active, phân bố status và thành phần nguồn;
- hover cạnh có hướng để xem relation/conflict/evidence; click để giữ provenance trong detail panel;
- mọi cạnh dùng cùng độ dày và mọi đầu mũi tên dùng cùng kích thước trong cả hai view. Thân cạnh chạy xuyên vào phần cổ của arrowhead để không lộ mối ghép; cạnh cũ chỉ nhạt nhẹ, còn cạnh mới giữ màu đầy và có luồng chạy theo hướng. Animation tôn trọng `prefers-reduced-motion`;
- layout force-directed xác định theo topology; node mới khởi tạo gần hàng xóm đã có, node cũ có lực neo để giữ mental map qua các mốc;
- kéo node sẽ ghim vị trí; nút đặt lại xóa ghim và tính lại layout; cạnh chỉ uốn cong khi nhiều relation chồng cùng một cặp node;
- phần tóm tắt cạnh timeline báo argument/relation mới, đổi status/activity và tương tác viewpoint mới.
- Agent Activity panel luôn tóm tắt chuỗi `new information → agent interaction → state update` ở mốc đang xem;
- khi đổi mốc trong Agent Society View, demo lần lượt hiện thông tin mới, cạnh tương tác `NEW`, rồi badge state diff trong khoảng 1,35 giây;
- Play tự chuyển sang Agent Society View và chạy `t1 → ... → t6` với nhịp 2,6 giây/mốc.

Visualization dùng SVG/JavaScript nhúng, không cần CDN hoặc frontend framework.

## Dữ liệu thật và phần mô hình hóa thủ công

Dữ liệu thật được đọc trực tiếp từ các tệp canonical trong `data/`:

- `data/timelines/ctq_timeline.csv`
- `data/annotations/ctq_selected_arguments.csv`
- `data/annotations/ctq_argument_status.csv`
- `data/annotations/ctq_relations.csv`
- `data/annotations/ctq_arguments.csv`
- `data/sources/ctq_sources.csv`

Phần mô hình hóa thủ công duy nhất là việc gán 27 argument vào tám viewpoint và một lớp bối cảnh. Demo không sửa claim, không tạo status, relation, timestamp hay source mới. Nội dung giải thích chỉ ghép theo mẫu xác định từ `reason`, relation notes/endpoints và evidence source đã có.

## Chạy demo

Từ thư mục gốc repository:

```bash
python -m bluesky.demo
```

Kết quả:

`bluesky/outputs/temporal_agentic_demo.html`

Để yêu cầu Python mở trình duyệt sau khi sinh file:

```bash
python -m bluesky.demo --open
```

## Hạn chế

- Phân cụm viewpoint là quyết định nghiên cứu thủ công, chưa được đánh giá liên mã hóa.
- Layout force-directed chạy phía client và ưu tiên ổn định mental map; chưa tối ưu cho đồ thị lớn hơn nhiều so với 27 argument.
- Carry-forward chỉ giữ status gần nhất đã ghi cho node lịch sử; không tuyên bố đây là một đánh giá canonical mới tại mốc sau.
- `WHY THIS CHANGED` là giải thích rule-based có provenance, không phải suy luận nhân quả hoàn chỉnh.
- Event stream mô tả phản ứng có căn cứ của viewpoint đối với graph; chưa có LLM dialogue, planning, belief-strength, chính sách hành động hay tối ưu thuyết phục.
- Aggregation agent chỉ đếm và truy nguyên quan hệ; chưa triển khai belief revision hay solver.
- Một số metadata nguồn còn bất định như đã ghi trong dataset.

## Hướng mở rộng

Ưu tiên tiếp theo là đánh giá độ ổn định của mapping viewpoint, bổ sung snapshot diff, tạo đường dẫn giải thích xuyên thời gian, tích hợp solver lập luận và thử nghiệm protocol tương tác agent nhưng vẫn giữ provenance ở cấp argument.
