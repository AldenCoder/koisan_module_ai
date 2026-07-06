# Tích hợp Pancake chọn ảnh Google Drive đúng màu từ tên file

## Mục tiêu

Tài liệu này mô tả phương án bổ sung cho flow [Pancake gửi ảnh từ Google Drive file/folder link](pancake-drive-link-image-reply.md): sau khi `BE` lookup được danh sách ảnh trong Google Drive folder, `BE` cần lấy thêm tên ảnh, detect màu từ tên ảnh, lưu metadata này vào `storage/pancake_image_cache.json`, rồi dùng metadata đó để chọn đúng ảnh theo màu mà AI nhắc trong reply.

Điểm thay đổi chính: flow hiện tại đang chọn ảnh ngẫu nhiên từ Drive folder. Flow mới chỉ can thiệp khi AI reply có Drive link và text reply có cụm màu rõ ràng theo dạng `màu + tên màu`, ví dụ `màu đỏ`, `màu xanh ngọc`. Khi đó `BE` lọc danh sách ảnh theo màu trước khi cache/download/upload/gửi Pancake. Nếu AI reply không có Drive link, `BE` không chạy color filter. Nếu AI reply có Drive link nhưng không có cụm `màu + tên màu`, `BE` giữ nguyên hành vi hiện tại: mỗi Drive folder link chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `AI Agent` / `Brain`: service tạo nội dung trả lời cho khách.
- `Drive folder link`: link Google Drive public trỏ tới một folder chứa ảnh sản phẩm.
- `drive_file_id`: id file Google Drive.
- `drive_file_name`: tên file ảnh trên Google Drive, ví dụ `vay_da_hoi_do.jpg`.
- `drive_file_color`: mã màu BE detect từ tên file, ví dụ `do`, `xanhngoc`.
- `requested_color`: mã màu BE detect từ cụm `màu + tên màu` trong text reply của AI.
- `content_id`: id nội dung do Pancake trả về sau khi upload file.

## Luồng tổng thể

Khách hàng nhắn tin vào kênh social đã nối Pancake.

`BE` nhận webhook Pancake, normalize message, lưu user message và gọi AI theo flow Pancake hiện tại.

AI trả về nội dung text có thể kèm một hoặc nhiều Drive file link hoặc Drive folder link.

`BE` tách Drive link khỏi text. Phần text còn lại được dùng làm tin nhắn phản hồi đầu tiên.

`BE` chỉ chạy color filter nếu reply của AI có Drive link. Nếu reply không có Drive link, flow text reply hiện tại không đổi và `BE` không cần detect màu.

Nếu reply có Drive link, `BE` detect `requested_color` từ phần text sau khi tách link, nhưng chỉ khi text có trigger rõ ràng `màu + tên màu`.

Với Drive folder link, `BE` lookup danh sách ảnh trong folder bằng Google Drive API, lấy tối thiểu `id`, `name`, `mimeType`, `size`.

Với từng ảnh lookup được, `BE` lấy `drive_file_id`, `drive_file_name`, detect `drive_file_color` từ token màu cuối tên file, rồi lưu metadata này vào cache Pancake image.

Nếu có `requested_color`, `BE` lọc ảnh trong folder theo `drive_file_color == requested_color`. Nếu có nhiều ảnh cùng màu, `BE` chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh trong nhóm match màu.

Nếu không có `requested_color`, bao gồm trường hợp text có tên màu đứng một mình nhưng không có chữ `màu` ngay trước đó, `BE` giữ logic hiện tại: chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh trong folder.

Sau khi chọn được danh sách `drive_file_id`, flow cache/download/upload/reuse `content_id` và gửi ảnh qua Pancake giữ nguyên như tài liệu gốc.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận response từ AI trong flow Pancake hiện có.
- Tách Drive file/folder link khỏi text trước khi gửi reply cho khách.
- Chỉ chạy color filter khi AI reply có Drive link.
- Detect `requested_color` từ text reply đã tách Drive link, chỉ khi có cụm `màu + tên màu`.
- Lookup Drive folder để lấy danh sách ảnh và tên ảnh.
- Detect `drive_file_color` từ `drive_file_name`.
- Lưu `drive_file_name` và `drive_file_color` vào `storage/pancake_image_cache.json`.
- Lọc ảnh theo màu khi có `requested_color`.
- Giữ logic chọn ngẫu nhiên max 3 ảnh/folder khi không có `requested_color`.
- Không gửi ảnh sai màu khi có `requested_color` nhưng không có ảnh match.
- Gửi text trước, gửi ảnh sau theo flow Pancake hiện tại.
- Log đủ thông tin để debug nhưng không log token hoặc dữ liệu nhạy cảm.

