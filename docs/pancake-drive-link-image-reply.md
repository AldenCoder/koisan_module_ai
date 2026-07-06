# Tích hợp Pancake gửi ảnh từ Google Drive file/folder link

## Mục tiêu

Tài liệu này mô tả phương án để `BE` xử lý trường hợp AI trả về text kèm Google Drive file link hoặc Drive folder link, sau đó gửi phản hồi cho khách qua Pancake theo đúng thứ tự: gửi text trước, rồi gửi ảnh ở tin nhắn thứ hai.

Điểm thay đổi chính: `BE` không gửi raw Drive link trực tiếp cho khách. Sau khi nhận response từ AI, `BE` tách Drive link khỏi text; nếu là folder link thì lookup danh sách ảnh trong folder để lấy `drive_file_id`; nếu là file link thì extract `drive_file_id` trực tiếp. Sau đó `BE` ưu tiên kiểm tra `content_id` trong cache, gửi thẳng bằng `content_id` nếu reuse đang bật, hoặc mới dùng file local/download Drive để upload ảnh lên Pancake lấy `content_id` mới.

Tài liệu bổ sung cho logic chọn ảnh theo màu từ tên file: [pancake-drive-image-color-filter.md](pancake-drive-image-color-filter.md).

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `AI Agent` / `Brain`: service tạo nội dung trả lời cho khách.
- `Drive file link`: link Google Drive public trỏ trực tiếp tới một file ảnh.
- `Drive folder link`: link Google Drive public trỏ tới một folder chứa ảnh; BE lookup và chọn ngẫu nhiên tối đa số ảnh đã cấu hình cho từng folder link.
- `drive_file_id`: id file Google Drive extract từ Drive file link.
- `drive_folder_id`: id folder Google Drive extract từ Drive folder link.
- `content_id`: id nội dung do Pancake trả về sau khi upload file.
- `pancake_conversation_id`: id hội thoại phía Pancake.

## Luồng tổng thể

Khách hàng nhắn tin vào kênh social đã nối Pancake.

`BE` nhận webhook Pancake, normalize message, lưu user message và gọi AI theo flow Pancake hiện tại.

AI trả về nội dung text có kèm một hoặc nhiều Drive file link public hoặc Drive folder link public.

`BE` tách Drive file/folder link khỏi text. Phần text còn lại được dùng làm tin nhắn phản hồi đầu tiên.

Với Drive file link, `BE` extract `drive_file_id` trực tiếp từ link. Với Drive folder link, `BE` extract `drive_folder_id`, gọi Google Drive API để lấy danh sách ảnh trong folder, rồi chọn ngẫu nhiên tối đa số ảnh cấu hình cho từng folder link thành danh sách `drive_file_id`.

`BE` kiểm tra cache `storage/pancake_image_cache.json`. Nếu cache đã có `content_id` và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, `BE` dùng luôn `content_id` đó để gửi ảnh, không cần kiểm tra file local và không download lại từ Drive.

Nếu chưa có `content_id` cache hợp lệ hoặc reuse đang tắt, `BE` mới kiểm tra file local trong `storage/pancake_images/{drive_file_id}.jpg`. Nếu file local đã tồn tại, `BE` bỏ qua bước download.

Nếu file local chưa tồn tại, `BE` convert Drive link thành direct download URL, download ảnh, lưu local, rồi update cache JSON.

Với ảnh chưa có `content_id` cache hợp lệ, `BE` upload từng file local lên Pancake qua endpoint `upload_contents`. Pancake trả về `content_id`; `BE` lưu `content_id` vào cache JSON và có thể xóa file local ngay khi reuse `content_id` đang bật.

`BE` gom danh sách `content_ids` và gửi tin nhắn ảnh vào hội thoại Pancake.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận response từ AI trong flow Pancake hiện có.
- Tách Drive file/folder link khỏi text trước khi gửi reply cho khách.
- Extract `drive_file_id` từ Drive file link.
- Extract `drive_folder_id` từ Drive folder link và lookup danh sách ảnh trong folder.
- Kiểm tra cache JSON và file ảnh local.
- Download ảnh từ Google Drive nếu chưa có `content_id` reusable và chưa có file local.
- Resize/compress ảnh về dưới ngưỡng Pancake trước khi lưu local.
- Lưu ảnh đã tối ưu vào `storage/pancake_images/{drive_file_id}.jpg`.
- Tái sử dụng `content_id` đã lưu nếu được bật cấu hình, hoặc upload file local lên Pancake để lấy `content_id`.
- Lưu `content_id` vào cache JSON.
- Gửi tin nhắn text trước, gửi tin nhắn ảnh sau.
- Log đủ thông tin để debug nhưng không log token hoặc dữ liệu nhạy cảm.

### Pancake

Pancake chịu trách nhiệm:

- Cung cấp Public API để upload file theo `page_id`.
- Trả về `content_id` sau khi upload thành công.
- Cung cấp Public API để gửi message có `content_ids` vào hội thoại.
- Trả response thành công hoặc lỗi rõ ràng để BE log và xử lý fallback.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Nhận text và context hội thoại đã được BE chuẩn hóa.
- Trả nội dung text cho khách.
- Trả Drive file link hoặc Drive folder link public nếu cần gửi ảnh sản phẩm.
- Không cần tự gọi Google Drive API.
- Không cần tự gọi Pancake Public API.
- Không cần biết `content_id` của Pancake.

### Ngoài phạm vi phương án này

- Không đổi flow Facebook webhook hiện tại.
- Không xử lý tin nhắn khách gửi vào là ảnh/sticker/file.
- Không yêu cầu AI upload ảnh hoặc tự gửi Pancake message.
- Không build màn hình quản lý cache ảnh.
- Không thêm queue/outbox persistent trong phase đầu nếu chưa cần.
- Không crawl folder đệ quy; chỉ lookup ảnh nằm trực tiếp trong Drive folder public.

## Contract dữ liệu từ AI

AI có thể trả response dạng text thuần có kèm Drive file link:

```text
Dạ mẫu này bên em còn hàng, em gửi ảnh anh/chị tham khảo ạ.
https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link
```

Sau khi parse, BE cần chuẩn bị object nội bộ tương đương:

```json
{
  "text": "Dạ mẫu này bên em còn hàng, em gửi ảnh anh/chị tham khảo ạ.",
  "drive_file_urls": [
    "https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link"
  ],
  "drive_folder_urls": []
}
```

AI cũng có thể trả Drive folder link public:

```text
Dạ trong file em chỉ thấy album sản phẩm thôi ạ, chưa có link riêng ảnh khách mặc.
Em gửi chị album để tham khảo form, chất và màu nhé:

https://drive.google.com/drive/folders/14zHh6CL5BXzrFNEgKCOj651gUWZM0IOb

Chị muốn em xem tiếp mẫu nào khác không ạ?
```

Sau khi parse, BE cần chuẩn bị object nội bộ tương đương:

```json
{
  "text": "Dạ trong file em chỉ thấy album sản phẩm thôi ạ, chưa có link riêng ảnh khách mặc.\nEm gửi chị album để tham khảo form, chất và màu nhé:\n\nChị muốn em xem tiếp mẫu nào khác không ạ?",
  "drive_file_urls": [],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/14zHh6CL5BXzrFNEgKCOj651gUWZM0IOb"
  ]
}
```

Quy tắc:

- `text`: nội dung gửi cho khách ở tin nhắn đầu tiên.
- `drive_file_urls`: danh sách Drive file link public đã tách khỏi text.
- `drive_folder_urls`: danh sách Drive folder link public đã tách khỏi text.
- Nếu AI trả nhiều Drive file link, BE giữ thứ tự xuất hiện trong response.
- Nếu AI trả Drive folder link, BE lookup danh sách ảnh trong từng folder, chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh cho mỗi folder link.
- Nếu AI trả nhiều Drive folder link, BE xử lý hết các folder link theo thứ tự xuất hiện. Ví dụ `PANCAKE_INBOX_IMAGE_MAX_COUNT=3 / PANCAKE_COMMENT_IMAGE_MAX_COUNT=3` và AI trả 2 folder link thì BE có thể gửi tối đa 6 ảnh từ folder, mỗi folder tối đa 3 ảnh.
- Nếu response không có Drive file/folder link, flow Pancake text reply hiện tại không đổi.
- Nếu text chỉ còn rỗng sau khi tách link, BE chỉ gửi ảnh nếu business chấp nhận gửi ảnh không kèm ngữ cảnh.

## Tách Drive file id

Drive file link mẫu:

```text
https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link
```

`drive_file_id`:

```text
1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk
```

BE nên hỗ trợ các biến thể URL phổ biến:

| Dạng URL | Cách lấy id |
|---|---|
| `https://drive.google.com/file/d/{drive_file_id}/view?usp=drive_link` | Lấy segment sau `/file/d/` |
| `https://drive.google.com/file/d/{drive_file_id}/view` | Lấy segment sau `/file/d/` |
| `https://drive.google.com/uc?export=download&id={drive_file_id}` | Lấy query param `id` |
| `https://drive.google.com/open?id={drive_file_id}` | Lấy query param `id` |

URL không thuộc `drive.google.com` hoặc không extract được file id thì bỏ qua và log reason. Một link lỗi không được làm hỏng toàn bộ reply.

## Tách Drive folder id và lookup ảnh

Drive folder link mẫu:

```text
https://drive.google.com/drive/folders/14zHh6CL5BXzrFNEgKCOj651gUWZM0IOb
```

`drive_folder_id`:

```text
14zHh6CL5BXzrFNEgKCOj651gUWZM0IOb
```

BE lookup ảnh trong folder bằng Google Drive API hiện có:

```text
GET https://www.googleapis.com/drive/v3/files
```

Query cần lọc:

```text
'{drive_folder_id}' in parents and trashed=false and (mimeType='image/jpeg' or mimeType='image/png')
```

