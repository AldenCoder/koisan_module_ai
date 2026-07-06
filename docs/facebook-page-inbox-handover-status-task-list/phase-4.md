# Task List Phase 4: Test và rollout

## Mục tiêu

Phase 4 kiểm tra toàn bộ thay đổi từ enum/schema status, detector, đến tích hợp webhook update `status = "handover"`. Sau khi test pass, chuẩn bị checklist rollout để bật behavior trong môi trường thật.

## Phạm vi kiểm thử

- Unit test detector handover.
- Test conversation API/service với status `handover`.
- Test Facebook webhook khi AI response match/không match.
- Test các lỗi update status không làm hỏng reply Facebook.
- Regression test toàn bộ suite bằng `pytest -q`.

## File test liên quan

- [tests/test_conversations_api.py](../../tests/test_conversations_api.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)
- [tests/test_facebook_handover_detection_service.py](../../tests/test_facebook_handover_detection_service.py)

Nếu không tách detector service:

- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)

## Checklist

### 1. Test conversation status handover

- [x] Test create conversation có thể nhận `status = "handover"` nếu API create cho phép status.
- [x] Test update conversation từ `new` sang `handover`.
- [x] Test update conversation từ `handover` sang `confirmed`.
- [x] Test update conversation từ `new` sang `confirmed` bị reject.
- [x] Test detail/list response serialize `status = "handover"`.
- [x] Test filter list theo `status=handover` nếu API đang support filter status.
- [x] Test filter list theo `status=confirmed`.
- [x] Test filter status của API list conversation chỉ expose `new`, `handover`, `confirmed`.
- [x] Test invalid status vẫn trả lỗi.

Kết quả mong muốn:
  API/service conversation xử lý `handover` như một status hợp lệ.

### 2. Test detector

- [x] Test đầy đủ các keyword/pattern phase đầu.
- [x] Test có dấu và không dấu.
- [x] Test spacing/dấu câu.
- [x] Test input rỗng/`None`.
- [x] Test câu không liên quan không match.
- [x] Test object debug có `detected`, `reason`, `matched_pattern`.

Kết quả mong muốn:
  Detector ổn định và không phụ thuộc Brain đổi contract.

### 3. Test webhook không handover

- [x] Mock Brain/AI Agent trả response không chứa keyword handover.
- [x] Assert BE vẫn gửi Facebook reply như hiện tại.
- [x] Assert không gọi update conversation status.
- [x] Assert conversation status không đổi.
- [x] Assert response/debug webhook không có lỗi mới.

Kết quả mong muốn:
  Không match thì behavior cũ giữ nguyên.

### 4. Test webhook có handover

- [x] Mock Brain/AI Agent trả text có `em chuyển sale`.
- [x] Assert BE detect match.
- [x] Assert BE update conversation hiện tại thành `handover`.
- [x] Assert BE vẫn gửi Facebook reply cho khách.
- [x] Assert không set field pause.
- [x] Assert nếu match lần nữa khi status đã `handover`, flow vẫn pass.

Kết quả mong muốn:
  Match handover tạo side effect đúng trên conversation mà không làm hỏng reply.

### 5. Test lỗi update status

- [x] Mock update conversation raise `ValueError` hoặc trả lỗi validate.
- [x] Mock conversation not found.
- [x] Mock timeout/exception nếu dùng HTTP self-call.
- [x] Assert lỗi update được log rút gọn.
- [x] Assert Facebook reply không fail vì lỗi update status.
- [x] Assert không retry vô hạn.

Kết quả mong muốn:
  Update status là best effort và không kéo sập webhook reply path.

### 6. Chạy regression suite

- [x] Chạy `pytest -q`.
- [x] Không chạy `pre-commit` theo guideline repo.
- [x] Ghi nhận warning hiện có nếu không liên quan task.
- [x] Nếu test fail do thay đổi status enum/schema, sửa test hoặc code đúng nguyên nhân.

Kết quả mong muốn:
  Toàn bộ test suite pass trước rollout.

### 7. Rollout checklist

- [ ] Deploy backend có status `handover` trong enum/schema trước khi webhook update status.
- [ ] Kiểm tra API/dashboard đọc được conversation có `status = "handover"`.
- [ ] Theo dõi log handover detection trong các ngày đầu.
- [ ] Theo dõi false positive/false negative của keyword.
- [ ] Thu thập thêm câu AI hay dùng để mở rộng pattern nếu cần.

Kết quả mong muốn:
  Rollout không làm đứt flow chat hiện tại và dashboard bắt được case handover.

## Acceptance criteria

- [x] Test conversation API/service với status `handover` pass.
- [x] Test detector pass.
- [x] Test webhook không match pass.
- [x] Test webhook match pass.
- [x] Test lỗi update status pass.
- [x] `pytest -q` pass.
- [x] Không có thay đổi secret/env không cần thiết.

## Ghi chú mở

- Nếu sau rollout thấy false positive, ưu tiên điều chỉnh pattern trước.
- Nếu cần notify admin sau khi status thành `handover`, nên mở task riêng để tránh scope creep.
