# Tạo AI session mới theo version và bổ sung context khi conversation đổi version

## Mục tiêu

Tài liệu này mô tả task đồng bộ phiên làm việc của `AI Agent` theo version được cấu hình ở backend.

Khi backend được nâng lên version mới, các conversation đã tồn tại có thể đang giữ AI session được khởi tạo bằng instruction/version cũ. Backend cần nhận diện conversation cũ, chuyển sang một AI session mới gắn với version mới, init lại bằng instruction hiện tại, gửi lại lịch sử hội thoại dạng text để AI lấy lại ngữ cảnh, rồi mới đánh dấu conversation đã lên version mới.

Luồng này áp dụng tại thời điểm customer message đủ điều kiện được forward sang AI. Admin message, bot echo, duplicate message, dangerous keyword bị block hoặc customer message đang bị pause không tự kích hoạt nâng version.

Việc tạo hội thoại/session mới được thực hiện bằng cách đổi giá trị `user` gửi lên `/api/chat` theo version.

Quy ước:

- `system version`: version hiện tại của backend, lấy từ env `AI_CONVERSATION_VERSION`.
- `conversation version`: field `version` trong document `conversations`.
- `baseline version`: `1.0`, dùng cho conversation cũ chưa có field `version`.
- `versioned AI user`: giá trị `user` gửi lên `/api/chat`, được gắn version để OpenClaw tạo session mới.
- `version upgrade turn`: lượt customer message đầu tiên chạy thành công chuỗi session mới/init/context cho version mới.
- `history context`: lịch sử text lấy từ collection `messages`, được gửi lại cho AI sau khi init.
- `current customer message`: message webhook đang kích hoạt version upgrade.
- `AI init message`: giá trị `FB_AI_INIT_MESSAGE` hiện tại.

## Quyết định chính

- Env version dùng `AI_CONVERSATION_VERSION`, ví dụ `1.1`.
- Dùng lại env giới hạn lịch sử hiện có `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`, mặc định `30`; không thêm env max-message mới cho task này.
- Field lưu ở MongoDB là `conversations.version` với kiểu `Optional[str]`, default `None`.
- Conversation cũ có `version="1.0"`, thiếu field, rỗng hoặc `null` được xem là baseline `1.0`.
- Conversation mới được tạo với version hiện tại ngay từ đầu và dùng versioned AI user ngay từ lần init đầu tiên.
- Chỉ nâng version khi `conversation.version < system version`.
- Nếu hai version bằng nhau, giữ flow xử lý message hiện tại nhưng phải dùng đúng versioned AI user của version đó.
- Nếu `conversation.version > system version`, không downgrade, không tạo session mới, log warning và giữ flow hiện tại.
- Version được so sánh theo numeric segments, không so sánh chuỗi. Ví dụ `1.10 > 1.9`.
- Chỉ update `conversations.version` sau khi bước gửi context/current message sang AI thành công.
- Không gửi response của init ra khách hàng.
- Lịch sử context chỉ chứa text; không chứa URL, link-only content, attachment URL hoặc content rỗng.
- Không log raw history context.

## Cấu hình backend

```env
AI_CONVERSATION_VERSION=1.1
PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30
```

Giá trị rollout hiện tại:

- `AI_CONVERSATION_VERSION` chốt là `1.1` để production bắt đầu nâng các conversation cũ khi có customer message mới.
- Conversation cũ thiếu/null/empty version vẫn được xem là baseline `1.0`.
- `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` mặc định `30`.
- Max messages nhỏ hơn `1` được clamp thành `1`.
- Max messages lớn hơn `50` được clamp thành `50`.
- System version sai format không được phép tạo session mới; backend log lỗi cấu hình và giữ flow message hiện tại.

Format version phase đầu:

```text
major.minor
major.minor.patch
```

Mỗi segment phải là số nguyên không âm. Helper normalize nên pad segment thiếu khi compare:

```text
1.1   -> (1, 1, 0)
1.1.1 -> (1, 1, 1)
1.10  -> (1, 10, 0)
```

Không dùng phép so sánh string trực tiếp.

## Quy ước tạo AI session mới

OpenClaw tạo session theo `user` khi backend gọi `/api/chat`. Vì vậy để tạo hội thoại mới theo version, backend đổi `user` từ legacy sender id sang versioned AI user.

Format đề xuất:

```text
<sender_id>:v<version>
```

Ví dụ:

```text
e8b3af1b-8978-4235-884e-fae3f33ef25f:v1.1
```