Quy tắc:

- Chỉ lấy ảnh nằm trực tiếp trong folder, không crawl folder con.
- Chỉ nhận `image/jpeg` và `image/png`.
- Dedupe theo `drive_file_id`.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` là giới hạn ảnh cho mỗi Drive folder link, mặc định 3.
- Với từng folder, BE chọn ngẫu nhiên từ 1 đến `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh nếu folder có ảnh hợp lệ; folder có ít hơn giới hạn thì lấy số ảnh hợp lệ hiện có.
- Tổng số ảnh trong một reply có thể lớn hơn 3 nếu AI trả nhiều Drive folder link. Ví dụ 2 folder link hợp lệ có thể tạo tối đa 6 ảnh.
- Drive file link trực tiếp không bị tính vào giới hạn theo folder; mỗi file link hợp lệ tương ứng một ảnh sau khi dedupe.
- Nếu folder lookup lỗi, BE vẫn gửi text nếu text hợp lệ, đồng thời log reason ở `pancake_drive_reply.errors`.
- Không log `GOOGLE_DRIVE_API_KEY`; request Google Drive phải suppress log URL đầy đủ có query `key`.

Sau khi lookup folder thành công, mỗi image id được chuyển thành file link nội bộ dạng:

```text
https://drive.google.com/file/d/{drive_file_id}/view
```

Các bước cache/download/upload phía sau dùng chung flow Drive file link.

## Cache và local storage

Cache JSON dùng để lưu metadata download/upload:

```text
storage/pancake_image_cache.json
```

File ảnh local lưu theo `drive_file_id`:

```text
storage/pancake_images/{drive_file_id}.jpg
```

Cache đề xuất:

```json
{
  "version": 1,
  "items": {
    "1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk": {
      "drive_file_id": "1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk",
      "direct_download_url": "https://drive.google.com/uc?export=download&id=1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk",
      "local_path": "storage/pancake_images/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk.jpg",
      "content_id": "CONTENT_ID_1"
    }
  }
}
```

Quy tắc cache:

- Nếu `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true` và cache đã có `content_id`, BE bỏ qua kiểm tra file local, bỏ qua download Drive và gửi thẳng bằng `content_id`.
- Nếu chưa có `content_id` reusable nhưng có file local `storage/pancake_images/{drive_file_id}.jpg`, BE bỏ qua download.
- Nếu chưa có `content_id` reusable và chưa có file local, BE download ảnh rồi lưu vào đúng path local.
- Trước khi lưu local, BE resize/compress ảnh về dưới `PANCAKE_IMAGE_STORAGE_MAX_BYTES`, mặc định `500000` bytes, để file trong `storage/pancake_images/` luôn sẵn sàng upload lên Pancake.
- Nếu file local cũ đã tồn tại nhưng vượt `PANCAKE_IMAGE_STORAGE_MAX_BYTES`, BE tối ưu lại file đó ngay trong bước cache hit trước khi upload.
- Nếu file local cũ vượt ngưỡng nhưng không đọc/tối ưu được, BE bỏ file local đó và download lại từ Drive.
- Sau khi download thành công, BE update cache JSON.
- Sau khi upload thành công, BE lưu `content_id` vào cache JSON.
- Sau khi upload thành công và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, BE xóa file local trong `storage/pancake_images/` để giảm dung lượng server. Cache JSON vẫn là nguồn kiểm tra chính cho ảnh đã có `content_id`.
- Nếu cache đã có `content_id` và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, BE bỏ qua upload và dùng luôn `content_id` đã lưu để gửi image message.
- Cache JSON cần được ghi bằng atomic write để tránh hỏng file khi nhiều webhook chạy cùng lúc.
- `storage/pancake_image_cache.json` và `storage/pancake_images/` không nên commit vào git.

Ghi chú về `content_id`: `PANCAKE_REUSE_UPLOADED_CONTENT_ID` mặc định bật để tránh upload lại ảnh đã có `content_id`. Khi reuse bật, backend có thể xóa ảnh local sau upload lần đầu; lần sau chỉ cần cache JSON còn `content_id` là đủ gửi ảnh. Nếu phát hiện Pancake làm `content_id` hết hạn hoặc không tái sử dụng được, có thể tắt cấu hình này để backend dùng file local nếu còn, hoặc download lại từ Drive rồi upload và cập nhật `content_id` mới vào cache.

## Download ảnh từ Google Drive

Nếu chưa có `content_id` reusable và chưa có file local, BE convert Drive file link thành direct download URL:

```text
https://drive.google.com/uc?export=download&id={drive_file_id}
```

Ví dụ:

```text
https://drive.google.com/uc?export=download&id=1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk
```

Sau đó BE download ảnh, resize/compress nếu cần, rồi lưu local:

```text
storage/pancake_images/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk.jpg
```

