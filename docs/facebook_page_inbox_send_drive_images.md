# Luồng gửi ảnh Google Drive qua Facebook Page Inbox

## Mục tiêu

Tài liệu này mô tả phương án mới cho luồng gửi ảnh sản phẩm từ Google Drive qua Facebook Page Inbox.

Điểm thay đổi chính: `BE` hiện tại là nơi điều phối toàn bộ phần Facebook và Google Drive. `Brain` / `AI Agent` chỉ trả dữ liệu hội thoại và link Drive liên quan đến sản phẩm. BE tự tách link Drive, lấy ảnh từ Google Drive, chọn danh sách ảnh cần gửi, rồi gửi text trước và ảnh sau cho khách qua Messenger Send API.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Brain` / `AI Agent`: service bên ngoài được cấu hình bằng `FB_AI_CHAT_URL`.
- `Drive folder link`: link Google Drive folder chứa ảnh sản phẩm.
- `Image URL`: URL ảnh đã chuyển từ file id Drive sang dạng `https://lh3.googleusercontent.com/d/{id}`.

## Luồng tổng thể

```text
Khách hàng nhắn tin vào Facebook Page
→ BE hiện tại nhận webhook message
→ BE gửi message/context sang Brain/AI Agent
→ BE nhận response/data từ Brain/AI Agent
→ BE phân tích response/data, nếu có link Drive thì tách ra
→ BE tách folder_id từ link Drive
→ BE call Google Drive API bằng folder_id và api_key
→ Google Drive API trả về danh sách file ảnh
→ BE lấy id từng ảnh
→ BE chuyển id ảnh thành URL dạng https://lh3.googleusercontent.com/d/{id}
→ BE chọn list ảnh 1-3 sản phẩm để gửi
→ BE gửi tin nhắn text trước cho khách
→ BE gửi ảnh ở tin nhắn thứ hai qua Messenger Send API
```

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận webhook message từ Facebook Page.
- Gửi message/context sang Brain/AI Agent qua `FB_AI_CHAT_URL`.
- Nhận response/data từ Brain/AI Agent.
- Tách Google Drive folder link từ response/data của Brain.
- Lấy `folder_id` từ từng Drive folder link.
- Gọi Google Drive API bằng `GOOGLE_DRIVE_API_KEY`.
- Lọc file ảnh hợp lệ.
- Chuyển Drive file id thành URL ảnh dạng `https://lh3.googleusercontent.com/d/{id}`.
- Chọn tối đa 1-3 ảnh sản phẩm để gửi cho khách.
- Tách text trả lời khỏi raw Drive link/raw image URL trước khi gửi.
- Gửi text trước, gửi ảnh sau qua Messenger Send API.
- Xử lý fallback khi gửi nhiều ảnh bị lỗi.

### Brain / AI Agent

Brain chịu trách nhiệm:

- Phân tích ngữ cảnh hội thoại và yêu cầu của khách.
- Trả câu trả lời text cho BE.
- Trả kèm Drive folder link liên quan đến sản phẩm nếu cần gửi ảnh.
- Có thể trả Drive link bằng field có cấu trúc hoặc nằm trong text, để BE tách ra.

Brain không còn là nơi gọi API riêng của BE để lấy danh sách ảnh Drive. BE tự xử lý Drive lookup sau khi nhận data từ Brain.

### Ngoài phạm vi phương án này

- Không để Brain chọn trực tiếp từng `imageUrl` từ Google Drive.
- Không yêu cầu Brain gọi endpoint `/drive-images` để lấy ảnh.
- Không đọc hoặc xử lý catalog sản phẩm trong tài liệu này, trừ khi luồng Brain hiện tại đã làm việc đó.
- Không download/rehost ảnh Drive ở BE trong phase đầu.
- Không thêm queue/outbox persistent cho media delivery trong phase đầu.

## Contract dữ liệu giữa BE và Brain

BE vẫn gọi Brain bằng luồng chat hiện tại qua `FB_AI_CHAT_URL`. Response từ Brain nên ưu tiên có cấu trúc rõ để BE dễ xử lý.

Response khuyến nghị:

```json
{
  "text": "Dạ mẫu này hiện có sẵn, em gửi anh/chị ảnh tham khảo ạ.",
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ"
  ],
  "image_limit": 3
}
```

Quy tắc:

- `text`: nội dung BE gửi cho khách ở tin nhắn đầu tiên.
- `drive_folder_urls`: danh sách Drive folder link sản phẩm, có thể rỗng hoặc không có.
- `image_limit`: tùy chọn, tối đa 3. Nếu không có thì BE dùng mặc định 3.

Để tương thích với response text thuần, BE cũng cần hỗ trợ trường hợp Brain trả về link Drive ngay trong nội dung text:

```text
Dạ mẫu này có ảnh ở đây ạ:
https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ
```

Khi đó BE:

- Tách Drive folder link khỏi text.
- Giữ phần text còn lại để gửi khách.
- Dùng Drive folder link để lấy ảnh.

## Google Drive image lookup

### Điều kiện cần có

- Drive folder ở trạng thái public hoặc API key có quyền đọc metadata file ảnh.
- BE có `GOOGLE_DRIVE_API_KEY` trong env.
- Google API key nên được restrict theo Google Drive API.
- Không hard-code API key trong source, tài liệu, log hoặc test fixture public.

### Tách folder id

Ví dụ Drive folder link:

```text
https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ
```

Folder id:

```text
16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ
```

BE cần hỗ trợ các biến thể phổ biến:

- URL có query string.
- URL có slash cuối.
- Nhiều Drive folder link trong cùng response Brain.
- Link không hợp lệ thì bỏ qua hoặc ghi lỗi ở mức folder, không làm hỏng toàn bộ tin nhắn.

### Gọi Google Drive API

Sử dụng Google Drive API v3:

```http
GET https://www.googleapis.com/drive/v3/files
```

Query lọc file ảnh:

```text
'FOLDER_ID' in parents
and trashed = false
and (mimeType = 'image/jpeg' or mimeType = 'image/png')
```

Fields tối thiểu:

```text
files(id,name,mimeType,size)
```

BE chỉ xử lý ảnh:

- `image/jpeg`
- `image/png`

BE bỏ qua:

- File thiếu `id`.
- File không phải ảnh.
- File đã bị xóa.
- Folder lỗi quyền, lỗi `403`, lỗi `404`, hoặc response không đọc được.

### Chuyển file id thành URL ảnh

Với mỗi file ảnh hợp lệ, BE lấy trường:

```text
id
```

Sau đó chuyển thành:

```text
https://lh3.googleusercontent.com/d/{id}
```

Ví dụ:

```json
{
  "id": "1tlmePpUN6ixklxwsWlHu1DsDH1v8q9rn",
  "name": "IMG_9184.JPG",
  "mimeType": "image/jpeg",
  "size": "190553"
}
```

URL ảnh:

```text
https://lh3.googleusercontent.com/d/1tlmePpUN6ixklxwsWlHu1DsDH1v8q9rn
```

## Chọn ảnh gửi cho khách

BE chỉ gửi tối đa 1-3 ảnh sản phẩm trong một lượt trả lời.

Quy tắc đề xuất cho phase đầu:

- Nếu Brain trả `image_limit`, BE dùng giá trị đó nhưng không vượt quá 3.
- Nếu Brain không trả `image_limit`, BE mặc định lấy tối đa 3 ảnh.
- Nếu có nhiều folder, BE ưu tiên folder theo thứ tự Brain trả về.
- Nếu một folder lỗi, BE thử folder tiếp theo.
- Nếu không lấy được ảnh nào, BE vẫn gửi text nếu có text.
- BE không gửi raw Drive folder link cho khách nếu link đó chỉ dùng để lấy ảnh.

Kết quả nội bộ sau khi BE xử lý:

```json
{
  "text": "Dạ mẫu này hiện có sẵn, em gửi anh/chị ảnh tham khảo ạ.",
  "images": [
    "https://lh3.googleusercontent.com/d/IMAGE_ID_1",
    "https://lh3.googleusercontent.com/d/IMAGE_ID_2",
    "https://lh3.googleusercontent.com/d/IMAGE_ID_3"
  ]
}
```

Object này là dữ liệu nội bộ để BE gửi Facebook, không phải contract bắt buộc Brain phải gọi.

## Gửi Facebook message

### Gửi text trước

BE gửi text bằng Messenger Send API:

```json
{
  "recipient": {
    "id": "PSID_KHACH_HANG"
  },
  "messaging_type": "RESPONSE",
  "message": {
    "text": "Dạ mẫu này hiện có sẵn, em gửi anh/chị ảnh tham khảo ạ."
  }
}
```

