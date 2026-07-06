# Task List Phase 5: Test và rollout handover context

## Mục tiêu

Phase 5 bổ sung test đầy đủ và rollout cấu hình `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.

Kết quả mong muốn:

- Các behavior chính có test.
- `pytest -q` pass.
- Rollout có checklist kiểm tra log và payload.
- Có kịch bản test thủ công với hội thoại Pancake thật hoặc payload mock.

## Đầu vào đã chốt

- Code Phase 1-4 đã hoàn tất.
- Env rollout là `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- Không có migration bắt buộc.

## Ngoài phạm vi Phase 5

- Không deploy production trực tiếp nếu chưa qua staging/test page.
- Không thêm dashboard riêng.
- Không sửa business prompt ngoài format đã chốt.

## File chính dự kiến sửa

- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- `tests/test_pancake_handover_context_service.py` nếu đã tách helper riêng.
- `.env.example` nếu team muốn document env mới.

## Checklist

### 1. Unit test config và pause snapshot

- [x] Test default max messages là `30`.
- [x] Test env sai format fallback `30`.
- [x] Test env nhỏ hơn `1` được clamp.
- [x] Test pause snapshot có đủ `bot_paused_at`, `bot_paused_until`, `bot_paused_reason`, `bot_paused_by`.
- [x] Test pause fields clear về `None` sau resume.

Kết quả mong muốn:
  Config và snapshot ổn định, không phá behavior pause cũ.

### 2. Unit test transcript query/build

- [x] Test query chỉ lấy role `staff` và `user`.
- [x] Test bỏ qua content rỗng.
- [x] Test không lấy current customer message.
- [x] Test hơn 30 message thì lấy 30 mới nhất.
- [x] Test render theo thứ tự cũ đến mới.
- [x] Test label `[Nhân viên]` và `[Khách]`.
- [x] Test transcript rỗng trả skip reason.

Kết quả mong muốn:
  Transcript đúng nguồn, đúng giới hạn, đúng thứ tự.

### 3. Integration test AI payload

- [x] Test customer message trong lúc pause được lưu nhưng không gọi AI.
- [x] Test customer message đầu tiên sau pause hết hạn gửi AI payload có handover context.
- [x] Test handover rỗng gửi AI payload gốc.
- [x] Test hook `hãy nhớ... conversation_id` xuất hiện đúng một lần.
- [x] Test raw customer message trong DB không bị thay bằng transcript.
- [x] Test pause fields đã clear thì lượt sau không inject transcript.

Kết quả mong muốn:
  Flow thực tế hoạt động đúng từ webhook đến AI payload.

### 4. Test fallback và logging

- [x] Test query transcript lỗi fallback về AI content gốc.
- [x] Test conversation vẫn pause không gọi AI.
- [x] Test logging skip reason khi transcript rỗng.
- [x] Test không log raw transcript nếu có thể assert qua logger mock.

Kết quả mong muốn:
  Tính năng mới fail mềm, không làm mất khả năng trả lời khách.

### 5. Chạy test suite

- [x] Chạy `pytest -q`.
- [x] Nếu fail, phân loại fail do test cũ hay behavior mới.
- [x] Không chạy pre-commit theo guideline repo.

Kết quả mong muốn:
  Test suite pass trước khi push/deploy.

### 6. Rollout staging/test page

- [ ] Set `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- [ ] Deploy staging hoặc môi trường test page.
- [ ] Tạo hội thoại Pancake thật:
  - Khách nhắn.
  - Admin reply.
  - Khách reply trong lúc pause.
  - Chờ pause hết hạn.
  - Khách nhắn lại.
- [ ] Kiểm tra AI payload/log có tối đa 30 message handover.
- [ ] Kiểm tra transcript render đúng role.
- [ ] Kiểm tra hook conversation vẫn ở cuối.
- [ ] Kiểm tra handover rỗng không gửi context.

Kết quả mong muốn:
  Flow đúng trên dữ liệu gần production trước khi bật rộng.

### 7. Rollout production

- [ ] Set env production `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- [ ] Deploy production.
- [ ] Theo dõi log:
  - `PANCAKE_HANDOVER_CONTEXT_INJECTED`
  - `PANCAKE_HANDOVER_CONTEXT_SKIPPED`
  - `PANCAKE_HANDOVER_CONTEXT_FETCH_FAILED`
- [ ] Theo dõi phản hồi AI có còn hỏi lại thông tin đã có hay không.
- [ ] Nếu xuất hiện race, mở task bổ sung marker/lock theo `paused_at`.

Kết quả mong muốn:
  Production có context tốt hơn sau handover và không phát sinh spam/lặp context.

## Acceptance criteria

- [x] Test config pass.
- [x] Test transcript query/build pass.
- [x] Test AI payload pass.
- [x] Test fallback pass.
- [x] `pytest -q` pass.
- [ ] Staging/test page xác nhận context inject đúng.
- [ ] Production rollout có log theo dõi.

## Ghi chú mở

- Không cần migration dữ liệu cũ.
- Không cần gọi Pancake API để kiểm tra history.
- Nếu sau rollout cần tăng/giảm context, chỉ đổi `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`.