File ghi vào `storage/pancake_images/` phải nhỏ hơn hoặc bằng `PANCAKE_IMAGE_STORAGE_MAX_BYTES`, mặc định `500000` bytes. Nếu ảnh tải về là PNG hoặc JPEG lớn hơn ngưỡng này, BE chuẩn hóa về JPEG, giảm quality/kích thước và chỉ ghi file đã tối ưu vào local storage. Nhờ vậy bước upload Pancake phía sau không cần xử lý resize nữa.

BE chỉ nên chấp nhận response là ảnh hợp lệ, ví dụ:

- `image/jpeg`
- `image/png`

Google Drive có thể trả `303 See Other` trước khi trả file ảnh thật. BE phải download với `follow_redirects=True`; nếu không, response redirect dễ bị đọc như non-image và rơi vào lỗi `drive_download_invalid_content_type`.

Nếu file Drive public yêu cầu thêm confirm token của Google Drive, BE cần xử lý rõ ở service download hoặc log lỗi có reason riêng. Phase đầu có thể giới hạn ở public image link download được trực tiếp.

## Reuse hoặc upload ảnh lên Pancake

Trước khi download hoặc upload file local, BE kiểm tra metadata cache của ảnh theo `drive_file_id`. Nếu cache đã có `content_id` và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, BE đưa `content_id` đó vào danh sách gửi ảnh, không gọi endpoint `upload_contents`, và không cần file trong `storage/pancake_images/`.

Nếu chưa có `content_id`, hoặc `PANCAKE_REUSE_UPLOADED_CONTENT_ID=false`, BE mới upload file local lên Pancake:

Với mỗi file local cần gửi, BE upload lên Pancake:

```http
POST /api/public_api/v1/pages/{page_id}/upload_contents
Content-Type: multipart/form-data
```

Form data:

```text
file=@storage/pancake_images/{drive_file_id}.jpg
```

Endpoint đầy đủ theo base URL đang dùng trong service Pancake:

```text
https://pages.fm/api/public_api/v1/pages/{page_id}/upload_contents
```

Token vẫn truyền theo contract Pancake hiện tại, thường là `page_access_token`. Token phải lấy từ biến môi trường hoặc hệ thống cấu hình an toàn, không hard-code trong source và không log ra.

Response thành công cần lấy được `content_id`:

```json
{
  "id": "CONTENT_ID_1",
  "type": "PHOTO",
  "success": true
}
```

Nếu response Pancake bọc `content_id` trong field khác, service Pancake cần normalize response về một object nội bộ ổn định trước khi trả cho webhook flow.

## API gửi tin nhắn phản hồi khách

Endpoint Pancake Public API dùng để gửi reply:

```text
POST https://pages.fm/api/public_api/v1/pages/{page_id}/conversations/{conversation_id}/messages
```

Thông tin tối thiểu để gửi reply:

| Thông tin | Nguồn |
|---|---|
| `page_id` | Object Pancake đã normalize |
| `conversation_id` phía Pancake | `pancake_conversation_id` |
| `action` | `reply_inbox` cho inbox |
| `message` | Text đã tách raw Drive link |
| `content_ids` | Danh sách id sau khi upload ảnh lên Pancake |

### Tin nhắn 1: text

BE gửi text trước:

```json
{
  "action": "reply_inbox",
  "message": "Dạ mẫu này bên em còn hàng, em gửi ảnh anh/chị tham khảo ạ."
}
```

### Tin nhắn 2: ảnh

BE gom các `content_id` upload thành công:

```json
[
  "CONTENT_ID_1",
  "CONTENT_ID_2"
]
```

Sau đó gửi message ảnh:

```json
{
  "action": "reply_inbox",
  "content_ids": [
    "CONTENT_ID_1",
    "CONTENT_ID_2"
  ]
}
```

Response Pancake thành công:

```json
{
  "success": true
}
```

Nếu không có `content_ids` hợp lệ, BE không gọi tin nhắn ảnh.

Nếu AI trả nhiều Drive folder link, BE vẫn gom toàn bộ ảnh đã chọn vào cùng một lần gửi `content_ids` sau tin nhắn text. Ví dụ 2 folder link, mỗi folder chọn được 3 ảnh, payload ảnh sẽ có 6 `content_ids`.

### Xác minh Pancake echo và retry ảnh

HTTP 200 từ endpoint gửi `content_ids` chỉ xác nhận Pancake đã nhận request API, chưa đủ để kết luận ảnh đã thật sự xuất hiện trong hội thoại. Sau mỗi lần gửi image message, BE cần xác minh bằng webhook echo từ Pancake.

Một lần gửi ảnh được coi là thành công thật khi BE quan sát được webhook message thỏa các điều kiện:

- Cùng `page_id`.
- Cùng `pancake_conversation_id`.
- `is_echo=true`.
- `message_from_admin_name="Public API"`.
- `attachment_count > 0`.
- Message echo xuất hiện trong cửa sổ verify của lần gửi ảnh.

Cửa sổ verify bắt đầu ngay trước khi BE gọi API gửi `content_ids`, không chỉ sau khi log `PANCAKE_DRIVE_IMAGE_SEND_OK`. Lý do: Pancake có thể tạo message và gọi webhook gần như đồng thời với HTTP response, nên webhook echo đôi khi có thể được ghi log trước hoặc sát dòng HTTP 200.