OpenClaw session key tương ứng:

```text
agent:main:openai-user:e8b3af1b-8978-4235-884e-fae3f33ef25f:v1.1
```

Quy tắc chọn AI user:

| Trạng thái conversation | AI user gửi lên `/api/chat` |
|---|---|
| Conversation mới | `<sender_id>:v<AI_CONVERSATION_VERSION>` |
| Conversation cũ đang upgrade | `<sender_id>:v<AI_CONVERSATION_VERSION>` |
| Conversation cùng version | `<sender_id>:v<conversation.version>` |
| Conversation DB version cao hơn env | `<sender_id>:v<conversation.version>` nếu version hợp lệ; không downgrade |
| DB/system version sai format | Không tạo session versioned mới; log warning/error và giữ behavior an toàn hiện tại |

Điểm quan trọng: sau khi một conversation được chốt `version=1.1`, mọi lượt message sau phải tiếp tục dùng cùng AI user `sender_id:v1.1`. Nếu quay lại dùng `sender_id` legacy, backend sẽ quay về session cũ.

## Dữ liệu hiện có

### Collection `conversations`

Field mới:

```json
{
  "version": "1.1"
}
```

Đề xuất model, bắt buộc giữ dạng optional để tương thích document cũ chưa có field:

```python
version: Optional[str] = Field(default=None, max_length=32)
```

`Conversation.version` và field version trong response schema đều là `Optional[str]`. Không đặt model default cứng thành system version vì Pydantic model không nên phụ thuộc env động. Service tạo conversation phải truyền version hiện tại khi insert; document cũ hoặc dữ liệu chưa được migrate vẫn có thể giữ `None`.

Quy tắc đọc dữ liệu cũ:

| Giá trị DB | Version dùng để compare |
|---|---|
| Thiếu field | `1.0` |
| `null` | `1.0` |
| `""` | `1.0` |
| `"1.0"` | `1.0` |
| `"1.1"` | `1.1` |
| Version DB sai format | Không upgrade tự động; log warning để tránh dùng sai session |

`version` là field do backend quản lý. Không thêm vào `ConversationCreateRequest` hoặc `ConversationUpdateRequest` public trong phase đầu. Có thể expose read-only trong response list/detail để debug rollout.

Các field hiện có liên quan trực tiếp đến flow:

| Field | Vai trò |
|---|---|
| `_id` | Khóa query history và lock/claim migration |
| `customer_id` | Sender id gốc để build versioned AI user |
| `fb_ai_initialized` | Xác định AI user hiện tại đã đọc init instruction hay chưa |
| `fb_ai_initialized_at` | Thời điểm init AI gần nhất |
| `bot_paused_until` | Guard không chạy migration khi bot còn pause |
| `version` | Optional target version đã hoàn tất, field mới của task |
| `updated_at` | Audit thời điểm trạng thái thay đổi |

### Collection `messages`

History context dùng collection `messages` hiện có:

| Field | Vai trò |
|---|---|
| `conversation_id` | Chỉ lấy message cùng conversation |
| `role` | Version context nhận `staff`, `user` và `bot`; handover context vẫn chỉ nhận `staff` và `user` |
| `content` | Nguồn text; phải sanitize URL/rỗng trước khi gửi AI |
| `message_mid` | Dedupe và exclude current/buffer message |
| `created_at` | Chọn message mới nhất và render timeline |

Không thêm collection history riêng và không lưu thêm một bản raw transcript.

## Bảng quyết định version

| Conversation | System | Hành vi |
|---|---|---|
| Conversation mới | `1.1` | Insert trực tiếp `version="1.1"`, dùng AI user `sender_id:v1.1`, init AI như flow bình thường |
| Thiếu version | `1.1` | Xem là `1.0`, chạy version upgrade |
| `1.0` | `1.1` | Chạy version upgrade |
| `1.1` | `1.1` | Dùng AI user `sender_id:v1.1`, xử lý message bình thường |
| `1.2` | `1.1` | Không downgrade, dùng AI user của `1.2` nếu hợp lệ, log warning |
| DB version sai | `1.1` | Không upgrade tự động, xử lý bình thường và log warning |
| System version sai | Bất kỳ | Không tạo session mới, log configuration error |

## Luồng tổng thể

### Conversation mới

