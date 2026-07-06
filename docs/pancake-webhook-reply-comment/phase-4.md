# Task List Phase 4: Tích hợp gửi comment reply và test rollout

## Mục tiêu

Phase 4 nối kết quả của Phase 2 và Phase 3 thành flow end-to-end: nhận comment hợp lệ, lưu message, gọi AI, kiểm tra guard an toàn, gửi `reply_comment`, lưu bot message và send result.

Kết quả mong muốn:

- Comment khách hợp lệ được xử lý tự động sau feature flag.
- Backend gửi `reply_comment`, không gửi `reply_inbox`.
- Nếu AI trả link Drive, backend gửi text trước và ảnh lookbook sau vào cùng comment.
- Bot message lưu đủ `reply_action`, `comment_message_id` và Pancake send result.
- Duplicate, dangerous keyword, admin pause và missing data đều không gửi API.
- Test end-to-end webhook branch pass.
- Có checklist rollout và log quan sát production.

## Đầu vào đã chốt

- Phase 2 đã normalize và classify được `customer_comment`.
- Phase 3 đã có `send_pancake_comment_reply`.
- Feature flag comment auto reply mặc định an toàn.
- Pipeline Drive hiện có được reuse cho comment reply.

## Ngoài phạm vi Phase 4

- Không triển khai mentions.
- Không resolve conversation bằng API phụ.
- Không thay đổi flow Facebook webhook.
- Không thay đổi flow auto consult ad/comment notice.
- Không bật rộng production nếu chưa kiểm tra page test.

## File chính dự kiến sửa

- [app/core/config.py](../../app/core/config.py)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py)

## Checklist

### 1. Thêm feature flag và guard gửi

- [x] Thêm `pancake_comment_auto_reply_enabled` vào settings.
- [x] Mặc định feature flag là `False`.
- [x] Nếu flag off, xử lý/lưu comment theo Phase 2 nhưng không gửi Pancake.
- [x] Nếu flag off, return reason rõ như `pancake_comment_auto_reply_disabled`.
- [x] Kiểm tra đủ `page_id` trước khi gửi.
- [x] Kiểm tra đủ `pancake_conversation_id` trước khi gửi.
- [x] Kiểm tra đủ `comment_message_id` trước khi gửi.
- [x] Kiểm tra reply text không rỗng trước khi gửi.

Kết quả mong muốn:
  Flow có thể rollout an toàn và tắt nhanh nếu có sự cố.

### 2. Nối flow AI với reply comment

- [x] Sau khi lưu user comment, gọi AI bằng text comment.
- [x] Không gọi AI nếu dangerous keyword blocked.
- [x] Không gọi AI nếu duplicate.
- [x] Không gọi AI nếu conversation đang pause.
- [x] Không gửi nếu AI init failed.
- [x] Không gửi nếu AI call failed.
- [x] Không gửi nếu AI response rỗng.
- [x] Giữ metadata AI/source đủ trace comment.

Kết quả mong muốn:
  AI chỉ chạy khi comment hợp lệ và các guard đều pass.

### 3. Kiểm tra pause lần cuối trước khi gửi

- [x] Reload conversation sau khi AI trả lời.
- [x] Resume pause nếu pause đã hết hạn.
- [x] Nếu admin pause xuất hiện trong lúc AI đang xử lý, không gửi comment reply.
- [x] Return reason `conversation_paused_before_send`.
- [x] Không lưu bot message như sent nếu chưa gửi.
- [x] Log suppression với `comment_message_id`.

Kết quả mong muốn:
  Bot không đè admin/người thật trong thời điểm handover.

### 4. Gửi Pancake reply comment

- [x] Gọi `send_pancake_comment_reply`.
- [x] Truyền đúng `page_id`.
- [x] Truyền đúng `pancake_conversation_id`.
- [x] Truyền đúng `comment_message_id`.
- [x] Truyền đúng reply text.
- [x] Không gọi `send_pancake_reply` cho `customer_comment`.
- [x] Không truyền `action = reply_inbox`.
- [x] Return `reply_action = reply_comment`.

Kết quả mong muốn:
  Comment được reply công khai vào đúng comment gốc.

### 5. Lưu bot message và conversation

- [x] Lưu bot message khi có send result.
- [x] Set bot meta `source = pancake_webhook_comment`.
- [x] Set bot meta `reply_action = reply_comment`.
- [x] Set bot meta `reply_to_message_mid`.
- [x] Set bot meta `comment_message_id`.
- [x] Set bot meta `pancake_send_result`.
- [x] Không lưu token trong bot meta.
- [x] Update `conversation.updated_at`.

Kết quả mong muốn:
  Lịch sử nội bộ thể hiện rõ bot đã reply comment nào và Pancake trả kết quả gì.

### 6. Gửi ảnh Drive vào comment