Thời gian chờ echo cho mỗi delivery attempt là `1` giây. Log thực tế cho các case ảnh xuất hiện cho thấy độ trễ từ `PANCAKE_DRIVE_IMAGE_SEND_OK` tới webhook echo `Public API` có `attachment_count > 0` tối đa khoảng `0.488` giây, nên `1` giây đủ cho hotfix này.

Retry delivery dùng tối đa 3 attempt:

| Attempt | Hành vi |
|---|---|
| 1 | Dùng flow hiện tại: reuse/upload để có danh sách `content_ids`, rồi gửi message ảnh. |
| 2 | Nếu attempt 1 nhận HTTP 200 nhưng không thấy echo attachment trong 1 giây, resend đúng danh sách `content_ids` đã có. Không download lại Drive, không upload lại Pancake. |
| 3 | Nếu attempt 2 vẫn không thấy echo attachment trong 1 giây, resend đúng danh sách `content_ids` một lần cuối. Không download lại Drive, không upload lại Pancake. |

Trước mỗi attempt retry, BE cần check lại trạng thái echo đã quan sát được cho cùng conversation để tránh gửi trùng khi webhook echo vừa đến muộn trong khoảng chuyển giữa hai attempt.

Hotfix này không thay đổi chính sách local image cleanup. Nếu `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, BE vẫn xóa file local ngay sau khi upload thành công như flow hiện tại. Retry chỉ resend lại `content_ids` đã gom được, nên không phụ thuộc vào file local.

Nếu cả 3 attempt đều nhận HTTP 200 nhưng không có echo attachment, BE log trạng thái gửi ảnh là chưa verified, giữ text reply đã gửi trước đó, và không tiếp tục retry thêm trong request hiện tại.

## Object nội bộ sau khi chuẩn bị reply

Object nội bộ sau khi BE parse response AI nên có dạng ổn định để dễ test:

| Field | Ý nghĩa |
|---|---|
| `text` | Text gửi ở tin nhắn đầu tiên, đã tách raw Drive link |
| `drive_file_urls` | Danh sách Drive file link extract từ AI response |
| `drive_file_ids` | Danh sách id extract được từ `drive_file_urls` |
| `drive_folder_urls` | Danh sách Drive folder link extract từ AI response |
| `drive_folder_results` | Kết quả lookup folder rút gọn để debug |
| `drive_folder_error_count` | Số folder lookup lỗi |
| `image_limit` | Số ảnh tối đa được chọn cho mỗi Drive folder link |
| `content_ids` | Danh sách content id sau khi upload thành công lên Pancake |
| `errors` | Danh sách lỗi cấp link/file/upload để log và debug |

Ví dụ:

```json
{
  "text": "Dạ mẫu này bên em còn hàng, em gửi ảnh anh/chị tham khảo ạ.",
  "drive_file_urls": [
    "https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link"
  ],
  "drive_file_ids": [
    "1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk"
  ],
  "drive_folder_urls": [],
  "drive_folder_results": [],
  "drive_folder_error_count": 0,
  "image_limit": 3,
  "content_ids": [
    "CONTENT_ID_1"
  ],
  "errors": []
}
```

## Quy tắc xử lý message

BE nên áp dụng các rule sau:

- Chỉ xử lý Drive image reply sau khi AI trả response thành công.
- Không thay đổi rule hiện tại về duplicate message, bot pause, admin takeover và text-only customer message.
- Raw Drive link chỉ được tách khỏi bot reply text, không tách khỏi user message đã lưu.
- Nếu không có Drive file/folder link, gọi Pancake text reply như flow hiện tại.
- Nếu có Drive file/folder link và có text, gửi text trước.
- Nếu có Drive folder link, lookup folder thành danh sách `drive_file_id` trước khi cache/download.
- Nếu upload được ít nhất một ảnh, gửi image message sau text.
- Sau khi gửi image message bằng `content_ids`, xác minh webhook echo `Public API` có `attachment_count > 0` trong 1 giây.
- Nếu gửi `content_ids` nhận HTTP 200 nhưng không có echo attachment, retry tối đa 2 lần nữa bằng chính danh sách `content_ids` đã có.
- Nếu upload/download ảnh lỗi hết, chỉ gửi text nếu text hợp lệ.
- Giới hạn số ảnh mỗi Drive folder link, mặc định 3; tổng số ảnh có thể lớn hơn 3 khi AI trả nhiều folder link.
- Ảnh trong mỗi Drive folder được chọn ngẫu nhiên để tránh luôn gửi các ảnh đầu tiên của folder.
- Không gửi `content_ids` rỗng.
- Không lưu token hoặc direct auth data vào `Message.meta`.

## Lỗi và fallback

BE nên xử lý lỗi theo hướng không làm mất text reply:

- AI có text nhưng Drive link lỗi: gửi text, log image error.
- Extract `drive_file_id` lỗi: bỏ qua link đó.
- Download lỗi: bỏ qua ảnh đó, tiếp tục ảnh khác.
- Upload lỗi: bỏ qua `content_id` đó, tiếp tục ảnh khác.
- Tất cả ảnh lỗi: không gửi image message.
- Text rỗng nhưng có ảnh hợp lệ: chỉ gửi ảnh nếu business chấp nhận, nếu không thì log và bỏ qua để tránh gửi ảnh không có ngữ cảnh.
- Pancake gửi image message lỗi HTTP: log response rút gọn, không log token, giữ retry HTTP hiện tại của service.
- Pancake gửi image message HTTP 200 nhưng không có webhook echo attachment trong 1 giây: resend cùng `content_ids`, tối đa 3 delivery attempt tổng cộng.

Nếu đã gửi text thành công nhưng gửi ảnh lỗi, khách vẫn nhận được câu trả lời text. Đây là behavior chấp nhận được cho phase đầu.

## Lưu message vào database

User message vẫn lưu như flow Pancake hiện tại.

Bot text message nên lưu như hiện tại với `content` là text đã tách raw Drive link.

Với image message, có hai hướng:

- Phase đầu: lưu `content_ids`, `drive_file_ids`, `drive_file_urls` và kết quả gửi ảnh trong `meta` của bot text message.
- Nếu cần lịch sử rõ hơn: lưu thêm một bot message riêng cho image send, `content` có thể là chuỗi rỗng hoặc mô tả nội bộ, `meta` chứa `content_ids` và response Pancake rút gọn.

Không lưu file binary vào database.

## Cấu hình backend

Các cấu hình nên bổ sung:

- `GOOGLE_DRIVE_API_KEY`: dùng khi AI trả Drive folder link để lookup danh sách ảnh trong folder.
- `PANCAKE_IMAGE_CACHE_PATH`: mặc định `storage/pancake_image_cache.json`.
- `PANCAKE_IMAGE_STORAGE_DIR`: mặc định `storage/pancake_images`.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`: số ảnh tối đa chọn ngẫu nhiên cho mỗi Drive folder link, mặc định 3. Ví dụ AI trả 2 folder link thì có thể gửi tối đa 6 ảnh từ folder.
- `PANCAKE_IMAGE_DOWNLOAD_TIMEOUT_SECONDS`: timeout download ảnh Drive.
- `PANCAKE_IMAGE_UPLOAD_TIMEOUT_SECONDS`: timeout upload ảnh Pancake.
- `PANCAKE_IMAGE_MAX_BYTES`: giới hạn kích thước ảnh tải về.
- `PANCAKE_IMAGE_STORAGE_MAX_BYTES`: giới hạn kích thước file ảnh lưu local để upload Pancake, mặc định `500000`.
- `PANCAKE_REUSE_UPLOADED_CONTENT_ID`: bật/tắt việc dùng lại `content_id` đã lưu trong cache, mặc định `true`; đặt `false` nếu cần upload lại từ file local.

