# Tích hợp Pancake tự tư vấn mẫu từ webhook quảng cáo/comment

## Mục tiêu

Tài liệu này mô tả phương án để `BE` xử lý các webhook Pancake có thể suy ra mẫu sản phẩm từ bài viết nguồn. Khi nhận được ad card có `message.id` bắt đầu bằng `ad-`, hoặc page comment reply notice trỏ tới comment trên bài viết, `BE` tự hydrate nội dung bài viết/quảng cáo, bóc toàn bộ mã sản phẩm từ `description`, tạo prompt cố định dạng `tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook`, gọi `AI Agent` theo đúng session khách hàng, rồi gửi câu trả lời vào đúng hội thoại Pancake hiện tại.

Điểm thay đổi chính: flow mới không chờ khách nhắn thêm rồi mới đưa context bài viết vào AI. Khi bắt được trigger hợp lệ và bóc được mã sản phẩm, `BE` chủ động tạo một user message tổng hợp để hỏi AI ngay. Câu trả lời của AI được gửi lại qua Pancake Public API vào `pancake_conversation_id` hiện tại.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `AI Agent` / `Brain`: service tạo nội dung trả lời cho khách.
- `ad card`: message Pancake có `message.id` bắt đầu bằng `ad-`.
- `page_comment_reply_notice`: page-side system notice có nội dung `Bạn đang phản hồi bình luận...`, có `message_tags[].link` chứa `comment_id=`.
- `auto_consult_trigger`: webhook đủ điều kiện để tự tạo prompt tư vấn mẫu, gồm `ad_card` và `page_comment_reply_notice`.
- `description`: caption/nội dung bài quảng cáo hoặc bài viết lấy từ Pancake Conversation Messages API, ưu tiên `post_attachments[].description`.
- `product_codes`: danh sách mã sản phẩm bóc từ `description`, ví dụ `["S7671263", "W2651713"]`.
- `auto_consult_prompt`: prompt tổng hợp gửi AI, ví dụ `tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook`.
- `trigger_message_mid`: `message_mid` của webhook làm phát sinh auto consult.
- `pancake_conversation_id`: id hội thoại phía Pancake.
- `page_access_token`: token Pancake Public API dùng theo đúng `page_id`.

## Luồng tổng thể

Khách hàng tương tác với quảng cáo đã nối vào Pancake.

Pancake gửi một hoặc nhiều webhook về `BE` trong cùng một `pancake_conversation_id`. Trong đó có thể có:

- Ad card `message.id` bắt đầu bằng `ad-`.
- Page comment reply notice có link comment Facebook trong `message_tags`.
- Customer message thật.
- Bot/admin/page echo khác.

`BE` normalize webhook như hiện tại.

Trước khi ignore echo/page message, `BE` kiểm tra webhook có phải `auto_consult_trigger` không.

Nếu là ad card `ad-*`, `BE` dùng chính `message_mid`, `page_id`, `pancake_conversation_id` để gọi Pancake Conversation Messages API và tìm lại đúng message ad.

Nếu là `page_comment_reply_notice`, `BE` dùng `message_mid`, `page_id`, `pancake_conversation_id` để gọi Pancake Conversation Messages API, tìm lại notice/comment context, lấy description bài viết liên quan tới `comment_id`, rồi xử lý giống ad card.

Sau khi lấy được detail bài viết/quảng cáo, `BE` lấy `description` từ `messages[].attachments[].post_attachments[].description` hoặc nguồn description hợp lệ tương đương, bóc `product_codes`, rồi tạo prompt cố định:

```text
tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook
```

`BE` phải resolve đúng customer identity trước khi gọi AI. Với các trigger page-side như ad card hoặc page comment reply notice, `sender_id` normalized ban đầu thường là `page_id` vì message đến từ page, nên không được dùng `sender_id` này làm user AI. `BE` phải tạo normalized message tổng hợp với `sender_id` là customer thật, ưu tiên:

1. `conversation_customer_id`
2. `page_customer_id`
3. `conversation_sender_id` nếu khác `page_id`

`BE` lấy hoặc tạo `Conversation` nội bộ theo customer thật, kiểm tra pause/admin takeover, chống trùng theo `trigger_message_mid`, gọi AI bằng `auto_consult_prompt`, rồi gửi reply qua Pancake vào đúng `page_id` và `pancake_conversation_id`.

Customer message thật vẫn xử lý theo flow hiện tại. Flow mới không yêu cầu lưu ad/comment context để chờ customer message sau đó.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận webhook Pancake qua endpoint hiện có.
- Normalize payload để lấy `page_id`, `pancake_conversation_id`, `message_mid`, customer identity và metadata hội thoại.
- Nhận diện ad card bằng `message_mid` bắt đầu với `ad-`.
- Nhận diện `page_comment_reply_notice` bằng tổ hợp page sender, nội dung notice, `message_tags` có `comment_id=`, không có admin/uid và không có attachment.
- Gọi Pancake Conversation Messages API bằng đúng token theo `page_id`.
- Tìm đúng message ad trong response Pancake.
- Tìm đúng page comment reply notice/comment context trong response Pancake.
- Lấy `ad_id`, `post_id`, `comment_id` nếu có, và `description` từ attachment/context bài viết.
- Bóc `product_codes` từ `description`.
- Tạo prompt cố định `tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook`.
- Gọi AI bằng customer identity thật, không dùng `page_id` làm user AI.
- Tái sử dụng flow hiện có để chuẩn bị reply text/Drive image nếu AI trả Drive link.
- Gửi reply vào đúng `pancake_conversation_id`.
- Lưu user message tổng hợp và bot message vào database để audit/idempotency.
- Tôn trọng pause do admin takeover trước khi gọi AI và trước khi gửi reply.
- Log đủ metadata để debug nhưng không log token hoặc raw URL có token.

