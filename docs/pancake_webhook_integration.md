# Tích hợp Pancake Webhook nhận tin nhắn mới và gửi phản hồi

## Mục tiêu

Tài liệu này mô tả phương án tích hợp Pancake Webhook để `BE` nhận tin nhắn mới từ khách hàng, chuẩn hóa dữ liệu về cùng kiểu xử lý với webhook Facebook hiện tại, lưu được hội thoại/tin nhắn vào database, sau đó gửi nội dung sang AI/rule và gọi Pancake Public API để phản hồi khách.

Điểm thay đổi chính: `BE` không đưa raw webhook Pancake trực tiếp vào logic xử lý. Payload Pancake cần được normalize về object nội bộ tương tự object `latest` của Facebook webhook để không làm ảnh hưởng tổng thể flow hiện tại: lấy/tạo `Conversation`, chống trùng `message_mid`, enqueue hoặc xử lý message, lưu `Message`, rồi gửi reply.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận event từ các kênh social và gửi webhook sang BE.
- `AI Agent` / `Brain`: service xử lý nội dung hội thoại nếu flow Pancake dùng AI.
- `page_id`: page/channel phát sinh event trong Pancake.
- `pancake_conversation_id`: id hội thoại phía Pancake.
- `message_mid`: id tin nhắn dùng để chống xử lý trùng, tương tự Facebook `message.mid`.
- `customer_id`: id khách hàng nội bộ đang lưu ở `conversations.customer_id`.

## Luồng tổng thể

Khách hàng nhắn tin vào kênh social đã nối Pancake.

Pancake gửi `messaging` webhook sang `BE` tại endpoint đề xuất `/api/v1/pancake/webhook`.

`BE` parse raw payload, log an toàn, kiểm tra event hợp lệ, rồi normalize về object nội bộ.

`BE` dùng object nội bộ để lấy hoặc tạo `Conversation` theo `customer_id`, tương tự cách Facebook webhook đang tìm bằng `sender_id`.

`BE` chống xử lý trùng bằng `message_mid`, kiểm tra trạng thái hội thoại, sau đó đưa message vào queue hoặc xử lý trực tiếp tùy implementation.

`BE` gọi AI/rule để tạo phản hồi, lưu message user/bot vào database, rồi gửi reply qua Pancake Public API.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận webhook `POST` từ Pancake.
- Validate payload tối thiểu trước khi xử lý.
- Chuẩn hóa payload Pancake về object nội bộ ổn định.
- Mapping object nội bộ sang model `Conversation` và `Message` hiện có.
- Chống xử lý trùng bằng `message_mid`.
- Không phụ thuộc vào raw payload Pancake trong các bước xử lý chính.
- Gọi AI/rule theo flow hiện có hoặc flow riêng của Pancake.
- Gửi phản hồi qua Pancake Public API.
- Không log token hoặc dữ liệu nhạy cảm.

### Pancake

Pancake chịu trách nhiệm:

- Nhận event từ Facebook, TikTok, Zalo hoặc kênh social đã kết nối.
- Gửi webhook khi có message mới.
- Cung cấp `page_id`, thông tin conversation, message, sender và attachment nếu có.
- Cung cấp Public API để gửi reply theo `page_id` và `conversation_id`.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Nhận text, public image URL nếu khách gửi ảnh, và context hội thoại đã được BE chuẩn hóa.
- Trả nội dung phản hồi để BE gửi lại khách.
- Không cần hiểu raw payload Pancake.
- Không cần tự gọi Pancake Public API.

### Ngoài phạm vi phương án này

- Không thêm bảng mới nếu `conversations` và `messages` hiện tại đã đủ lưu hội thoại.
- Không đổi flow Facebook webhook hiện tại.
- Không yêu cầu Pancake đổi format webhook.
- Không build màn hình admin mới.
- Không upload/rehost ảnh khách gửi trong phase đầu; nếu Pancake đã trả public image URL thì BE dùng trực tiếp URL đó để gửi sang AI.

