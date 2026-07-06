# Lưu `pancake_info_url` vào conversation Pancake

## Mục tiêu

Tài liệu này mô tả phương án để khi khách nhắn tin lần đầu qua Pancake và `BE` tạo mới một record trong bảng `conversations`, record đó có thêm field `pancake_info_url` dạng optional string.

Điểm thay đổi chính: `pancake_info_url` được build một lần duy nhất tại thời điểm tạo `Conversation`, từ `page_id` và `pancake_conversation_id` của tin nhắn Pancake đầu tiên. Các lần xử lý tin nhắn sau chỉ lấy lại conversation hiện có, không tính lại và không overwrite `pancake_info_url`.

Format URL:

```text
https://pancake.vn/{page_id}?c_id={pancake_conversation_id}
```

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `Conversation`: document nội bộ trong collection `conversations`.
- `Message`: document nội bộ trong collection `messages`.
- `page_id`: ID page/kênh phát sinh message trong Pancake.
- `pancake_conversation_id`: ID hội thoại phía Pancake, đang lưu ở `messages.meta.pancake_conversation_id`.
- `pancake_info_url`: URL mở hội thoại tương ứng trên Pancake.

## Luồng tổng thể

Khách hàng nhắn tin lần đầu vào kênh social đã nối Pancake.

`BE` nhận webhook Pancake, parse JSON và normalize payload như flow hiện tại.

`BE` validate các field tối thiểu, trong đó có `page_id`, `pancake_conversation_id`, `message_mid` và `sender_id`.

`BE` tìm conversation theo `customer_id = sender_id` như flow Pancake hiện tại.

Nếu chưa có conversation, `BE` build `pancake_info_url` theo format:

```text
https://pancake.vn/{page_id}?c_id={pancake_conversation_id}
```

`BE` tạo `Conversation` mới với `channel`, `customer_name`, `customer_id`, `pancake_info_url`, `is_active`, `created_at`, `updated_at`.

`BE` tiếp tục lưu message user vào bảng `messages` như hiện tại.

Nếu conversation đã tồn tại, `BE` không build lại và không update `pancake_info_url`.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Normalize được `page_id` và `pancake_conversation_id` từ webhook Pancake.
- Tạo `pancake_info_url` từ hai field đã normalize khi tạo conversation mới.
- Lưu `pancake_info_url` vào collection `conversations`.
- Đảm bảo `pancake_info_url` là optional để conversation cũ vẫn hợp lệ.
- Không overwrite `pancake_info_url` khi conversation đã tồn tại.
- Không tự động backfill conversation cũ trong request xử lý message mới.
- Không đưa token hoặc thông tin xác thực nào vào `pancake_info_url`.

### Pancake

Pancake chịu trách nhiệm:

- Gửi webhook message về `BE`.
- Cung cấp đủ dữ liệu để `BE` normalize được `page_id`.
- Cung cấp đủ dữ liệu để `BE` normalize được `pancake_conversation_id`.
- Cho phép mở hội thoại bằng URL dạng `https://pancake.vn/{page_id}?c_id={pancake_conversation_id}`.

### AI Agent / Brain

AI Agent không tham gia flow tạo `pancake_info_url`.

AI Agent không cần:

- Biết URL Pancake.
- Trả về `page_id`.
- Trả về `pancake_conversation_id`.
- Tạo hoặc cập nhật `pancake_info_url`.

### Ngoài phạm vi phương án này

- Không đổi flow Facebook webhook.
- Không đổi flow gửi reply Pancake.
- Không thêm bảng mới.
- Không yêu cầu Pancake đổi format webhook.
- Không tự động backfill `pancake_info_url` cho conversation cũ.
- Không cho phép nhập tay `pancake_info_url` qua API create/update conversation.
- Không thêm index cho `pancake_info_url` nếu field này chỉ dùng để hiển thị/mở link.
- Không build UI/admin mới để hiển thị link trong task này.

## Bối cảnh dữ liệu hiện tại

Record `conversations` hiện tại đang có các field chính:

```json
{
  "_id": {"$oid": "6a0e59d5eff2db60790d2112"},
  "channel": "970198996185881",
  "customer_name": "Lương Lê",
  "customer_id": "7820dfde-af12-4c77-b202-abacd0dce7e5",
  "is_active": true,
  "status": "confirmed",
  "summaries": [],
  "fb_ai_initialized": true,
  "fb_ai_initialized_at": {"$date": "2026-05-21T01:03:34.139Z"},
  "bot_paused_until": null,
  "bot_paused_at": null,
  "bot_paused_reason": null,
  "bot_paused_by": null,
  "created_at": {"$date": "2026-05-21T01:03:17.905Z"},
  "updated_at": {"$date": "2026-05-21T05:23:27.071Z"}
}
```

Record `messages` đã lưu đủ thông tin Pancake trong `meta`:

```json
{
  "_id": {"$oid": "6a0e6e3cf39c9bd4860e65db"},
  "conversation_id": {"$oid": "6a0e59d5eff2db60790d2112"},
  "message_mid": "m_f-5ICnX9juEytTfYjHr57PrjwMPBgDNglPsZ0ZaHCkSYFNrsen9HEIaoN6URXYhMUqyDhMgSdShwMsx_mxSx1Q",
  "role": "user",
  "content": "sao lâu quá mà ko nhận được",
  "meta": {
    "source": "pancake_webhook_ai_forward",
    "page_id": "970198996185881",
    "pancake_conversation_id": "970198996185881_27094379273584117"
  },
  "created_at": {"$date": "2026-05-21T02:30:20.696Z"},
  "updated_at": {"$date": "2026-05-21T02:30:20.696Z"}
}
```

Sau thay đổi, `conversations` có thêm field optional:

```json
{
  "_id": {"$oid": "6a0e59d5eff2db60790d2112"},
  "channel": "970198996185881",
  "customer_name": "Lương Lê",
  "customer_id": "7820dfde-af12-4c77-b202-abacd0dce7e5",
  "pancake_info_url": "https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431",
  "is_active": true,
  "status": "confirmed",
  "summaries": [],
  "created_at": {"$date": "2026-05-21T01:03:17.905Z"},
  "updated_at": {"$date": "2026-05-21T05:23:27.071Z"}
}
```

Vì field này optional, các conversation cũ không có `pancake_info_url` vẫn hợp lệ và không cần migration bắt buộc.

## Contract dữ liệu từ Pancake

Tin nhắn đầu tiên đã có hai field cần dùng trong `Message.meta`:

| DB field | Dùng để ghép |
|---|---|
| `meta.page_id` | `{page_id}` |
| `meta.pancake_conversation_id` | `{c_id}` |

Trong flow webhook hiện tại, conversation được tạo trước khi message được insert. Vì vậy implementation không cần đọc lại message từ DB, mà dùng ngay object normalized của tin nhắn đầu tiên.

Hai field tương ứng trong object normalized:

| Field normalized | Field sẽ lưu trong message |
|---|---|
| `normalized["page_id"]` | `messages.meta.page_id` |
| `normalized["pancake_conversation_id"]` | `messages.meta.pancake_conversation_id` |

Ví dụ:

```text
page_id = 970198996185881
pancake_conversation_id = 970198996185881_27060574493629431
```

Kết quả:

```text
https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431
```

## Mapping field tạo `pancake_info_url`

Mapping cố định:

| Field nguồn | Field đích | Ghi chú |
|---|---|---|
| `normalized["page_id"]` | `pancake_info_url` path segment | Tương ứng `messages.meta.page_id` |
| `normalized["pancake_conversation_id"]` | `pancake_info_url` query param `c_id` | Tương ứng `messages.meta.pancake_conversation_id` |

Không dùng các field sau để ghép URL:

- `message_mid`
- `customer_id`
- `sender_id`
- `conversation_id` nội bộ MongoDB
- `Message._id`

## Format URL Pancake

URL được tạo theo template:

```text
https://pancake.vn/{page_id}?c_id={pancake_conversation_id}
```

Ví dụ thực tế:

```text
https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431
```

Helper đề xuất:

```python
def build_pancake_info_url(
    *,
    page_id: str | None,
    pancake_conversation_id: str | None,
) -> str | None:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(pancake_conversation_id or "").strip()
    if not normalized_page_id or not normalized_conversation_id:
        return None
    return (
        f"https://pancake.vn/{normalized_page_id}"
        f"?c_id={normalized_conversation_id}"
    )
```

Quy tắc:

- Chỉ dùng `page_id` và `pancake_conversation_id` đã trim.
- Nếu thiếu một trong hai field, trả `None`.
- Với flow Pancake bình thường, normalize đã reject payload thiếu `page_id` hoặc `pancake_conversation_id`, nên trường hợp `None` chỉ là fallback an toàn.
- Không encode thêm query param khác.
- Không đưa token hoặc thông tin xác thực vào URL.

## Object nội bộ sau khi normalize

Object normalized Pancake hiện tại đã cần có đủ dữ liệu để tạo URL:

| Field | Ý nghĩa |
|---|---|
| `page_id` | Page/kênh phát sinh message, dùng làm `{page_id}` |
| `pancake_conversation_id` | ID hội thoại phía Pancake, dùng làm `{c_id}` |
| `sender_id` | Khóa tìm/tạo `Conversation.customer_id` |
| `sender_name` | Tên khách để lưu `Conversation.customer_name` |
| `message_mid` | ID message để chống duplicate |
| `text` | Nội dung message khách để lưu và gửi AI |
| `metadata` | Metadata Pancake khác phục vụ debug |

Ví dụ object rút gọn:

```json
{
  "page_id": "970198996185881",
  "pancake_conversation_id": "970198996185881_27060574493629431",
  "sender_id": "7820dfde-af12-4c77-b202-abacd0dce7e5",
  "sender_name": "Lương Lê",
  "message_mid": "m_f-5ICnX9juEytTfYjHr57PrjwMPBgDNglPsZ0ZaHCkSYFNrsen9HEIaoN6URXYhMUqyDhMgSdShwMsx_mxSx1Q",
  "text": "sao lâu quá mà ko nhận được"
}
```

Sau khi tạo mới conversation, field mới cần có:

```json
{
  "pancake_info_url": "https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431"
}
```

## Lưu `pancake_info_url` vào database

Collection `conversations` bổ sung field optional:

```python
pancake_info_url: Optional[str] = Field(default=None, max_length=500)
```

Khi `_get_or_create_pancake_conversation` không tìm thấy conversation hiện có, tạo mới record kèm URL:

```python
conversation = Conversation(
    channel=channel,
    customer_name=sender_name,
    customer_id=sender_id,
    pancake_info_url=_build_pancake_info_url(normalized),
    is_active=True,
    created_at=now_vn(),
    updated_at=now_vn(),
)
```

Khi conversation đã tồn tại:

- Không build lại `pancake_info_url`.
- Không set `conversation.pancake_info_url`.
- Không backfill field đang thiếu trong request message mới.
- Chỉ giữ các update hiện tại như `channel`, `customer_name`, `updated_at` nếu flow đang làm như vậy.

## Quy tắc xử lý message

BE nên áp dụng các rule sau:

- Chỉ tạo `pancake_info_url` trong flow Pancake webhook.
- Chỉ tạo `pancake_info_url` khi tạo mới conversation.
- Không thay đổi rule hiện tại về duplicate message, bot pause, admin takeover và text-only customer message.
- Duplicate check vẫn dùng `Message.message_mid`, không dùng `pancake_info_url`.
- Reply Pancake vẫn dùng `page_id` và `pancake_conversation_id` từ normalized/message meta như flow hiện tại.
- `pancake_info_url` chỉ phục vụ mở hội thoại trên Pancake, không phải khóa định danh nội bộ.
- Conversation cũ không có field này vẫn được list/detail/update bình thường.
- API create/update conversation không nên nhận `pancake_info_url` từ client để giữ rule field này do webhook tạo.

## Lỗi và fallback

BE nên xử lý lỗi theo hướng không làm hỏng flow message hiện tại:

- Nếu thiếu `page_id` hoặc `pancake_conversation_id`, normalize Pancake đã trả reason lỗi như hiện tại và không đi tới bước tạo conversation.
- Nếu helper build URL trả `None`, conversation vẫn có thể được tạo nếu flow hiện tại cho phép, nhưng `pancake_info_url` để `None`.
- Nếu conversation insert lỗi, giữ behavior lỗi hiện tại của webhook.
- Nếu conversation đã tồn tại nhưng thiếu `pancake_info_url`, không tự sửa trong request hiện tại.
- Nếu sau này cần backfill, chạy script riêng có kiểm soát.