### Pancake

Pancake chịu trách nhiệm:

- Gửi webhook có đủ `page_id`, `conversation_id`, `message.id`.
- Cung cấp Conversation Messages API để BE hydrate ad card hoặc comment/post context.
- Trả payload có `attachments[].type = ad_click` và `post_attachments[].description` khi dữ liệu ad tồn tại.
- Trả payload có đủ message tag/comment/post context để BE tìm description bài viết khi page comment reply notice tồn tại.
- Nhận message reply qua Public API.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Nhận prompt tự nhiên dạng `tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook`.
- Dùng session theo `user` mà BE truyền vào để trả lời nhất quán với hội thoại khách.
- Trả nội dung text tư vấn.
- Có thể trả Drive file/folder link nếu cần gửi ảnh sản phẩm theo flow Pancake hiện tại.
- Không cần tự gọi Pancake API hoặc biết `ad_id`, `post_id`, `comment_id`.

### Ngoài phạm vi phương án này

- Không chờ customer message thật rồi mới đưa ad/comment context vào AI.
- Không lưu `description` làm context để sử dụng ở lượt khách sau.
- Không xử lý system ad message báo khách đã trả lời quảng cáo làm trigger riêng.
- Không dùng Meta Graph API trong phase đầu.
- Không lấy ảnh từ ad payload trong phase đầu; ảnh nếu có vẫn đi qua reply của AI và flow Drive image hiện tại.
- Không đổi flow Facebook webhook.
- Không tự xử lý comment `COMMENT` trong phase đầu nếu flow Pancake hiện tại chỉ hỗ trợ `INBOX`.
- Không gửi auto reply khi conversation đang bị admin pause, trừ khi có yêu cầu business riêng và bật bằng cấu hình sau này.

## Hiện trạng hệ thống

Webhook Pancake hiện tại được xử lý ở:

- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/services/pancake_webhook_normalize_service.py](../app/services/pancake_webhook_normalize_service.py)
- [app/services/pancake_message_service.py](../app/services/pancake_message_service.py)

Normalize hiện tại có các field cần dùng:

- `page_id`
- `sender_id`
- `message_mid`
- `message_type`
- `is_echo`
- `pancake_conversation_id`
- `conversation_customer_id`
- `conversation_sender_id`
- `conversation_sender_name`
- `message_from_id`
- `message_from_admin_name`
- `attachments`
- `post_id`

Với ad card trong log, normalized message có dạng:

```json
{
  "message_mid": "ad-2692195438413833912024387249670048017797536.0",
  "page_id": "109370365206868",
  "sender_id": "109370365206868",
  "is_echo": true,
  "message_kind": "bot_echo",
  "pancake_conversation_id": "109370365206868_26921954384138339",
  "conversation_customer_id": "2a331718-36de-43cd-95df-e1f68d9d68f5",
  "conversation_sender_id": "26921954384138339",
  "text_present": false,
  "attachment_count": 1
}
```

Vì `sender_id` đang là `page_id`, flow mới phải rewrite identity sang customer trước khi gọi AI. Đây là điểm bắt buộc để không gom nhiều khách vào cùng một AI session của page.

Hiện tại `_process_normalized_message` ignore `bot_echo` rất sớm. Vì vậy ad card `ad-*` đang bị xử lý:

```text
status=ignored reason=pancake_echo_message message_kind=bot_echo
```

Flow mới cần chèn các nhánh `auto_consult_trigger` trước nhánh ignore echo.

`pancake_message_service` hiện đã có helper gửi reply/upload/send content ids và đã dùng mapping token:

```text
PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID
```

Khi bổ sung GET Conversation Messages API, service mới cũng phải dùng mapping token này và truyền param theo contract hiện tại của code là `page_access_token`.

## Phân loại actor đề xuất

Để giữ rule webhook đủ đơn giản nhưng vẫn tránh nhầm giữa khách, admin thật, automation và các trigger chủ động, phase này chốt gộp các actor Pancake thành 5 nhóm xử lý:

| Actor mới | Ý nghĩa ngắn gọn | Gộp từ actor chi tiết |
|---|---|---|
| `ad_card` | Message đại diện khách đến từ quảng cáo; dùng làm trigger auto consult. | Ad card |
| `page_comment_reply_notice` | System notice khi page phản hồi comment trên bài viết; dùng làm trigger auto consult nếu lấy được description bài viết. | Page comment reply notice |
| `customer_message` | Tin nhắn thật từ khách; actor duy nhất đi vào AI theo flow chat thường. | Customer message |
| `human_admin_message` | Tin page-side do người thật/admin gửi; lưu staff message và pause bot. | Human admin; Human admin private reply có post/comment context |
| `page_echo_or_automation` | Message page-side/system/automation không phải người thật; ignore AI và không pause. | Public API; Botcake automation; POS automation; Facebook notification notice; Facebook notification template; Page system/page echo unknown |