1. Webhook nhận customer message.
2. Backend không tìm thấy conversation và tạo document mới.
3. Khi insert, backend set `conversation.version = AI_CONVERSATION_VERSION`.
4. `fb_ai_initialized` mặc định `false`.
5. Backend build AI user `<sender_id>:v<AI_CONVERSATION_VERSION>`.
6. Flow hiện tại gọi `_ensure_sender_initialized(...)` và gửi `FB_AI_INIT_MESSAGE` vào AI user mới.
7. Backend gửi customer message như bình thường vào cùng AI user.
8. AI user mới tạo session mới cho conversation mới.

### Conversation cùng version

1. Backend load conversation.
2. Normalize và compare version.
3. Hai version bằng nhau.
4. Không reset `fb_ai_initialized`.
5. Backend build AI user `<sender_id>:v<conversation.version>`.
6. Không inject version history context.
7. Tiếp tục flow hiện tại với AI user này.

### Conversation version cũ

Khi customer message đủ điều kiện gửi AI và `conversation.version < system version`, xử lý tuần tự, không chạy song song:

```text
B1. Chuyển sang AI session mới theo version
    -> set fb_ai_initialized=false
    -> clear fb_ai_initialized_at
    -> save conversation
    -> build AI user <sender_id>:v<system_version>

B2. Init lại AI
    -> gọi flow _ensure_sender_initialized(...) với AI user mới
    -> vì flag=false nên gửi FB_AI_INIT_MESSAGE
    -> chờ AI trả lời thành công
    -> set fb_ai_initialized=true

B3. Gửi context + message hiện tại
    -> lấy tối đa PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES history item hợp lệ
    -> loại content rỗng và URL
    -> render history cũ đến mới
    -> gộp history với customer message hiện tại
    -> gửi AI bằng payload message bình thường vào cùng AI user mới
    -> chờ AI response thành công

B4. Chốt version
    -> update conversations.version=AI_CONVERSATION_VERSION
    -> save conversation
    -> tiếp tục gửi AI reply ra khách như flow hiện tại
```

Nếu bất kỳ bước B1-B3 lỗi, dừng chuỗi và giữ version cũ.

## B1: Chuyển sang AI session mới theo version

Trước khi init session mới:

```python
conversation.fb_ai_initialized = False
conversation.fb_ai_initialized_at = None
await conversation.save()
```

Sau đó build AI user:

```python
ai_user = f"{sender_id}:v{system_version}"
```

B1 chỉ persist trạng thái DB và chọn session identity mới cho B2/B3.

Nên có helper tập trung, ví dụ:

```python
build_versioned_ai_user(sender_id: str, version: str) -> str
```

Facebook và Pancake phải dùng chung helper này để tránh một channel đi session mới còn channel khác quay về legacy session.

## B2: Init lại AI instruction hiện tại

Sau B1, `fb_ai_initialized=false`, nên dùng lại `_ensure_sender_initialized(...)` nhưng truyền AI user mới.

Init message hiện tại:

```text
Hãy đọc file markdown tại /data/workspace/koisan_chatbot_brain/SKILL.md và bắt đầu koisan chatbot.
```

Behavior hiện tại của `_build_ai_chat_payload(...)` đã special-case chính xác `FB_AI_INIT_MESSAGE`; task mới cần giữ rule init này khi đổi AI user.

Chỉ khi init call thành công mới set:

```text
fb_ai_initialized = true
fb_ai_initialized_at = now
```

Response init là kết quả nội bộ của bước khởi tạo.

## B3: Query và làm sạch lịch sử text

### Nguồn dữ liệu

Không gọi API ngoài để lấy history. Dùng collection `messages`:

```text
conversation_id == conversation.id
role in ["staff", "user", "bot"]
created_at < current_customer_message.created_at
```

Nếu flow chưa lưu current customer message trước AI call, query toàn bộ history đã lưu và truyền current message riêng. Không được đưa current message vào cả history lẫn phần `Tin nhắn hiện tại của khách`.

Riêng version context cần lấy cả `bot` để AI session mới biết trước đó bot đã tư vấn gì. Luồng handover/resume vẫn giữ contract cũ chỉ lấy `staff` và `user`, vì mục tiêu của handover là mô tả phần nhân viên/khách trao đổi trong lúc bot pause.

`Tin nhắn hiện tại của khách` luôn là content mới nhất của customer đang kích hoạt upgrade sau khi build text/image content cơ bản; không lồng block handover/resume vào section này. Nếu cùng lượt vừa resume handover vừa upgrade version, version context dùng history `staff/user/bot` và current customer content sạch, còn handover audit ghi rõ không inject vì đã được xử lý bởi version context.