### Pancake

Pancake chịu trách nhiệm:

- Cung cấp Public API để upload file theo `page_id`.
- Trả về `content_id` sau khi upload thành công.
- Cung cấp Public API để gửi message có `content_ids` vào hội thoại.
- Không chịu trách nhiệm chọn ảnh theo màu.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Nhận text và context hội thoại đã được BE chuẩn hóa.
- Trả nội dung text cho khách.
- Trả Drive file link hoặc Drive folder link public nếu cần gửi ảnh sản phẩm.
- Nếu muốn BE chọn ảnh đúng màu, text reply phải nói rõ màu theo dạng `màu + tên màu`, ví dụ `màu đỏ`, `màu xanh ngọc`.
- Không cần biết `drive_file_name`, `drive_file_color` hoặc `content_id`.
- Không cần tự gọi Google Drive API hoặc Pancake Public API.

### Ngoài phạm vi phương án này

- Không đổi flow Facebook webhook hiện tại.
- Không xử lý ảnh/sticker/file do khách gửi vào.
- Không yêu cầu AI trả structured color field riêng.
- Không build màn hình quản lý cache ảnh/màu.
- Không đổi naming convention file ảnh cũ ngoài Google Drive.
- Không dùng computer vision để nhận diện màu từ ảnh.
- Không crawl folder đệ quy; chỉ lookup ảnh nằm trực tiếp trong Drive folder public.
- Không xử lý một reply yêu cầu nhiều màu khác nhau trong phase đầu.

## Contract dữ liệu từ AI

AI có thể trả response có Drive folder link và nói rõ màu:

```text
Em gửi chị ảnh váy màu đỏ ạ

https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ
```

Sau khi parse, BE cần chuẩn bị object nội bộ tương đương:

```json
{
  "text": "Em gửi chị ảnh váy màu đỏ ạ",
  "drive_file_urls": [],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ"
  ],
  "requested_color": "do"
}
```

AI cũng có thể trả Drive folder link nhưng không nói màu:

```text
Em gửi chị album mẫu này tham khảo ạ

https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ
```

Sau khi parse, BE cần chuẩn bị object nội bộ tương đương:

```json
{
  "text": "Em gửi chị album mẫu này tham khảo ạ",
  "drive_file_urls": [],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ"
  ],
  "requested_color": null
}
```

AI có thể trả response không có Drive link:

```text
Dạ mẫu này bên em còn hàng ạ.
```

Khi đó BE không chạy color filter:

```json
{
  "text": "Dạ mẫu này bên em còn hàng ạ.",
  "drive_file_urls": [],
  "drive_folder_urls": [],
  "requested_color": null,
  "color_filter_skipped_reason": "no_drive_link"
}
```

Quy tắc:

- `requested_color` chỉ được detect khi AI reply có Drive file/folder link.
- Nếu AI reply không có Drive link, không detect màu, không lookup cache màu, không đổi flow text reply hiện tại.
- Nếu AI reply có Drive link nhưng không có cụm `màu + tên màu`, giữ random selection hiện tại.
- Nếu AI reply có Drive link và có cụm `màu + tên màu`, filter ảnh theo `requested_color`.
- Nếu có nhiều cụm `màu + tên màu` trong một reply, phase đầu chọn cụm xuất hiện đầu tiên trong text sau khi tách link.
- Nếu text chỉ còn rỗng sau khi tách link, không detect màu và xử lý ảnh theo rule hiện tại.

## Tách màu từ AI text

BE không được suy luận màu bằng cách search tự do mọi từ trong text. `requested_color` chỉ được tạo khi text có trigger rõ ràng theo dạng `màu + tên màu`. Các màu xuất hiện lẻ như `đỏ`, `xanh ngọc`, hoặc trong cụm không phải trigger như `mẫu đỏ` không được kích hoạt color filter.

Nên dùng bảng màu có kiểm soát để map nhiều cách viết tên màu về cùng một `color_key`.

Ví dụ bảng màu:

```json
{
  "do": ["đỏ", "do"],
  "den": ["đen", "den"],
  "trang": ["trắng", "trang"],
  "xanhngoc": ["xanh ngọc", "xanh ngoc", "xanhngoc"],
  "xanhreu": ["xanh rêu", "xanh reu", "xanhreu"],
  "xanhduong": ["xanh dương", "xanh duong", "xanhduong"]
}
```