Thứ tự classify đề xuất:

```text
ad_card -> page_comment_reply_notice -> customer_message -> human_admin_message -> page_echo_or_automation
```

Lý do `ad_card` đứng đầu: ad card `ad-*` cũng là page-side echo, thường có `admin_name=null`, `uid=null`, `is_echo=true`. Nếu để nhánh echo chạy trước, `BE` sẽ ignore ad card như hiện tại và không thể hydrate description quảng cáo.

Lý do `page_comment_reply_notice` đứng ngay sau `ad_card`: notice này cũng là page-side echo, thường có `admin_name=null`, `uid=null`, attachment rỗng, nhưng có link `comment_id=` để truy ra bài viết nguồn. Nếu để nhánh echo chạy trước, `BE` sẽ ignore notice và không thể hydrate description bài viết.

Lý do `customer_message` đứng trước admin/page echo: customer thật có `from.id` khác `page_id`, dù cũng có thể `admin_name=null`, `uid=null`. Không được dùng riêng cặp null/null để kết luận message là system/ad.

Lý do tách `human_admin_message` khỏi `page_echo_or_automation`: `Botcake` và `POS` có `admin_name` nhưng là automation, không nên pause bot như admin thật. Rule admin thật nên dựa vào sender là page, có `admin_name`, có content, và `admin_name` không thuộc nhóm automation đã biết như `Public API`, `Botcake`, `POS`.

## Nhận diện trigger auto consult

Flow này chỉ nhận diện và xử lý 2 trigger chủ động:

- `ad_card`
- `page_comment_reply_notice`

Các page/status message khác vẫn đi theo rule actor hiện tại, không dùng làm trigger hydrate context và không tự gọi AI.

### Ad card

Điều kiện nhận diện chính:

- `event_type = messaging`
- `message_type = INBOX`
- `message_mid` bắt đầu bằng `ad-`
- Có `page_id`
- Có `pancake_conversation_id`

Không yêu cầu `text` vì ad card trong log thường có `text_present=false`.

Ad card có thể là echo/page-side message. Đây vẫn là tín hiệu hợp lệ để hydrate ad detail, nhưng không được gửi raw ad card cho AI.

### Page comment reply notice

`page_comment_reply_notice` là page-side system notice cho biết page đang phản hồi bình luận của người dùng về bài viết. Message này cũng là trigger hợp lệ để lấy description bài viết, bóc mã sản phẩm và tự tư vấn mẫu.

Không nhận diện actor này bằng một field duy nhất. Phải thỏa tổ hợp điều kiện:

```text
from.id == page_id
AND message/original_message contains "Bạn đang phản hồi bình luận"
AND message_tags[].link contains "comment_id="
AND attachments is empty
AND admin_name is null
AND uid is null
```

Ví dụ nội dung thường gặp:

```text
Bạn đang phản hồi bình luận của người dùng về bài viết trên Trang của mình. Xem bình luận...
```

Link trong `message_tags` thường có dạng:

```text
https://facebook.com/.../posts/.../?comment_id=...
```

Phân biệt với các actor khác:

- Không phải `ad_card` vì `message_mid` không bắt đầu bằng `ad-`, không có `attachments[].type=ad_click`, không có `ad_id`.
- Không phải `customer_message` vì sender là page.
- Không phải `human_admin_message` vì không có `admin_name` và không có `uid`.
- Không phải `facebook_notification_template` vì không có attachment template và không có `notification_messages_*`.

### Customer message thật

Customer message thật vẫn xử lý theo flow hiện tại:

- `message_from_id` là PSID/customer platform id, không phải page id.
- `page_customer_id` hoặc `conversation_customer_id` là customer id nội bộ ổn định.
- `is_echo=false`.
- Thường có `text` hoặc attachment do khách gửi.

Flow auto consult không yêu cầu customer message thật xuất hiện sau trigger.

## API Pancake cần gọi

Endpoint dùng để hydrate ad card hoặc page comment reply notice:

```text
GET https://pages.fm/api/public_api/v1/pages/{page_id}/conversations/{conversation_id}/messages
```

Param token theo code hiện tại:

```text
page_access_token={token}
```

Token lấy từ env mapping:

```text
PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID
```

Không dùng `PANCAKE_PAGE_ACCESS_TOKEN` chung.

Service đề xuất:

```python
async def fetch_pancake_conversation_messages(
    *,
    page_id: str,
    conversation_id: str,
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_seconds: Optional[float] = None,
) -> dict[str, Any]:
    ...
```

Với `ad_card`, response được dùng để tìm đúng ad message và lấy `attachments[].post_attachments[].description`.

Với `page_comment_reply_notice`, response được dùng để tìm lại notice/comment context theo `message_mid` và `comment_id`, sau đó lấy description bài viết liên quan.

Output thành công:

```json
{
  "ok": true,
  "status_code": 200,
  "response_data": {
    "messages": []
  }
}
```

Output lỗi giữ cùng style với các hàm Pancake hiện có:

```json
{
  "ok": false,
  "reason": "pancake_auth_error",
  "status_code": 403,
  "non_retryable": true
}
```

Không log token, không log URL đầy đủ có query token.

## Trích xuất ad detail

Sau khi fetch conversation messages, `BE` cần tìm đúng ad message theo webhook hiện tại:

- Tìm `messages[]` có `id == ad_message_mid`.
- Nếu không tìm thấy đúng `ad_message_mid`, không gọi AI và không gửi reply.

Ad message hợp lệ nên có attachment:

```json
{
  "id": "ad-2692195438413833912024387249670048017797536.0",
  "attachments": [
    {
      "type": "ad_click",
      "ad_id": "120243872496700480",
      "post_attachments": [
        {
          "description": "..."
        }
      ]
    }
  ]
}
```

Nguồn dữ liệu ưu tiên:

| Field | Nguồn ưu tiên | Fallback |
|---|---|---|
| `ad_id` | `messages[].attachments[].ad_id` | `ad_clicks[].ad_id` nếu cần |
| `description` | `messages[].attachments[].post_attachments[].description` | description đầu tiên khác rỗng trong ad attachment |
| `post_id` | `ad_clicks[]` match theo `ad_id` | `customers[].ad_clicks[]` match theo `ad_id` |

Nếu nhiều `post_attachments`, lấy `description` đầu tiên khác rỗng.

Nếu không có `description`, không gọi AI và không gửi reply. Trả reason `pancake_ad_description_missing`.

## Trích xuất page comment reply detail

Với `page_comment_reply_notice`, webhook ban đầu thường chỉ có text notice, `message_tags` chứa link comment, `admin_name=null`, `uid=null`, và `attachments=[]`. Vì vậy `BE` không parse mã sản phẩm trực tiếp từ system text.

Các bước hydrate:

1. Extract `comment_id` từ `message_tags[].link` có query `comment_id=`.
2. Gọi Pancake Conversation Messages API bằng `page_id` và `pancake_conversation_id`.
3. Tìm lại message notice theo `message_mid` nếu response có message tương ứng.
4. Dùng `comment_id` để tìm post/comment context trong response, ưu tiên message/attachment có link hoặc comment metadata match cùng `comment_id`.
5. Lấy description bài viết từ context tìm được.

Nguồn description ưu tiên:

| Field | Ghi chú |
|---|---|
| `messages[].attachments[].post_attachments[].description` | Nguồn ưu tiên nếu Pancake hydrate post attachment |
| `messages[].attachments[].name` | Fallback nếu `name` chứa caption/post content |
| `messages[].attachments[].description` | Fallback nếu attachment có description trực tiếp |

Không dùng text notice `Bạn đang phản hồi bình luận...` để bóc mã sản phẩm, vì đây là system text, không phải nội dung bài viết bán hàng.

Nếu không có `comment_id`, không gọi AI và không gửi reply. Trả reason `pancake_comment_id_missing`.

Nếu không tìm được post/comment context trong response Pancake, không gọi AI và không gửi reply. Trả reason `pancake_comment_post_context_missing`.

Nếu tìm được context nhưng không có description bài viết, không gọi AI và không gửi reply. Trả reason `pancake_comment_post_description_missing`.

## Bóc mã sản phẩm từ description

`product_codes` phải được bóc từ `description` bài viết/quảng cáo lấy từ trigger đã hydrate.

Mã sản phẩm Koisan hiện có dạng chữ cái in hoa kèm dãy số, ví dụ:

- `S7671263`
- `W2651713`

Regex phase đầu đề xuất:

```text
\b[A-Z]{1,3}\d{5,10}\b
```

Quy tắc:

- Normalize description về text thuần, trim whitespace.
- Giữ uppercase cho mã sản phẩm.
- Bỏ qua các chuỗi toàn số như `120243872496700480` để tránh nhầm `ad_id`.
- Nếu mã có khoảng trắng hoặc dấu gạch giữa chữ và số, phase đầu có thể chưa support, trừ khi business xác nhận dữ liệu thực tế có dạng đó.
- Nếu có nhiều mã, lấy tất cả mã hợp lệ theo thứ tự xuất hiện trong `description`.
- Dedupe mã trùng nhau nhưng giữ thứ tự xuất hiện đầu tiên.
- Log `product_code_count`.
- Nếu không có mã, không gọi AI và không gửi reply. Trả reason `pancake_product_code_missing`.

Ví dụ:

| Description | `product_codes` | Prompt |
|---|---|---|
| `Mẫu S7671263 đang về thêm màu mới` | `["S7671263"]` | `tư vấn mẫu S7671263 và gửi ảnh lookbook` |
| `Lookbook W2651713 cho tiệc tối` | `["W2651713"]` | `tư vấn mẫu W2651713 và gửi ảnh lookbook` |
| `S7671263 và W2651713 đều đang về thêm màu mới` | `["S7671263", "W2651713"]` | `tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook` |
| `Ưu đãi hôm nay 120243872496700480` | `null` | Không gọi AI |

## Prompt gửi AI

Prompt gửi AI phải có cấu trúc cố định:

```text
tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook
```

Ví dụ:

```text
tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook
```

Trong đó `product_codes_csv` là danh sách mã sản phẩm đã dedupe, nối bằng dấu phẩy và khoảng trắng theo thứ tự xuất hiện trong caption.

Không gửi toàn bộ `description` sang AI trong phase đầu, để tránh prompt dài, nhiễu giá/caption/CTA hoặc làm AI tư vấn sai trọng tâm. `description`, `ad_id`, `post_id` chỉ lưu vào `Message.meta` phục vụ audit/debug.