Các cấu hình Pancake hiện có như `PANCAKE_PAGE_ACCESS_TOKEN`, base URL, timeout và retry vẫn dùng chung với service gửi reply hiện tại.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/services/pancake_message_service.py](../app/services/pancake_message_service.py)
- [app/core/config.py](../app/core/config.py)

Nếu tách service/helper riêng để dễ test:

- `app/services/pancake_drive_image_service.py`

Nếu cần đảm bảo storage không bị commit:

- [.gitignore](../.gitignore)

## Checklist implementation tổng hợp

### Phase 0. Chốt giải pháp

- [x] Chốt BE là nơi xử lý Drive file/folder link sau khi AI trả response, không để AI gọi Google Drive hoặc Pancake API.
- [x] Chốt reply Pancake gồm hai bước: gửi text đã tách raw Drive link trước, rồi gửi ảnh bằng `content_ids` sau.
- [x] Chốt phase đầu xử lý Drive file link public và Drive folder link public.
- [x] Chốt giới hạn số ảnh theo từng Drive folder link, mặc định 3 ảnh/folder.
- [x] Chốt không thay đổi rule hiện tại về duplicate message, bot pause, admin takeover và text-only customer message.

### Phase 1. Tách Drive link và chuẩn bị reply

- [x] Tách Drive file link khỏi AI text và giữ lại text sạch.
- [x] Tách Drive folder link khỏi AI text và giữ lại text sạch.
- [x] Extract `drive_file_id` từ các dạng Drive URL đã mô tả.
- [x] Extract `drive_folder_id` và chọn ngẫu nhiên tối đa 3 ảnh cho mỗi folder link.
- [x] Bỏ qua link không hợp lệ và log reason ở cấp link.
- [x] Chuẩn bị object nội bộ có `text`, `drive_file_urls`, `drive_file_ids`, `drive_folder_urls`, `drive_folder_results`, `image_limit`, `content_ids` và `errors`.
- [x] Nếu không có Drive link, giữ nguyên flow Pancake text reply hiện tại.