## Contract dữ liệu từ Pancake

Webhook Pancake cho tin nhắn mới cần được hiểu theo các block chính:

| Block | Ý nghĩa |
|---|---|
| `page_id` | ID page/kênh phát sinh event trong Pancake |
| `event_type` | Loại event, với tin nhắn cần xử lý là `messaging` |
| `data.conversation` | Thông tin hội thoại phía Pancake |
| `data.message` | Tin nhắn mới hoặc tin nhắn được cập nhật |
| `data.message.from` | Thông tin người gửi tin nhắn |
| `data.message.attachments` | Danh sách attachment nếu tin nhắn có media/file |
| `data.post` | Bài viết/comment liên quan, nếu event gắn với post/comment |

### Attachment ảnh từ webhook Pancake

Webhook ảnh inbox thực tế trả attachment trong `data.message.attachments`. Với ảnh khách gửi, BE nhận được dạng `type = "photo"`, có `image_data` và public image URL ở field `url`.

Ví dụ attachment ảnh:

```json
[
  {
    "image_data": {"height": 2048, "width": 2048},
    "type": "photo",
    "url": "https://content.pancake.vn/2-2606/2026/6/15/6b6ea3a6e31b13abd914496b10dd8a7688b8b569.jpg"
  }
]
```

BE cần coi message có ảnh hợp lệ là message có nội dung, tương tự tin nhắn text. Điều kiện tối thiểu để xử lý ảnh là attachment có `type` thuộc nhóm ảnh như `photo`/`image` và có `url` public truy cập được.

Các field tối thiểu cần có để BE xử lý được:

| Field Pancake | Mục đích |
|---|---|
| `page_id` hoặc `data.message.page_id` | Xác định kênh/page để mapping `channel` và gửi reply |
| `event_type` | Lọc đúng event message |
| `data.conversation.id` hoặc `data.message.conversation_id` | Xác định hội thoại phía Pancake để gửi reply |
| `data.message.id` | Làm `message_mid` chống trùng |
| `data.message.type` | Phân biệt message khách gửi vào hay message loại khác |
| `data.message.original_message` hoặc `data.message.message` | Text của khách |
| `data.message.attachments` | Danh sách attachment; nếu là ảnh thì lấy `type`, `url`, `image_data` |
| `data.message.from.id` | ID khách trên nền tảng gốc |
| `data.message.from.page_customer_id` | ID khách theo page Pancake nếu có |
| `data.message.from.name` hoặc `data.conversation.from.name` | Tên khách để lưu `customer_name` |
| `data.message.inserted_at` | Timestamp gốc của message |

Webhook mẫu hiện tại không đảm bảo có một `customer_id` tổng giống hệ thống nội bộ. Vì vậy BE cần tự chọn khóa ổn định để lưu `conversations.customer_id`, ưu tiên `page_customer_id`, sau đó fallback về sender id nền tảng.

## Mapping field cần lấy từ webhook

| Field nội bộ | Path Pancake ưu tiên | Ghi chú |
|---|---|---|
| `page_id` | `page_id`, fallback `data.message.page_id` | Dùng cho channel và API gửi reply |
| `event_type` | `event_type` | Chỉ xử lý `messaging` |
| `pancake_conversation_id` | `data.conversation.id`, fallback `data.message.conversation_id` | Dùng gửi reply qua Pancake |
| `conversation_type` | `data.conversation.type`, fallback `data.message.type` | Phase đầu ưu tiên `INBOX` |
| `message_mid` | `data.message.id` | Tương tự Facebook `message_mid` |
| `message_type` | `data.message.type` | Dùng lọc message khách |
| `text` | `data.message.original_message`, fallback `data.message.message` | Nếu fallback từ HTML thì strip trước khi đưa vào AI |
| `sender_id` | `data.message.from.page_customer_id`, fallback `data.message.from.id` | Dùng làm `conversations.customer_id` |
| `sender_name` | `data.message.from.name`, fallback `data.conversation.from.name` | Dùng làm `conversations.customer_name` |
| `platform_sender_id` | `data.message.from.id`, fallback `data.conversation.from.id` | Lưu trong `Message.meta` |
| `timestamp` | `data.message.inserted_at` | Giữ timestamp gốc trong meta |
| `attachments` | `data.message.attachments` | Lưu nguyên vào `Message.meta.attachments`; nếu là ảnh thì dùng `url` để gửi AI |
| `image_urls` | Các `data.message.attachments[].url` có `type = photo/image` | Public image URL gửi sang `FB_AI_CHAT_URL` |
| `post_id` | `data.post.id` | Lưu meta khi event gắn với post/comment |
| `raw` | Toàn bộ event hoặc payload | Chỉ lưu/log khi đã cân nhắc dung lượng và dữ liệu nhạy cảm |

