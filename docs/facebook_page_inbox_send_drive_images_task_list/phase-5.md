# Task List Phase 5: Test, rollout, và dọn hướng cũ

## Mục tiêu

Phase 5 hoàn thiện test, cập nhật env/docs, chạy regression, và rollout an toàn cho phương án mới. Phase này cũng cần xử lý sự nhập nhằng với endpoint `/drive-images` của phương án cũ.

Kết quả mong muốn:

- Test chính pass bằng `pytest -q`.
- Docs/env phản ánh đúng luồng mới.
- Endpoint `/drive-images` cũ được remove để tránh nhầm contract.
- Rollout không commit secret thật.

## Đầu vào đã chốt

- Repo dùng Python 3.11.
- Không chạy `pre-commit`.
- Test chạy bằng `pytest -q`.
- Tests không yêu cầu external service.
- Secret thật không được commit vào repo.

## Ngoài phạm vi Phase 5

- Không deploy Brain/AI Agent trong repo này.
- Không thêm dashboard/metrics mới nếu chưa cần.
- Không manual test Google/Facebook thật trong CI.
- Không thêm queue/retry/dedupe persistent.

## File chính dự kiến sửa

- [.env.example](../../.env.example)
- [docs/facebook_page_inbox_send_drive_images.md](../facebook_page_inbox_send_drive_images.md)
- [app/api/router_v1.py](../../app/api/router_v1.py)
- [app/api/v1/facebook_webhook.py](../../app/api/v1/facebook_webhook.py)
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)
- [tests/test_facebook_message_service.py](../../tests/test_facebook_message_service.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)

## Checklist

### 1. Hoàn thiện unit/integration test

- [x] Test Brain response structured có `drive_folder_urls`.
- [x] Test Brain response text thuần có Drive link.
- [x] Test Brain response không có Drive link giữ luồng text hiện tại.
- [x] Test parse Drive folder URL.
- [x] Test Google Drive API response parsing.
- [x] Test convert file id thành `imageUrl`.
- [x] Test chọn tối đa 1-3 ảnh.
- [x] Test text được gửi trước ảnh.
- [x] Test payload Facebook attachment/attachments.
- [x] Test fallback gửi từng ảnh.

Kết quả mong muốn:
  Các behavior chính của phương án mới đều có test tự động.

### 2. Regression local

- [x] Chạy `pytest -q`.
- [x] Xác nhận test không gọi Google Drive thật.
- [x] Xác nhận test không gọi Facebook thật.
- [x] Xác nhận test không gọi Brain thật nếu không mock.
- [x] Không chạy `pre-commit`.

Kết quả mong muốn:
  Có tín hiệu regression nhanh đúng guideline repo.

### 3. Cập nhật env/docs

- [x] `.env.example` mô tả `GOOGLE_DRIVE_API_KEY` dùng cho BE tự lookup ảnh.
- [x] Docs ghi rõ `FB_AI_CHAT_URL` là nơi BE gọi Brain.
- [x] Docs ghi rõ Brain trả Drive link cho BE.
- [x] Docs ghi rõ BE tự gửi text + ảnh cho Facebook.
- [x] Docs ghi rõ không commit secret thật.

Kết quả mong muốn:
  Người deploy không cấu hình theo nhầm phương án cũ.

### 4. Dọn hoặc đánh dấu hướng cũ

- [x] Quyết định remove endpoint `/drive-images`.
- [x] Không giữ endpoint phụ để tránh nhầm contract chính của luồng mới.
- [x] Xóa auth nội bộ chỉ dùng cho endpoint cũ.
- [x] Xóa route/schema/test liên quan.
- [x] Cập nhật comment `.env.example`, không còn nhắc `/api/v1/drive-images` như luồng chính.

Kết quả mong muốn:
  Code/docs không làm team hiểu nhầm rằng Brain vẫn phải gọi BE để lấy ảnh.

### 5. Manual rollout checklist

- [ ] Set `GOOGLE_DRIVE_API_KEY` trên BE production.
- [ ] Kiểm tra Drive folder public hoặc quyền đọc metadata phù hợp.
- [ ] Kiểm tra Brain trả structured `drive_folder_urls` nếu có thể.
- [ ] Test một hội thoại có text không ảnh.
- [ ] Test một hội thoại có một Drive folder.
- [ ] Test một hội thoại có nhiều Drive folder.
- [ ] Test Page Inbox nhận text trước và ảnh sau.
- [ ] Kiểm tra log không lộ secret.

Kết quả mong muốn:
  Rollout có đường kiểm tra rõ trước khi mở rộng cho traffic thật.

### 6. Rollback và monitoring

- [ ] Có cách tắt nhanh phần Drive lookup nếu lỗi.
- [ ] Có cách fallback về text-only nếu Facebook media lỗi.
- [ ] Theo dõi lỗi Drive API `403`/`404`.
- [ ] Theo dõi lỗi Facebook media send.
- [ ] Theo dõi latency khi folder có nhiều ảnh.

Kết quả mong muốn:
  Nếu production có sự cố, có thể quay về text-only mà không tắt toàn bộ webhook.

## Acceptance criteria

- [x] `pytest -q` pass.
- [x] Docs/env phản ánh đúng phương án BE tự xử lý Drive.
- [x] Luồng Brain gọi BE endpoint `/drive-images` không còn là contract chính.
- [x] BE gửi được text trước, ảnh sau.
- [x] BE chỉ gửi 1-3 ảnh.
- [x] Có checklist rollout và rollback rõ.

## Ghi chú mở

- Nếu Brain chưa thể trả structured field ngay, giữ parser plain text để triển khai trước.
- Nếu sau rollout có duplicate media do retry, bài toán dedupe nên tách sang phase sau.