Quy tắc detect:

- Normalize text về lowercase.
- Normalize nhiều khoảng trắng thành một khoảng trắng.
- Token trigger phải là `màu` hoặc `mau`.
- Không bỏ dấu trước khi nhận diện trigger, để tránh nhầm `mẫu đỏ` thành `mau do`.
- Sau khi xác định đúng trigger `màu`/`mau`, BE mới normalize tên màu phía sau để so với bảng màu.
- Bỏ dấu tiếng Việt khi so sánh tên màu phía sau trigger.
- Normalize alias màu bằng cùng rule với tên màu phía sau trigger.
- Ưu tiên alias dài hơn trước alias ngắn hơn để tránh match nhầm.
- Chỉ trả một `requested_color` trong phase đầu.
- Nếu không có pattern `màu + tên màu` hợp lệ, `requested_color=null`.

Ví dụ:

| Text AI | `requested_color` |
|---|---|
| `Em gửi chị ảnh váy màu đỏ ạ` | `do` |
| `Em gửi chị ảnh màu xanh ngọc ạ` | `xanhngoc` |
| `Em gửi chị ảnh màu xanhngoc ạ` | `xanhngoc` |
| `Em gửi chị ảnh váy đỏ ạ` | `null` |
| `Em gửi chị mẫu đỏ này ạ` | `null` |
| `Mẫu này còn size M, em gửi ảnh chị xem ạ` | `null` |

## Tách Drive file id và metadata tên ảnh

Drive file link mẫu:

```text
https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link
```

`drive_file_id`:

```text
1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk
```

BE tiếp tục dùng helper extract `drive_file_id` hiện tại từ các dạng URL phổ biến:

| Dạng URL | Cách lấy id |
|---|---|
| `https://drive.google.com/file/d/{drive_file_id}/view?usp=drive_link` | Lấy segment sau `/file/d/` |
| `https://drive.google.com/file/d/{drive_file_id}/view` | Lấy segment sau `/file/d/` |
| `https://drive.google.com/uc?export=download&id={drive_file_id}` | Lấy query param `id` |
| `https://drive.google.com/open?id={drive_file_id}` | Lấy query param `id` |

Với Drive file link trực tiếp, URL thường không chứa tên ảnh. Nếu muốn lưu `drive_file_name` và `drive_file_color` cho file link trực tiếp, BE có thể lấy metadata bằng một trong hai cách:

- Gọi Google Drive API `files.get` với field `id,name,mimeType,size`.
- Fallback parse filename từ header `Content-Disposition` khi download nếu Google Drive trả header này.

Nếu không lấy được `drive_file_name`, BE vẫn xử lý file link trực tiếp theo flow hiện tại. Color filter chủ yếu áp dụng cho Drive folder link vì folder có nhiều ảnh để chọn; file link trực tiếp đã là một ảnh cụ thể nên BE không cần chọn giữa nhiều ảnh.

## Tách màu từ tên ảnh Google Drive

Tên ảnh trên Google Drive cần đặt màu ở token cuối cùng trước extension.

Token trong filename được ngăn cách bằng dấu gạch dưới `_`.

Màu tiếng Việt viết không dấu. Nếu màu có nhiều từ, viết liền không dấu.

Ví dụ:

| Tên ảnh | Token màu | `drive_file_color` |
|---|---|---|
| `vay_da_hoi_do.jpg` | `do` | `do` |
| `vay_da_hoi_den.jpg` | `den` | `den` |
| `vay_da_hoi_xanhngoc.jpg` | `xanhngoc` | `xanhngoc` |
| `vay_da_hoi_xanhreu.jpg` | `xanhreu` | `xanhreu` |
| `vay_da_hoi_xanhduong.jpg` | `xanhduong` | `xanhduong` |

Quy tắc parse filename:

- Lấy `drive_file_name` từ Google Drive API field `name`.
- Bỏ extension cuối như `.jpg`, `.jpeg`, `.png`.
- Lowercase filename.
- Split theo `_`.
- Lấy token cuối làm candidate color.
- Candidate color chỉ hợp lệ nếu nằm trong bảng `color_key` đã cấu hình.
- Nếu token cuối không nằm trong bảng màu, không ghi `drive_file_color`.

Ví dụ không hợp lệ:

| Tên ảnh | Lý do |
|---|---|
| `vay_do_da_hoi.jpg` | Token cuối là `hoi`, không phải màu |
| `vay_da_hoi_xanh_ngoc.jpg` | Theo quy tắc phase đầu, màu nhiều từ phải viết liền `xanhngoc` |
| `vay_da_hoi.jpg` | Không có token màu |

