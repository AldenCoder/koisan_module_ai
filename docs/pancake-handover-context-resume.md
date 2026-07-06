# Bổ sung context handover khi Pancake bot resume

## Mục tiêu

Tài liệu này mô tả phương án để `BE` không làm mất ngữ cảnh khi hội thoại Pancake chuyển sang handover/admin takeover rồi sau đó bot hoạt động trở lại.

Vấn đề hiện tại: khi admin hoặc người thật tham gia support, bot pause và không gửi tin nhắn sang `AI Agent`. Trong khoảng pause, admin và khách có thể trao đổi thêm thông tin quan trọng như mẫu, màu, size, giá, số điện thoại, địa chỉ, tình trạng còn hàng hoặc hướng xử lý đơn. Khi hết pause, khách nhắn lại thì `BE` gửi tin nhắn mới của khách sang AI như một lượt chat bình thường. AI không nhìn thấy đoạn admin/khách đã trao đổi trong lúc handover, nên dễ hỏi lại thông tin đã có hoặc tư vấn lệch bối cảnh.

Điểm thay đổi chính: ở lượt customer message đầu tiên sau khi pause hết hạn, `BE` lấy tối đa `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` tin nhắn mới nhất trong khoảng handover, gồm role `staff` và `user`, format thành đoạn bối cảnh ngắn, gộp với tin nhắn mới của khách rồi gửi sang AI. Nếu trong khoảng handover không có hội thoại admin/khách đủ điều kiện, `BE` không gửi bối cảnh bổ sung và giữ flow gửi tin nhắn khách sang AI như hiện tại.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `AI Agent` / `Brain`: service tạo nội dung trả lời cho khách.
- `Conversation`: document nội bộ trong collection `conversations`.
- `Message`: document nội bộ trong collection `messages`.
- `handover` / `admin takeover`: trạng thái bot tạm dừng vì admin/người thật đang hỗ trợ khách.
- `pause window`: khoảng thời gian từ `bot_paused_at` đến lượt khách nhắn lại sau khi `bot_paused_until` đã hết hạn.
- `resume turn`: lượt customer message đầu tiên được xử lý sau khi pause hết hạn.
- `handover transcript`: đoạn hội thoại giới hạn được lấy từ database trong thời gian handover để đưa lại cho AI.
- `conversation_id`: id hội thoại nội bộ của `BE`, vẫn được append vào AI content bằng note hiện tại.
- `pancake_conversation_id`: id hội thoại phía Pancake.

## Luồng tổng thể

Admin nhắn trong Pancake.

`BE` nhận webhook admin message, lưu message với role `staff`, set các field pause trên conversation:

```text
bot_paused_at
bot_paused_until
bot_paused_reason
bot_paused_by
```

Trong lúc conversation còn pause, nếu khách nhắn thêm, `BE` vẫn lưu customer message với role `user`, nhưng không gọi AI và không gửi bot reply.

Khi `bot_paused_until` đã hết hạn, khách nhắn lại.

`BE` lấy conversation, kiểm tra pause đã hết hạn, chụp lại pause snapshot trước khi clear các field pause.

`BE` query message trong cùng conversation theo pause snapshot:

```text
conversation_id == conversation.id
created_at >= bot_paused_at
created_at < current_customer_message.created_at
role in ["staff", "user"]
content != ""
```

`BE` lấy tối đa `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` tin mới nhất trong tập này. Sau khi chọn xong, `BE` sắp xếp lại theo `created_at` tăng dần để AI đọc theo đúng thứ tự thời gian.

Nếu có transcript, `BE` tạo nội dung gửi AI dạng:

```text
Bối cảnh trong lúc nhân viên hỗ trợ:
[Nhân viên] Dạ mẫu này còn màu đen size M.
[Khách] Em lấy màu đen size M.
[Nhân viên] Chị để lại số điện thoại giúp em nhé.

Tin nhắn mới của khách:
Số em 09xxxxxxx

Hãy trả lời tiếp dựa trên bối cảnh trên, không hỏi lại thông tin đã có.
```

Sau đó `_build_ai_chat_payload(...)` vẫn append note hiện tại:

```text
hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: <conversation_id>
```