Không lấy:

- `system`
- role rỗng/không xác định
- init response
- content rỗng sau khi trim
- content chỉ có URL
- attachment URL hoặc image URL được lưu trong `Message.content`

### Quy tắc text-only

Context lịch sử gửi AI phải là text thuần:

- Trim khoảng trắng.
- Xóa URL bắt đầu bằng `http://`, `https://` hoặc `www.` khỏi content hỗn hợp.
- Nếu sau khi xóa URL không còn text có nghĩa, bỏ toàn bộ item.
- Không serialize `attachments`, `image_urls`, `meta`, `message_mid` hoặc raw payload.
- Không cố tải nội dung URL.
- Không OCR ảnh trong task này.
- Không log content sau sanitize.

Ví dụ:

| `Message.content` | Kết quả context |
|---|---|
| `"Em lấy size M"` | Giữ `Em lấy size M` |
| `"https://cdn.example/a.jpg"` | Bỏ item |
| `"Mẫu này nhé https://cdn.example/a.jpg"` | Giữ `Mẫu này nhé` |
| `"   "` | Bỏ item |
| Nhiều URL, không có chữ | Bỏ item |

Giới hạn `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` áp dụng sau sanitize. Task này dùng lại setting/helper handover context hiện có thay vì tạo thêm env mới. Helper có thể fetch theo batch từ mới đến cũ cho đến khi đủ số item text hợp lệ hoặc hết history. Sau khi chọn đủ item mới nhất, render lại theo thời gian cũ đến mới.

### Mapping role

| DB role | Label gửi AI |
|---|---|
| `staff` | `[Nhân viên]` |
| `user` | `[Khách]` |
| `bot` | `[Bot]` |

### Format gửi AI

```text
Bối cảnh hội thoại trước khi cập nhật phiên bản AI:
[Khách] Chị cần mẫu màu đen size M.
[Nhân viên] Mẫu này còn size M, giá 450k.
[Bot] Dạ mẫu này bên em còn hàng ạ.
[Khách] Chị chốt mẫu đó.

Tin nhắn hiện tại của khách:
Số điện thoại của chị là 09xxxxxxxx.

Hãy tiếp tục hội thoại dựa trên bối cảnh trên và không hỏi lại thông tin đã có.
```

Payload vẫn dùng một item `messages[0].role="user"`; history được mô tả bằng text có label, chưa chuyển thành structured multi-role messages trong phase đầu.

Nếu history rỗng sau sanitize, B3 vẫn gửi current customer message bình thường, không tạo heading context rỗng. Nếu current message cũng không có content được AI hỗ trợ thì giữ behavior reject hiện tại và không update version.

## B4: Update conversation version

Chỉ update version sau khi AI đã trả kết quả thành công cho payload B3:

```python
conversation.version = system_version
conversation.updated_at = now_vn()
await conversation.save()
```

Thời điểm đề xuất là ngay sau AI response B3 hợp lệ và trước khi gửi reply qua API channel. Lý do: nếu AI đã nhận context nhưng API gửi reply ra Pancake/Facebook lỗi, retry outbound không nên tạo thêm session version mới lần nữa.

Nếu save version lỗi sau khi AI call thành công:

- Log error rõ conversation/version.
- Không giả vờ migration đã hoàn tất.
- Không log raw context.
- Lần customer message sau có thể chạy lại chuỗi; đây là behavior at-least-once của phase đầu.

## Ranh giới trách nhiệm

### Backend

Backend chịu trách nhiệm:

- Đọc system version từ `AI_CONVERSATION_VERSION`.
- Đọc history limit từ `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` hiện có.
- Load/normalize `Conversation.version: Optional[str]`.
- Chỉ kích hoạt upgrade cho customer message đủ điều kiện gọi AI.
- Build versioned AI user thống nhất cho Facebook/Pancake.
- Persist init flag về false, init lại AI và await đúng thứ tự.
- Query/sanitize history thành text-only context.
- Chỉ update conversation version sau B3 thành công.
- Chặn upgrade trùng khi nhiều message cùng conversation đến đồng thời.
- Không log raw history hoặc secret.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Tạo session mới khi nhận `user` mới từ `/api/chat`.
- Hoàn tất init instruction trước khi xử lý context.
- Đọc history text có label `[Nhân viên]`, `[Khách]` và `[Bot]`.
- Dùng history để tiếp tục hội thoại mà không hỏi lại thông tin đã có.
- Chỉ trả customer-facing answer từ call B3; response init là nội bộ.