## Tách Drive folder id và lookup ảnh

Drive folder link mẫu:

```text
https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ
```

`drive_folder_id`:

```text
16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ
```

BE lookup ảnh trong folder bằng Google Drive API hiện có:

```text
GET https://www.googleapis.com/drive/v3/files
```

Query cần lọc:

```text
'{drive_folder_id}' in parents and trashed=false and (mimeType='image/jpeg' or mimeType='image/png')
```

Fields tối thiểu:

```text
nextPageToken,files(id,name,mimeType,size)
```

Quy tắc:

- Chỉ lấy ảnh nằm trực tiếp trong folder, không crawl folder con.
- Chỉ nhận `image/jpeg` và `image/png`.
- Dedupe theo `drive_file_id`.
- Giữ `drive_file_name` để detect màu và ghi cache.
- Detect `drive_file_color` trước khi chọn ảnh gửi cho khách.
- Không log `GOOGLE_DRIVE_API_KEY`; request Google Drive phải suppress log URL đầy đủ có query `key`.

## Cache và local storage

Cache JSON dùng chung với flow Pancake Drive image hiện tại:

```text
storage/pancake_image_cache.json
```

File ảnh local vẫn lưu theo `drive_file_id`:

```text
storage/pancake_images/{drive_file_id}.jpg
```

Không đổi local path sang tên ảnh, vì tên ảnh có thể trùng, có ký tự đặc biệt, hoặc thay đổi trên Google Drive.

Cache đề xuất sau khi bổ sung metadata màu:

```json
{
  "version": 1,
  "items": {
    "drive_file_1": {
      "drive_file_id": "drive_file_1",
      "drive_file_name": "vay_da_hoi_do.jpg",
      "drive_file_color": "do",
      "drive_url": "https://drive.google.com/file/d/drive_file_1/view",
      "direct_download_url": "https://drive.google.com/uc?export=download&id=drive_file_1",
      "local_path": "storage/pancake_images/drive_file_1.jpg",
      "content_id": "CONTENT_ID_1",
      "mime_type": "image/jpeg",
      "size_bytes": 123456,
      "local_present": true
    }
  }
}
```

Quy tắc cache:

- `drive_file_name` là optional metadata nhưng nên lưu nếu lookup được.
- `drive_file_color` chỉ ghi khi detect được màu hợp lệ từ `drive_file_name`.
- Cache cũ không có `drive_file_name` và `drive_file_color` vẫn hợp lệ cho flow không filter màu.
- Khi AI reply có Drive link và có `requested_color`, cache item thiếu `drive_file_name` hoặc thiếu `drive_file_color` không đủ điều kiện để reuse.
- Với cache item thiếu metadata trong flow có `requested_color`, BE phải xóa entry đó khỏi `items` theo `drive_file_id`, rồi xử lý lại ảnh từ bước chuẩn bị local/download/cache để ghi lại `drive_file_id`, `drive_file_name`, `drive_file_color`, `direct_download_url`, `local_path` và các metadata liên quan.
- Sau khi entry thiếu metadata bị xóa, BE không được dùng `content_id` cũ của entry đó để gửi ảnh theo màu, vì không chứng minh được ảnh cũ đúng màu.
- Khi folder lookup lại cùng `drive_file_id`, BE có thể bổ sung hoặc cập nhật `drive_file_name` và `drive_file_color`.
- Khi upload thành công và lưu `content_id`, BE phải giữ lại metadata tên/màu đã có trong entry.
- Khi xóa file local sau upload, BE chỉ update `local_present` và `local_removed_at`, không xóa metadata tên/màu.
- Cache JSON vẫn cần atomic write hoặc lock để tránh hỏng file khi nhiều webhook chạy cùng lúc.

## Download ảnh từ Google Drive

Download ảnh vẫn dùng flow hiện tại sau khi BE đã chọn xong danh sách ảnh cần gửi.

Với ảnh đến từ Drive folder lookup, `drive_file_name` đã có từ metadata Google Drive trước khi download.

Với Drive file link trực tiếp, link thường chỉ có `drive_file_id` và không có tên file. Nếu muốn lưu `drive_file_name` cho file link trực tiếp, BE có hai lựa chọn:

- Gọi Google Drive metadata API `files.get` theo `drive_file_id` để lấy field `name`.
- Fallback parse filename từ response header `Content-Disposition` khi download nếu Google Drive trả header này.