## Object nội bộ sau khi chuẩn hóa

Object nội bộ của Pancake nên bám sát object `latest` trong Facebook webhook hiện tại để tái sử dụng tư duy xử lý:

| Field nội bộ | Ý nghĩa | Tương đương Facebook |
|---|---|---|
| `source` | Nguồn webhook, giá trị `pancake_webhook` | `facebook_webhook_ai_forward` trong meta khi lưu |
| `page_id` | Page/channel phát sinh event | `page_id` |
| `page_name` | Tên page nếu BE mapping được | `page_name` |
| `sender_id` | ID ổn định của khách dùng làm `customer_id` | `sender_id` |
| `sender_name` | Tên khách | `sender_name` |
| `recipient_id` | ID page nhận message; với Pancake có thể dùng `page_id` | `recipient_id` |
| `timestamp` | Thời điểm message gốc | `timestamp` |
| `message_mid` | ID message để chống trùng | `message_mid` |
| `message_type` | Loại message Pancake, ví dụ `INBOX` | Phục vụ phân loại tương tự `is_echo` |
| `is_echo` | Cờ xác định message có phải do page/admin gửi ra hay không | `is_echo` |
| `text` | Text đã normalize để gửi AI và lưu `Message.content` | `text` |
| `metadata` | Thông tin phụ dạng object hoặc string an toàn | `metadata` |
| `app_id` | App/source nếu Pancake có trả hoặc BE tự set | `app_id` |
| `pancake_conversation_id` | ID hội thoại phía Pancake | Lưu thêm trong meta để gửi reply |
| `platform` | Kênh gốc như Facebook, TikTok, Zalo nếu detect được | Lưu meta |
| `platform_sender_id` | ID khách trên nền tảng gốc | Lưu meta |
| `page_customer_id` | ID khách theo page Pancake nếu có | Lưu meta |
| `conversation_customer_id` | ID khách nằm ở `data.conversation.customer_id`, dùng để map đúng hội thoại khi page/admin gửi ra | Tương đương customer id cần pause trong admin takeover |
| `conversation_sender_id` | ID khách trong `data.conversation.from.id` | Dùng fallback khi thiếu `conversation_customer_id` |
| `conversation_sender_name` | Tên khách trong `data.conversation.from.name` | Dùng cập nhật `Conversation.customer_name` khi tin page gửi ra |
| `message_from_id` | ID người gửi raw của `data.message.from.id` | Dùng phân loại page/customer |
| `message_from_admin_name` | Tên admin hoặc `Public API` nếu tin do page gửi ra | Tương đương tín hiệu admin/echo của Facebook |
| `message_from_uid` | UID admin nếu Pancake trả về | Lưu meta/debug, dùng `bot_paused_by` nếu là admin thật |
| `message_from_ai_generated` | Cờ Pancake trả về nếu message do AI tạo | Lưu meta/debug nếu có |
| `attachments` | Danh sách attachment đã nhận | Lưu meta |
| `image_urls` | Danh sách public URL của ảnh khách gửi | Gửi sang AI như nội dung message |
| `post_id` | ID post/comment liên quan nếu có | Lưu meta |
| `raw` | Event gốc đã giới hạn dung lượng nếu cần debug | `raw` |