### Database

Database chịu trách nhiệm lưu:

- `Conversation.version` dạng optional.
- Trạng thái `fb_ai_initialized` và thời điểm init.
- Message history làm nguồn dựng context.
- Audit metadata rút gọn nếu phase implementation cần.

Không yêu cầu backfill version hàng loạt ở phase đầu.

### Facebook/Pancake channel

Channel webhook cung cấp customer/admin message như hiện tại. Backend không yêu cầu thay đổi payload webhook hoặc API gửi reply của Facebook/Pancake.

### Ngoài phạm vi phương án này

- Không thay đổi nội dung file instruction của AI Agent.
- Không gửi structured multi-role history; phase đầu dùng text có label.
- Không gửi link/attachment/image trong history context.
- Không OCR ảnh hoặc fetch nội dung URL.
- Không tạo session mới hàng loạt tất cả conversation ngay khi deploy.
- Không cho client public tự sửa `Conversation.version`.
- Không giải quyết exactly-once tuyệt đối nếu chưa có DB claim/distributed lock.

## Vị trí tích hợp webhook

Version check chỉ chạy khi message đã qua các guard hiện tại:

- Đúng customer message.
- Không phải bot echo/admin echo.
- Không duplicate/in-flight duplicate.
- Không bị dangerous keyword block.
- Conversation không còn active pause.
- Message có content được AI hỗ trợ.

Version check phải chạy trước `_ensure_sender_initialized(...)` của normal flow.

### Facebook webhook

Điểm tích hợp chính là `_run_ai_forward_and_reply(...)` sau khi có conversation và qua pause check, trước `_ensure_sender_initialized(...)`.

Facebook hiện lưu user/bot message sau khi AI và send reply thành công. Khi implement history helper cần bảo đảm:

- Current customer message không bị lặp trong history.
- Customer messages đã được lưu trước đó mới có thể xuất hiện trong context.
- Nếu muốn bảo đảm cả message trong lúc admin pause được đưa vào version context, cần đổi Facebook flow để lưu customer message trong pause với dedupe theo `message_mid`; đây là thay đổi cần test riêng.

### Pancake webhook

Điểm tích hợp nằm ở luồng xử lý customer message/buffer, sau khi lưu user message và sau pause guard, trước `_generate_pancake_reply(...)` gọi init AI.

Nếu sender buffer đang bật:

- Chỉ một worker xử lý migration cho batch.
- Current content là text đã merge của batch.
- History query phải exclude toàn bộ message IDs thuộc batch để không lặp.
- Version chỉ update một lần sau AI call B3 thành công.

### Conversation tạo từ admin message

Conversation có thể được tạo trước bởi admin echo khi chưa có customer AI session. Service tạo mới vẫn set version hiện tại. Customer message đầu tiên sau đó dùng versioned AI user và chạy init bình thường vì `fb_ai_initialized=false`.

## Concurrency và idempotency

Hai customer messages có thể đến gần như đồng thời và cùng nhìn thấy old version. Nếu không có guard, cả hai có thể cùng init/context vào cùng target session và update version chồng chéo.

Yêu cầu tối thiểu:

- Lock theo `conversation.id` trong một process.
- Sau khi vào lock phải reload conversation và compare version lại.
- Chỉ request còn thấy old version mới chạy migration.
- Các request còn lại chờ request đầu hoàn tất rồi tiếp tục normal flow.

Khuyến nghị implementation:

- In-memory `asyncio.Lock` theo `conversation.id` để request cùng process chờ nhau.
- Mongo atomic claim theo current version + target version + owner token + lease để tránh hai replica cùng chạy upgrade.
- Request gặp claim đang chạy chờ một khoảng giới hạn. Nếu worker trước hoàn tất version, request reload và đi normal flow; nếu claim được release/hết hạn, request có thể claim và retry.
- B4 update version và xóa claim trong cùng một atomic update. Failure trước B4 release claim; nếu release lỗi, lease bảo đảm worker khác có thể tiếp quản sau khi hết hạn.

Duplicate guard theo `message_mid` không được dùng thay concurrency guard vì race có thể xảy ra giữa hai message khác nhau. Topology/số replica production và race behavior vẫn phải được xác nhận trên staging trước rollout.

## Failure và retry