Phase đầu có thể ưu tiên folder link vì color filter có giá trị chính khi folder có nhiều ảnh để chọn.

## Reuse hoặc upload ảnh lên Pancake

Logic reuse/upload không đổi so với tài liệu gốc.

Trước khi upload file local, BE kiểm tra cache theo `drive_file_id`. Nếu cache đã có `content_id` và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, BE đưa `content_id` đó vào danh sách gửi ảnh, không upload lại.

Riêng flow có `requested_color`: BE chỉ được reuse `content_id` nếu cache item cũng có đủ `drive_file_name` và `drive_file_color` match màu yêu cầu. Nếu cache item có `content_id` nhưng thiếu `drive_file_name` hoặc `drive_file_color`, BE phải xóa entry thiếu metadata khỏi cache và chạy lại từ bước download/cache/upload để tạo entry mới có đủ metadata. Không dùng `content_id` cũ để gửi ảnh theo màu.

Khi ghi `content_id` vào cache, BE cần merge vào entry hiện tại để không mất:

- `drive_file_name`
- `drive_file_color`
- `drive_url`
- `direct_download_url`
- `local_path`
- metadata size/mime

Nếu reuse bật và BE xóa file local sau upload thành công, cache vẫn giữ `drive_file_name` và `drive_file_color` để các lần sau debug và filter metadata.

## API gửi tin nhắn phản hồi khách

Endpoint Pancake Public API dùng để gửi reply vẫn là:

```text
POST https://pages.fm/api/public_api/v1/pages/{page_id}/conversations/{conversation_id}/messages
```

### Tin nhắn 1: text

BE gửi text đã tách raw Drive link trước:

```json
{
  "action": "reply_inbox",
  "message": "Em gửi chị ảnh váy màu đỏ ạ"
}
```

### Tin nhắn 2: ảnh

Nếu `requested_color=do`, BE chỉ upload/reuse các ảnh match màu `do`.

Sau khi có `content_ids`, BE gửi image message:

```json
{
  "action": "reply_inbox",
  "content_ids": [
    "CONTENT_ID_DO_1"
  ]
}
```

Nếu có `requested_color` nhưng folder không có ảnh match màu, BE fallback sang random selection theo logic cũ rồi vẫn gửi image message nếu chọn được ảnh.

## Object nội bộ sau khi chuẩn bị reply

Object nội bộ sau khi BE parse response AI và chọn ảnh nên có dạng ổn định để dễ test:

| Field | Ý nghĩa |
|---|---|
| `text` | Text gửi ở tin nhắn đầu tiên, đã tách raw Drive link |
| `drive_file_urls` | Danh sách Drive file link extract từ AI response |
| `drive_file_ids` | Danh sách id extract được từ `drive_file_urls` và folder selection |
| `drive_folder_urls` | Danh sách Drive folder link extract từ AI response |
| `requested_color` | Màu detect từ cụm `màu + tên màu` trong AI text, chỉ detect khi có Drive link |
| `color_filter_applied` | `true` nếu có Drive link và có `requested_color` |
| `color_filter_reason` | Reason khi filter không chạy hoặc không chọn được ảnh |
| `drive_folder_results` | Kết quả lookup folder rút gọn để debug, gồm id/name/color |
| `selected_drive_file_ids` | Danh sách ảnh được chọn sau khi filter/random |
| `image_limit` | Số ảnh tối đa được chọn cho mỗi Drive folder link |
| `content_ids` | Danh sách content id sau khi upload/reuse thành công |
| `errors` | Danh sách lỗi cấp link/folder/color/upload để log và debug |

Ví dụ:

```json
{
  "text": "Em gửi chị ảnh váy màu đỏ ạ",
  "drive_file_urls": [
    "https://drive.google.com/file/d/file_1/view"
  ],
  "drive_file_ids": [
    "file_1"
  ],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ"
  ],
  "requested_color": "do",
  "color_filter_applied": true,
  "color_filter_reason": null,
  "drive_folder_results": [
    {
      "folder_id": "16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ",
      "images": [
        {
          "id": "file_1",
          "name": "vay_da_hoi_do.jpg",
          "drive_file_color": "do",
          "selected": true
        },
        {
          "id": "file_2",
          "name": "vay_da_hoi_den.jpg",
          "drive_file_color": "den",
          "selected": false
        }
      ]
    }
  ],
  "selected_drive_file_ids": [
    "file_1"
  ],
  "image_limit": 3,
  "content_ids": [
    "CONTENT_ID_DO_1"
  ],
  "errors": []
}
```

