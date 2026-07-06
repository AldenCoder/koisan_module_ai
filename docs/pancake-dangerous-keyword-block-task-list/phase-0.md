# Task List Phase 0: Chốt giải pháp dangerous keyword block

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho lớp chặn dangerous keyword trong Pancake webhook. Lớp chặn này chạy sau normalize payload Pancake, nhưng trước mọi side effect như kiểm tra duplicate DB, tạo/lấy conversation, lưu message, gọi AI/RAG/Brain hoặc gửi reply Pancake.

Phase này chỉ chốt giải pháp và ranh giới trách nhiệm. Chưa sửa code, chưa thêm service, chưa thay đổi logging và chưa thêm test.

## Quyết định cần chốt

- Source keyword cố định là [docs/dangerous_keywords.md](../dangerous_keywords.md).
- Dangerous keyword block chỉ áp dụng cho tin nhắn khách hàng Pancake.
- Block chạy sau `normalize_pancake_payload`.
- Block chạy trước `_is_duplicate_pancake_message`.
- Block chạy trước `_get_or_create_pancake_conversation`.
- Block chạy trước `_save_pancake_user_message`.
- Khi match keyword, webhook trả internal result `ignored`.
- Khi match keyword, khách không nhận phản hồi nào từ bot.
- Khi match keyword, không gọi AI/RAG/Brain.
- Khi match keyword, không tạo/lấy/lưu `Conversation` hoặc `Message`.
- Block luôn bật, không thêm env bật/tắt trong phase đầu.
- Keyword reload theo `mtime` là behavior mặc định, không thêm env reload riêng.

## Ngoài phạm vi Phase 0

- Chưa implement service đọc keyword.
- Chưa sửa Pancake webhook flow.
- Chưa chỉnh raw payload logging.
- Chưa thêm audit storage.
- Chưa phân loại mức độ nguy hiểm theo category.
- Chưa build UI quản lý keyword.
- Chưa sửa nội dung file [docs/dangerous_keywords.md](../dangerous_keywords.md).
- Chưa thêm test.

## File tài liệu liên quan

- [docs/pancake-dangerous-keyword-block.md](../pancake-dangerous-keyword-block.md)
- [docs/dangerous_keywords.md](../dangerous_keywords.md)
- [docs/pancake-dangerous-keyword-block-task-list/phase-1.md](phase-1.md)
- [docs/pancake-dangerous-keyword-block-task-list/phase-2.md](phase-2.md)
- [docs/pancake-dangerous-keyword-block-task-list/phase-3.md](phase-3.md)
- [docs/pancake-dangerous-keyword-block-task-list/phase-4.md](phase-4.md)

## Checklist

### 1. Chốt source keyword

- [x] Xác nhận source keyword là [docs/dangerous_keywords.md](../dangerous_keywords.md).
- [x] Xác nhận mỗi dòng trong file là một keyword/cụm keyword.
- [x] Xác nhận bỏ qua dòng rỗng.
- [x] Xác nhận chỉ trim khoảng trắng đầu/cuối keyword khi load.
- [x] Xác nhận dedupe theo giá trị nguyên văn sau trim.
- [x] Xác nhận không sửa nội dung keyword trong task này.

Kết quả mong muốn:
  Team thống nhất một nguồn keyword duy nhất và tránh thêm config song song.

### 2. Chốt vị trí block trong webhook

- [x] Xác nhận block chạy sau bước normalize Pancake webhook.
- [x] Xác nhận block chạy trước duplicate DB check.
- [x] Xác nhận block chạy trước tạo/lấy conversation.
- [x] Xác nhận block chạy trước lưu user message.
- [x] Xác nhận block chạy trước gọi AI/RAG/Brain.
- [x] Xác nhận block chạy trước mọi call Pancake Public API.

Kết quả mong muốn:
  Message nguy hiểm không đi vào DB, AI hoặc Pancake reply.

### 3. Chốt behavior khi match keyword

- [x] Xác nhận webhook trả `status="ignored"`.
- [x] Xác nhận reason trả về là `pancake_dangerous_keyword_blocked`.
- [x] Xác nhận không phản hồi gì cho khách.
- [x] Xác nhận không gọi `_ensure_sender_initialized`.
- [x] Xác nhận không gọi `_post_ai_chat_with_retry`.
- [x] Xác nhận không gọi `send_pancake_reply`.
- [x] Xác nhận không gọi `send_pancake_content_ids`.
- [x] Xác nhận không upload ảnh hoặc xử lý Drive image reply.

Kết quả mong muốn:
  Block là fail-closed và không tạo side effect ngoài log tối thiểu.

### 4. Chốt behavior khi không match

- [x] Xác nhận flow Pancake hiện tại tiếp tục bình thường.
- [x] Xác nhận duplicate guard không đổi.
- [x] Xác nhận admin takeover không đổi.
- [x] Xác nhận bot echo vẫn bị ignore như hiện tại.
- [x] Xác nhận non-INBOX vẫn giữ behavior hiện tại.
- [x] Xác nhận message bán hàng bình thường vẫn lưu/gọi AI/gửi reply như hiện tại.

Kết quả mong muốn:
  Lớp chặn không làm lệch các flow hợp lệ đang hoạt động.

## Acceptance criteria

- [x] Team chốt source keyword là [docs/dangerous_keywords.md](../dangerous_keywords.md).
- [x] Team chốt dangerous keyword block chạy sau normalize và trước mọi side effect.
- [x] Team chốt khi match thì không lưu DB, không gọi AI và không gửi Pancake reply.
- [x] Team chốt block luôn bật trong phase đầu.
- [x] Team chốt keyword reload theo `mtime` là mặc định.

## Ghi chú mở

- Nếu sau này cần audit message bị chặn, nên mở task riêng với cơ chế redaction và retention rõ ràng.
- Nếu danh sách keyword gây false positive, xử lý bằng cách chỉnh [docs/dangerous_keywords.md](../dangerous_keywords.md), không thêm normalize ngầm trong code.