| Lỗi | Behavior |
|---|---|
| Set `fb_ai_initialized=false` lỗi | Không init session mới, dừng migration |
| Build versioned AI user lỗi | Giữ version cũ, không chạy init/context |
| Init lỗi | Giữ version cũ, initialized false, không chạy context |
| Query history lỗi | Fallback history rỗng, vẫn gửi current message; chỉ update version nếu AI call thành công |
| History rỗng | Gửi current message bình thường |
| B3 AI call lỗi | Không update version |
| Save version lỗi | Log error; lần sau có thể retry toàn chuỗi |
| DB version cao hơn env | Không downgrade, warning |
| Version env sai | Không tạo session versioned mới, configuration error |

Không được update version ngay sau B1 hoặc ngay sau init vì AI chưa nhận lại context/customer message.

## Logging và audit

Đề xuất event:

```text
AI_VERSION_CHECK
AI_VERSION_UPGRADE_STARTED
AI_VERSION_SESSION_SELECTED
AI_VERSION_INIT_COMPLETED
AI_VERSION_HISTORY_PREPARED
AI_VERSION_CONTEXT_SENT
AI_VERSION_UPGRADE_COMPLETED
AI_VERSION_UPGRADE_FAILED
AI_VERSION_DOWNGRADE_SKIPPED
AI_VERSION_CONFIG_INVALID
```

Log được phép chứa:

- `conversation_id`
- channel/page/conversation platform ID nếu cần
- old version, target version
- step/reason
- history message count
- max messages
- duration

Không log:

- Raw history content
- Số điện thoại/địa chỉ từ history
- Full AI payload
- Token/bearer header

Có thể lưu audit rút gọn vào `Message.meta` của current customer message:

```json
{
  "ai_version_upgrade": {
    "from": "1.0",
    "to": "1.1",
    "ai_user_version": "1.1",
    "history_message_count": 12,
    "context_sent": true
  }
}
```

Không lưu transcript đầy đủ lần thứ hai trong metadata.

## API/schema conversation

Đề xuất expose read-only `version: Optional[str]` trong:

- `ConversationInfoResponse`
- `ConversationListItemResponse`
- `ConversationDetailResponse`
- Dashboard export nếu vận hành cần theo dõi rollout

Không cho client CRUD tự ghi version trong phase đầu. Version chỉ được thay đổi bởi:

- Service tạo conversation mới.
- Version upgrade orchestrator sau B3 thành công.

## Migration dữ liệu cũ

Không bắt buộc chạy migration Mongo hàng loạt.

- Document cũ thiếu field được hiểu là `1.0` tại runtime.
- Chỉ conversation có customer message mới mới chạy tạo session versioned/init/context.
- Tránh tạo hàng loạt AI session ngay khi deploy.
- Sau khi hoàn tất B4, document tự có `version` mới.

Nếu cần báo cáo trước rollout, có thể chạy read-only query đếm:

```javascript
{
  $or: [
    { version: { $exists: false } },
    { version: null },
    { version: "" },
    { version: "1.0" }
  ]
}
```

## Danh sách file dự kiến thay đổi khi implement

- `app/core/config.py`
- `.env.example`
- `app/models/conversations.py`
- `app/api/schemas/conversation.py`
- `app/services/conversation_service.py`
- `app/api/v1/facebook_webhook.py`
- `app/api/v1/pancake_webhook.py`
- Helper/service mới, ví dụ `app/services/ai_version_context_service.py`
- `tests/test_facebook_webhook_forward.py`
- `tests/test_pancake_webhook.py`
- Test service mới, ví dụ `tests/test_ai_version_context_service.py`

## Checklist implementation tổng hợp

Trạng thái hiện tại: branch đã được reset về commit `f5a963bce16c4d8520749f0261afcabedb9a5c0d`. Code implementation sau commit đó được coi là bỏ. Phase 0-6 đã được code theo hướng tạo AI session mới bằng versioned AI user; phần deploy/staging/production rollout vẫn là bước vận hành riêng.

### Phase 0. Chốt contract version upgrade

- [x] Chốt env system version là `AI_CONVERSATION_VERSION`.
- [x] Chốt dùng lại `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` cho history limit.
- [x] Chốt `Conversation.version` là `Optional[str]`.
- [x] Chốt document thiếu/null/empty version được xem là baseline `1.0`.
- [x] Chốt conversation mới được insert với system version nhưng field model vẫn optional.
- [x] Chốt chỉ upgrade khi DB version thấp hơn system version.
- [x] Chốt không downgrade khi DB version cao hơn env.
- [x] Chốt tạo AI session mới bằng versioned AI user.
- [x] Chốt sequence session mới → init → text context/current message → update version.
- [x] Chốt version history chỉ chứa text của role `staff`, `user` và `bot`; handover context vẫn giữ `staff` và `user`.
- [x] Tài liệu đã được duyệt để bắt đầu code Phase 0-3.

