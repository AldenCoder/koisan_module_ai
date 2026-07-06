# Task List Phase 0: Chốt contract auto consult từ Pancake webhook

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho flow Pancake auto consult. Flow này chỉ chạy khi webhook thuộc một trong hai trigger đã chốt: `ad_card` hoặc `page_comment_reply_notice`. BE hydrate bài viết/quảng cáo nguồn, bóc toàn bộ mã sản phẩm, tạo prompt cố định, gọi AI và gửi reply vào đúng hội thoại Pancake.

Phase này chỉ chốt giải pháp và ranh giới trách nhiệm. Chưa sửa code, chưa gọi Pancake API mới, chưa thay đổi logic gửi reply production.

Kết quả mong muốn:

- Có thứ tự actor rõ ràng để không ignore nhầm trigger page-side.
- Có prompt contract duy nhất cho một hoặc nhiều mã.
- Có ranh giới rõ giữa trigger được xử lý và page echo/system bị ignore.
- Có rule pause/idempotency trước khi implement.

## Quyết định cần chốt

- `ad_card` là trigger khi `message_mid` bắt đầu bằng `ad-`.
- `page_comment_reply_notice` là trigger khi sender là page, text chứa `Bạn đang phản hồi bình luận`, `message_tags` có `comment_id=`, attachments rỗng, `admin_name=null`, `uid=null`.
- System ad message kiểu khách đã trả lời quảng cáo không phải trigger riêng.
- Customer message thật vẫn đi theo flow Pancake hiện tại.
- Human admin thật vẫn pause bot.
- `Public API`, `POS`, `Botcake`, notification và page echo unknown thuộc `page_echo_or_automation`, ignore AI và không pause.
- Prompt cố định là `tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook`.
- Nếu nhiều mã trong description, lấy tất cả mã hợp lệ theo thứ tự xuất hiện, dedupe mã trùng.
- Nếu không có mã, không gọi AI và không gửi reply.
- Nếu conversation đang admin pause, không gọi AI và không gửi reply.

## Ngoài phạm vi Phase 0

- Chưa implement fetch Pancake Conversation Messages API.
- Chưa implement parser ad/comment context.
- Chưa thay đổi `_process_normalized_message`.
- Chưa thêm config mới.
- Chưa thêm test.

## File tài liệu liên quan

- [docs/pancake-webhook-ad-message.md](../pancake-webhook-ad-message.md)
- [docs/pancake-webhook-ad-message-task-list/phase-1.md](phase-1.md)
- [docs/pancake-webhook-ad-message-task-list/phase-2.md](phase-2.md)
- [docs/pancake-webhook-ad-message-task-list/phase-3.md](phase-3.md)
- [docs/pancake-webhook-ad-message-task-list/phase-4.md](phase-4.md)
- [docs/pancake-webhook-ad-message-task-list/phase-5.md](phase-5.md)

## Checklist

### 1. Chốt actor và thứ tự classify

- [x] Chốt thứ tự actor: `ad_card -> page_comment_reply_notice -> customer_message -> human_admin_message -> page_echo_or_automation`.
- [x] Xác nhận `ad_card` phải đứng trước page echo vì `ad-*` là page-side echo.
- [x] Xác nhận `page_comment_reply_notice` phải đứng trước page echo vì notice cũng là page-side echo.
- [x] Xác nhận customer thật được nhận diện bằng sender không phải page.
- [x] Xác nhận `POS` và `Botcake` không còn được xem là `human_admin_message`.

Kết quả mong muốn:
  BE chỉ chủ động xử lý đúng hai trigger có thể hydrate bài viết nguồn, không pause nhầm automation.

### 2. Chốt prompt và mã sản phẩm

- [x] Chốt regex phase đầu `\b[A-Z]{1,3}\d{5,10}\b`.
- [x] Chốt lấy tất cả mã hợp lệ trong description.
- [x] Chốt dedupe mã trùng nhưng giữ thứ tự xuất hiện đầu tiên.
- [x] Chốt không parse chuỗi toàn số như `ad_id`, `post_id`.
- [x] Chốt prompt một mã: `tư vấn mẫu S7671263 và gửi ảnh lookbook`.
- [x] Chốt prompt nhiều mã: `tư vấn mẫu S7671263, S7672889 và gửi ảnh lookbook`.
- [x] Chốt không gửi raw description sang AI trong phase đầu.

Kết quả mong muốn:
  AI nhận một prompt ngắn, ổn định và đủ yêu cầu gửi lookbook.

### 3. Chốt guard an toàn

- [x] Chốt duplicate key: `page_id + pancake_conversation_id + trigger_type + trigger_message_mid`.
- [x] Chốt không gọi AI nếu thiếu `page_id`.
- [x] Chốt không gọi AI nếu thiếu `pancake_conversation_id`.
- [x] Chốt không gọi AI nếu thiếu token theo page.
- [x] Chốt không gọi AI hoặc không gửi reply khi conversation đang admin pause.
- [x] Chốt kiểm tra pause lần hai trước khi gửi Pancake reply.

Kết quả mong muốn:
  Flow không spam khách, không gửi nhầm hội thoại và không đè người thật.

## Acceptance criteria

- [x] Team chốt 5 actor và thứ tự classify.
- [x] Team chốt 2 trigger auto consult.
- [x] Team chốt prompt lookbook cho một và nhiều mã.
- [x] Team chốt duplicate guard.
- [x] Team chốt behavior khi thiếu description, thiếu mã, hoặc đang admin pause.

## Ghi chú mở

- Nếu sau này cần prompt khác cho từng page, nên thêm config riêng thay vì hard-code nhiều nhánh trong webhook.
- Nếu caption có mã dạng có dấu gạch hoặc khoảng trắng, cần business xác nhận trước khi mở rộng regex.