## Quy tắc xử lý message

BE nên áp dụng các rule sau:

- Chỉ xử lý color filter sau khi AI trả response thành công.
- Chỉ detect/filter màu khi AI reply có Drive file/folder link.
- Nếu AI reply không có Drive link, không chạy color filter và giữ flow hiện tại.
- Raw Drive link chỉ được tách khỏi bot reply text, không tách khỏi user message đã lưu.
- Nếu có Drive link, detect `requested_color` từ text đã tách link, chỉ khi có pattern `màu + tên màu`.
- Nếu không có `requested_color`, chọn ngẫu nhiên ảnh trong mỗi folder như hiện tại.
- Nếu có `requested_color`, lọc ảnh theo `drive_file_color`.
- Nếu có `requested_color` nhưng cache item của ảnh match đang thiếu `drive_file_name` hoặc `drive_file_color`, xóa cache item đó và chạy lại từ bước download/cache/upload metadata.
- Nếu một folder có nhiều ảnh match màu, chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh trong nhóm match.
- Nếu nhiều folder link cùng một reply và có một `requested_color`, áp dụng cùng màu đó cho từng folder.
- Nếu có `requested_color` nhưng một folder không có ảnh match, fallback chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh trong folder đó theo logic cũ.
- Không gửi `content_ids` rỗng.
- Không lưu token hoặc direct auth data vào `Message.meta`.

## Lỗi và fallback

BE nên xử lý lỗi theo hướng không làm mất text reply:

- AI có text và có Drive link nhưng không có pattern `màu + tên màu` hợp lệ: gửi text, dùng random selection hiện tại.
- Folder lookup lỗi: gửi text nếu text hợp lệ, log folder error.
- Tên ảnh thiếu hoặc không parse được màu: ảnh vẫn hợp lệ cho random selection, nhưng không match khi có `requested_color`.
- Cache item thiếu `drive_file_name` hoặc `drive_file_color` trong flow có `requested_color`: xóa cache item đó, chạy lại từ bước download/cache/upload metadata; nếu vẫn thiếu metadata sau khi chạy lại, không gửi ảnh đó theo màu.
- Có `requested_color` nhưng không có ảnh match trong folder: gửi text và fallback ảnh random theo logic cũ, log reason `drive_color_no_match_random_fallback`.
- Có `requested_color` nhưng folder không có ảnh nào có thể chọn: gửi text, không gửi image message, log reason `drive_color_no_match`.
- Download lỗi: bỏ qua ảnh đó, tiếp tục ảnh khác.
- Upload lỗi: bỏ qua `content_id` đó, tiếp tục ảnh khác.
- Tất cả ảnh lỗi: không gửi image message.
- Pancake gửi image message lỗi: log response rút gọn, không log token.

Nếu đã gửi text thành công nhưng gửi ảnh lỗi hoặc folder không có ảnh nào có thể chọn, khách vẫn nhận được câu trả lời text. Đây là behavior chấp nhận được cho phase đầu.

## Lưu message vào database

User message vẫn lưu như flow Pancake hiện tại.

Bot text message nên lưu với `content` là text đã tách raw Drive link.

Metadata nên lưu rút gọn trong `meta` của bot message:

- `requested_color`
- `color_filter_applied`
- `color_filter_reason`
- `selected_drive_file_ids`
- `drive_file_names`
- `drive_file_colors`
- `content_ids`
- response Pancake rút gọn

Không lưu file binary vào database.

Không lưu token Google Drive hoặc Pancake vào database.

## Cấu hình backend

Các cấu hình nên bổ sung:

- `PANCAKE_IMAGE_COLOR_FILTER_ENABLED`: bật/tắt color filter, mặc định `true`.
- `PANCAKE_IMAGE_COLOR_MAP`: JSON string hoặc path tới file cấu hình map `color_key -> aliases`.
Các cấu hình hiện có vẫn dùng chung:

- `GOOGLE_DRIVE_API_KEY`: dùng để lookup danh sách ảnh trong folder.
- `PANCAKE_IMAGE_CACHE_PATH`: mặc định `storage/pancake_image_cache.json`.
- `PANCAKE_IMAGE_STORAGE_DIR`: mặc định `storage/pancake_images`.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`: số ảnh tối đa chọn cho mỗi Drive folder link, mặc định 3.
- `PANCAKE_IMAGE_DOWNLOAD_TIMEOUT_SECONDS`: timeout download ảnh Drive.
- `PANCAKE_IMAGE_UPLOAD_TIMEOUT_SECONDS`: timeout upload ảnh Pancake.
- `PANCAKE_IMAGE_MAX_BYTES`: giới hạn kích thước ảnh tải về.
- `PANCAKE_IMAGE_STORAGE_MAX_BYTES`: giới hạn kích thước file ảnh lưu local để upload Pancake.
- `PANCAKE_REUSE_UPLOADED_CONTENT_ID`: bật/tắt việc dùng lại `content_id` đã lưu trong cache.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/services/google_drive_image_service.py](../app/services/google_drive_image_service.py)
- [app/services/pancake_drive_image_service.py](../app/services/pancake_drive_image_service.py)
- [app/core/config.py](../app/core/config.py)
- [tests/test_google_drive_image_service.py](../tests/test_google_drive_image_service.py)
- [tests/test_pancake_drive_image_service.py](../tests/test_pancake_drive_image_service.py)
- [tests/test_pancake_webhook.py](../tests/test_pancake_webhook.py)

Nếu tách helper riêng để dễ test:

- `app/services/pancake_drive_image_color_service.py`
- `tests/test_pancake_drive_image_color_service.py`

## Checklist implementation tổng hợp

### Phase 0. Chốt giải pháp

- [x] Chốt chỉ chạy color filter khi AI reply có Drive link.
- [x] Chốt nếu AI reply không có Drive link thì không detect màu và không đổi flow hiện tại.
- [x] Chốt nếu có Drive link nhưng không có cụm `màu + tên màu` thì giữ random selection hiện tại.
- [x] Chốt nếu có cụm `màu + tên màu` nhưng không match ảnh thì fallback random theo logic cũ.
- [x] Chốt chỉ detect màu từ AI text khi có pattern `màu + tên màu`.
- [x] Chốt màu filename nằm ở token cuối trước extension.
- [x] Chốt màu nhiều từ viết liền không dấu, ví dụ `xanhngoc`.

### Phase 1. Lấy tên ảnh và detect màu từ Drive metadata

- [x] Đảm bảo Google Drive folder lookup lấy field `name`.
- [x] Chuẩn hóa `drive_file_name` từ Google Drive API.
- [x] Detect `drive_file_color` từ token cuối filename.
- [x] Bỏ qua `drive_file_color` nếu token cuối không nằm trong bảng màu.
- [x] Giữ metadata `drive_file_name` và `drive_file_color` trong folder result để debug.

### Phase 2. Lưu metadata tên/màu vào Pancake image cache

- [x] Thêm `drive_file_name` vào cache item.
- [x] Thêm `drive_file_color` vào cache item khi detect được.
- [x] Khi download/cache ảnh, merge metadata vào entry hiện có.
- [x] Nếu AI reply có `requested_color` và cache item thiếu `drive_file_name` hoặc `drive_file_color`, xóa entry khỏi `items`.
- [x] Sau khi xóa entry thiếu metadata, chạy lại từ bước download/cache để lưu lại `drive_file_id`, `drive_file_name`, `drive_file_color`, `direct_download_url`, `local_path`.
- [x] Khi record `content_id`, không làm mất metadata tên/màu.
- [x] Khi xóa local file, không làm mất metadata tên/màu.
- [x] Cache cũ không có tên/màu vẫn đọc được bình thường.

### Phase 3. Detect màu từ AI reply và chọn ảnh đúng màu

- [x] Chỉ detect màu nếu AI reply có Drive link.
- [x] Chỉ detect màu nếu text có pattern `màu + tên màu`.
- [x] Normalize text và alias màu để detect `requested_color`.
- [x] Không detect màu khi tên màu xuất hiện lẻ nhưng không có trigger `màu`.
- [x] Không nhầm `mẫu đỏ` thành `màu đỏ`.
- [x] Nếu không có `requested_color`, giữ random selection hiện tại.
- [x] Nếu có `requested_color`, lọc ảnh theo `drive_file_color`.
- [x] Nếu nhiều ảnh match màu, random tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- [x] Nếu không có ảnh match, fallback random theo logic cũ.

### Phase 4. Lưu message, fallback và logging

- [x] Lưu `requested_color`, `drive_file_name`, `drive_file_color`, `selected_drive_file_ids` vào meta rút gọn.
- [x] Log `drive_folder_id`, `drive_file_id`, `drive_file_name`, `drive_file_color`, `requested_color`.
- [x] Log reason `drive_color_no_match_random_fallback` khi không có ảnh match nhưng fallback random.
- [x] Không log token hoặc Google Drive API URL đầy đủ có `key`.
- [x] Đảm bảo text vẫn gửi được khi media lỗi hoặc không match màu.

### Phase 5. Test và rollout

- [x] Test parse color từ filename một từ.
- [x] Test parse color từ filename nhiều từ viết liền.
- [x] Test detect requested color từ text có dấu.
- [x] Test detect requested color từ text không dấu.
- [x] Test không detect màu khi chỉ có `váy đỏ` mà không có chữ `màu`.
- [x] Test không detect màu từ `mẫu đỏ`.
- [x] Test AI reply không có Drive link thì không gọi color filter.
- [x] Test AI reply có Drive link nhưng không có cụm `màu + tên màu` thì giữ random selection.
- [x] Test AI reply có Drive link và có cụm `màu + tên màu` thì chỉ chọn ảnh match màu.
- [x] Test không có ảnh match màu thì fallback random theo logic cũ.
- [x] Chạy `pytest -q`.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp chọn ảnh theo màu](pancake-drive-image-color-filter-task-list/phase-0.md)
- [Phase 1. Lấy tên ảnh và detect màu từ Drive metadata](pancake-drive-image-color-filter-task-list/phase-1.md)
- [Phase 2. Lưu metadata tên/màu vào Pancake image cache](pancake-drive-image-color-filter-task-list/phase-2.md)
- [Phase 3. Detect màu từ AI reply và chọn ảnh đúng màu](pancake-drive-image-color-filter-task-list/phase-3.md)
- [Phase 4. Lưu message, fallback và logging](pancake-drive-image-color-filter-task-list/phase-4.md)
- [Phase 5. Test và rollout](pancake-drive-image-color-filter-task-list/phase-5.md)

## Test cần có khi implement

- Parse `drive_file_color=do` từ `vay_da_hoi_do.jpg`.
- Parse `drive_file_color=xanhngoc` từ `vay_da_hoi_xanhngoc.jpg`.
- Không parse màu từ `vay_do_da_hoi.jpg`.
- Không parse màu từ `vay_da_hoi_xanh_ngoc.jpg` trong phase đầu.
- Detect `requested_color=do` từ text `màu đỏ`.
- Detect `requested_color=xanhngoc` từ text `màu xanh ngọc`.
- Detect `requested_color=do` từ text không dấu `mau do`.
- Không detect màu từ text `váy đỏ` nếu không có chữ `màu`.
- Không detect màu từ text `mẫu đỏ`, dù bỏ dấu sẽ giống `mau do`.
- Không detect màu khi AI reply không có Drive link.
- Không đổi flow khi AI reply không có Drive link.
- AI reply có Drive folder link nhưng không có cụm `màu + tên màu` thì vẫn chọn ngẫu nhiên max 3 ảnh/folder.
- AI reply có Drive folder link và `requested_color=do` thì chỉ truyền ảnh `drive_file_color=do` vào `ensure_local_images`.
- Nhiều ảnh cùng màu thì chọn ngẫu nhiên trong nhóm match màu.
- Nhiều folder link cùng một màu thì áp dụng cùng `requested_color` cho từng folder.
- Có `requested_color` nhưng không có ảnh match thì fallback random theo logic cũ.
- Cache item sau folder lookup có `drive_file_name` và `drive_file_color`.
- Cache item cũ thiếu `drive_file_name` hoặc `drive_file_color` bị xóa và chạy lại từ bước download/cache khi reply có `requested_color`.
- Ghi `content_id` sau upload không làm mất `drive_file_name` và `drive_file_color`.

## Ghi chú production

- Naming convention ảnh trên Google Drive là điều kiện quan trọng. Nếu team upload sai tên file, BE không nên đoán màu.
- Nên chuẩn hóa bảng màu ở config hoặc file riêng để cập nhật không cần sửa nhiều code.
- Khi đã detect được màu nhưng folder không có ảnh match, fallback random là behavior business hiện tại để vẫn gửi được ảnh cho khách; log `drive_color_no_match_random_fallback` để theo dõi chất lượng naming ảnh.
- Cache JSON cần atomic write hoặc lock vì webhook có thể xử lý đồng thời.
- Khi `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, file local có thể bị xóa sau upload; metadata tên/màu trong cache vẫn cần được giữ.
- Log nên đủ để debug tại sao ảnh được chọn hoặc không được chọn, nhưng không log token.
- Nếu sau này cần hỗ trợ nhiều màu trong một reply, nên mở rộng object nội bộ từ `requested_color` sang `requested_colors` và có rule map từng folder/link theo màu riêng.