Nếu transcript rỗng, `BE` không tạo phần "Bối cảnh trong lúc nhân viên hỗ trợ" và gửi tin nhắn mới của khách sang AI như flow hiện tại.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Lưu admin message Pancake với role `staff`.
- Lưu customer message Pancake với role `user`.
- Pause bot khi admin/người thật tham gia theo logic hiện tại.
- Không gọi AI khi conversation còn đang pause.
- Khi pause hết hạn, chụp lại pause snapshot trước khi clear các field pause.
- Lấy tối đa `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` message mới nhất trong pause window.
- Chỉ lấy message role `staff` và `user`, không lấy system/automation/bot echo.
- Render transcript theo thứ tự thời gian cũ đến mới.
- Gắn transcript vào AI content chỉ ở resume turn.
- Không thay đổi raw customer message được lưu vào DB.
- Không gửi transcript ra Pancake cho khách.
- Không log raw transcript nếu có thông tin cá nhân.

### Pancake

Pancake chịu trách nhiệm:

- Gửi webhook admin message và customer message đủ metadata.
- Gửi webhook trong cùng `pancake_conversation_id` để BE lưu được lịch sử nội bộ.
- Nhận reply sau khi bot resume như flow hiện tại.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Nhận AI content đã có phần bối cảnh handover nếu BE cung cấp.
- Phân biệt rõ phần bối cảnh và tin nhắn mới của khách dựa trên format text.
- Trả lời tiếp dựa trên thông tin admin/khách đã trao đổi.
- Không hỏi lại thông tin đã có trong transcript nếu không cần xác nhận thêm.

### Ngoài phạm vi phương án này

- Không gửi toàn bộ lịch sử hội thoại không giới hạn sang AI.
- Không gọi Pancake API để lấy lại history handover.
- Không thêm LLM riêng để tóm tắt handover trong phase đầu.
- Không thay đổi Pancake Public API contract.
- Không thay đổi logic detect handover keyword từ reply của AI.
- Không tự động bật bot khi conversation vẫn đang pause.
- Không replay các tin nhắn cũ ra Pancake.
- Không bắt AI xử lý lại từng message trong lúc pause như các event độc lập.
- Không tạo task-list file chi tiết trong proposal chính này.

## Bối cảnh dữ liệu hiện tại

Record `conversations` hiện có các field pause:

```json
{
  "_id": {"$oid": "6a3c7dcead6606c1f8d8326e"},
  "channel": "970198996185881",
  "customer_name": "Nguyen Van A",
  "customer_id": "customer-1",
  "status": "handover",
  "fb_ai_initialized": true,
  "bot_paused_at": {"$date": "2026-06-26T03:00:00.000Z"},
  "bot_paused_until": {"$date": "2026-06-26T03:10:00.000Z"},
  "bot_paused_reason": "pancake_admin_message",
  "bot_paused_by": "admin-uid-1",
  "created_at": {"$date": "2026-06-26T02:50:00.000Z"},
  "updated_at": {"$date": "2026-06-26T03:00:00.000Z"}
}
```

Record `messages` đã lưu admin message với role `staff`:

```json
{
  "_id": {"$oid": "message-admin-1"},
  "conversation_id": {"$oid": "6a3c7dcead6606c1f8d8326e"},
  "message_mid": "mid-admin-1",
  "role": "staff",
  "content": "Dạ mẫu W2651703 còn màu đen size M, giá 450k.",
  "meta": {
    "source": "pancake_webhook_staff",
    "page_id": "970198996185881",
    "pancake_conversation_id": "970198996185881_27060574493629431"
  },
  "created_at": {"$date": "2026-06-26T03:02:00.000Z"}
}
```

Customer message trong lúc pause vẫn được lưu với role `user`:

```json
{
  "_id": {"$oid": "message-user-paused-1"},
  "conversation_id": {"$oid": "6a3c7dcead6606c1f8d8326e"},
  "message_mid": "mid-user-paused-1",
  "role": "user",
  "content": "Em lấy màu đen size M.",
  "meta": {
    "source": "pancake_webhook_ai_forward",
    "page_id": "970198996185881",
    "pancake_conversation_id": "970198996185881_27060574493629431"
  },
  "created_at": {"$date": "2026-06-26T03:03:00.000Z"}
}
```

Sau khi pause hết hạn, customer message mới vẫn được lưu như hiện tại. Phần handover transcript chỉ được dùng để augment nội dung gửi AI, không thay đổi `Message.content` raw của khách.

## Contract dữ liệu từ Pancake

Flow này không yêu cầu Pancake cung cấp API hoặc field mới.

Các field cần dùng đã có trong webhook và record nội bộ:

| Field | Nguồn | Ghi chú |
|---|---|---|
| `page_id` | normalized webhook / `Message.meta` | Dùng để giữ context đúng page |
| `pancake_conversation_id` | normalized webhook / `Message.meta` | Dùng để giữ context đúng hội thoại Pancake |
| `message_mid` | normalized webhook / `Message.message_mid` | Chống duplicate/debug |
| `sender_id` | normalized webhook | Customer id hoặc page id theo actor |
| `message_from_admin_name` | normalized webhook | Dùng cho admin takeover hiện tại |
| `text` | normalized webhook / `Message.content` | Nội dung lưu DB và gửi AI |

Không gọi Pancake Conversation Messages API để lấy handover history. BE dùng chính `messages` đã lưu trong database.

## Mapping field tạo handover transcript

Mapping từ DB message sang transcript:

| Field nguồn | Field đích | Ghi chú |
|---|---|---|
| `Message.role == "staff"` | label `[Nhân viên]` | Tin admin/người thật |
| `Message.role == "user"` | label `[Khách]` | Tin khách |
| `Message.content` | transcript line content | Bỏ qua nếu rỗng |
| `Message.created_at` | sort timeline | Chọn message mới nhất trước, render cũ đến mới |
| `Message.message_mid` | debug/meta | Không hiển thị cho AI |

Không dùng các role sau trong phase đầu:

- `bot`
- `system`
- role rỗng/không xác định

Không lấy current customer message vào transcript. Current message được đặt riêng ở phần:

```text
Tin nhắn mới của khách:
...
```

## Format transcript gửi AI

Transcript chỉ là phần bổ sung cho AI, không ghi đè raw text của khách trong DB.

Format đề xuất:

```text
Bối cảnh trong lúc nhân viên hỗ trợ:
[Nhân viên] ...
[Khách] ...

Tin nhắn mới của khách:
...

Hãy trả lời tiếp dựa trên bối cảnh trên, không hỏi lại thông tin đã có.
```

Ví dụ AI content trước khi `_build_ai_chat_payload(...)` append hook:

```text
Bối cảnh trong lúc nhân viên hỗ trợ:
[Nhân viên] Dạ mẫu W2651703 còn màu đen size M, giá 450k.
[Khách] Em lấy màu đen size M.
[Nhân viên] Dạ chị để lại số điện thoại giúp em nhé.

Tin nhắn mới của khách:
Số em 0901234567

Hãy trả lời tiếp dựa trên bối cảnh trên, không hỏi lại thông tin đã có.
```

Payload cuối cùng gửi AI vẫn có note test mode/conversation ở cuối do helper hiện tại append:

```text
... nội dung ở trên ...

hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: 6a3c7dcead6606c1f8d8326e
```

Quy tắc quan trọng:

- Không tự append hook `hãy nhớ... conversation_id` thêm lần nữa.
- Không gửi phần "Bối cảnh trong lúc nhân viên hỗ trợ" nếu transcript rỗng.
- Không log raw transcript.

## Object nội bộ sau khi normalize

Object normalized Pancake hiện tại đã có dữ liệu cần dùng:

| Field | Ý nghĩa |
|---|---|
| `page_id` | Page/kênh phát sinh message |
| `pancake_conversation_id` | ID hội thoại phía Pancake |
| `sender_id` | Customer id hoặc page id |
| `message_mid` | ID message để chống duplicate |
| `message_type` | INBOX/COMMENT |
| `text` | Nội dung message khách |
| `message_from_admin_name` | Tên admin nếu là admin message |
| `conversation_was_ai_initialized` | Trạng thái init AI |

Đề xuất bổ sung nội bộ khi resume từ pause:

```json
{
  "handover_resume_context": {
    "resumed": true,
    "bot_paused_at": "2026-06-26T10:00:00+07:00",
    "bot_paused_until": "2026-06-26T10:10:00+07:00",
    "bot_paused_reason": "pancake_admin_message",
    "bot_paused_by": "admin-uid-1",
    "transcript_message_count": 3
  }
}
```

Đây chỉ là object nội bộ trong runtime hoặc metadata của lượt xử lý, không yêu cầu Pancake thay đổi payload.

## Lưu handover context vào database

Không lưu transcript đầy đủ vào database trong phase đầu.

Raw message vẫn lưu như hiện tại:

- Admin message: `role="staff"`, `content` là câu admin nhắn.
- Customer message: `role="user"`, `content` là câu khách nhắn.
- Bot reply: `role="bot"`, `content` là câu bot trả lời.