### Phase 1. Config, model và version comparison

- [x] Thêm `AI_CONVERSATION_VERSION=1.1` vào config và `.env.example`.
- [x] Dùng lại config `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`, không thêm max-message env mới.
- [x] Thêm `version: Optional[str] = None` vào model `Conversation`.
- [x] Thêm `version: Optional[str]` read-only vào response schema/serializer.
- [x] Không thêm version vào public create/update request.
- [x] Implement parse/compare numeric version.
- [x] Set system version khi tạo conversation mới ở các create path.
- [x] Bảo đảm document cũ thiếu version load bình thường.

### Phase 2. AI session mới theo version và init AI

- [x] Thêm helper build versioned AI user `<sender_id>:v<version>`.
- [x] AI call Facebook/Pancake dùng versioned AI user khi conversation cùng/higher version.
- [x] Persist `fb_ai_initialized=false` và clear `fb_ai_initialized_at` trước khi chuyển session.
- [x] Gọi `_ensure_sender_initialized(...)` với versioned AI user để gửi `FB_AI_INIT_MESSAGE`.
- [x] Không gửi/lưu response init như reply cho khách.
- [x] Failure ở B1/init giữ conversation version cũ.

### Phase 3. Query và sanitize text history

- [x] Query history theo đúng `conversation_id`.
- [x] Chỉ lấy role `staff`, `user` và `bot` cho version context.
- [x] Bỏ content rỗng, URL-only và attachment/image URL.
- [x] Mixed text/URL chỉ giữ phần text.
- [x] Áp dụng `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` sau sanitize.
- [x] Lấy item hợp lệ mới nhất rồi render cũ đến mới.
- [x] Exclude current customer message hoặc toàn bộ message trong sender buffer batch.
- [x] Không log raw history.

### Phase 4. Tích hợp webhook và chốt version

- [x] Chạy version check sau duplicate/dangerous keyword/pause guard và trước normal init.
- [x] Tích hợp vào Facebook customer AI-forward flow.
- [x] Tích hợp vào Pancake customer/buffer AI-forward flow.
- [x] Same/higher version giữ normal flow nhưng dùng đúng versioned AI user.
- [x] Older version chạy đủ B1-B3 trước reply cuối.
- [x] Chỉ update `Conversation.version` sau B3 AI response thành công.
- [x] Save version trước outbound channel reply.

### Phase 5. Concurrency, logging và fallback

- [x] Có in-memory lock theo conversation và target version trong một process.
- [x] Reload/recheck version sau khi nhận lock.
- [x] Hai message đồng thời trong cùng process chỉ tạo một upgrade sequence.
- [x] History query lỗi fallback current message không context.
- [x] Invalid/higher version không tạo session mới và có warning.
- [x] Log rõ check/lock/init/context/completed/failed.
- [x] Không log raw context, full AI payload hoặc secret trong helper version.
- [x] Không thêm audit metadata/raw transcript mới.
- [ ] Xác nhận hoặc thay bằng distributed lock/Mongo lease nếu production chạy nhiều replica.

### Phase 6. Test và rollout

- [x] Unit test config/model/version comparator.
- [x] Unit test versioned AI user format.
- [x] Unit test text-only sanitizer và limit dùng setting hiện có.
- [x] Integration test Facebook và Pancake sequence.
- [x] Test failure từng bước không update version.
- [x] Test concurrency chỉ có một upgrade sequence.
- [ ] Chạy `pytest -q` bằng Python 3.11 nếu môi trường có.
- [x] Chạy `pytest -q` bằng `.venv` và nạp `.env` (`614 passed, 11 warnings`; `.venv` hiện là Python 3.13.3).
- [ ] Test staging với target `1.1`.
- [ ] Rollout production và theo dõi log.

Task list chi tiết từng phase:

- [Phase 0. Chốt contract version upgrade](conversation-ai-version-context-reset-task-list/phase-0.md)
- [Phase 1. Config, model và version comparison](conversation-ai-version-context-reset-task-list/phase-1.md)
- [Phase 2. AI session mới theo version và init AI](conversation-ai-version-context-reset-task-list/phase-2.md)
- [Phase 3. Query và sanitize text history](conversation-ai-version-context-reset-task-list/phase-3.md)
- [Phase 4. Tích hợp webhook và chốt version](conversation-ai-version-context-reset-task-list/phase-4.md)
- [Phase 5. Concurrency, logging và fallback](conversation-ai-version-context-reset-task-list/phase-5.md)
- [Phase 6. Test và rollout](conversation-ai-version-context-reset-task-list/phase-6.md)

Tiến độ hiện tại:

- [x] Phase 0. Tài liệu proposal đã cập nhật theo hướng versioned AI user.
- [x] Phase 1. Config, model và version comparison.
- [x] Phase 2. AI session mới theo version và init AI.
- [x] Phase 3. Query và sanitize text history.
- [x] Phase 4. Tích hợp webhook và chốt version.
- [x] Phase 5. Concurrency, logging và fallback trong một process; còn cần xác nhận distributed lock nếu production nhiều replica.
- [ ] Phase 6. Automated test đã bổ sung và full-suite `.env`/`.venv` pass; staging/production rollout chưa thực hiện.

## Test cần có khi implement

- Parse/compare `1.0`, `1.1`, `1.1.1`, `1.10` đúng numeric.
- Missing DB version được xem là `1.0`.
- Model và response schema chấp nhận `version=None`.
- Conversation mới được insert với system version và dùng AI user `sender_id:v<system_version>`.
- Same version không thay đổi flow nhưng vẫn dùng đúng versioned AI user.
- Higher DB version không downgrade.
- Old version set initialized false trước khi init session mới.
- Init payload dùng `FB_AI_INIT_MESSAGE`.
- B3 chỉ chạy sau init success.
- Version history lấy `staff/user/bot`; handover history vẫn chỉ lấy `staff/user`.
- Section `Tin nhắn hiện tại của khách` là latest customer content, không phải handover-wrapped content.
- URL-only và empty content bị bỏ.
- Mixed text/URL giữ text, bỏ URL.
- Limit áp dụng sau sanitize và render cũ đến mới.
- Current customer message không bị lặp.
- Version chỉ update sau B3 AI success.
- Query history lỗi fallback current message.
- Init hoặc B3 lỗi không update version.
- Hai message đồng thời chỉ có một upgrade sequence cho cùng version.
- Không log raw history.
- Chạy `pytest -q` bằng Python 3.11 nếu môi trường có; test thực tế theo yêu cầu dùng `.env` và `.venv`.

## Ghi chú production

Rollout đề xuất:

1. Deploy code với `AI_CONVERSATION_VERSION=1.1`.
2. Xác nhận conversation mới được ghi version `1.1` và dùng AI user `sender_id:v1.1`.
3. Chọn conversation cũ thiếu version hoặc version `1.0` có history text rồi gửi một customer message.
4. Xác nhận thứ tự call: init trên AI user mới → context/current message trên cùng AI user.
5. Xác nhận DB version chỉ thành `1.1` sau B3 success.
6. Test history có URL/image và xác nhận AI payload context không có URL.
7. Test hai message đồng thời.
8. Theo dõi log lỗi/upgrade rate khi rollout production.

Rollback env từ `1.1` về `1.0` không được downgrade conversation `1.1`; code phải log warning và tiếp tục normal flow.

- Không bump version production trước khi staging xác nhận đủ thứ tự session mới → init → context.
- Không log raw history vì context có thể chứa số điện thoại, địa chỉ hoặc thông tin đơn hàng.
- Theo dõi tỉ lệ upgrade started/completed/failed và số lần duplicate upgrade.
- `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` đang được dùng chung cho handover resume và version context; khi thay đổi env phải đánh giá tác động lên cả hai flow.

## Tiêu chí hoàn thành

- Conversation mới nhận system version và dùng versioned AI user.
- `Conversation.version` giữ kiểu `Optional[str]` và document cũ thiếu field vẫn load được.
- Conversation cũ chạy đúng thứ tự session mới → init → text context/current message.
- History context 100% text, không URL/rỗng/attachment.
- Current message không bị lặp trong history.
- Version chỉ update sau AI context call thành công.
- Same/higher version không tạo session mới sai version.
- Race cùng conversation không tạo nhiều chuỗi upgrade.
- Không log raw history hoặc dữ liệu nhạy cảm.
- Automated test và staging verification pass trước production.
