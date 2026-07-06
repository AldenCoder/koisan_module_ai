# Task List Phase 0: Chốt giải pháp Pancake Drive link image reply

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho flow Pancake gửi ảnh từ Google Drive file/folder link. Flow này chạy sau khi AI trả response trong Pancake webhook hiện tại: BE tách Drive link khỏi text, gửi text trước, xử lý ảnh qua folder lookup/cache/download/upload, rồi gửi ảnh bằng `content_ids`.

Phase này chỉ chốt giải pháp và ranh giới trách nhiệm. Chưa sửa code, chưa thêm service, chưa gọi Google Drive hoặc Pancake upload thật.

## Quyết định cần chốt

- BE là nơi xử lý Drive file/folder link sau khi AI trả response.
- AI/Brain chỉ trả text và Drive file/folder link public, không gọi Google Drive API.
- AI/Brain không gọi Pancake Public API và không trả trực tiếp `content_id`.
- Reply Pancake gồm hai bước: gửi text đã tách raw Drive link trước, rồi gửi ảnh bằng `content_ids` sau.
- Phase đầu xử lý Drive file link public và Drive folder link public.
- Giới hạn số ảnh mỗi reply, mặc định 3.
- Không thay đổi rule hiện tại về duplicate message, bot pause, admin takeover và text-only customer message.
- Raw Drive link chỉ bị tách khỏi bot reply text, không tách khỏi user message đã lưu.
- Nếu không có Drive link, flow Pancake text reply hiện tại không đổi.

## Ngoài phạm vi Phase 0

- Chưa implement parser Drive URL.
- Chưa tạo cache JSON.
- Chưa download ảnh từ Google Drive.
- Chưa upload file lên Pancake.
- Chưa gửi message có `content_ids`.
- Chưa thay đổi database schema.
- Chưa thêm test.

## File tài liệu liên quan

- [docs/pancake-drive-link-image-reply.md](../pancake-drive-link-image-reply.md)
- [docs/pancake-drive-link-image-reply-task-list/phase-1.md](phase-1.md)
- [docs/pancake-drive-link-image-reply-task-list/phase-2.md](phase-2.md)
- [docs/pancake-drive-link-image-reply-task-list/phase-3.md](phase-3.md)
- [docs/pancake-drive-link-image-reply-task-list/phase-4.md](phase-4.md)
- [docs/pancake-drive-link-image-reply-task-list/phase-5.md](phase-5.md)

## Checklist

### 1. Chốt ranh giới BE và AI

- [x] Xác nhận AI chỉ trả text và Drive file link public.
- [x] Xác nhận BE tự tách Drive file link khỏi AI response.
- [x] Xác nhận BE tự extract `drive_file_id`.
- [x] Xác nhận BE tự xử lý cache/download/upload ảnh.
- [x] Xác nhận AI không cần biết `content_id` Pancake.
- [x] Xác nhận AI không cần gọi Google Drive hoặc Pancake API.

Kết quả mong muốn:
  Trách nhiệm của AI và BE được tách rõ, tránh đẩy logic tích hợp sang AI.

### 2. Chốt thứ tự gửi message

- [x] Xác nhận tin nhắn text được gửi trước.
- [x] Xác nhận text gửi cho khách đã tách raw Drive link.
- [x] Xác nhận tin nhắn ảnh được gửi sau bằng `content_ids`.
- [x] Xác nhận không gửi image message nếu `content_ids` rỗng.
- [x] Xác nhận nếu ảnh lỗi hết, khách vẫn nhận text nếu text hợp lệ.

Kết quả mong muốn:
  Khách không thấy raw Drive link và vẫn nhận được phản hồi text khi media lỗi.

### 3. Chốt phạm vi Drive link

- [x] Xác nhận phase đầu xử lý Drive file link public.
- [x] Xác nhận phase đầu xử lý Drive folder link public bằng Google Drive folder lookup.
- [x] Xác nhận không crawl folder đệ quy, chỉ lấy ảnh trực tiếp trong folder.
- [x] Xác nhận link không thuộc `drive.google.com` bị bỏ qua.
- [x] Xác nhận link không extract được `drive_file_id` bị bỏ qua theo từng link.
- [x] Xác nhận một link lỗi không làm hỏng toàn bộ reply.

Kết quả mong muốn:
  Scope Drive đủ nhỏ để implement an toàn và dễ test.

### 4. Chốt giới hạn và rule không đổi

- [x] Xác nhận số ảnh tối đa mỗi reply mặc định là 3.
- [x] Xác nhận duplicate message vẫn được xử lý như flow Pancake hiện tại.
- [x] Xác nhận bot pause/admin takeover vẫn được ưu tiên như flow Pancake hiện tại.
- [x] Xác nhận text-only customer message rule không bị thay đổi.
- [x] Xác nhận user message đã lưu không bị rewrite để xóa Drive link.

Kết quả mong muốn:
  Flow mới chỉ bổ sung media reply sau AI, không làm lệch các guard hiện có.

## Acceptance criteria

- [x] Team chốt BE là nơi xử lý Drive file/folder link và Pancake media upload.
- [x] Team chốt thứ tự gửi text trước, ảnh sau.
- [x] Team chốt phase đầu xử lý Drive file link public và Drive folder link public.
- [x] Team chốt giới hạn mặc định 3 ảnh mỗi reply.
- [x] Team chốt không thay đổi rule duplicate, pause, admin takeover và text-only.

## Ghi chú mở

- Drive folder link hiện reuse logic Google Drive folder lookup đã có ở flow Facebook, nhưng output được chuyển thành `drive_file_id` để đi qua cache/upload Pancake.
- Cache reuse `content_id` đã được bật bằng `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`; nếu Pancake không cho reuse ổn định, có thể tắt cấu hình này để upload lại từ file local.