Có thể lưu metadata audit trên user message resume:

```json
{
  "handover_context": {
    "injected": true,
    "paused_at": "2026-06-26T10:00:00+07:00",
    "paused_until": "2026-06-26T10:10:00+07:00",
    "paused_reason": "pancake_admin_message",
    "message_count": 3
  }
}
```

Nếu transcript rỗng:

```json
{
  "handover_context": {
    "injected": false,
    "reason": "empty_handover_transcript",
    "paused_at": "2026-06-26T10:00:00+07:00"
  }
}
```

Metadata này không phải cờ trạng thái chính. Nó chỉ phục vụ audit/debug hoặc bổ sung idempotency nếu cần.

Không thêm field boolean kiểu `handover_context_injected` vào conversation trong phase đầu.

## Quy tắc xử lý message

Quy tắc chính:

1. Admin message vẫn pause conversation theo logic hiện tại.
2. Customer message trong lúc pause vẫn được lưu DB nhưng không gọi AI.
3. Khi customer message đến sau `bot_paused_until`, BE chụp pause snapshot trước khi clear pause fields.
4. BE lưu customer message mới như hiện tại.
5. BE query transcript trong pause window, không bao gồm current customer message.
6. Nếu transcript có message hợp lệ, BE wrap AI content bằng phần bối cảnh.
7. Nếu transcript rỗng, BE gửi AI content gốc.
8. `_build_ai_chat_payload(...)` vẫn append hook `hãy nhớ... conversation_id`.
9. Sau khi resume, pause fields được clear về `None`, nên lượt sau không inject transcript nữa.

Quy tắc chọn message:

```text
conversation_id == conversation.id
created_at >= bot_paused_at
created_at < current_customer_message.created_at
role in ["staff", "user"]
content != ""
```

Thứ tự lấy message:

1. Query theo filter.
2. Sort `created_at` giảm dần.
3. Limit `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`.
4. Đảo lại danh sách để render theo `created_at` tăng dần.

Nếu có 35 message trong pause window và max là 30:

- BE bỏ 5 message cũ nhất.
- BE giữ 30 message mới nhất.
- BE render 30 message đó theo timeline cũ đến mới.

Không thêm flow đặt cờ `false` mỗi lần handover và `true` khi hết handover. Các field `bot_paused_*` hiện có là tín hiệu đủ cho luồng bình thường:

1. Khi admin/handover xảy ra, code set `bot_paused_at`, `bot_paused_until`, `bot_paused_reason`, `bot_paused_by`.
2. Khi khách nhắn lại sau `bot_paused_until`, BE chụp pause snapshot.
3. BE build transcript theo snapshot đó.
4. BE clear các pause fields về `None`.
5. Vì pause fields đã về `None`, các message sau không inject transcript nữa.

Trường hợp concurrent/retry:

- Nếu hai customer message khác nhau đến gần như cùng lúc ngay sau khi pause hết hạn, cả hai có thể cùng thấy pause fields trước khi field bị clear.
- Nếu muốn chặn tuyệt đối, có thể dùng marker trong `Message.meta` theo `paused_at` hoặc dùng lock theo conversation.
- Phase đầu ưu tiên đơn giản: dựa vào pause fields + duplicate/in-flight guard hiện có. Marker meta chỉ dùng để audit/debug hoặc bổ sung idempotency nếu test phát hiện race.

## Lỗi và fallback

### Không có transcript

Kết quả mong muốn:

- Không block AI.
- Không gửi phần bối cảnh rỗng.
- AI nhận tin nhắn mới của khách như flow hiện tại.
- Log reason `empty_handover_transcript` nếu cần debug.

### Query transcript lỗi

Kết quả mong muốn:

- Log warning/error rút gọn.
- Không block xử lý khách.
- Fallback gửi tin nhắn mới sang AI như hiện tại.

### Env sai format

Ví dụ:

```env
PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=abc
```

Kết quả mong muốn:

- Fallback `30`.
- Log warning cấu hình nếu cần.
- Không crash webhook.

### Conversation vẫn đang pause

Nếu sau khi reload conversation vẫn đang pause:

- Không gọi AI.
- Không build transcript.
- Giữ behavior hiện tại `conversation_paused_by_admin` hoặc `conversation_paused_before_send`.

### Hook conversation bị lặp

Nếu implementation lỡ append note `hãy nhớ... conversation_id` trong handover wrapper, AI payload có thể bị lặp hook.

Kết quả mong muốn:

- Handover wrapper chỉ build content chính.
- `_build_ai_chat_payload(...)` là nơi duy nhất append hook.
- Test phải assert hook xuất hiện đúng một lần.

## API/schema trả dữ liệu conversation

Không thay đổi API/schema public trong phase đầu.

Không thêm field mới vào response conversation.

Nếu lưu `handover_context` trong `Message.meta`, dữ liệu này chỉ phục vụ debug/audit nội bộ. Các API list/detail conversation hiện có không cần expose field riêng mới.

Nếu sau này UI cần hiển thị "AI đã dùng context handover", có thể bổ sung schema/response ở task riêng.

## Migration và dữ liệu cũ

Không cần migration bắt buộc.

Các conversation cũ không có handover context metadata vẫn hợp lệ.

Các message cũ đã lưu role `staff` và `user` vẫn có thể được dùng nếu pause snapshot còn tồn tại ở thời điểm khách resume. Nếu pause fields đã bị clear trước khi deploy logic mới, BE không thể khôi phục pause window để inject context cho lượt sau, và sẽ fallback về flow hiện tại.

Không backfill transcript handover cho dữ liệu cũ.

## Cấu hình backend

Thêm một env cho phase đầu:

```env
PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30
```

Default nếu không set env:

```text
30
```

Quy tắc parse:

- Nếu env rỗng hoặc sai format, fallback về `30`.
- Nếu env nhỏ hơn `1`, clamp về `1`.
- Nếu env quá lớn, có thể clamp ở mức an toàn trong code, ví dụ `50`, để tránh payload quá dài ngoài ý muốn.

Nếu sau này cần feature flag hoặc giới hạn ký tự riêng, sẽ thêm ở task khác. Phase đầu chỉ cấu hình bằng `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`.

## Danh sách file dự kiến thay đổi khi implement

- [app/core/config.py](../app/core/config.py)
- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../tests/test_pancake_webhook.py)

Nếu muốn tách helper riêng để dễ test:

- `app/services/pancake_handover_context_service.py`
- `tests/test_pancake_handover_context_service.py`

Không dự kiến thay đổi:

- `app/services/pancake_message_service.py`, vì không cần gọi Pancake API để lấy history.
- Pancake Public API contract.
- API/schema conversation public.

## Checklist implementation tổng hợp

Trạng thái hiện tại: đã implement Phase 0-5 phần code/test. BE đã có config `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`, resume snapshot trước khi clear pause fields, helper query/build transcript handover, wrapper AI content, logging/fallback và test coverage. Rollout staging/production còn chờ thực hiện.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp handover context resume](pancake-handover-context-resume-task-list/phase-0.md)
- [Phase 1. Cấu hình và pause snapshot](pancake-handover-context-resume-task-list/phase-1.md)
- [Phase 2. Query và build transcript handover](pancake-handover-context-resume-task-list/phase-2.md)
- [Phase 3. Gộp handover context vào AI content](pancake-handover-context-resume-task-list/phase-3.md)
- [Phase 4. Logging, fallback và an toàn vận hành](pancake-handover-context-resume-task-list/phase-4.md)
- [Phase 5. Test và rollout handover context](pancake-handover-context-resume-task-list/phase-5.md)

### Phase 0. Chốt giải pháp