Nếu sau này cần thêm context bài viết/quảng cáo, nên mở rộng bằng field riêng có kiểm soát, không nối raw description vào prompt cố định này.

## Tạo normalized message tổng hợp

Vì `ad_card` và `page_comment_reply_notice` đều là page-side echo/system message, `BE` cần tạo một object normalized tổng hợp trước khi dùng flow AI hiện tại.

Object tổng hợp nên giữ metadata gửi Pancake từ webhook gốc, nhưng đổi identity sang customer thật:

```json
{
  "source": "pancake_auto_consult",
  "event_type": "messaging",
  "page_id": "109370365206868",
  "sender_id": "2a331718-36de-43cd-95df-e1f68d9d68f5",
  "sender_name": "Hoàng Dương Huyền",
  "recipient_id": "109370365206868",
  "message_mid": "ad-2692195438413833912024387249670048017797536.0",
  "message_type": "INBOX",
  "conversation_type": "INBOX",
  "is_echo": false,
  "text": "tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook",
  "pancake_conversation_id": "109370365206868_26921954384138339",
  "platform": "facebook",
  "conversation_customer_id": "2a331718-36de-43cd-95df-e1f68d9d68f5",
  "conversation_sender_id": "26921954384138339",
  "conversation_sender_name": "Hoàng Dương Huyền",
  "auto_consult": {
    "trigger_type": "ad_card",
    "trigger_message_mid": "ad-2692195438413833912024387249670048017797536.0",
    "ad_message_mid": "ad-2692195438413833912024387249670048017797536.0",
    "ad_id": "120243872496700480",
    "post_id": "109370365206868_953543847461970",
    "comment_id": null,
    "product_codes": ["S7671263", "W2651713"],
    "product_code_count": 2,
    "description_present": true
  }
}
```

Quy tắc:

- `sender_id` phải là customer id thật.
- `is_echo` của object tổng hợp phải là `false` để đi qua flow customer/AI.
- `text` là prompt cố định, không phải raw description.
- `message_mid` có thể dùng chính `trigger_message_mid` để chống trùng theo trigger.
- `meta.source` khi lưu DB nên là `pancake_auto_consult`, không dùng lẫn với customer message thật.
- `auto_consult.trigger_type` phải là `ad_card` hoặc `page_comment_reply_notice`.

## Idempotency và chống gửi trùng

Webhook Pancake có thể gửi lại cùng một trigger. Flow mới phải idempotent.

Khóa chống trùng đề xuất:

```text
page_id + pancake_conversation_id + trigger_type + trigger_message_mid
```

Trong DB, có thể lưu user message tổng hợp với:

```json
{
  "message_mid": "ad-2692195438413833912024387249670048017797536.0",
  "role": "user",
  "content": "tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook",
  "meta": {
    "source": "pancake_auto_consult",
    "trigger_type": "ad_card",
    "trigger_message_mid": "ad-2692195438413833912024387249670048017797536.0"
  }
}
```

Trước khi gọi AI, `BE` kiểm tra đã tồn tại message có:

- `message_mid == trigger_message_mid`
- `meta.source == pancake_auto_consult`
- `meta.trigger_type == trigger_type`

Nếu đã có, bỏ qua với reason `duplicate_auto_consult`.

## Quy tắc xử lý message trong webhook

Thứ tự rule trong `_process_normalized_message` nên theo đúng 5 actor đã chốt:

1. `ad_card`: nếu `message_mid` bắt đầu bằng `ad-`, xử lý auto consult.
2. `page_comment_reply_notice`: nếu match tổ hợp rule comment notice, xử lý auto consult.
3. `customer_message`: nếu sender không phải page, xử lý flow Pancake hiện tại.
4. `human_admin_message`: nếu sender là page, có `admin_name`, có content, và không phải automation đã biết, lưu staff message và pause bot.
5. `page_echo_or_automation`: các message page-side/system/automation còn lại, ignore AI và không pause.

Không được đặt nhánh `page_echo_or_automation` trước nhánh `ad_card` hoặc `page_comment_reply_notice`, vì cả hai trigger này đều đang bị classify là page echo/bot echo trong hệ thống hiện tại.

Không nên giữ rule rộng `page sender + admin_name != Public API + có content -> admin_message`, vì rule này kéo cả `POS` và `Botcake` vào admin takeover. Với phase này, `POS`, `Botcake`, `Public API`, notification template, notification notice và page echo unknown đều thuộc `page_echo_or_automation`.

## Gửi reply qua Pancake

Sau khi AI trả text thành công, `BE` gửi reply vào đúng conversation hiện tại:

```text
POST https://pages.fm/api/public_api/v1/pages/{page_id}/conversations/{pancake_conversation_id}/messages
```

Payload text:

```json
{
  "action": "reply_inbox",
  "message": "Dạ mẫu S7671263 bên em còn hàng..."
}
```

Nếu AI reply có Drive file/folder link, flow tách link, cache/download/upload/send `content_ids` giữ nguyên như tài liệu:

- [pancake-drive-link-image-reply.md](pancake-drive-link-image-reply.md)
- [pancake-drive-image-color-filter.md](pancake-drive-image-color-filter.md)

`action` phase đầu chỉ support `reply_inbox` cho `INBOX`. Nếu message type không phải `INBOX`, return `unsupported_reply_action`.