Mapping vào database hiện tại:

| Model | Field | Giá trị từ object nội bộ |
|---|---|---|
| `Conversation` | `channel` | Ưu tiên `page_name`, fallback `page_id` hoặc tên kênh BE mapping được |
| `Conversation` | `customer_name` | `sender_name` |
| `Conversation` | `customer_id` | `sender_id` |
| `Conversation` | `is_active` | Giữ behavior hiện tại, mặc định active khi có message khách |
| `Conversation` | `status` | Giữ mặc định `new` nếu không có rule khác |
| `Message` | `conversation_id` | ID conversation nội bộ sau khi get/create |
| `Message` | `message_mid` | `message_mid` |
| `Message` | `role` | `user` cho message khách, `staff` cho message admin, `bot` cho reply của AI/BE |
| `Message` | `content` | `text` |
| `Message` | `meta.source` | `pancake_webhook_ai_forward`, `pancake_webhook_admin_echo` hoặc source tương ứng |
| `Message` | `meta.page_id` | `page_id` |
| `Message` | `meta.sender_id` | `sender_id` |
| `Message` | `meta.platform_sender_id` | `platform_sender_id` |
| `Message` | `meta.page_customer_id` | `page_customer_id` |
| `Message` | `meta.conversation_customer_id` | `conversation_customer_id` |
| `Message` | `meta.conversation_sender_id` | `conversation_sender_id` |
| `Message` | `meta.message_from_admin_name` | `message_from_admin_name` |
| `Message` | `meta.message_from_uid` | `message_from_uid` |
| `Message` | `meta.pancake_conversation_id` | `pancake_conversation_id` |
| `Message` | `meta.timestamp` | `timestamp` |
| `Message` | `meta.attachments` | `attachments`; với ảnh phải giữ nguyên `image_data`, `type`, `url` |
| `Message` | `meta.post_id` | `post_id` |

Quy tắc chọn `sender_id` rất quan trọng để không tạo trùng conversation. Phase đầu nên ưu tiên `page_customer_id` vì field này gắn khách với page Pancake. Nếu thiếu, dùng `from.id`. Nếu cần tránh đụng giữa nhiều page, có thể namespace bằng `page_id` cộng với sender id trong service normalize.

## Quy tắc xử lý message

BE nên áp dụng các rule sau:

- Chỉ xử lý `event_type = messaging`.
- Phase đầu chỉ xử lý message khách gửi vào, ưu tiên `data.message.type = INBOX`.
- Bỏ qua message bị xóa hoặc không còn nội dung hợp lệ. Message có ảnh hợp lệ được coi là có nội dung nếu có public image URL trong `attachments[].url`.
- Ưu tiên `original_message`; nếu phải dùng `message`, cần strip HTML trước khi gửi AI.
- Nếu message không có text nhưng có ảnh, BE lấy public image URL từ `data.message.attachments[].url` và gửi sang `FB_AI_CHAT_URL` như một tin nhắn bình thường.
- Nếu Pancake tách ảnh và text thành 2 webhook gần nhau trong cùng `page_id` + `pancake_conversation_id` + `sender_id`, BE cần gom trong cửa sổ chờ cố định 1 giây trước khi gọi `FB_AI_CHAT_URL`, tránh gửi 2 request AI và trả lời khách thành 2 tin.
- Bỏ qua message không có `page_id`, `pancake_conversation_id`, `message_mid` hoặc `sender_id` nếu các field này là bắt buộc trong flow lưu/gửi.
- Kiểm tra `message_mid` đã tồn tại trong `messages` trước khi enqueue hoặc gọi AI.
- Dùng `page_id` động từ payload, không hard-code page. Nếu `data.message.from.id == page_id` thì đây là tin page gửi ra.
- Nếu tin page gửi ra có `message_from_admin_name = "Public API"` thì coi là bot/API echo, chỉ log và bỏ qua để không tạo loop reply.
- Nếu tin page gửi ra có `message_from_admin_name` khác `Public API`, coi là admin người thật. BE lưu message `role = "staff"`, pause bot cho customer trong `data.conversation.customer_id`, và không gọi AI.
- Với message khách, luôn kiểm tra trạng thái pause trước khi gọi AI/rule. Sau khi AI/rule trả kết quả, kiểm tra lại pause một lần nữa trước khi gửi Pancake reply.
- Không chạy AI quá lâu trực tiếp trong webhook request nếu môi trường production cần phản hồi nhanh cho Pancake.
- Lưu đủ metadata để debug và gửi reply lại Pancake, nhưng không lưu token.

