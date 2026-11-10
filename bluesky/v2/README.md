# AGORA V2 — Autonomous Argumentative Agents

V2 là baseline **autonomous argumentative agents with deterministic symbolic reasoning and explicit belief revision**. Đây không phải mô phỏng hành vi con người, dư luận xã hội thật hay hệ thống thuyết phục đã được kiểm định.

## 1. V1 và V2

V1 dựng temporal argument graph rồi tổng hợp relation nền thành cạnh viewpoint. Agent V1 chỉ phản ứng theo snapshot diff. V2 giữ nguyên pipeline dữ liệu V1 nhưng bổ sung vòng tự trị:

`OBSERVE → REASON → SELECT ACTION → INTERACT → BELIEF REVISION → UPDATE STATE`

Action V2 được agent lựa chọn; nó không đồng nhất với mọi relation hiện hữu trong graph.

## 2. Kiến trúc

`Canonical CSV → V1 loader/validation → G_t → viewpoint mapping → agent initialization → autonomous loop → metrics → JSON trace + HTML`

Mã V2 nằm riêng trong `bluesky/v2/`. CSV canonical và source V1 không bị sửa.

## 3. Hai chiều thời gian

- `t1…t6`: trạng thái thông tin thật của vụ CTQ, do `G_t` cung cấp.
- `k0…kN`: bước thảo luận nội bộ chạy bên trong một `t`.

`S_i(t,k)` là state nội bộ của agent i; không được diễn giải t1…t6 thành vòng debate nhân tạo.

## 4. Agent state

`ArgumentativeAgent` có `agent_id`, `kind`, `name`, `position_summary`, `belief_base`, `evidence_base`, tập argument active/historical, observations, interaction/action/state history.

Mỗi `BeliefState` giữ:

- `argument_id`;
- `canonical_status` — dữ liệu CTQ, không bị simulation ghi đè;
- `agent_belief_status` — `accepted|rejected|undecided|retracted`;
- internal `confidence ∈ [0,1]`;
- activity, support/attack sets, evidence sources, provenance;
- thời điểm/bước cập nhật và revision reason.

Confidence là biến mô phỏng nội bộ, không phải độ chắc chắn factual trong dataset.

## 5. Observation

Mỗi agent chỉ thấy argument nó sở hữu theo mapping, canonical relation liên quan trong `G_t`, evidence/source IDs có thật, canonical status change và action V2 từ bước trước có liên quan. Không có hidden information hoặc factual claim tự sinh.

## 6. Symbolic reasoning

`WeightedArgumentReasoner` dùng cấu hình duy nhất tại `config.py`. Với argument a:

```text
score(a,t,k) = canonical_status_baseline
             + Σ incoming_support_weight × relation_confidence
             - Σ incoming_attack_weight × relation_confidence
             + evidence_quality_weight × (mean(source_quality) - 0.5)
             - historical_penalty
             + observed_action_effects
```

Baseline status: accepted `0.68`, undecided `0.50`, rejected `0.30`. Relation confidence: high `1.0`, medium `0.7`. Source quality là `source_type_weight × verification_weight`. Mọi term, relation ID, source ID và before/after score đều có trong trace. Đây là heuristic bảo thủ, không phải argumentation semantics đã được chứng minh.

## 7. Action policy

`RuleBasedArgumentationPolicy` sinh và xếp hạng:

- `PRESENT_ARGUMENT` cho argument mới;
- `SUPPORT`/`ATTACK` chỉ khi có canonical relation cùng chiều;
- `PROVIDE_EVIDENCE` qua canonical support relation;
- `CHALLENGE` một incoming attack, giữ relation gốc và không tạo cạnh đảo chiều;
- `RETRACT` khi internal score dưới ngưỡng;
- `NO_OP` khi không còn action grounded hợp lệ.

Tie-break ổn định theo utility, action type và argument IDs.

Argument historical chỉ có thể được dùng khi canonical relation tương ứng vẫn còn hiệu lực trong `G_t`; policy áp dụng historical penalty, không tự phục hồi activity canonical.

## 8. Interaction protocol

Protocol kiểm tra ownership, agent đích, endpoints relation, relation đang thuộc `G_t`, evidence thuộc provenance và duplicate signature. Agent được duyệt theo `agent_id`; không dùng randomness. Action trùng trong cùng timestamp bị chặn.

## 9. Belief revision

Belief mới blend confidence cũ với symbolic score (`reasoning_blend=0.35`), sau đó áp dụng effect của action được giao. Threshold mặc định: accepted `≥0.62`, rejected `≤0.38`, còn lại undecided; retract threshold `0.22`. Mọi revision ghi old/new, trigger action, observation, relation và source. Canonical status chỉ được sao chép để đối chiếu, không bị sửa.

## 10. Convergence

Một timestamp dừng khi:

1. mọi agent trả `NO_OP`; hoặc
2. không có belief change và society-state hash lặp lại; hoặc
3. đạt `max_deliberation_steps=5`.

Stop reason được ghi riêng cho từng timestamp.

## 11. Society metrics

V2 báo active agents/interactions, support/attack activity và ratio, density, mean internal confidence, revisions, retractions, dominant viewpoint theo số accepted active beliefs, conflict intensity, disagreement proxy (population standard deviation của confidence), connected components và convergence indicator. Đây chỉ là structural proxy, không phải thước đo xã hội học đã kiểm định.

## 12. Provenance

Mọi action có đường dẫn:

`agent → action → argument IDs → relation IDs → source IDs → observation`

Mọi revision có:

`agent → old belief → observation/action → reasoning trace → new belief`

`validation.py` từ chối ID ngoài canonical data hoặc relation chưa tồn tại trong `G_t`.

## 13. UI và output

UI giữ baseline bố cục V1, nhưng có hai trục độc lập `t` và `k`. Graph chỉ hiện action V2 thực thi tại bước đang chọn. Panel phải có Reasoning, Activity Log và Society Metrics; phase animation làm rõ `OBSERVE → REASON → ACT → REVISE`. Node có thể kéo-thả; vị trí tùy chỉnh được giữ xuyên suốt các mốc `t/k`, lưu trong trình duyệt và có nút đặt lại bố cục.

- HTML: `bluesky/outputs/autonomous_agent_demo_v2.html`
- Trace: `bluesky/outputs/v2_simulation_trace.json`

## 14. Chạy

Từ repository root:

```bash
python -m bluesky.v2.demo_v2
python -m bluesky.v2.demo_v2 --open
python -m bluesky.v2.demo_v2 --verbose
python -m unittest discover -s tests -v
```

## Hạn chế

- Viewpoint mapping là phân nhóm nghiên cứu thủ công, loại trừ lẫn nhau.
- Weight/threshold là cấu hình thử nghiệm minh bạch, chưa được hiệu chỉnh hoặc kiểm định hành vi.
- Baseline không có LLM, ngôn ngữ tự sinh, split/merge viewpoint hoặc learned policy.
- `CHALLENGE` chỉ phản hồi attack có sẵn; nó không khẳng định một relation đảo chiều mới.
- Max-step stop cho biết ngân sách mô phỏng đã hết, không đồng nghĩa đồng thuận xã hội.