Nếu không có ảnh, flow kết thúc sau tin nhắn text.

Nếu không có text nhưng có ảnh, BE có thể gửi ảnh trực tiếp hoặc dùng text mặc định rất ngắn tùy behavior hiện tại của webhook.

### Gửi ảnh sau

Với nhiều ảnh, BE ưu tiên gửi bằng `message.attachments`:

```json
{
  "recipient": {
    "id": "PSID_KHACH_HANG"
  },
  "messaging_type": "RESPONSE",
  "message": {
    "attachments": [
      {
        "type": "image",
        "payload": {
          "url": "https://lh3.googleusercontent.com/d/IMAGE_ID_1"
        }
      },
      {
        "type": "image",
        "payload": {
          "url": "https://lh3.googleusercontent.com/d/IMAGE_ID_2"
        }
      }
    ]
  }
}
```

Với một ảnh hoặc khi bulk send lỗi, BE fallback sang `message.attachment`:

```json
{
  "recipient": {
    "id": "PSID_KHACH_HANG"
  },
  "messaging_type": "RESPONSE",
  "message": {
    "attachment": {
      "type": "image",
      "payload": {
        "url": "https://lh3.googleusercontent.com/d/IMAGE_ID_1"
      }
    }
  }
}
```

## Error handling

Luồng nên xử lý lỗi theo hướng không làm mất text trả lời:

- Brain lỗi: dùng behavior fallback hiện tại của BE.
- Brain trả text không có Drive link: gửi text như bình thường.
- Brain trả Drive link không hợp lệ: bỏ qua link, gửi text nếu có.
- Google Drive API lỗi toàn bộ: log lỗi rút gọn, gửi text nếu có.
- Một folder lỗi: thử folder khác nếu có.
- Một ảnh lỗi khi gửi Facebook: skip ảnh đó, tiếp tục ảnh khác.
- Bulk `message.attachments` lỗi: fallback gửi từng ảnh bằng `message.attachment`.

Không log:

- `GOOGLE_DRIVE_API_KEY`
- Facebook Page access token
- Bearer token gọi Brain
- Nội dung header auth nội bộ nếu còn endpoint cũ

Nên log:

- Số Drive link tìm thấy.
- Số folder xử lý thành công/thất bại.
- Số ảnh lấy được.
- Số ảnh chọn gửi.
- Kết quả gửi text.
- Kết quả gửi ảnh bulk/fallback.

## Cấu hình runtime

Các env liên quan:

- `FB_AI_CHAT_URL`: endpoint Brain/AI Agent.
- `FB_AI_BEARER_TOKEN`: token gọi Brain nếu luồng hiện tại yêu cầu.
- `GOOGLE_DRIVE_API_KEY`: API key để gọi Google Drive API.
- `FB_PAGE_ACCESS_TOKEN`: token gửi Messenger Send API.
- `FB_PAGE_ID`: Page id.
- `FB_WEBHOOK_VERIFY_TOKEN`: token verify webhook Facebook.

`BACKEND_INTERNAL_API_KEY` và endpoint `/drive-images` không còn là phần của luồng mới. Endpoint `/drive-images` cũ đã được remove khỏi router/code để tránh nhầm rằng Brain phải gọi BE để lấy ảnh.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/v1/facebook_webhook.py](../app/api/v1/facebook_webhook.py)
- [app/api/router_v1.py](../app/api/router_v1.py)
- [app/services/google_drive_image_service.py](../app/services/google_drive_image_service.py)
- [app/services/facebook_message_service.py](../app/services/facebook_message_service.py)
- [.env.example](../.env.example)
- [tests/test_google_drive_image_service.py](../tests/test_google_drive_image_service.py)
- [tests/test_facebook_message_service.py](../tests/test_facebook_message_service.py)
- [tests/test_facebook_webhook_forward.py](../tests/test_facebook_webhook_forward.py)

Các file endpoint/schema cũ `app/api/v1/drive_images.py` và `app/api/schemas/drive_images.py` đã được remove vì thuộc phương án cũ.

## Checklist implementation tổng hợp

### Phase 0. Chốt giải pháp mới

- [x] Chốt BE là nơi tự xử lý Drive link và gửi ảnh Facebook.
- [x] Chốt Brain chỉ trả text/data/link Drive cho BE.
- [x] Chốt không dùng Brain gọi endpoint `/drive-images` làm luồng chính.
- [x] Chốt BE gửi text trước, ảnh sau.
- [x] Chốt BE chỉ gửi 1-3 ảnh sản phẩm mỗi lượt.