## Xử lý ảnh khách gửi

Mục tiêu của flow ảnh là xử lý ảnh inbox giống một message khách bình thường, nhưng nội dung gửi sang AI là public image URL thay vì text khách gõ.

Quy trình đề xuất:

- Normalize webhook như hiện tại, giữ nguyên `data.message.attachments`.
- Detect ảnh bằng attachment có `type = "photo"` hoặc `type = "image"` và có `url`.
- Lưu message khách vào database với `role = "user"`, `message_mid` từ Pancake, và `meta.attachments` là nguyên danh sách attachments Pancake gửi về.
- Trước khi gọi AI, gom các webhook gần nhau theo cùng `page_id`, `pancake_conversation_id`, `sender_id` trong cửa sổ chờ cố định 1 giây. Giá trị này hard-code trong code, không thêm env config. Trường hợp khách gửi ảnh kèm text nhưng Pancake tách thành 2 webhook, BE phải ghép thành một nội dung gửi AI duy nhất.
- Với ảnh-only message, nếu hết cửa sổ gom mà không có text đi kèm, tạo nội dung gửi sang `FB_AI_CHAT_URL` từ public image URL:

```text
https://content.pancake.vn/2-2606/2026/6/15/6b6ea3a6e31b13abd914496b10dd8a7688b8b569.jpg

hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: 6a1c2...64ddf
```

- Nếu message vừa có text vừa có ảnh, hoặc text và ảnh nằm trong 2 webhook sát nhau đã được gom, gửi cả text và các public image URL sang AI trong một request duy nhất để AI có đủ ngữ cảnh và chỉ trả lời một lần:

```text
<text khách gửi>
https://content.pancake.vn/2-2606/2026/6/15/6b6ea3a6e31b13abd914496b10dd8a7688b8b569.jpg

hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: 6a1c2...64ddf
```

- Không gọi `FB_AI_CHAT_URL` riêng cho webhook ảnh rồi gọi tiếp riêng cho webhook text nếu hai webhook thuộc cùng một lượt khách gửi gần nhau.
- Nếu attachment là ảnh nhưng không có `url` public, BE vẫn có thể lưu message/meta để audit nhưng không gọi AI cho ảnh đó; reason nên thể hiện rõ là thiếu public image URL.
- Sau khi AI trả lời, BE dùng flow gửi reply Pancake hiện tại theo `page_id` và `pancake_conversation_id`.

Metadata ảnh cần lưu trong `Message.meta.attachments` đúng dạng Pancake trả về:

```json
[
  {
    "image_data": {"height": 2048, "width": 2048},
    "type": "photo",
    "url": "https://content.pancake.vn/2-2606/2026/6/15/6b6ea3a6e31b13abd914496b10dd8a7688b8b569.jpg"
  }
]
```

## Admin takeover trên Pancake

Facebook webhook hiện tại phân biệt admin người thật bằng echo message không có metadata bot. Pancake không có cùng metadata đó, nên BE dùng tín hiệu từ logger Pancake:

- Customer message: `data.message.from.id != page_id`; ưu tiên `page_customer_id` làm `sender_id`.
- Bot/API echo: `data.message.from.id == page_id` và `data.message.from.admin_name == "Public API"`.
- Human admin message: `data.message.from.id == page_id` và `data.message.from.admin_name` có giá trị khác `Public API`.

Khi human admin message xuất hiện, `sender_id` raw của message là page id, không phải khách. Vì vậy BE phải lấy customer thật từ `data.conversation.customer_id`, fallback `data.conversation.from.id`, rồi pause đúng `Conversation.customer_id` của khách đó.

Sau khi pause, chatbot dừng trả lời các tin khách mới trong khoảng `PANCAKE_ADMIN_TAKEOVER_PAUSE_MINUTES`; nếu biến này không set thì dùng cùng thời gian với `FB_ADMIN_TAKEOVER_PAUSE_MINUTES`. Message khách vẫn có thể được lưu để giữ lịch sử, nhưng không gửi sang Brain và không gửi reply tự động.

## API gửi tin nhắn phản hồi khách

Endpoint Pancake Public API dùng để gửi reply theo dạng:

`POST https://pages.fm/api/public_api/v1/pages/{page_id}/conversations/{conversation_id}/messages`

Token nên truyền theo cách Pancake yêu cầu, thường là `page_access_token`. Token phải lấy từ biến môi trường hoặc hệ thống quản lý cấu hình an toàn, không hard-code trong source.

Thông tin tối thiểu để gửi reply:

| Thông tin | Nguồn |
|---|---|
| `page_id` | Object nội bộ sau normalize |
| `conversation_id` phía Pancake | `pancake_conversation_id` |
| Nội dung reply | Kết quả AI/rule |
| Action gửi reply | Theo contract Pancake cho inbox/comment tương ứng |

Response từ Pancake cần được log rút gọn để biết gửi thành công hay thất bại. Nếu gửi lỗi, BE nên lưu reason đủ rõ để retry hoặc điều tra, nhưng không để lỗi log lộ token.

## Cấu hình backend

Các cấu hình nên bổ sung:

- `PANCAKE_PAGE_ACCESS_TOKEN`: token gọi Pancake Public API.
- Mapping `page_id` sang tên channel/page nếu muốn lưu `Conversation.channel` dễ đọc hơn.
- Timeout và retry cho Pancake Public API.
- `PANCAKE_ADMIN_TAKEOVER_PAUSE_MINUTES`: thời gian pause bot khi admin Pancake người thật tham gia; nếu bỏ trống thì fallback về `FB_ADMIN_TAKEOVER_PAUSE_MINUTES`.
- Cờ bật/tắt flow Pancake nếu cần rollout từng bước.

File xử lý đề xuất theo cấu trúc hiện tại của repo là `app/api/v1/pancake_webhook.py`, được include trong router v1 với prefix `/pancake`. Khi đó webhook public nằm dưới `/api/v1/pancake/webhook`.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/router_v1.py](../app/api/router_v1.py)
- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/core/config.py](../app/core/config.py)
- [app/models/conversations.py](../app/models/conversations.py)
- [app/models/messages.py](../app/models/messages.py)

Nếu tách service/helper riêng để dễ test:

- `app/services/pancake_webhook_normalize_service.py`
- `app/services/pancake_message_service.py`

File test dự kiến:

- `tests/test_pancake_webhook.py`
- `tests/test_pancake_message_service.py`

## Checklist implementation tổng hợp

### Phase 0. Chốt giải pháp

- [x] Chốt Pancake là webhook source mới, không thay đổi flow Facebook hiện tại.
- [x] Chốt raw payload Pancake phải normalize trước khi đi vào logic xử lý chính.
- [x] Chốt object nội bộ cần bám sát object `latest` của Facebook webhook.
- [x] Chốt `sender_id` nội bộ ưu tiên `page_customer_id`, fallback về id khách trên nền tảng gốc.
- [x] Chốt `pancake_conversation_id` phải được giữ trong object/meta để gửi reply qua Pancake.
- [x] Chốt phase đầu chưa xử lý upload/rehost attachment nếu chưa có yêu cầu riêng.

