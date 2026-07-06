# Task cập nhật status handover cho Facebook Page Inbox

## Mục tiêu

Tài liệu này mô tả phương án để BE tự detect nội dung cần handover từ text trả lời của Brain/AI Agent qua `FB_AI_CHAT_URL`, sau đó update `status` của conversation hiện tại thành `handover`.

Điểm thay đổi chính: `BE` vẫn gọi Brain/AI Agent và vẫn gửi tin nhắn Facebook cho khách như hiện tại. Sau khi nhận response từ Brain/AI Agent, BE detect keyword/pattern handover trong text trả lời. Nếu match, BE gọi API update conversation theo `conversation_id` để đổi `conversations.status` từ giá trị hiện tại, mặc định là `new`, sang `handover`.

Không pause bot trong task này. Nếu khách tiếp tục nhắn sau đó, BE vẫn xử lý luồng Facebook Page Inbox như hiện tại.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Brain` / `AI Agent`: service bên ngoài được cấu hình bằng `FB_AI_CHAT_URL`.
- `conversation_id`: id của document trong collection `conversations`.
- `status`: field hiện có trong collection `conversations`, hiện mặc định là `new`.
- `handover`: giá trị status mới dùng để đánh dấu conversation cần người phụ trách/admin/sale xử lý.

## Luồng tổng thể

```text
Khách hàng nhắn tin vào Facebook Page
→ BE hiện tại nhận webhook message
→ BE lấy hoặc tạo conversation hiện tại
→ BE gửi message/context sang Brain/AI Agent qua FB_AI_CHAT_URL
→ BE nhận response/data từ Brain/AI Agent
→ BE extract text trả lời bằng logic hiện tại
→ BE detect keyword/pattern handover trong text trả lời
→ BE gửi tin nhắn cho khách qua Facebook như hiện tại
→ Nếu match handover: BE gọi API update conversation_id, set status = "handover"
→ Nếu không match: không update status
```

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận webhook message từ Facebook Page.
- Lấy hoặc tạo `Conversation` tương ứng với khách hàng.
- Gửi message/context sang Brain/AI Agent qua `FB_AI_CHAT_URL`.
- Nhận response/data từ Brain/AI Agent.
- Extract text trả lời bằng logic hiện tại trong code.
- Detect handover bằng keyword/pattern trong text trả lời đã chuẩn bị gửi khách.
- Gửi tin nhắn Facebook cho khách như hiện tại.
- Nếu detect match, gọi API update conversation theo `conversation_id`.
- Đổi `conversations.status` thành `handover`.
- Không dùng các field pause như `bot_paused_at`, `bot_paused_until`, `bot_paused_reason`, `bot_paused_by` cho task này.
- Không chặn các lượt hỏi tiếp theo của khách.

### Brain / AI Agent

Brain chịu trách nhiệm:

- Phân tích ngữ cảnh hội thoại và yêu cầu của khách.
- Trả câu trả lời text cho BE qua contract hiện tại.
- Có thể dùng các cụm chuyển người phụ trách trong text khi cần handover.

Brain không cần:

- Gọi API update conversation.
- Trả field mới như `handover=true` trong phase đầu.
- Biết `conversation_id` nội bộ của BE.

### API update conversation

API update conversation chịu trách nhiệm:

- Nhận `conversation_id`.
- Validate conversation tồn tại.
- Validate status `handover` là giá trị hợp lệ.
- Update `conversations.status = "handover"`.
- Update `updated_at` theo behavior hiện tại của service.
- Trả lỗi rõ ràng nếu `conversation_id` không hợp lệ hoặc conversation không tồn tại.

### Ngoài phạm vi phương án này

- Không thay đổi luồng gọi `FB_AI_CHAT_URL`.
- Không thay đổi cách BE lấy text trả lời từ response Brain/AI Agent.
- Không yêu cầu Brain đổi format response.
- Không thêm bảng mới.
- Không thêm field handover riêng nếu `status` đã đáp ứng được nhu cầu.
- Không pause bot sau khi detect handover.
- Không build màn hình admin mới.
- Không tự assign admin cụ thể theo ca trực trong phase đầu.

## Contract dữ liệu giữa BE và Brain

BE vẫn gọi Brain bằng luồng chat hiện tại qua `FB_AI_CHAT_URL`. Response từ Brain giữ nguyên các format hiện tại mà BE đang extract được text, ví dụ từ các field như `assistant_message`, `answer`, `message`, `response`, `text`, `content`, `output`, `result`, hoặc `data`.

Ví dụ response dạng text thuần:

```text
Dạ trường hợp này em chuyển bộ phận phụ trách kiểm tra và phản hồi anh/chị sớm nhất ạ.
```

Ví dụ response dạng JSON:

```json
{
  "text": "Dạ em chuyển sale hỗ trợ anh/chị chi tiết hơn ạ."
}
```

Quy tắc:

- BE extract text trả lời bằng logic hiện tại.
- BE không yêu cầu Brain trả field handover mới.
- BE detect handover từ text cuối cùng dự kiến gửi cho khách.
- Nếu text match handover, BE update status conversation bằng `conversation_id` đang có trong flow webhook.

## Handover detection

### Input detect

Input chính là text trả lời sau khi BE đã extract/prepare từ response Brain/AI Agent bằng flow hiện tại.

BE không detect handover từ message của khách trong phase này, vì mục tiêu là bắt tín hiệu mà AI đã quyết định cần chuyển người phụ trách.

### Normalize text

Trước khi match, BE nên normalize text để giảm miss:

- Chuyển về lowercase.
- Trim đầu/cuối.
- Gộp nhiều khoảng trắng thành một khoảng trắng.
- Chuẩn hóa dấu câu thường gặp thành khoảng trắng khi cần.
- Tạo thêm bản bỏ dấu tiếng Việt để match biến thể không dấu.

Ví dụ:

```text
"Dạ em chuyển bộ phận phụ trách kiểm tra ạ."
→ "dạ em chuyển bộ phận phụ trách kiểm tra ạ"
→ "da em chuyen bo phan phu trach kiem tra a"
```

### Keyword/pattern phase đầu

Các cụm cần detect:

- `chuyển bộ phận phụ trách`
- `em chuyển bộ phận phụ trách`
- `em chuyển sale`
- `cần bộ phận phụ trách kiểm tra`
- `em chuyển xử lý`

BE nên hỗ trợ cả bản có dấu và không dấu:

- `chuyen bo phan phu trach`
- `em chuyen bo phan phu trach`
- `em chuyen sale`
- `can bo phan phu trach kiem tra`
- `em chuyen xu ly`

Pattern đề xuất:

```python
HANDOVER_REPLY_PATTERNS = [
    r"\b(?:em\s+)?chuyen\s+bo\s+phan\s+phu\s+trach\b",
    r"\bem\s+chuyen\s+sale\b",
    r"\bcan\s+bo\s+phan\s+phu\s+trach\s+kiem\s+tra\b",
    r"\bem\s+chuyen\s+xu\s+ly\b",
]
```

Object kết quả nội bộ:

```json
{
  "detected": true,
  "reason": "ai_reply_handover_keyword",
  "matched_pattern": "em chuyen sale"
}
```

Object này chỉ phục vụ xử lý/log nội bộ trong request hiện tại. Trạng thái cần lưu xuống database là `conversations.status = "handover"`.

## Cập nhật conversation status

Collection `conversations` hiện đã có field `status` và giá trị mặc định là `new`.

Ví dụ document hiện tại:

```json
{
  "_id": "6a0698b32961bc581e78717f",
  "channel": "MediaX AI chatbot testing",
  "customer_name": "Bảo Duy",
  "customer_id": "24472953752402662",
  "is_active": true,
  "status": "new"
}
```

Khi BE detect handover, kết quả mong muốn:

```json
{
  "_id": "6a0698b32961bc581e78717f",
  "status": "handover"
}
```

### API update đề xuất

Nếu dùng API CRUD conversation hiện có:

```http
PATCH /api/v1/conversations/{conversation_id}
```

Payload:

```json
{
  "status": "handover"
}
```

Response rút gọn:

```json
{
  "id": "6a0698b32961bc581e78717f",
  "channel": "MediaX AI chatbot testing",
  "customer_name": "Bảo Duy",
  "customer_id": "24472953752402662",
  "is_active": true,
  "status": "handover"
}
```

Nếu phần xử lý webhook đang chạy trong cùng BE process, implementation có thể reuse service update conversation hiện có thay vì tự HTTP call về chính BE. Tuy nhiên behavior cuối cùng vẫn phải tương đương API update theo `conversation_id` với payload `{"status": "handover"}`.

### Status hợp lệ

Collection `conversations` dùng field `status` để theo dõi trạng thái xử lý. Các status hợp lệ cho task này:

- `new`: conversation mới/chưa cần handover.
- `handover`: conversation đã được AI detect cần người phụ trách xử lý.
- `confirmed`: conversation handover đã được xác nhận xử lý xong.

Các status cũ `not_interested` và `highly_interested` không còn dùng trong task này và cần được gỡ khỏi enum/schema.

Enum model:

```python
class ConversationStatus(str, Enum):
    NEW = "new"
    HANDOVER = "handover"
    CONFIRMED = "confirmed"