### Phase 2. Cache local và download ảnh

- [x] Đọc cache JSON từ `storage/pancake_image_cache.json`.
- [x] Nếu reuse bật và cache đã có `content_id`, bỏ qua download/local file.
- [x] Kiểm tra file local tại `storage/pancake_images/{drive_file_id}.jpg`.
- [x] Nếu có file local, bỏ qua download.
- [x] Nếu chưa có file local, convert sang direct download URL và download ảnh.
- [x] Download Drive với `follow_redirects=True` để xử lý response `303 See Other`.
- [x] Resize/compress ảnh về dưới `PANCAKE_IMAGE_STORAGE_MAX_BYTES` trước khi lưu local.
- [x] Tối ưu lại file local cũ nếu cache hit nhưng file đang vượt ngưỡng Pancake.
- [x] Lưu ảnh đã tối ưu vào `storage/pancake_images/{drive_file_id}.jpg`.
- [x] Update cache JSON sau khi download thành công.
- [x] Ghi cache bằng atomic write hoặc lock để tránh hỏng file khi webhook chạy đồng thời.

### Phase 3. Upload ảnh và gửi Pancake message

- [x] Upload file local lên endpoint `/pages/{page_id}/upload_contents`.
- [x] Parse response upload để lấy `content_id`.
- [x] Lưu `content_id` vào cache JSON sau khi upload thành công.
- [x] Xóa file local sau khi upload thành công nếu `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`.
- [x] Reuse `content_id` đã lưu trong cache khi `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`.
- [x] Bỏ qua upload nếu ảnh đã có `content_id` cache hợp lệ và reuse đang bật.
- [x] Gom danh sách `content_ids` upload thành công.
- [x] Gửi text message trước nếu text hợp lệ.
- [x] Gửi image message sau bằng body có `content_ids`.
- [x] Không gửi image message nếu `content_ids` rỗng.

### Phase 4. Lưu message, fallback và logging

- [x] Lưu bot text message với `content` là text đã tách raw Drive link.
- [x] Lưu `content_ids`, `drive_file_ids`, `drive_file_urls` và response Pancake rút gọn vào `meta` theo hướng đã chọn.
- [x] Nếu download/upload ảnh lỗi hết, vẫn gửi text nếu text hợp lệ.
- [x] Nếu một số ảnh lỗi, tiếp tục gửi các ảnh thành công.
- [x] Không log token hoặc direct auth data.
- [x] Log đủ `drive_file_id`, `page_id`, `conversation_id`, `content_id` và reason lỗi.

### Phase 5. Test và rollout

- [x] Test extract `drive_file_id` từ URL `/file/d/{id}/view`.
- [x] Test extract `drive_file_id` từ URL `uc?export=download&id={id}`.
- [x] Test tách Drive file link khỏi AI text và giữ lại text sạch.
- [x] Test tách Drive folder link khỏi AI text và lookup ảnh trong folder.
- [x] Test không đổi flow khi AI response không có Drive link.
- [x] Test cache hit có file local thì không download lại.
- [x] Test cache có `content_id` và reuse bật thì không cần file local, không download Drive.
- [x] Test cache có `content_id` nhưng reuse tắt thì vẫn chuẩn bị file local để upload lại.
- [x] Test cache miss thì download ảnh và update cache JSON.
- [x] Test download Drive dùng `follow_redirects=True`.
- [x] Test upload multipart lên Pancake đúng endpoint `upload_contents`.
- [x] Test lưu `content_id` vào cache sau upload thành công.
- [x] Test xóa file local sau upload thành công khi reuse bật.
- [x] Test reuse `content_id` đã cache thì không upload lại.
- [x] Test tắt reuse thì vẫn upload lại và cập nhật `content_id` mới.
- [x] Test gửi image message với body có `content_ids`.
- [x] Test nếu download/upload lỗi một ảnh, các ảnh còn lại vẫn được gửi.
- [x] Test nếu tất cả ảnh lỗi, backend vẫn gửi text nếu text hợp lệ.
- [x] Chạy `pytest -q`.

### Phase 6. Hotfix verify Pancake echo và retry content_ids