### Phase 1. Endpoint và cấu hình runtime

- [x] Tạo route `POST /api/v1/pancake/webhook`.
- [x] Include router Pancake vào router v1 hiện tại.
- [x] Thêm cấu hình `PANCAKE_PAGE_ACCESS_TOKEN`.
- [x] Thêm timeout/retry config cho Pancake Public API nếu cần.
- [x] Đảm bảo log không in token hoặc query string chứa token.

### Phase 2. Normalize payload Pancake

- [x] Tạo helper normalize raw payload Pancake về object nội bộ.
- [x] Map `page_id`, `event_type`, `pancake_conversation_id`, `message_mid`.
- [x] Map `sender_id`, `sender_name`, `platform_sender_id`, `page_customer_id`.
- [x] Ưu tiên `original_message`, fallback `message` sau khi strip HTML nếu cần.
- [x] Map `timestamp`, `attachments`, `post_id`, `platform`.
- [x] Detect hoặc set được `is_echo`/`message_type` để tránh reply loop.
- [x] Map thêm tín hiệu `conversation_customer_id`, `conversation_sender_id`, `message_from_admin_name`, `message_from_uid` để phân biệt Public API với admin thật.
- [x] Trả reason rõ ràng khi payload thiếu field bắt buộc.

### Phase 3. Tích hợp với conversation/message hiện tại

- [x] Lấy hoặc tạo `Conversation` theo `sender_id`.
- [x] Lưu `Conversation.channel` từ `page_name`, fallback `page_id`.
- [x] Lưu `Conversation.customer_name` từ `sender_name`.
- [x] Giữ `Conversation.status` mặc định theo behavior hiện tại nếu không có rule khác.
- [x] Check duplicate bằng `Message.message_mid` trước khi gọi AI/gửi reply.
- [x] Lưu message khách với `role = "user"`.
- [x] Lưu đủ meta: `source`, `page_id`, `sender_id`, `platform_sender_id`, `page_customer_id`, `pancake_conversation_id`, `timestamp`, `attachments`, `post_id`.
- [x] Lưu message bot sau khi có reply nếu flow hiện tại yêu cầu lưu bot response.
- [x] Khi admin Pancake người thật gửi tin, lưu message `role = "staff"` vào conversation của khách và pause bot.

### Phase 4. Gọi AI/rule và gửi reply Pancake

- [x] Gửi text/context đã normalize sang AI/rule, không gửi raw payload trực tiếp.
- [x] Gửi public image URL từ `attachments[].url` sang `FB_AI_CHAT_URL` khi khách gửi ảnh.
- [x] Gom webhook ảnh + text gần nhau thành một request `FB_AI_CHAT_URL` duy nhất để tránh bot trả lời 2 tin.
- [x] Chuẩn hóa reply text trước khi gửi Pancake.
- [x] Gọi Pancake Public API bằng `page_id` và `pancake_conversation_id`.
- [x] Gửi đúng action theo loại hội thoại, ví dụ inbox/comment nếu Pancake yêu cầu khác nhau.
- [x] Xử lý response Pancake thành object kết quả nội bộ dễ log/debug.
- [x] Retry có giới hạn với lỗi tạm thời.
- [x] Không retry vô hạn với lỗi auth, permission hoặc payload sai.
- [x] Trước khi gọi AI và trước khi gửi Pancake reply đều kiểm tra `bot_paused_until`.

### Phase 5. Test và rollout

