# Task List Phase 6: Test và rollout

## Mục tiêu

Phase 6 hoàn thiện automated test, kiểm tra staging và rollout system version mới có kiểm soát.

Kết quả mong muốn:

- Unit/integration/concurrency test pass.
- Deploy code với target version `1.1` để conversation cũ được upgrade runtime khi có customer message mới.
- Staging xác nhận sequence/payload/database đúng trước production.
- Có rollback không downgrade.

## Đầu vào đã chốt

- Phase 1-5 đã hoàn tất code.
- Target rollout ví dụ `1.1`.
- History limit dùng lại `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- Không backfill/tạo session hàng loạt cho conversation cũ.

## Ngoài phạm vi Phase 6

- Không tăng version production trước staging.
- Không sửa AI instruction ngoài task này.
- Không chạy pre-commit theo guideline repo.

## File chính dự kiến sửa

- `tests/test_ai_version_context_service.py`
- `tests/test_facebook_webhook_forward.py`
- `tests/test_pancake_webhook.py`
- `.env.example`
- README/config docs nếu cần

## Checklist

### 1. Unit test config/version

- [x] Target system version `1.1`.
- [x] `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` tiếp tục default `30`, clamp `1..50`.
- [x] Numeric version comparison đúng.
- [x] Missing DB version dùng baseline.
- [x] Invalid/higher version behavior đúng.
- [x] Conversation mới nhận system version.

Kết quả mong muốn:
  Version gate ổn định trước khi test AI sequence.

### 2. Unit test AI user/payload/sequence

- [x] Versioned AI user có format `<sender_id>:v<version>`.
- [x] Conversation mới dùng versioned AI user ngay từ init.
- [x] Old version dùng target system version trong AI user.
- [x] Same version tiếp tục dùng cùng AI user theo conversation version.
- [x] Call order chính xác.
- [x] Init response được xử lý nội bộ.
- [x] Version update sau B3 success.

Kết quả mong muốn:
  Contract B1-B4 không bị regression.

### 3. Unit test history text-only

- [x] Version context chỉ role `staff/user/bot`; handover context vẫn chỉ `staff/user`.
- [x] Empty/link-only bị bỏ.
- [x] Mixed text/URL giữ text.
- [x] Attachment/image URL không vào context.
- [x] Limit sau sanitize.
- [x] Render cũ đến mới.
- [x] Current message/buffer batch không lặp và không bị thay bằng handover-wrapped content.

Kết quả mong muốn:
  AI context 100% text theo yêu cầu.

### 4. Integration/failure/concurrency test

- [x] Same version giữ normal flow với đúng versioned AI user.
- [x] Older version chạy đủ B1-B4 trên Facebook.
- [x] Older version chạy đủ B1-B4 trên Pancake/buffer.
- [x] Từng step failure không update version.
- [x] History query lỗi vẫn gửi current message.
- [x] Khi vừa resume handover vừa upgrade version, `Tin nhắn hiện tại của khách` vẫn là latest customer content.
- [x] Hai message đồng thời chỉ tạo một upgrade sequence.
- [x] Không log raw history.

Kết quả mong muốn:
  Webhook thực tế an toàn cả happy path và retry/race.

### 5. Chạy test suite

- [ ] Dùng Python 3.11 nếu môi trường có.
- [x] Nạp `.env` và dùng `.venv` theo môi trường project.
- [x] Chạy `pytest -q`.
- [x] Không chạy pre-commit.
- [x] Ghi nhận warning không liên quan riêng với failure.

Kết quả mong muốn:
  Toàn bộ test suite pass trước deploy.

### 6. Deploy code với target `1.1`

- [ ] Set `AI_CONVERSATION_VERSION=1.1`.
- [ ] Set `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- [ ] Deploy code.
- [ ] Xác nhận conversation mới ghi `version=1.1`.
- [ ] Xác nhận conversation mới dùng AI user `sender_id:v1.1`.
- [ ] Xác nhận conversation cũ chỉ upgrade khi có customer message mới.

Kết quả mong muốn:
  Code mới bật migration runtime có kiểm soát, không tạo session hàng loạt ngay khi deploy.

### 7. Staging kiểm tra target `1.1`

- [ ] Chọn conversation missing version/`1.0` có history text và URL.
- [ ] Gửi customer message.
- [ ] Xác nhận init → context/current message cùng AI user `sender_id:v1.1`.
- [ ] Xác nhận context không URL.
- [ ] Xác nhận DB version thành `1.1` sau B3.
- [ ] Gửi message tiếp và xác nhận không upgrade lại.
- [ ] Test race hai message.

Kết quả mong muốn:
  Staging chứng minh migration chạy đúng một lần mỗi conversation/version.

### 8. Production và rollback

- [ ] Deploy production với target version trong khung theo dõi.
- [ ] Theo dõi số started/completed/failed/duplicate upgrade.
- [ ] Theo dõi AI reply quality sau context restore.
- [ ] Nếu rollback env, xác nhận DB version cao hơn không bị downgrade.
- [ ] Không hạ DB version hàng loạt để rollback instruction nếu chưa có kế hoạch reset/session tương ứng.

Kết quả mong muốn:
  Rollout có quan sát, giới hạn blast radius và không tạo vòng upgrade.

## Acceptance criteria

- [x] Automated tests pass.
- [ ] Staging payload đúng contract.
- [x] Text-only context được xác nhận.
- [x] Version update đúng thời điểm.
- [x] Concurrency test pass.
- [ ] Production monitoring/rollback checklist sẵn sàng.

## Ghi chú mở

- `.venv` local hiện là Python 3.13.3, khác Python 3.11 trong `AGENTS.md`; full suite đã chạy bằng `.env` + `.venv` và pass `614 passed, 11 warnings`.
- Mỗi lần nâng instruction lớn trong tương lai chỉ cần bump `AI_CONVERSATION_VERSION`; không sửa version thủ công từng conversation.
- Test thực tế theo yêu cầu user sẽ dùng `.env` và `.venv`.