- [x] Thêm hằng số/cấu hình nội bộ cho delivery verify: tối đa 3 attempt và chờ echo 1 giây mỗi attempt.
- [x] Tạo helper nhận diện webhook echo ảnh từ Pancake: cùng `page_id`, cùng `pancake_conversation_id`, `is_echo=true`, `message_from_admin_name="Public API"` và `attachment_count > 0`.
- [x] Ghi nhận echo ảnh `Public API` vào bộ nhớ tạm thời có TTL trước khi `_process_normalized_message` ignore bot echo, để flow gửi ảnh có thể kiểm tra delivery.
- [x] Khi gửi image message, mở cửa sổ verify ngay trước lúc gọi API gửi `content_ids`, không chỉ sau dòng `PANCAKE_DRIVE_IMAGE_SEND_OK`.
- [x] Attempt 1 giữ flow hiện tại: reuse/upload để có `content_ids`, gửi image message bằng danh sách đó.
- [x] Nếu attempt 1 HTTP 200 nhưng không thấy echo attachment trong 1 giây, attempt 2 resend đúng danh sách `content_ids` đã có.
- [x] Nếu attempt 2 HTTP 200 nhưng vẫn không thấy echo attachment trong 1 giây, attempt 3 resend đúng danh sách `content_ids` đã có.
- [x] Attempt 2 và attempt 3 không download lại Drive, không upload lại Pancake, không tạo `content_id` mới.
- [x] Giữ nguyên cơ chế xóa file local ngay sau upload thành công khi `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`.
- [x] Trước mỗi retry, check lại echo đã ghi nhận trong cửa sổ verify để tránh gửi trùng nếu webhook vừa tới sát thời điểm retry.
- [x] Log từng delivery attempt với `attempt`, `content_id_count`, HTTP status, trạng thái `echo_verified` và reason khi chưa verified.
- [x] Trả `image_send_result` có thông tin delivery verification: `attempt_count`, `echo_verified`, `verified_attachment_count`, `verified_message_mid` nếu có, và `unverified_after_attempts` nếu thất bại.
- [x] Không coi HTTP 200 là thành công cuối cùng nếu thiếu echo attachment; chỉ coi là thành công API request.
- [x] Test attempt 1 có echo trong 1 giây thì không retry.
- [x] Test không có echo thì retry đủ 3 lần với cùng `content_ids`.
- [x] Test echo đến trước/sát HTTP 200 vẫn được verify vì cửa sổ bắt đầu trước API call.
- [x] Test retry không gọi download Drive hoặc upload Pancake lại.
- [x] Test hết 3 attempt vẫn không có echo thì result là `echo_verified=false` và text reply vẫn đã gửi.
- [x] Chạy `pytest -q`.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp Pancake Drive link image reply](pancake-drive-link-image-reply-task-list/phase-0.md)
- [Phase 1. Tách Drive link và chuẩn bị reply](pancake-drive-link-image-reply-task-list/phase-1.md)
- [Phase 2. Cache local và download ảnh](pancake-drive-link-image-reply-task-list/phase-2.md)
- [Phase 3. Upload ảnh và gửi Pancake message](pancake-drive-link-image-reply-task-list/phase-3.md)
- [Phase 4. Lưu message, fallback và logging](pancake-drive-link-image-reply-task-list/phase-4.md)
- [Phase 5. Test và rollout](pancake-drive-link-image-reply-task-list/phase-5.md)
- [Phase 6. Hotfix verify Pancake echo và retry content_ids](pancake-drive-link-image-reply-task-list/phase-6.md)

## Test cần có khi implement

- Extract `drive_file_id` từ URL `/file/d/{id}/view`.
- Extract `drive_file_id` từ URL `uc?export=download&id={id}`.
- Tách Drive file/folder link khỏi AI text và giữ lại text sạch.
- Lookup Drive folder link thành danh sách ảnh trước khi cache/download.
- Không đổi flow khi AI response không có Drive link.
- Cache hit có file local thì không download lại.
- Cache hit có `content_id` và reuse bật thì không download lại dù file local đã bị xóa.
- Cache hit có file local vượt ngưỡng Pancake thì tối ưu lại trước khi upload.
- Cache miss thì download ảnh và update cache JSON.
- Cache miss với ảnh lớn thì lưu file đã resize/compress dưới `PANCAKE_IMAGE_STORAGE_MAX_BYTES`.
- Upload multipart lên Pancake đúng endpoint `upload_contents`.
- Lưu `content_id` vào cache sau upload thành công.
- Xóa file local sau upload thành công khi reuse `content_id` đang bật.
- Reuse `content_id` đã cache thì bỏ qua upload.
- Gửi image message với body có `content_ids`.
- Download Drive có follow redirect để tránh lỗi `303 See Other`.
- Nếu download/upload lỗi một ảnh, các ảnh còn lại vẫn được gửi.
- Nếu tất cả ảnh lỗi, backend vẫn gửi text nếu text hợp lệ.

## Ghi chú production

- Cache JSON cần atomic write hoặc lock vì webhook có thể xử lý đồng thời.
- Khi `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, file trong `storage/pancake_images/` được xóa sau upload thành công; thư mục này chủ yếu còn là fallback tạm thời cho ảnh chưa có `content_id` reusable.
- Nếu Pancake thay đổi giới hạn upload `500KB`, cập nhật `PANCAKE_IMAGE_STORAGE_MAX_BYTES` để local cache vẫn chỉ chứa file sẵn sàng upload.
- Log nên có `drive_file_id`, `page_id`, `conversation_id`, `content_id` và reason lỗi, nhưng không log token.
- Timeout download Drive và upload Pancake cần đủ ngắn để không làm webhook treo lâu.
- Nếu sau này chuyển webhook sang queue/background worker, phần download/upload ảnh nên chạy trong worker thay vì chạy inline trong request Pancake.