Không log token, access token, raw auth header hoặc URL chứa token. `pancake_info_url` không chứa token nên có thể log ở mức debug nếu cần, nhưng log production nên ưu tiên `page_id`, `pancake_conversation_id` và `conversation_id` rút gọn.

## API/schema trả dữ liệu conversation

Nếu admin/API list detail cần trả link Pancake ra client, thêm field vào response schema:

```python
pancake_info_url: Optional[str] = Field(None)
```

Nên thêm vào `ConversationInfoResponse` để các response kế thừa như list/detail có thể trả field này.

Không nên thêm vào request schema:

- `ConversationCreateRequest`
- `ConversationUpdateRequest`

Lý do: `pancake_info_url` là dữ liệu hệ thống tạo từ webhook Pancake, không phải field nhập tay từ client.

## Migration và dữ liệu cũ

Không bắt buộc migration vì field mới là optional.

Conversation cũ có thể có một trong ba trạng thái:

| Trạng thái | Hành vi |
|---|---|
| Không có field `pancake_info_url` | Hợp lệ |
| Có `pancake_info_url = null` | Hợp lệ |
| Có string URL | Hợp lệ |

Nếu cần backfill sau này, nên làm bằng một script riêng:

- Tìm message sớm nhất của từng `conversation_id` có `meta.page_id` và `meta.pancake_conversation_id`.
- Build URL cùng format.
- Chỉ set `conversations.pancake_info_url` khi field đang thiếu hoặc `null`.
- Không overwrite giá trị đã có.

Backfill không nằm trong phạm vi thay đổi chính vì yêu cầu hiện tại chỉ cần tạo URL khi tạo conversation mới.

## Cấu hình backend

Task này không cần thêm biến môi trường mới.

Quy tắc cố định:

- Base URL Pancake info là `https://pancake.vn`.
- Query param conversation là `c_id`.
- Field chỉ tạo trong flow webhook Pancake.
- Field chỉ tạo ở nhánh insert conversation mới.

Nếu sau này Pancake đổi domain hoặc format URL, nên mở task riêng để đưa base URL vào cấu hình.

## Danh sách file dự kiến thay đổi khi implement

- [app/models/conversations.py](../app/models/conversations.py)
- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/api/schemas/conversation.py](../app/api/schemas/conversation.py)
- [tests/test_pancake_webhook.py](../tests/test_pancake_webhook.py)
- [tests/test_conversations_api.py](../tests/test_conversations_api.py)

Nếu tách helper riêng để dễ test:

- `app/services/pancake_conversation_link_service.py`
- `tests/test_pancake_conversation_link_service.py`

Nếu cần backfill sau này:

- `scripts/backfill_pancake_info_url.py`

## Checklist implementation tổng hợp

### Phase 0. Chốt giải pháp

- [x] Chốt `pancake_info_url` là optional string trên `conversations`.
- [x] Chốt URL format là `https://pancake.vn/{page_id}?c_id={pancake_conversation_id}`.
- [x] Chốt field được tạo một lần duy nhất khi insert conversation mới.
- [x] Chốt không overwrite field khi conversation đã tồn tại.
- [x] Chốt không backfill conversation cũ trong request xử lý message mới.
- [x] Chốt không thêm biến env mới trong phase này.

### Phase 1. Bổ sung model/schema

- [x] Thêm `pancake_info_url` vào `Conversation` model với `Optional[str]`.
- [x] Giữ field có default `None` để tương thích conversation cũ.
- [x] Không thêm index cho `pancake_info_url`.
- [x] Thêm `pancake_info_url` vào `ConversationInfoResponse` nếu API cần trả ra client.
- [x] Không thêm `pancake_info_url` vào create/update request schema.

### Phase 2. Build URL và gắn vào create conversation

- [x] Tạo helper build `pancake_info_url` từ `page_id` và `pancake_conversation_id`.
- [x] Helper trim hai field đầu vào trước khi build.
- [x] Helper trả `None` nếu thiếu `page_id` hoặc `pancake_conversation_id`.
- [x] Gọi helper trong nhánh tạo mới của `_get_or_create_pancake_conversation`.
- [x] Lưu `pancake_info_url` khi insert `Conversation`.
- [x] Không gọi helper trong nhánh update conversation đã tồn tại.

### Phase 3. Dữ liệu cũ, logging và fallback

