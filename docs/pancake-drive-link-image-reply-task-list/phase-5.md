# Task List Phase 5: Test và rollout

## Mục tiêu

Phase 5 hoàn thiện test coverage và kế hoạch rollout cho flow Pancake Drive link image reply. Toàn bộ flow cần được test bằng mock, không gọi Google Drive hoặc Pancake thật trong test suite.

Kết quả mong muốn:

- Unit test cover parser/folder lookup/cache/download/upload.
- Webhook test cover luồng text trước, ảnh sau.
- Error path chính được cover.
- `pytest -q` pass.
- Có checklist rollout production an toàn.

## Đầu vào đã chốt

- Tests không cần external service.
- Google Drive folder lookup, Google Drive download và Pancake API được mock.
- Flow hiện tại không đổi nếu AI không trả Drive link.
- Rule duplicate, bot pause, admin takeover và text-only message không bị regression.

## Ngoài phạm vi Phase 5

- Không gọi Google Drive thật.
- Không gọi Pancake thật.
- Không load ảnh thật lớn trong test.
- Không benchmark tải lớn nếu chưa có yêu cầu riêng.

## File chính dự kiến sửa

- `tests/test_pancake_drive_image_service.py`
- `tests/test_pancake_message_service.py`
- `tests/test_pancake_webhook.py`
- Test fixture/helper nếu cần.

## Checklist

### 1. Test parser và prepare reply

- [x] Test extract `drive_file_id` từ URL `/file/d/{id}/view`.
- [x] Test extract `drive_file_id` từ URL `/file/d/{id}/view?usp=drive_link`.
- [x] Test extract `drive_file_id` từ URL `uc?export=download&id={id}`.
- [x] Test extract `drive_file_id` từ URL `open?id={id}`.
- [x] Test tách Drive file link khỏi AI text và giữ lại text sạch.
- [x] Test tách Drive folder link khỏi AI text và giữ lại text sạch.
- [x] Test Drive folder link được lookup thành danh sách `drive_file_ids`.
- [x] Test nhiều Drive link trong cùng AI response.
- [x] Test URL sai host bị bỏ qua.
- [x] Test không có Drive link thì flow text hiện tại không đổi.

Kết quả mong muốn:
  Parser hoạt động ổn định với các URL đã chốt.

### 2. Test cache và download

- [x] Test cache chưa tồn tại thì khởi tạo cache rỗng.
- [x] Test cache có `content_id` và reuse bật thì không cần file local, không download Drive.
- [x] Test cache có `content_id` nhưng reuse tắt thì vẫn chuẩn bị file local để upload lại.
- [x] Test cache hit có file local thì không download lại.
- [x] Test cache hit có file local lớn hơn ngưỡng Pancake thì resize/compress lại và không download.
- [x] Test file local lớn hơn ngưỡng nhưng không đọc được thì download lại từ Drive.
- [x] Test cache miss thì download ảnh.
- [x] Test download dùng đúng direct download URL.
- [x] Test download dùng `follow_redirects=True` để xử lý `303 See Other`.
- [x] Test download thành công với ảnh lớn thì lưu file local dưới `PANCAKE_IMAGE_STORAGE_MAX_BYTES`.
- [x] Test PNG tải về được convert thành JPEG trước khi lưu local.
- [x] Test download thành công thì lưu file local.
- [x] Test download thành công thì update cache JSON.
- [x] Test content type không hợp lệ thì bỏ qua.
- [x] Test download timeout/error không crash toàn batch.

Kết quả mong muốn:
  Cache/download không phụ thuộc external network trong test.

### 3. Test upload và gửi message Pancake

- [x] Test upload multipart lên đúng endpoint `upload_contents`.
- [x] Test upload gửi đúng field `file`.
- [x] Test parse `content_id` từ response thành công.
- [x] Test response thiếu `content_id` trả lỗi rõ ràng.
- [x] Test lưu `content_id` vào cache sau upload thành công.
- [x] Test xóa file local sau upload thành công khi reuse bật.
- [x] Test reuse `content_id` đã cache thì không upload lại.
- [x] Test tắt reuse `content_id` thì upload lại và dùng `content_id` mới.
- [x] Test gửi text message trước.
- [x] Test gửi image message sau bằng `content_ids`.
- [x] Test không gửi image message khi `content_ids` rỗng.

Kết quả mong muốn:
  Pancake API integration được mock đầy đủ và assert đúng payload.

### 4. Test webhook end-to-end bằng mock

- [x] Mock AI trả text không có Drive link, assert flow cũ không đổi.
- [x] Mock AI trả text có một Drive link, assert gửi text rồi gửi ảnh.
- [x] Mock cache có `content_id` reusable, assert không download lại ảnh Drive.
- [x] Mock AI trả Drive folder link, assert lookup folder, cache ảnh, gửi text rồi gửi ảnh.
- [x] Mock AI trả nhiều Drive link, assert giới hạn tối đa 3 ảnh.
- [x] Mock download lỗi một ảnh, assert ảnh còn lại vẫn được gửi.
- [x] Mock upload lỗi một ảnh, assert content id còn lại vẫn được gửi.
- [x] Mock tất cả ảnh lỗi, assert vẫn gửi text nếu text hợp lệ.
- [x] Assert user message không bị rewrite.
- [x] Assert bot text message không chứa raw Drive link.

Kết quả mong muốn:
  Webhook flow mới được kiểm tra ở mức hành vi người dùng nhận được.

### 5. Test regression guard hiện có

- [x] Test duplicate `message_mid` không gọi AI/download/upload/send.
- [x] Test conversation đang pause không gọi AI/download/upload/send.
- [x] Test admin takeover trước khi gọi AI vẫn suppress flow.
- [x] Test admin pause trước khi gửi reply vẫn suppress send.
- [x] Test non-text customer message vẫn không gọi AI.
- [x] Test quota fallback hiện có không bị ảnh hưởng.
- [x] Test token không xuất hiện trong log.
- [x] Kiểm tra Google Drive API key không bị log qua URL request đầy đủ.

Kết quả mong muốn:
  Flow media mới không phá guard đã có của Pancake webhook.

### 6. Rollout

- [x] Chạy `pytest -q`.
- [x] Kiểm tra `.gitignore` đã loại storage cache/images nếu cần.
- [x] Kiểm tra env/config mới có default an toàn.
- [x] Kiểm tra dependency `Pillow` đã có trong `requirements.txt` để resize/compress ảnh.
- [x] Kiểm tra log không in token.
- [x] Kiểm tra log không in Google Drive API key.
- [x] Kiểm tra timeout download/upload đủ ngắn.
- [ ] Nếu có feature flag, bật thử ở môi trường staging trước.
- [ ] Theo dõi log nhóm lỗi: parse failed, download failed, upload failed, send image failed.

Kết quả mong muốn:
  Có thể rollout có kiểm soát và rollback được nếu media path lỗi.

## Acceptance criteria

- [x] Parser tests pass.
- [x] Cache/download tests pass.
- [x] Pancake upload/send tests pass.
- [x] Webhook end-to-end mock tests pass.
- [x] Regression guard tests pass.
- [x] `pytest -q` pass.
- [x] Rollout checklist được review.

## Ghi chú mở

- Nếu sau này chuyển webhook sang background worker, test nên tách thêm job/outbox behavior.
- Nếu Pancake upload API có response thực tế khác tài liệu, cập nhật service normalize và fixture ngay khi có mẫu thật.