## Lưu message vào database

Flow mới không lưu ad/comment context để đợi customer message sau. Tuy nhiên vẫn cần lưu message tổng hợp và bot reply để audit, chống trùng và hiển thị lịch sử nội bộ.

User message tổng hợp:

```json
{
  "role": "user",
  "message_mid": "ad-2692195438413833912024387249670048017797536.0",
  "content": "tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook",
  "meta": {
    "source": "pancake_auto_consult",
    "page_id": "109370365206868",
    "pancake_conversation_id": "109370365206868_26921954384138339",
    "trigger_type": "ad_card",
    "trigger_message_mid": "ad-2692195438413833912024387249670048017797536.0",
    "ad_id": "120243872496700480",
    "post_id": "109370365206868_953543847461970",
    "comment_id": null,
    "product_codes": ["S7671263", "W2651713"],
    "product_code_count": 2,
    "description_present": true,
    "description_length": 240
  }
}
```

Bot message:

```json
{
  "role": "bot",
  "message_mid": null,
  "content": "Dạ mẫu S7671263 bên em còn hàng...",
  "meta": {
    "source": "pancake_auto_consult",
    "reply_to_message_mid": "ad-2692195438413833912024387249670048017797536.0",
    "pancake_send_result": {
      "ok": true,
      "status_code": 200
    },
    "auto_consult": {
      "trigger_type": "ad_card",
      "product_codes": ["S7671263", "W2651713"],
      "product_code_count": 2,
      "ad_id": "120243872496700480",
      "post_id": "109370365206868_953543847461970",
      "comment_id": null
    }
  }
}
```

Không lưu token vào `Message.meta`.

Không bắt buộc lưu raw full description. Nếu cần audit, ưu tiên lưu:

- `description_present`
- `description_length`
- `description_preview` đã truncate ngắn
- `product_codes`

## Lỗi và xử lý an toàn

BE nên xử lý lỗi theo hướng không gửi nhầm và không spam khách:

- Thiếu `page_id`: không gọi Pancake API, reason `missing_page_id`.
- Thiếu `pancake_conversation_id`: không gọi Pancake API, reason `missing_pancake_conversation_id`.
- Thiếu token theo page: không gọi Pancake API, reason `missing_pancake_page_access_token_for_page`.
- Pancake GET lỗi auth: không gọi AI, reason `pancake_auth_error`.
- Pancake GET lỗi 404: không gọi AI, reason `pancake_conversation_not_found`.
- Không tìm được ad message: không gọi AI, reason `pancake_ad_message_not_found`.
- Ad message không có `ad_click`: không gọi AI, reason `pancake_ad_click_missing`.
- Page comment reply notice thiếu `comment_id`: không gọi AI, reason `pancake_comment_id_missing`.
- Không tìm được post/comment context: không gọi AI, reason `pancake_comment_post_context_missing`.
- Không có description: không gọi AI, reason theo trigger, ví dụ `pancake_ad_description_missing` hoặc `pancake_comment_post_description_missing`.
- Không bóc được mã sản phẩm nào: không gọi AI, reason `pancake_product_code_missing`.
- Conversation đang bị admin pause: không gọi AI hoặc không gửi reply, reason `conversation_paused_by_admin`.
- AI init/call lỗi: không gửi Pancake reply, reason `ai_call_failed` hoặc `ai_init_failed`.
- AI response rỗng: không gửi Pancake reply, reason `ai_response_empty`.
- Pancake send reply lỗi: lưu bot/send result nếu phù hợp, reason theo response hiện có.
- Webhook duplicate: không gọi AI, reason `duplicate_auto_consult`.

Không gửi raw description hoặc raw product code trực tiếp cho khách.

## Logging

Nên bổ sung log theo các bước sau:

- `PANCAKE_AUTO_CONSULT_TRIGGER_DETECTED`
- `PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_START`
- `PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_OK`
- `PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_FAILED`
- `PANCAKE_AUTO_CONSULT_PRODUCT_CODE_EXTRACTED`
- `PANCAKE_AUTO_CONSULT_DUPLICATE_SKIPPED`
- `PANCAKE_AUTO_CONSULT_AI_START`
- `PANCAKE_AUTO_CONSULT_AI_OK`
- `PANCAKE_AUTO_CONSULT_AI_FAILED`
- `PANCAKE_AUTO_CONSULT_SEND_OK`
- `PANCAKE_AUTO_CONSULT_SEND_FAILED`
- `PANCAKE_AUTO_CONSULT_SUPPRESSED_BY_ADMIN_PAUSE`

Field nên log:

- `page_id`
- `pancake_conversation_id`
- `conversation_id` nội bộ nếu đã có
- `customer_id`
- `trigger_type`
- `trigger_message_mid`
- `ad_message_mid`
- `ad_id`
- `post_id`
- `comment_id`
- `description_present`
- `description_length`
- `product_codes`
- `product_code_count`
- `ai_user`
- `send_status_code`
- `reason`

Không log:

- `page_access_token`
- URL đầy đủ có query token
- Raw full `description` nếu quá dài hoặc chứa dữ liệu nhạy cảm

## Cấu hình backend

Không bắt buộc thêm env mới cho phase đầu nếu bật luôn theo code. Tuy nhiên để rollout an toàn, nên có feature flag:

- `PANCAKE_AUTO_CONSULT_ENABLED`: bật/tắt flow, mặc định `false` khi rollout production lần đầu.
- `PANCAKE_AUTO_CONSULT_PRODUCT_CODE_REGEX`: override regex bóc mã sản phẩm nếu business đổi format.

Các cấu hình hiện có dùng lại:

- `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`: mapping `page_id -> page_access_token`.
- `PANCAKE_API_TIMEOUT_SECONDS`: timeout gọi Pancake Public API.
- `PANCAKE_API_RETRY_ATTEMPTS`: số lần retry Pancake API.
- `PANCAKE_API_RETRY_BACKOFF_SECONDS`: backoff retry Pancake API.
- `PANCAKE_ADMIN_TAKEOVER_PAUSE_MINUTES`: thời gian pause bot khi admin tham gia.
- `FB_AI_CHAT_URL`: endpoint AI Agent hiện đang dùng chung.
- `FB_AI_BEARER_TOKEN`: bearer token gọi AI Agent.
- `FB_AI_RETRY_ATTEMPTS`: retry AI.
- `FB_AI_RETRY_BACKOFF_SECONDS`: backoff retry AI.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/services/pancake_message_service.py](../app/services/pancake_message_service.py)
- [app/core/config.py](../app/core/config.py)
- [tests/test_pancake_webhook.py](../tests/test_pancake_webhook.py)
- [tests/test_pancake_message_service.py](../tests/test_pancake_message_service.py)

Nếu tách helper riêng để dễ test:

- `app/services/pancake_auto_consult_service.py`
- `tests/test_pancake_auto_consult_service.py`

## Checklist implementation tổng hợp

Trạng thái hiện tại: Phase 0-4 đã hoàn tất implementation và test. Phase 5 đã hoàn tất logging, feature flag và test coverage; còn các bước quan sát log/metrics sau deploy trên page test hoặc production.

### Phase 0. Chốt contract và ranh giới

- [x] Chốt 2 trigger auto consult: `ad_card` và `page_comment_reply_notice`.
- [x] Chốt system ad message báo khách trả lời quảng cáo không chạy auto consult.
- [x] Chốt không lưu ad/comment context để chờ customer message.
- [x] Chốt auto prompt cố định là `tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook`.
- [x] Chốt không gửi raw description sang AI trong phase đầu.
- [x] Chốt không auto reply nếu conversation đang admin pause.
- [x] Chốt chỉ support `INBOX` trong phase đầu.

### Phase 1. Fetch và parse Pancake source detail

- [x] Thêm GET Conversation Messages API vào `pancake_message_service`.
- [x] Dùng `page_access_token` lookup theo `page_id`.
- [x] Không log token hoặc URL có token.
- [x] Tìm ad message theo `ad_message_mid`.
- [x] Extract attachment `type=ad_click`.
- [x] Extract `ad_id`.
- [x] Extract `description` từ `post_attachments[].description`.
- [x] Match `post_id` từ `ad_clicks` hoặc `customers[].ad_clicks`.
- [x] Nhận diện `page_comment_reply_notice` bằng tổ hợp rule đã chốt.
- [x] Extract `comment_id` từ `message_tags[].link`.
- [x] Tìm post/comment context match `comment_id`.
- [x] Extract description bài viết từ post/comment context.

### Phase 2. Bóc mã sản phẩm và tạo prompt

- [x] Normalize description text.
- [x] Bóc `product_codes` bằng regex chữ cái + số.
- [x] Bỏ qua chuỗi toàn số để tránh nhầm `ad_id`.
- [x] Nếu nhiều mã, lấy tất cả mã theo thứ tự xuất hiện, dedupe mã trùng và log count.
- [x] Nếu không có mã, không gọi AI.
- [x] Tạo prompt `tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook`.

### Phase 3. Tạo normalized message tổng hợp

- [x] Resolve customer id từ `conversation_customer_id`, `page_customer_id`, `conversation_sender_id`.
- [x] Không dùng `page_id` làm `sender_id` cho AI.
- [x] Set `is_echo=false` cho message tổng hợp.
- [x] Set `text` bằng prompt cố định.
- [x] Gắn `auto_consult` metadata gồm `trigger_type`, `trigger_message_mid`, `product_codes`, `ad_id` hoặc `comment_id` nếu có.
- [x] Lấy hoặc tạo `Conversation` nội bộ theo customer thật.
- [x] Lưu user message tổng hợp với `meta.source=pancake_auto_consult`.

### Phase 4. Gọi AI và gửi reply

- [x] Chạy duplicate guard theo `trigger_type + trigger_message_mid`.
- [x] Kiểm tra admin pause trước khi gọi AI.
- [x] Gọi init AI nếu conversation chưa initialized.
- [x] Gọi AI bằng prompt tổng hợp.
- [x] Xử lý quota/error hiện có.
- [x] Reuse flow chuẩn bị Drive image nếu AI trả Drive link.
- [x] Kiểm tra admin pause lần nữa trước khi gửi.
- [x] Gửi text reply qua Pancake đúng `page_id` và `pancake_conversation_id`.
- [x] Gửi image `content_ids` nếu flow Drive image tạo được ảnh.
- [x] Lưu bot message và send result.

### Phase 5. Logging, test và rollout