- [x] Tách Drive link từ phản hồi AI bằng logic Pancake hiện có.
- [x] Lookup folder, chọn ảnh và cache/download bằng service hiện có.
- [x] Chỉ gửi ảnh sau khi text reply thành công.
- [x] Bắt buộc có file local và upload file qua Pancake để lấy `content_id`.
- [x] Gửi ảnh bằng `reply_comment`, không dùng `reply_inbox`.
- [x] Truyền đúng `comment_message_id` vào payload ảnh.
- [x] Mỗi payload ảnh chỉ có một `content_id` trong `content_ids`, không gửi đồng thời `message`.
- [x] Không gửi URL Drive trực tiếp tới Facebook hoặc nền tảng nguồn.
- [x] Nếu ảnh lỗi, giữ kết quả text thành công.
- [x] Lưu `pancake_drive_reply`, cache result và image send result trong bot meta.

Kết quả mong muốn:
  Phản hồi AI có link Drive được chuyển thành text sạch và ảnh lookbook hiển thị dưới đúng comment.

### 7. Logging

- [x] Log `PANCAKE_COMMENT_AI_START`.
- [x] Log `PANCAKE_COMMENT_AI_OK`.
- [x] Log `PANCAKE_COMMENT_AI_FAILED`.
- [x] Log `PANCAKE_COMMENT_REPLY_SEND_START`.
- [x] Log `PANCAKE_COMMENT_REPLY_SEND_OK`.
- [x] Log `PANCAKE_COMMENT_REPLY_SEND_FAILED`.
- [x] Log `PANCAKE_COMMENT_REPLY_SUPPRESSED_BY_ADMIN_PAUSE`.
- [x] Log `page_id`, `pancake_conversation_id`, `comment_message_id`, `message_mid`, reason.
- [x] Không log token.
- [x] Không log full URL có token.

Kết quả mong muốn:
  Có thể đọc log và biết flow fail ở AI, guard hay Pancake send.

### 8. Unit test end-to-end branch

- [x] Test comment happy path gọi AI và gửi `send_pancake_comment_reply`.
- [x] Test gửi đúng `page_id`.
- [x] Test gửi đúng `pancake_conversation_id`.
- [x] Test gửi đúng `comment_message_id`.
- [x] Test không gọi `send_pancake_reply`.
- [x] Test duplicate comment không gọi AI/send.
- [x] Test dangerous keyword blocked không gọi AI/send.
- [x] Test conversation paused không gọi AI/send.
- [x] Test pause xuất hiện trước send thì không gửi.
- [x] Test missing `comment_message_id` không gọi Pancake.
- [x] Test feature flag off không gửi Pancake.
- [x] Test bot message meta có `reply_action = reply_comment`.
- [x] Test comment có Drive image gọi `_send_pancake_drive_images`.
- [x] Test action ảnh là `reply_comment`.
- [x] Test media helper nhận đúng `comment_message_id`.
- [x] Test không gọi payload `send_pancake_content_ids` kiểu inbox cho ảnh comment.
- [x] Test mỗi ảnh comment được upload Pancake và gửi bằng một `content_id`.
- [x] Test bot meta lưu `pancake_drive_image_send_result`.

Kết quả mong muốn:
  Webhook branch mới được test đủ các đường quan trọng.

### 9. Regression và rollout

- [x] Chạy `pytest -q`.
- [x] Xác nhận tests Pancake inbox hiện có vẫn pass.
- [x] Xác nhận tests auto consult ad/comment notice vẫn pass.
- [ ] Deploy page test với flag off trước.
- [ ] Bật flag cho page test.
- [ ] Kiểm tra log webhook comment thật.
- [ ] Kiểm tra một comment text-only được reply đúng.
- [x] Kiểm tra một comment có Drive folder nhận đúng text và ảnh lookbook trên page test ngày 11/06/2026.
- [ ] Theo dõi duplicate/skipped/error reason.
- [ ] Chưa bật rộng nếu còn thiếu `conversation_id` hoặc `comment_message_id` trong payload thật.

Kết quả mong muốn:
  Rollout có kiểm soát, không spam comment và có đường tắt feature flag.

## Acceptance criteria

- [x] Comment hợp lệ có thể đi từ webhook tới Pancake `reply_comment`.
- [x] Không có comment path nào gửi `reply_inbox`.
- [x] Duplicate comment không gửi lần hai.
- [x] Admin pause chặn AI/send đúng kỳ vọng.
- [x] Missing `comment_message_id` không gọi Pancake API.
- [x] Bot message lưu đúng meta reply comment.
- [x] Ảnh Drive dùng đúng contract media `reply_comment`.
- [x] Regression test hiện có pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Sau khi deploy, nên quan sát log vài ngày để đo tỉ lệ thiếu `comment_message_id` và `pancake_conversation_id`.
- Nếu tỉ lệ thiếu ID cao, cần bổ sung phase resolve conversation/comment từ Pancake API thay vì gửi dựa trên dữ liệu không chắc chắn.
- Contract media đã có automated test và đã xác nhận thật bằng webhook echo có attachment trên page test.