### Phase 1. Chuẩn hóa Drive link và image lookup

- [x] Tách được Drive folder link từ structured field và plain text.
- [x] Tách được `folder_id` từ Drive folder URL.
- [x] Gọi Google Drive API bằng `GOOGLE_DRIVE_API_KEY`.
- [x] Lọc ảnh `image/jpeg` và `image/png`.
- [x] Convert file id thành `https://lh3.googleusercontent.com/d/{id}`.
- [x] Trả kết quả nội bộ theo folder để dễ log/debug.

### Phase 2. Tích hợp response Brain vào BE

- [x] BE nhận response/data từ Brain qua luồng chat hiện tại.
- [x] BE lấy `text` và `drive_folder_urls` nếu Brain trả structured payload.
- [x] BE fallback parse Drive link từ text thuần.
- [x] BE làm sạch text, bỏ raw Drive link trước khi gửi khách.
- [x] BE chọn tối đa 1-3 image URL từ kết quả Drive lookup.

### Phase 3. Gửi Facebook text và ảnh

- [x] BE gửi text trước bằng `message.text`.
- [x] BE gửi ảnh sau bằng `message.attachments` khi có nhiều ảnh.
- [x] BE gửi một ảnh bằng `message.attachment` nếu chỉ có một ảnh.
- [x] BE không gửi quá 3 ảnh theo phương án mới.
- [x] BE không gửi raw URL trong text nếu URL đã được gửi thành ảnh.

### Phase 4. Fallback và quan sát lỗi

- [x] Bulk image send lỗi thì fallback gửi từng ảnh.
- [x] Một ảnh lỗi thì skip ảnh đó, không làm fail toàn bộ flow.
- [x] Drive folder lỗi thì thử folder tiếp theo.
- [x] Log đủ count và reason rút gọn, không log secret.
- [x] Gửi text nếu có text dù Drive lookup hoặc media send lỗi.

### Phase 5. Test và rollout

- [x] Test parse Drive folder link từ structured payload.
- [x] Test parse Drive folder link từ plain text.
- [x] Test Google Drive response parsing và URL conversion.
- [x] Test chọn tối đa 1-3 ảnh.
- [x] Test text được gửi trước ảnh.
- [x] Test fallback bulk attachment sang single attachment.
- [x] Chạy `pytest -q`.
- [x] Rollout với Google Drive API key và Page token thật nhưng không commit secret.

## Tiêu chí hoàn thành

- BE nhận/gửi message Facebook bình thường như luồng hiện tại.
- BE gọi Brain và nhận data từ Brain bình thường.
- Nếu data từ Brain có Drive folder link, BE tự tách link và lấy ảnh.
- BE lấy được danh sách file ảnh từ Google Drive public folder.
- BE chuyển được Drive file id thành `https://lh3.googleusercontent.com/d/{id}`.
- BE chọn và gửi 1-3 ảnh sản phẩm cho khách.
- Khách nhận text trước, ảnh sau.
- Không còn phụ thuộc Brain gọi API riêng của BE để lấy ảnh Drive.
- Test chính pass bằng `pytest -q`.

## Rủi ro cần theo dõi

- Brain không trả Drive link đủ rõ để BE tách.
- Drive folder không public hoặc API key thiếu quyền.
- Google Drive trả metadata được nhưng Facebook không fetch được ảnh.
- Text sau khi bỏ Drive link bị trống hoặc cụt nghĩa.
- Gửi nhiều ảnh bằng `message.attachments` không ổn định theo Page/API version.
- Nếu phục hồi endpoint `/drive-images` cũ, team có thể nhầm đây là contract chính.

## Khuyến nghị

- Ưu tiên yêu cầu Brain trả structured field `drive_folder_urls` thay vì chỉ nhúng link trong text.
- Vẫn giữ parser text để tương thích nhanh.
- Giới hạn 1-3 ảnh ngay trong BE, không gửi toàn bộ folder ảnh.
- Gửi text trước ảnh để khách vẫn nhận được phản hồi nếu phần ảnh lỗi.
- Không phục hồi endpoint `/drive-images` cũ trừ khi có nhu cầu debug nội bộ rõ ràng và có auth riêng.