- [x] Đảm bảo conversation cũ không có `pancake_info_url` vẫn parse/list/detail được.
- [x] Đảm bảo message mới của conversation cũ không tự backfill field này.
- [x] Log tạo conversation vẫn không chứa token hoặc dữ liệu nhạy cảm.
- [x] Nếu build URL trả `None`, flow không crash ngoài behavior validate hiện tại.
- [x] Ghi chú backfill là script riêng nếu sau này cần.

### Phase 4. Test và rollout

- [x] Test tạo conversation Pancake mới có `pancake_info_url` đúng format.
- [x] Test conversation đã tồn tại không bị overwrite `pancake_info_url`.
- [x] Test conversation đã tồn tại và `pancake_info_url=None` không bị backfill tự động.
- [x] Test helper trả `None` khi thiếu `page_id`.
- [x] Test helper trả `None` khi thiếu `pancake_conversation_id`.
- [x] Test schema/API response trả `pancake_info_url` nếu field tồn tại.
- [x] Test conversation cũ thiếu field vẫn list/detail bình thường.
- [x] Chạy `pytest -q`.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp Pancake info URL](pancake-info-url-conversation-task-list/phase-0.md)
- [Phase 1. Bổ sung model/schema](pancake-info-url-conversation-task-list/phase-1.md)
- [Phase 2. Build URL và gắn vào create conversation](pancake-info-url-conversation-task-list/phase-2.md)
- [Phase 3. Dữ liệu cũ, logging và fallback](pancake-info-url-conversation-task-list/phase-3.md)
- [Phase 4. Test và rollout](pancake-info-url-conversation-task-list/phase-4.md)

Tiến độ hiện tại:

- [x] Phase 0. Chốt giải pháp Pancake info URL.
- [x] Phase 1. Bổ sung model/schema.
- [x] Phase 2. Build URL và gắn vào create conversation.
- [x] Phase 3. Dữ liệu cũ, logging và fallback.
- [x] Phase 4. Test và rollout.

## Test cần có khi implement

- Tạo conversation Pancake mới từ normalized có `page_id` và `pancake_conversation_id` thì lưu đúng `pancake_info_url`.
- URL được lưu theo đúng format `https://pancake.vn/{page_id}?c_id={pancake_conversation_id}`.
- Với ví dụ `page_id=970198996185881` và `pancake_conversation_id=970198996185881_27060574493629431`, URL là `https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431`.
- Conversation đã tồn tại và có `pancake_info_url` không bị overwrite bởi message mới.
- Conversation đã tồn tại và `pancake_info_url=None` không bị backfill tự động.
- Helper build URL trả `None` nếu thiếu `page_id`.
- Helper build URL trả `None` nếu thiếu `pancake_conversation_id`.
- Conversation cũ không có field `pancake_info_url` vẫn list/detail bình thường.
- Response schema trả `pancake_info_url` nếu field tồn tại trên model.
- API create/update conversation không cho client set `pancake_info_url`.
- Chạy `pytest -q`.

## Ghi chú production

- Field này chỉ là convenience link để mở hội thoại trên Pancake, không nên dùng làm khóa định danh nghiệp vụ.
- Không cần migration bắt buộc vì field optional và conversation cũ vẫn hợp lệ.
- Nếu team cần hiển thị link cho conversation cũ, nên backfill bằng script riêng, không piggyback vào webhook request.
- Nếu Pancake đổi domain hoặc query param, nên đưa base URL vào config trong task riêng.
- Nếu backend xử lý nhiều page, `page_id` trong URL phải lấy từ payload normalized của message, không hard-code page.
- Khi log production, vẫn giữ nguyên nguyên tắc không log token hoặc thông tin xác thực.

## Tiêu chí hoàn thành

- `Conversation` model có field optional `pancake_info_url`.
- Khi khách Pancake nhắn tin lần đầu và tạo conversation mới, DB lưu đúng URL theo format:

```text
https://pancake.vn/{page_id}?c_id={pancake_conversation_id}
```

- Với ví dụ thực tế, URL được lưu là:

```text
https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431
```

- Các message tiếp theo không làm thay đổi `pancake_info_url`.
- Conversation cũ không có field này vẫn hoạt động bình thường.
- API response conversation trả được `pancake_info_url` nếu field tồn tại.
- Không log hoặc lưu token Pancake trong `pancake_info_url`.
- Test chính pass bằng `pytest -q`.
