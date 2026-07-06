# Task List Phase 6: Hotfix verify Pancake echo và retry content_ids

## Mục tiêu

Phase 6 bổ sung lớp xác minh delivery cho tin nhắn ảnh Pancake. HTTP 200 khi gửi `content_ids` chỉ được xem là API request thành công; ảnh chỉ được xem là gửi thành công thật khi Pancake echo lại một message mới từ `Public API` có attachment.

Kết quả mong muốn:

- Sau khi gửi image message, BE chờ webhook echo ảnh trong 1 giây.
- Nếu HTTP 200 nhưng không có echo attachment, BE resend cùng danh sách `content_ids`.
- Tối đa 3 delivery attempt cho cùng một lần gửi ảnh.
- Attempt 2 và attempt 3 không download lại Drive, không upload lại Pancake, không tạo `content_id` mới.
- Cơ chế xóa file local sau upload thành công khi reuse bật vẫn giữ nguyên.
- Kết quả gửi ảnh có metadata rõ ràng để debug: attempt count, echo verified hay chưa, message id echo nếu có.

## Đầu vào đã chốt

- Log thực tế cho các case ảnh xuất hiện cho thấy echo `Public API` có `attachment_count > 0` về trong khoảng tối đa khoảng `0.488` giây sau `PANCAKE_DRIVE_IMAGE_SEND_OK`.
- Thời gian chờ echo của mỗi delivery attempt là `1` giây.
- Attempt 1 dùng flow hiện tại để có `content_ids`.
- Attempt 2 resend đúng `content_ids` đã có.
- Attempt 3 resend đúng `content_ids` đã có.
- Không tải ảnh mới và không upload ảnh mới trong attempt 2/3.
- `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true` vẫn được phép xóa file local ngay sau upload thành công.
- Text reply đã gửi trước đó không bị gửi lại do lỗi ảnh.

## Ngoài phạm vi Phase 6

- Không thêm queue/outbox persistent.
- Không đổi flow chọn ảnh từ Drive folder.
- Không đổi logic download, resize/compress hoặc cache ảnh.
- Không đổi endpoint Pancake dùng để gửi `content_ids`.
- Không thay đổi chính sách local image cleanup.
- Không retry vô hạn hoặc tạo background worker mới.
- Không gửi raw Drive link cho khách như fallback ảnh.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py), nếu cần mở rộng metadata/log response gửi `content_ids`.
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py), nếu service contract thay đổi.

## Checklist

### 1. Echo tracker

- [x] Tạo helper nhận diện echo ảnh Pancake từ normalized webhook payload.
- [x] Điều kiện echo ảnh: cùng `page_id`, cùng `pancake_conversation_id`, `is_echo=true`, `message_from_admin_name="Public API"` và `attachment_count > 0`.
- [x] Ghi nhận echo ảnh vào in-memory tracker trước khi `_process_normalized_message` ignore bot echo.
- [x] Key tracker theo `page_id` và `pancake_conversation_id`.
- [x] Tracker lưu tối thiểu `message_mid`, `attachment_count`, thời điểm nhận webhook, và timestamp/inserted_at nếu có.
- [x] Tracker có TTL ngắn để tránh memory leak và tránh verify nhầm echo quá cũ.

Kết quả mong muốn:
  Webhook echo ảnh được ghi nhận dù bot echo vẫn bị ignore trong flow xử lý message chính.

### 2. Verify window

- [x] Khi gửi image message, tạo `verify_started_at` ngay trước lúc gọi API gửi `content_ids`.
- [x] Không chỉ dựa vào thời điểm log `PANCAKE_DRIVE_IMAGE_SEND_OK`, vì webhook có thể về sát hoặc trước dòng log HTTP 200.
- [x] Helper verify chỉ accept echo nằm trong cửa sổ của attempt hiện tại hoặc sau `verify_started_at`.
- [x] Mỗi attempt chờ echo tối đa `1` giây.
- [x] Trước mỗi retry, check lại tracker một lần để tránh gửi trùng nếu echo vừa tới sát thời điểm retry.

Kết quả mong muốn:
  BE phân biệt được HTTP success với delivery success, và không retry nếu echo thật đã xuất hiện.

### 3. Delivery attempt flow

- [x] Attempt 1 giữ flow hiện tại: reuse/upload để có danh sách `content_ids`, rồi gửi image message.
- [x] Nếu attempt 1 HTTP fail, giữ retry/error behavior HTTP hiện có của service và không chuyển sang echo retry giả.
- [x] Nếu attempt 1 HTTP 200 nhưng không có echo attachment trong 1 giây, attempt 2 resend cùng `content_ids`.
- [x] Nếu attempt 2 HTTP 200 nhưng không có echo attachment trong 1 giây, attempt 3 resend cùng `content_ids`.
- [x] Attempt 2 và attempt 3 không gọi Drive download.
- [x] Attempt 2 và attempt 3 không gọi Pancake upload.
- [x] Attempt 2 và attempt 3 không mutate cache `content_id`.
- [x] Không gửi lại text message ở bất kỳ image retry attempt nào.
- [x] Dừng retry ngay khi có echo attachment verified.