- [x] Test non-`messaging` event bị bỏ qua.
- [x] Test payload thiếu field bắt buộc trả reason rõ ràng.
- [x] Test message `INBOX` normalize đúng `sender_id`, `sender_name`, `page_id`, `message_mid`, `text`.
- [x] Test `Conversation` được tạo hoặc tái sử dụng theo `sender_id`.
- [x] Test `Message` user lưu đúng `message_mid`, `role`, `content`, `meta`.
- [x] Test duplicate `message_mid` không gọi AI/gửi reply lần hai.
- [x] Mock Pancake Public API để assert BE gửi đúng `page_id`, `pancake_conversation_id`, action và nội dung reply.
- [x] Test lỗi Pancake Public API không làm mất log/debug cần thiết.
- [x] Test Public API echo không pause, admin người thật có pause, customer message đang pause không gọi Brain, và reply bị suppress nếu admin pause trong lúc AI đang xử lý.
- [x] Chạy `pytest -q`.

### Phase 6. Xử lý ảnh khách gửi từ webhook

- [x] Detect attachment ảnh bằng `type = photo/image` và `url`.
- [x] Coi image-only message có public URL là message hợp lệ, không trả `unsupported_message_content_type`.
- [x] Buffer/gom webhook ảnh + text gần nhau theo `page_id`, `pancake_conversation_id`, `sender_id` trong cửa sổ chờ cố định 1 giây, hard-code trong code và không thêm env config.
- [x] Build một nội dung gửi `FB_AI_CHAT_URL` từ text nếu có và public image URL nếu có.
- [x] Lưu nguyên `attachments` vào `Message.meta.attachments`, gồm `image_data`, `type`, `url`.
- [x] Nếu ảnh thiếu public URL, lưu metadata để audit nhưng không gọi AI, trả reason rõ ràng.
- [x] Test webhook ảnh inbox normalize đúng `attachments`, detect đúng image URL và gọi AI với public URL.
- [x] Test text + ảnh trong 2 webhook gần nhau chỉ gọi AI một lần, content có cả text và image URL.
- [x] Test message vừa text vừa ảnh trong cùng webhook gửi đủ cả text và image URL sang AI.
- [x] Test ảnh không có URL không gọi AI/gửi reply.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp](pancake_webhook_integration_task_list/phase-0.md)
- [Phase 1. Endpoint và cấu hình runtime](pancake_webhook_integration_task_list/phase-1.md)
- [Phase 2. Normalize payload Pancake](pancake_webhook_integration_task_list/phase-2.md)
- [Phase 3. Tích hợp với conversation/message hiện tại](pancake_webhook_integration_task_list/phase-3.md)
- [Phase 4. Gọi AI/rule và gửi reply Pancake](pancake_webhook_integration_task_list/phase-4.md)
- [Phase 5. Test và rollout](pancake_webhook_integration_task_list/phase-5.md)
- [Phase 6. Xử lý ảnh khách gửi từ webhook](pancake_webhook_integration_task_list/phase-6.md)

## Ghi chú production

Khi triển khai thật, nên bổ sung:

- Queue xử lý async nếu AI hoặc Pancake Public API có thể chậm.
- Retry có giới hạn khi gửi reply thất bại.
- Lưu idempotency theo `message_mid` trong database thay vì memory.
- Rate limit theo `page_id` và `sender_id`.
- Mask token, số điện thoại và dữ liệu nhạy cảm khỏi log.
- Theo dõi lỗi theo nhóm: payload invalid, duplicate, AI failed, Pancake send failed.
- Mapping nhiều page/token nếu backend xử lý nhiều page Pancake.
- Cơ chế handoff sang CS thật nếu message cần người xử lý.

## Kết luận

Flow Pancake nên được tích hợp như một webhook source mới nhưng chuẩn hóa về cùng kiểu object mà Facebook webhook đang dùng. Khi object nội bộ có đủ `page_id`, `sender_id`, `sender_name`, `message_mid`, `text` hoặc `image_urls`, `timestamp`, `pancake_conversation_id` và metadata liên quan, BE có thể lưu vào `conversations`/`messages` hiện tại mà không làm lệch logic tổng thể.

Phần khác biệt quan trọng của Pancake nằm ở bước gửi reply: BE cần giữ `pancake_conversation_id` trong object/meta để gọi Pancake Public API theo đúng hội thoại phía Pancake.