- [x] Chốt chỉ inject context ở lượt customer message đầu tiên sau khi pause hết hạn.
- [x] Chốt giới hạn bằng `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- [x] Chốt nếu có hơn 30 message thì lấy 30 message mới nhất.
- [x] Chốt render transcript theo thứ tự cũ đến mới.
- [x] Chốt handover rỗng thì không gửi bối cảnh sang AI.
- [x] Chốt hook `hãy nhớ... conversation_id` vẫn do `_build_ai_chat_payload(...)` append.
- [x] Chốt không thêm cờ boolean riêng trên conversation.

### Phase 1. Cấu hình và pause snapshot

- [x] Thêm config `pancake_handover_context_max_messages`.
- [x] Thêm helper parse/clamp `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`.
- [x] Tạo hoặc chỉnh helper resume pause để trả được pause snapshot trước khi clear fields.
- [x] Đảm bảo pause fields vẫn được clear về `None` sau khi resume.
- [x] Không thay đổi behavior khi conversation vẫn đang pause.

### Phase 2. Query và build transcript

- [x] Thêm helper query message trong pause window.
- [x] Chỉ lấy role `staff` và `user`.
- [x] Exclude content rỗng.
- [x] Không lấy current customer message vào transcript.
- [x] Sort mới nhất trước, limit theo env, rồi render cũ đến mới.
- [x] Build transcript label `[Nhân viên]` và `[Khách]`.
- [x] Skip transcript nếu không có message hợp lệ.

### Phase 3. Gộp vào AI content

- [x] Gắn handover context vào `normalized` hoặc runtime context, không ghi đè `normalized["text"]`.
- [x] Wrap AI content trong `_generate_pancake_reply(...)` trước khi `_build_ai_chat_payload(...)`.
- [x] Giữ hook `hãy nhớ... conversation_id` xuất hiện đúng một lần.
- [x] Lưu metadata audit `handover_context` nếu cần.
- [x] Đảm bảo flow auto-consult/comment không bị ảnh hưởng ngoài phạm vi.

### Phase 4. Logging và fallback

- [x] Log resume detected.
- [x] Log fetch transcript start/ok/failed.
- [x] Log injected/skipped với reason.
- [x] Không log raw transcript.
- [x] Fallback về AI content gốc nếu query transcript lỗi.
- [x] Fallback về AI content gốc nếu transcript rỗng.

### Phase 5. Test và rollout

- [x] Test customer message trong pause không gọi AI.
- [x] Test resume có transcript thì AI payload chứa context.
- [x] Test handover rỗng không gửi context.
- [x] Test hơn 30 message thì lấy 30 mới nhất.
- [x] Test render cũ đến mới sau khi limit.
- [x] Test hook conversation xuất hiện đúng một lần.
- [x] Test pause fields đã clear thì lượt sau không inject.
- [x] Chạy `pytest -q`.
- [ ] Rollout với env `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.

## Test cần có khi implement

- Admin message pause conversation và được lưu role `staff`.
- Customer message trong lúc pause được lưu role `user` nhưng không gọi AI.
- Customer message đầu tiên sau pause hết hạn gửi AI content có transcript `staff` + `user`.
- Transcript dùng label `[Nhân viên]` và `[Khách]`.
- Current customer message không bị lặp trong transcript.
- Nếu trong pause window không có `staff`/`user` message đủ điều kiện thì không gửi bối cảnh.
- Nếu pause window có hơn 30 message, lấy 30 message mới nhất.
- Sau khi lấy 30 message mới nhất, render theo thứ tự cũ đến mới.
- Hook `hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: ...` vẫn có trong AI payload.
- Hook cuối không bị append hai lần.
- Nếu query transcript lỗi thì fallback về flow hiện tại.
- Nếu env max messages sai format thì fallback `30`.
- Nếu pause fields đã clear, lượt sau không inject transcript.
- Nếu conversation vẫn đang pause, không gọi AI.

## Ghi chú production

- Đây là logic cải thiện context khi bot resume, không phải logic cho phép bot chen vào khi admin đang support.
- Không log raw transcript vì có thể chứa số điện thoại, địa chỉ hoặc thông tin đơn hàng.
- Nếu admin đã chốt hướng xử lý, prompt cần yêu cầu AI tiếp tục theo hướng đó và không hỏi lại từ đầu.
- Nếu sau rollout AI vẫn hỏi lại thông tin đã có, ưu tiên chỉnh format transcript trước khi tăng giới hạn message.
- Nếu conversation có nhiều hơn 30 message trong handover, việc lấy message mới nhất là hợp lý hơn vì các tin gần resume thường phản ánh trạng thái mới nhất.
- Nếu cần chống race tuyệt đối sau production observation, bổ sung marker theo `paused_at` hoặc lock theo conversation ở task riêng.

## Tiêu chí hoàn thành

- Khi khách nhắn lại sau pause hết hạn, AI có bối cảnh admin/khách trong lúc handover nếu bối cảnh tồn tại.
- BE lấy tối đa `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30` message.
- Nếu có hơn 30 message, BE giữ 30 message mới nhất.
- AI nhận transcript theo thứ tự thời gian cũ đến mới.
- Nếu handover rỗng, BE không gửi transcript bối cảnh sang AI.
- Hook `hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: ...` vẫn được append như hiện tại.
- Không cần thêm cờ boolean riêng trên conversation.
- Pause fields hiện có được dùng làm tín hiệu resume.
- Raw customer message lưu DB không bị thay bằng transcript dài.
- Không gọi Pancake API thêm chỉ để lấy handover history.
- Không thay đổi API/schema conversation public.
- Tests pass bằng `pytest -q`.