Kết quả mong muốn:
  Retry chỉ tác động lên image delivery bằng `content_ids`, không làm phát sinh upload/download hoặc text duplicate.

### 4. Local cleanup và cache

- [x] Giữ nguyên behavior xóa file local sau upload thành công khi `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`.
- [x] Không yêu cầu file local tồn tại cho attempt 2/3.
- [x] Retry dùng `content_ids` đã gom được từ attempt 1.
- [x] Nếu attempt 1 dùng toàn bộ `content_id` cache hit, retry vẫn dùng chính danh sách đó.
- [x] Nếu attempt 1 vừa upload vừa reuse cache, retry vẫn dùng danh sách `content_ids` cuối cùng đã gửi.

Kết quả mong muốn:
  Hotfix không đảo ngược quyết định dọn file local và không làm tăng disk usage.

### 5. Logging và result metadata

- [x] Log bắt đầu delivery verify với `page_id`, `conversation_id`, `message_mid`, `content_id_count`, `max_attempts`, `echo_wait_seconds`.
- [x] Log từng attempt với `attempt`, HTTP `status_code`, `content_id_count`, `echo_verified` và reason nếu chưa verified.
- [x] Log khi retry vì HTTP 200 nhưng thiếu echo attachment.
- [x] Log khi echo được verify, gồm `verified_message_mid` và `verified_attachment_count`.
- [x] Log khi hết 3 attempt vẫn chưa có echo attachment.
- [x] `image_send_result` trả thêm `attempt_count`.
- [x] `image_send_result` trả thêm `echo_verified`.
- [x] `image_send_result` trả thêm `verified_message_mid` nếu có.
- [x] `image_send_result` trả thêm `verified_attachment_count` nếu có.
- [x] `image_send_result` trả reason rõ như `pancake_image_echo_not_observed` hoặc `unverified_after_attempts` khi không verified.

Kết quả mong muốn:
  Log và bot message meta đủ để điều tra case HTTP 200 nhưng ảnh không xuất hiện.

### 6. Test phase 6

- [x] Test helper nhận diện đúng echo ảnh `Public API` có attachment.
- [x] Test helper không nhận echo text-only `Public API`.
- [x] Test helper không nhận attachment từ khách hoặc human admin.
- [x] Test attempt 1 có echo trong 1 giây thì không retry.
- [x] Test không có echo thì retry đủ 3 lần với cùng `content_ids`.
- [x] Test echo đến trước/sát HTTP 200 vẫn được verify vì cửa sổ bắt đầu trước API call.
- [x] Test trước retry nếu tracker đã có echo thì không gửi attempt tiếp theo.
- [x] Test attempt 2/3 không gọi download Drive.
- [x] Test attempt 2/3 không gọi upload Pancake.
- [x] Test vẫn xóa local image sau upload thành công khi reuse bật.
- [x] Test hết 3 attempt vẫn không có echo thì `echo_verified=false`.
- [x] Test hết 3 attempt vẫn không có echo thì text reply không bị gửi lại.
- [x] Test result lưu đủ `attempt_count`, `echo_verified`, `verified_message_mid`, `verified_attachment_count`.
- [x] Chạy `pytest -q`.

Kết quả mong muốn:
  Retry path được cover bằng mock, không cần gọi Pancake hoặc Google Drive thật.

## Acceptance criteria

- [x] HTTP 200 khi gửi `content_ids` không còn là điều kiện thành công cuối cùng nếu thiếu echo attachment.
- [x] Case có echo attachment trong 1 giây pass ngay attempt 1.
- [x] Case không có echo attachment retry tối đa 3 delivery attempt.
- [x] Attempt 2/3 resend cùng `content_ids`, không download/upload lại.
- [x] Local cleanup sau upload vẫn giữ nguyên.
- [x] Log thể hiện rõ attempt nào verified hoặc vì sao không verified.
- [x] Test phase này pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Nếu sau này cần đảm bảo delivery xuyên process restart, có thể nâng cấp từ in-memory tracker sang outbox/DB event, nhưng không nằm trong hotfix này.
- Nếu Pancake có response body chứa message id khi gửi `content_ids`, nên log rút gọn message id đó để đối chiếu với webhook echo.
- Nếu production xuất hiện echo thật chậm hơn 1 giây, có thể tăng wait window bằng config sau khi có số liệu mới.