```

Schema public:

```python
class ConversationStatusSchema(str, Enum):
    NEW = "new"
    HANDOVER = "handover"
    CONFIRMED = "confirmed"
```

Validator status chỉ nhận các giá trị:

- `new`
- `handover`
- `confirmed`

Riêng filter `status` của API list conversation expose đúng ba giá trị cần dùng cho dashboard handover:

- `new`
- `handover`
- `confirmed`

`confirmed` dùng để xác nhận conversation handover đã được xử lý xong.

### Quy tắc update

- Mỗi lần detect match handover thì trigger update `status = "handover"` cho conversation hiện tại.
- Nếu conversation đang có status khác `handover`, update sang `handover`.
- Nếu conversation đã là `handover`, update có thể là no-op nhưng không được làm fail flow.
- Cho phép update `status = "confirmed"` khi conversation hiện tại đang là `handover`.
- Nếu conversation đã là `confirmed`, update `confirmed` tiếp có thể là no-op.
- Không cho update trực tiếp từ `new` sang `confirmed`.
- Không update status nếu text không match handover.
- Không update status nếu không xác định được `conversation_id`.
- Không set các field pause của bot.
- Không chặn việc gửi tin nhắn Facebook cho khách.

## Gửi Facebook message

Khi detect handover, BE vẫn gửi text hiện tại cho khách như một tin nhắn Facebook bình thường.

Ví dụ:

```json
{
  "recipient": {
    "id": "PSID_KHACH_HANG"
  },
  "messaging_type": "RESPONSE",
  "message": {
    "text": "Dạ em chuyển sale hỗ trợ anh/chị chi tiết hơn ạ."
  }
}
```

Nếu khách tiếp tục nhắn sau đó, BE vẫn xử lý như luồng hiện tại: nhận webhook, gọi Brain/AI Agent, gửi câu trả lời cho khách. Nếu text trả lời lại match handover, BE tiếp tục trigger update `status = "handover"` cho conversation đó.

## Error handling

Luồng nên xử lý lỗi theo hướng không làm mất reply cho khách:

- Brain lỗi: dùng behavior fallback hiện tại của BE.
- Brain trả text không match handover: gửi text như bình thường, không update status.
- Detector lỗi ngoài ý muốn: log lỗi rút gọn, gửi text như bình thường.
- Match handover nhưng thiếu `conversation_id`: log `handover_missing_conversation_id`, không update status.
- Match handover nhưng conversation không tồn tại: log `handover_conversation_not_found`, không retry vô hạn.
- Update status lỗi `400`: log lỗi validate, gửi text cho khách như hiện tại.
- Update status lỗi `404`: log conversation not found, gửi text cho khách như hiện tại.
- Update status lỗi `5xx` hoặc timeout: không làm fail Facebook reply.
- Facebook send lỗi: trả lỗi theo behavior hiện tại; update status vẫn là best effort theo phase này.

Không log:

- `FB_PAGE_ACCESS_TOKEN`
- `FB_AI_BEARER_TOKEN`
- Nội dung header auth nội bộ

Nên log:

- Conversation id.
- Customer id đã mask nếu cần.
- Có detect handover hay không.
- Pattern đã match.
- Status trước khi update nếu có sẵn.
- Kết quả update status ở mức `ok`, `status_code`, `reason`.

## Cấu hình runtime

Các env liên quan hiện có:

- `FB_AI_CHAT_URL`: endpoint Brain/AI Agent.
- `FB_AI_BEARER_TOKEN`: token gọi Brain nếu luồng hiện tại yêu cầu.
- `FB_PAGE_ACCESS_TOKEN`: token gửi Messenger Send API.
- `FB_PAGE_ID`: Page id.
- `FB_WEBHOOK_VERIFY_TOKEN`: token verify webhook Facebook.

Task này không cần thêm env mới nếu update status bằng service nội bộ hiện có. Nếu team chọn HTTP self-call vào API CRUD conversation, cần thống nhất auth nội bộ riêng, nhưng không hard-code token trong source hoặc docs.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/v1/facebook_webhook.py](../app/api/v1/facebook_webhook.py)
- [app/models/conversations.py](../app/models/conversations.py)
- [app/api/schemas/conversation.py](../app/api/schemas/conversation.py)
- [app/services/conversation_service.py](../app/services/conversation_service.py)
- [tests/test_facebook_webhook_forward.py](../tests/test_facebook_webhook_forward.py)
- [tests/test_conversations_api.py](../tests/test_conversations_api.py)

Nếu tách detector riêng để dễ test:

- [app/services/facebook_handover_detection_service.py](../app/services/facebook_handover_detection_service.py)
- [tests/test_facebook_handover_detection_service.py](../tests/test_facebook_handover_detection_service.py)

## Checklist implementation tổng hợp

### Phase 0. Chốt giải pháp

- [x] Chốt BE vẫn gọi `FB_AI_CHAT_URL` và lấy text trả lời bằng logic hiện tại.
- [x] Chốt Brain không cần đổi response contract trong phase đầu.
- [x] Chốt detect handover dựa trên keyword/pattern trong text trả lời.
- [x] Chốt mỗi lần match handover thì update conversation hiện tại sang `status = "handover"`.
- [x] Chốt không pause bot; khách hỏi tiếp thì BE vẫn xử lý tiếp như hiện tại.
- [x] Chốt text hiện tại vẫn được gửi cho khách khi match handover.

### Phase 1. Bổ sung status handover

- [x] Gỡ `not_interested` và `highly_interested` khỏi `ConversationStatus`.
- [x] Gỡ `not_interested` và `highly_interested` khỏi `ConversationStatusSchema`.
- [x] Thêm `HANDOVER = "handover"` vào `ConversationStatus`.
- [x] Thêm `HANDOVER = "handover"` vào `ConversationStatusSchema`.
- [x] Giữ `CONFIRMED = "confirmed"` để xác nhận handover đã xử lý xong.
- [x] Update `_normalize_conversation_status` để chỉ accept `new`, `handover`, `confirmed`.
- [x] Test create/update/list conversation với status `handover`, update/list với status `confirmed`.

### Phase 2. Xây detector handover

- [x] Tạo helper normalize text tiếng Việt có dấu và không dấu.
- [x] Tạo danh sách keyword/pattern phase đầu.
- [x] Detect được các cụm `chuyển bộ phận phụ trách`, `em chuyển sale`, `cần bộ phận phụ trách kiểm tra`, `em chuyển xử lý`.
- [x] Trả object debug gồm `detected`, `reason`, `matched_pattern`.
- [x] Test các biến thể có dấu, không dấu, nhiều khoảng trắng và dấu câu.

### Phase 3. Tích hợp update conversation status

- [x] Sau khi extract/prepare text trả lời, gọi detector handover.
- [x] Nếu không match, giữ nguyên flow gửi reply hiện tại và không update status.
- [x] Nếu match, lấy `conversation_id` từ conversation hiện tại.
- [x] Gọi API/service update conversation với payload `{"status": "handover"}`.
- [x] Không ghi field pause vào database.
- [x] Vẫn gửi text hiện tại cho khách.
- [x] Nếu khách hỏi tiếp, flow vẫn tiếp tục gọi Brain/AI Agent như hiện tại.
- [x] Log đủ thông tin debug rút gọn.

### Phase 4. Test và rollout

- [x] Test webhook không handover vẫn gọi/gửi như hiện tại và không update status.
- [x] Test webhook có handover keyword thì update status conversation thành `handover`.
- [x] Test conversation đang `handover` mà match tiếp không làm fail flow.
- [x] Test thiếu `conversation_id` không làm hỏng reply Facebook.
- [x] Test update status lỗi không làm hỏng reply Facebook.
- [x] Test các enum/schema/API conversation accept status `handover`.
- [x] API list conversation chỉ expose filter status `new`, `handover`, `confirmed`.
- [x] Test chỉ cho update `confirmed` khi conversation hiện tại là `handover` hoặc đã `confirmed`.
- [x] Chạy `pytest -q`.

## Tiêu chí hoàn thành

- BE vẫn gọi Brain qua `FB_AI_CHAT_URL` như hiện tại.
- BE vẫn extract text trả lời từ response Brain bằng logic hiện tại.
- BE detect được các cụm handover đã chốt trong text trả lời.
- Collection `conversations` hỗ trợ status `handover`.
- Khi match handover, BE update đúng conversation hiện tại sang `status = "handover"`.
- Khi không match handover, BE không đổi status conversation.
- Khi match handover, khách vẫn nhận được tin nhắn Facebook như hiện tại.
- Sau handover, nếu khách hỏi tiếp thì bot vẫn tiếp tục xử lý như hiện tại.
- Lỗi update status không làm fail reply Facebook.
- Test chính pass bằng `pytest -q`.

## Rủi ro cần theo dõi

- Keyword quá rộng có thể false positive và đổi status sang `handover` không cần thiết.
- Keyword quá hẹp có thể miss khi AI dùng cách diễn đạt khác.
- Nếu quên thêm `handover` vào enum/schema, API update conversation sẽ trả `400`.
- Nếu update bằng HTTP self-call, auth nội bộ có thể làm flow phức tạp hơn cần thiết.
- Nếu update status sau khi gửi Facebook và update lỗi, khách vẫn nhận tin nhưng dashboard chưa thấy `handover`.
- Nếu update status trước khi gửi Facebook và Facebook send lỗi, dashboard có thể đã thấy `handover` dù khách chưa nhận được tin.

## Khuyến nghị

- Bắt đầu với keyword/pattern rõ ràng như danh sách phase đầu, chưa dùng fuzzy matching.
- Match trên cả bản có dấu và không dấu để giảm miss.
- Giữ detector ở BE để không phụ thuộc Brain đổi contract.
- Reuse service update conversation hiện có nếu webhook chạy cùng process, tránh HTTP self-call không cần thiết.
- Nếu vẫn cần đúng nghĩa call API, dùng endpoint `PATCH /api/v1/conversations/{conversation_id}` với payload `{"status": "handover"}` và auth nội bộ rõ ràng.
- Sau khi chạy thật, thu thập các câu AI hay dùng để mở rộng pattern có kiểm soát.