- [x] Bổ sung log trigger/fetch/extract/AI/send.
- [x] Bổ sung feature flag nếu rollout production cần tắt nhanh.
- [x] Test ad card happy path.
- [x] Test page comment reply notice happy path.
- [x] Test duplicate ad card không gửi 2 lần.
- [x] Test duplicate page comment reply notice không gửi 2 lần.
- [x] Test conversation đang pause thì không gọi AI/send.
- [x] Test không có description thì không gọi AI.
- [x] Test không có product code thì không gọi AI.
- [x] Chạy `pytest -q`.

### Rollout còn pending sau deploy

- [ ] Kiểm tra log trên một page test trước khi bật rộng.
- [ ] Theo dõi duplicate/skipped/error reason sau deploy.
- [ ] Theo dõi tỉ lệ `pancake_product_code_missing`.
- [ ] Theo dõi tỉ lệ `pancake_comment_post_context_missing`.

Task list chi tiết từng phase:

- [Phase 0. Chốt contract auto consult từ Pancake webhook](pancake-webhook-ad-message-task-list/phase-0.md)
- [Phase 1. Fetch và parse Pancake source detail](pancake-webhook-ad-message-task-list/phase-1.md)
- [Phase 2. Bóc mã sản phẩm và tạo prompt lookbook](pancake-webhook-ad-message-task-list/phase-2.md)
- [Phase 3. Tạo normalized message tổng hợp và lưu audit](pancake-webhook-ad-message-task-list/phase-3.md)
- [Phase 4. Gọi AI và gửi reply Pancake](pancake-webhook-ad-message-task-list/phase-4.md)
- [Phase 5. Logging, test và rollout](pancake-webhook-ad-message-task-list/phase-5.md)

## Test cần có khi implement

- Normalize ad card `ad-*` vẫn ok dù `text` rỗng và có attachment.
- `_is_pancake_ad_card_message` trả true với `message_mid=ad-...`.
- `_is_pancake_page_comment_reply_notice` trả true khi sender là page, text chứa `Bạn đang phản hồi bình luận`, `message_tags` có `comment_id=`, không có admin/uid và attachment rỗng.
- `_is_pancake_page_comment_reply_notice` trả false nếu thiếu `comment_id`, có attachment template, có admin/uid, hoặc sender không phải page.
- Fetch conversation messages dùng đúng `page_access_token` theo `page_id`.
- Fetch conversation messages thiếu token trả `missing_pancake_page_access_token_for_page`.
- Extract đúng ad message theo `ad_message_mid`.
- Extract `ad_id` từ `attachments[].ad_id`.
- Extract `description` đầu tiên khác rỗng từ `post_attachments`.
- Match `post_id` từ `ad_clicks` theo `ad_id`.
- Match `post_id` từ `customers[].ad_clicks` khi `ad_clicks` cấp cao thiếu dữ liệu.
- Extract `comment_id` từ `message_tags[].link`.
- Không parse product code trực tiếp từ text notice `Bạn đang phản hồi bình luận...`.
- Extract đúng post/comment context theo `comment_id`.
- Extract description bài viết từ context của `page_comment_reply_notice`.
- Không có `comment_id` thì return `pancake_comment_id_missing`.
- Không có post/comment context thì return `pancake_comment_post_context_missing`.
- Không có description bài viết thì return `pancake_comment_post_description_missing`.
- Parse `S7671263` từ description.
- Parse `W2651713` từ description.
- Không parse chuỗi toàn số như ad id.
- Nhiều mã trong description thì lấy tất cả mã theo thứ tự xuất hiện.
- Mã trùng trong description thì chỉ giữ một lần.
- Không có mã thì return `pancake_product_code_missing`.
- Tạo prompt đúng `tư vấn mẫu S7671263, W2651713 và gửi ảnh lookbook` khi có nhiều mã.
- Tạo normalized tổng hợp với `sender_id` là customer, không phải page.
- Auto consult từ ad card đi qua AI với `user=customer_id`.
- Auto consult từ page comment reply notice đi qua AI với `user=customer_id`.
- Duplicate `trigger_message_mid` không gọi AI lần hai.
- Conversation admin pause thì không gọi AI và không gửi Pancake.
- AI success thì gửi `send_pancake_reply` với đúng `page_id`, `pancake_conversation_id`, `action=reply_inbox`.
- Bot message lưu `meta.source=pancake_auto_consult`.
- Không lưu token vào `Message.meta`.

## Ghi chú production

- Feature flag nên bật theo từng page hoặc bật toàn cục sau khi test log ổn.
- Flow này có thể chủ động nhắn khách ngay khi trigger xuất hiện, nên duplicate guard rất quan trọng.
- Không dùng `sender_id` raw của trigger page-side để gọi AI vì raw value thường là `page_id`.
- Nếu sale/admin đang xử lý hội thoại, mặc định không auto reply để tránh đè người thật.
- Product code regex cần theo dữ liệu thực tế. Nếu caption có nhiều mã, business phải chốt chọn mã đầu tiên hay bỏ qua.
- Nếu Pancake không trả `description`, không nên tự đoán mã.
- Log nên đủ để biết fail ở trigger, Pancake API, parse description, parse product code, AI hay send reply.
- Khi AI reply có Drive link, flow ảnh hiện tại vẫn có thể chạy; cần đảm bảo metadata bot message phân biệt được nguồn `pancake_auto_consult`.
