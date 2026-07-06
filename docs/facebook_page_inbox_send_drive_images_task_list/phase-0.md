# Task List Phase 0: Chốt giải pháp mới và ranh giới trách nhiệm

## Mục tiêu

Phase 0 chốt lại hướng triển khai mới: BE hiện tại là nơi nhận/gửi Facebook message, gọi Brain, nhận data từ Brain, tự tách Drive link, tự lấy danh sách ảnh, rồi tự gửi ảnh cho khách.

Khác với phương án cũ, Brain không còn gọi endpoint `/drive-images` của BE để lấy danh sách ảnh. Endpoint cũ đã được gỡ khỏi router/code để tránh nhầm contract.

## Quyết định đã chốt

- BE nhận webhook message từ Facebook Page.
- BE gửi message/context sang Brain qua `FB_AI_CHAT_URL`.
- BE nhận response/data từ Brain.
- Brain trả text và Drive folder link liên quan đến sản phẩm.
- BE tự phân tích response/data, nếu có Drive link thì tách ra.
- BE tự gọi Google Drive API bằng `folder_id` và `GOOGLE_DRIVE_API_KEY`.
- BE tự tạo image URL dạng `https://lh3.googleusercontent.com/d/{id}`.
- BE chọn tối đa 1-3 ảnh sản phẩm để gửi khách.
- BE gửi text trước, gửi ảnh sau qua Messenger Send API.

## Ngoài phạm vi Phase 0

- Chưa sửa code xử lý Facebook webhook.
- Chưa sửa service gọi Brain.
- Chưa sửa service Google Drive image lookup.
- Chưa sửa logic gửi ảnh Messenger.
- Việc gỡ endpoint `/drive-images` được xử lý ở phase implementation, không phải quyết định contract ban đầu.

## File tài liệu liên quan

- [docs/facebook_page_inbox_send_drive_images.md](../facebook_page_inbox_send_drive_images.md)
- [docs/facebook_page_inbox_send_drive_images_task_list/phase-1.md](phase-1.md)
- [docs/facebook_page_inbox_send_drive_images_task_list/phase-2.md](phase-2.md)
- [docs/facebook_page_inbox_send_drive_images_task_list/phase-3.md](phase-3.md)
- [docs/facebook_page_inbox_send_drive_images_task_list/phase-4.md](phase-4.md)
- [docs/facebook_page_inbox_send_drive_images_task_list/phase-5.md](phase-5.md)

## Checklist

### 1. Chốt owner của luồng mới

- [x] Chốt BE là nơi điều phối Facebook message end-to-end.
- [x] Chốt BE là nơi xử lý Google Drive image lookup.
- [x] Chốt Brain chỉ trả text/data/Drive link cho BE.
- [x] Chốt Brain không cần gọi API riêng của BE để lấy ảnh.

Kết quả mong muốn:
  Team không còn nhầm giữa phương án cũ "Brain gọi BE lấy ảnh" và phương án mới "BE tự lấy ảnh sau khi nhận data từ Brain".

### 2. Chốt contract Brain trả về BE

- [x] Ưu tiên Brain trả field `text`.
- [x] Ưu tiên Brain trả field `drive_folder_urls`.
- [x] Cho phép fallback parse Drive link từ plain text nếu Brain chưa trả structured field.
- [x] Chốt `image_limit` nếu có cũng không được vượt quá 3.

Kết quả mong muốn:
  BE có input đủ rõ để tách text và Drive link mà không cần Brain gọi endpoint phụ.

### 3. Chốt output nội bộ của BE

- [x] BE tạo danh sách image URL nội bộ từ Google Drive file id.
- [x] Image URL dùng format `https://lh3.googleusercontent.com/d/{id}`.
- [x] BE chỉ chọn 1-3 ảnh cho một lượt trả lời.
- [x] BE dùng danh sách ảnh này để gửi Facebook, không bắt buộc trả ngược cho Brain.

Kết quả mong muốn:
  Danh sách ảnh là dữ liệu nội bộ của pipeline gửi Facebook.

### 4. Chốt thứ tự gửi Facebook

- [x] Text được gửi trước.
- [x] Ảnh được gửi ở message sau.
- [x] Nếu Drive lookup lỗi, text vẫn được gửi nếu có.
- [x] Nếu gửi ảnh lỗi, lỗi ảnh không làm hỏng toàn bộ luồng chat.

Kết quả mong muốn:
  Khách vẫn nhận phản hồi text ngay cả khi phần ảnh gặp sự cố.

## Acceptance criteria

- [x] Tài liệu chính đã mô tả đúng luồng mới.
- [x] Task list đã bỏ dependency chính vào endpoint `/drive-images`.
- [x] Ranh giới BE/Brain đã rõ.
- [x] Thứ tự gửi text trước, ảnh sau đã rõ.
- [x] Giới hạn 1-3 ảnh đã rõ.

## Ghi chú mở

- Endpoint `/drive-images` cũ đã được remove trong phase implementation vì không còn thuộc luồng chính.
- Nếu Brain chưa trả structured field, BE vẫn nên parse Drive link từ plain text trong phase đầu để rollout nhanh.
