# Tích hợp Pancake tìm ảnh trong Google Drive folder con

## Mục tiêu

Tài liệu này mô tả phương án bổ sung cho flow [Pancake gửi ảnh từ Google Drive file/folder link](pancake-drive-link-image-reply.md): khi AI trả Drive folder link, `BE` được phép list ảnh và folder con, chọn nhánh phù hợp, rồi đi xuống folder con nếu cần để tìm ảnh gửi cho khách qua Pancake.

Điểm thay đổi chính: flow hiện tại chỉ lookup ảnh trực tiếp trong Drive folder link. Nếu Google Drive API trả `200` nhưng folder không có file `image/jpeg` hoặc `image/png`, kết quả hiện tại là `images=[]`, `error=null`, khách chỉ nhận text và không nhận ảnh. Flow mới list cả ảnh và folder con trong folder hiện tại; ở root folder có thể random giữa nhóm ảnh và nhóm folder con theo rule bên dưới; nếu cần đi sâu, `BE` chọn một folder con trong nhánh đang xét, tối đa 3 tầng. Nếu Google Drive API phân trang, `BE` chỉ dùng page đầu tiên.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `AI Agent` / `Brain`: service tạo nội dung trả lời cho khách.
- `Drive folder link`: link Google Drive public trỏ tới một folder.
- `root folder`: folder lấy trực tiếp từ Drive folder link AI trả về.
- `current folder`: folder đang được BE list ở một tầng cụ thể.
- `child folder`: folder con nằm trực tiếp trong `current folder`.
- `depth`: số tầng đã truy cập, tính `root folder` là tầng 1.
- `max depth`: giới hạn truy cập tối đa 3 tầng.
- `first page`: page đầu tiên của Google Drive API response khi list children của một folder.
- `drive_file_id`: id file Google Drive được dùng để tạo Drive file link nội bộ và cache ảnh Pancake.
- `drive_file_color`: màu `BE` detect từ tên file ảnh.
- `drive_folder_color`: màu `BE` detect từ tên folder con.
- `requested_color`: màu `BE` detect từ text reply của AI theo flow [pancake-drive-image-color-filter.md](pancake-drive-image-color-filter.md). Phase hiện tại dùng color key/map; update tiếp theo chuyển sang bắt cụm màu động sau chữ `màu`.
- `requested_color_phrase`: cụm màu raw lấy từ text AI sau chữ `màu`, ví dụ `Đỏ đô`, `Kem`, `Hồng sen`.
- `color_match_terms`: tập token dùng để match tên ảnh/folder sau khi normalize `requested_color_phrase`, gồm phrase đầy đủ, dạng không dấu, dạng liền, dạng separator và từng từ lẻ.
- `visited branch`: chuỗi folder thực tế đã được lookup từ root xuống tối đa tầng 3. Fallback chỉ được dùng ảnh trong nhánh này, không scan toàn bộ cây folder.
- `content_id`: id nội dung do Pancake trả về sau khi upload file.

## Luồng tổng thể

Khách hàng nhắn tin vào kênh social đã nối Pancake.

`BE` nhận webhook Pancake, normalize message, lưu user message và gọi AI theo flow Pancake hiện tại.

AI trả về nội dung text có thể kèm một hoặc nhiều Drive file link hoặc Drive folder link.

`BE` tách Drive link khỏi text. Phần text còn lại được dùng làm tin nhắn phản hồi đầu tiên.

Với Drive file link, `BE` giữ flow hiện tại: extract `drive_file_id`, cache/download/upload/reuse `content_id`, rồi gửi ảnh qua Pancake nếu có ảnh hợp lệ.

Với Drive folder link, `BE` extract `drive_folder_id` từ link và bắt đầu lookup tại `root folder`.

Ở mỗi tầng, `BE` list children của `current folder` bằng Google Drive API. Response chỉ lấy page đầu tiên. Children được chia thành hai nhóm: ảnh hợp lệ `image/jpeg` hoặc `image/png`, và folder con `application/vnd.google-apps.folder`.

Nếu AI reply không có `requested_color`, root folder có cả ảnh và folder con thì `BE` random giữa hai hướng: dùng nhóm ảnh ở root hoặc đi tiếp vào một folder con. Rule random giữa ảnh và folder chỉ áp dụng tại tầng 1. Từ tầng 2 trở đi, nếu folder đang xét có ảnh hợp lệ thì dùng ảnh ở folder đó và dừng traversal.

Nếu AI reply có `requested_color`, `BE` xét màu trên cả tên ảnh và tên folder con. Tại root folder, nếu chỉ ảnh match màu thì chọn ảnh; nếu chỉ folder con match màu thì đi vào folder đó; nếu cả hai cùng match hoặc cùng không match thì random giữa nhóm ảnh và nhóm folder. Từ tầng 2 trở đi, `BE` vẫn ưu tiên tìm ảnh/folder match màu trong nhánh đang đi.

Nếu đi qua tối đa 3 tầng mà không tìm được ảnh match màu, `BE` fallback chọn ngẫu nhiên ảnh trong các folder đã lookup thuộc `visited branch`. `BE` không mở sibling folder khác chỉ để fallback.

Nếu `current folder` không có ảnh và không có folder con, `BE` dừng lookup và ghi lỗi `drive_folder_no_images`. Nếu đã ở tầng 3 nhưng vẫn cần đi sâu hơn để tìm ảnh/folder phù hợp, `BE` dừng lookup và ghi lỗi `drive_folder_no_images_within_depth_limit`. `BE` không truy cập tầng 4.

Sau khi chọn được danh sách `drive_file_id`, flow cache/download/upload/reuse `content_id` và gửi ảnh qua Pancake giữ nguyên như tài liệu gốc.

## Phase 7: chọn ảnh đa màu từ nhiều folder

Phần này mô tả behavior Phase 7 đã implement cho Drive folder link. Rule này thay thế hướng random một nhánh khi root folder có folder con detect được màu, nhưng vẫn giữ fallback/rollback qua config.

Mục tiêu mới là để `BE` đọc Drive folder và gửi được ảnh đại diện cho tất cả màu mà `BE` tự tìm thấy trong cấu trúc Drive, thay vì phụ thuộc vào việc AI có nói đúng cụm màu hay không. Câu AI kiểu `Mẫu này có 3 màu: Be, Xanh biển, Tím` chỉ là thông tin tư vấn, không phải điều kiện bắt buộc để lọc đúng 3 màu. `BE` vẫn tự detect màu từ tên folder và tên file.

Rule chọn ảnh Phase 7:

- Với mỗi Drive folder link, `BE` list root folder và phân nhóm children thành ảnh root, folder con có màu, folder con không rõ màu.
- Nếu có folder con có màu, `BE` ưu tiên mở tất cả folder màu trong giới hạn depth/page hiện có, thay vì random một folder. Ví dụ root có `S2650543 BE`, `S2650543 HỒNG`, `S2650543 ĐEN` thì mở cả 3 folder.
- Ảnh nằm trong folder màu được kế thừa màu từ folder cha nếu tên file không có màu. Ví dụ ảnh trong folder `be` được coi là màu `be`.
- Selection pass 1: gom ảnh theo màu và chọn ngẫu nhiên 1 ảnh cho mỗi màu tìm được, không vượt `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- Selection pass 2: nếu chưa đủ limit, chọn ngẫu nhiên thêm từ các ảnh còn lại, không bắt buộc rõ màu.
- Nếu không có folder màu, `BE` dùng ảnh ở root folder, group theo màu detect từ filename nếu có, rồi áp dụng cùng rule đa màu.
- Nếu root có cả folder màu và ảnh root, ưu tiên pass 1 từ folder màu trước; ảnh root tham gia fill random ở pass 2, trừ khi không có folder màu.
- Nếu một folder màu không có ảnh hợp lệ, bỏ qua folder đó và tiếp tục các folder còn lại; không làm mất text reply.
- Với limit `5`, nếu Drive có 3 ảnh xanh và 4 ảnh đỏ, kết quả mong muốn là 1 ảnh xanh + 1 ảnh đỏ + 3 ảnh random từ phần còn lại.

Rule màu Phase 7:

- `drive_folder_color` được detect từ tên folder bằng color map hiện có và alias động theo token trong tên folder. Folder tên `be`, `xanh`, `tím` lần lượt tạo nhóm màu `be`, `xanh`, `tim`.
- Folder `xanh` được coi là màu xanh chung. Nếu cần phân biệt sâu hơn, đặt folder/file là `xanh biển`, `xanhbien`, `xanh ngọc`, `xanh lá`, v.v.
- `drive_file_color` vẫn được detect từ tên file. Nếu file và folder cùng có màu nhưng khác nhau, màu từ file nên được ưu tiên vì cụ thể hơn.
- Câu hỏi dạng `Chị thích màu nào...` không được tạo `requested_color`; cụm `màu nào` là câu hỏi lựa chọn, không phải màu cần lọc.
- Danh sách màu trong text AI như `Mẫu này có 3 màu: Be, Xanh biển, Tím` có thể dùng làm metadata/debug, nhưng không nên ép selection chỉ theo danh sách đó. Nguồn quyết định chính vẫn là Drive metadata.

Giới hạn để kiểm soát latency:

- Vẫn chỉ dùng page đầu của mỗi folder được mở.
- Vẫn clamp `GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH` tối đa 3.
- Chỉ mở các folder con có màu ở tầng đang xét; không crawl toàn bộ cây không màu.
- Phase hiện tại mở tuần tự các folder màu; nếu latency cao mới nên bổ sung concurrency có giới hạn.
- Nếu số folder màu quá lớn, có thể cap số folder màu được mở trong một Drive folder link và log `color_folder_scan_truncated=true`.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận response từ AI trong flow Pancake hiện có.
- Tách Drive file/folder link khỏi text trước khi gửi reply cho khách.
- Extract `drive_file_id` từ Drive file link trực tiếp.
- Extract `drive_folder_id` từ Drive folder link.
- List children của Drive folder bằng Google Drive API.
- Chỉ lấy page đầu tiên của mỗi folder lookup.
- Lọc ảnh hợp lệ `image/jpeg` và `image/png`.
- Lọc folder con hợp lệ `application/vnd.google-apps.folder`.
- Detect `requested_color` từ text reply nếu AI nhắc màu theo trigger hợp lệ.
- Với update dynamic color phrase, bắt cụm màu nằm sau chữ `màu` trong text AI, không bắt chữ không dấu `mau` để tránh hiểu sai ngữ nghĩa.
- Tạo `color_match_terms` từ cụm màu AI nói để match với tên ảnh và tên folder.
- Detect `drive_file_color` hoặc match term từ tên ảnh.
- Detect `drive_folder_color` hoặc match term từ tên folder con.
- Nếu không có `requested_color`, root folder có cả ảnh và folder con thì random giữa nhóm ảnh và nhóm folder.
- Nếu có `requested_color`, chọn ảnh hoặc folder dựa trên màu ở tên ảnh và tên folder.
- Từ tầng 2 trở đi, nếu folder hiện tại có ảnh phù hợp với rule hiện tại thì dùng ảnh ở folder hiện tại và dừng traversal.
- Nếu folder hiện tại không có ảnh và có nhiều folder con, chọn ngẫu nhiên một folder con để đi tiếp.
- Không đọc hết toàn bộ folder con.
- Không thử folder sibling khác nếu nhánh random không có ảnh.
- Fallback màu chỉ dùng ảnh trong các folder đã lookup thuộc nhánh đã chọn.
- Giới hạn traversal tối đa 3 tầng, tính root folder là tầng 1.
- Trả folder-level error rõ ràng nếu traversal dừng mà không có ảnh.
- Giữ metadata ảnh `id`, `name`, `mimeType`, `size` để flow cache, color filter và debug tiếp tục dùng được.
- Giữ metadata folder con `id`, `name`, `mimeType` để debug và chọn nhánh theo màu.
- Gửi text trước, gửi ảnh sau theo flow Pancake hiện tại.
- Log đủ thông tin để debug nhưng không log token hoặc dữ liệu nhạy cảm.

### Pancake

Pancake chịu trách nhiệm:

- Cung cấp Public API để upload file theo `page_id`.
- Trả về `content_id` sau khi upload thành công.
- Cung cấp Public API để gửi message có `content_ids` vào hội thoại.
- Không chịu trách nhiệm tìm ảnh trong Google Drive folder con.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Nhận text và context hội thoại đã được BE chuẩn hóa.
- Trả nội dung text cho khách.
- Trả Drive file link hoặc Drive folder link public nếu cần gửi ảnh sản phẩm.
- Không cần biết ảnh nằm trực tiếp trong root folder hay nằm trong folder con.
- Không cần chọn folder con.
- Không cần tự gọi Google Drive API hoặc Pancake Public API.
- Không cần biết `drive_file_id` hoặc `content_id`.

### Ngoài phạm vi phương án này

Các giới hạn dưới đây mô tả scope đã implement tới Phase 6. Phase 7 nới một phần scope theo hướng có kiểm soát: mở nhiều folder con có màu, nhưng vẫn không crawl toàn bộ cây Drive không giới hạn.

- Không xử lý ảnh/sticker/file do khách gửi vào.
- Không yêu cầu AI trả structured nested folder field riêng.
- Không crawl toàn bộ cây Drive folder.
- Không đọc hết tất cả folder con trong một tầng.
- Không thử nhiều nhánh folder con trong phase đầu.
- Không scan toàn bộ cây folder để fallback màu; fallback chỉ dùng ảnh trong `visited branch`.
- Không lấy page thứ hai trở đi nếu Google Drive API trả `nextPageToken`.
- Không truy cập tầng 4 trở lên.
- Không build màn hình quản lý folder traversal.
- Không đổi logic cache/download/upload Pancake sau khi đã chọn được `drive_file_id`.
- Không đổi endpoint gửi tin nhắn Pancake.
- Không fallback gửi raw Drive folder link cho khách trong phase này.

## Contract dữ liệu từ AI

AI có thể trả Drive folder link trỏ trực tiếp tới folder có ảnh:

```text
Em gửi chị ảnh mẫu này tham khảo ạ

https://drive.google.com/drive/folders/root_folder
```

Sau khi parse và lookup, nếu `root_folder` có ảnh trực tiếp, BE cần chuẩn bị object nội bộ tương đương:

```json
{
  "text": "Em gửi chị ảnh mẫu này tham khảo ạ",
  "drive_file_urls": [
    "https://drive.google.com/file/d/file_1/view",
    "https://drive.google.com/file/d/file_2/view"
  ],
  "drive_file_ids": ["file_1", "file_2"],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/root_folder"
  ],
  "drive_folder_error_count": 0
}
```

Nếu `root_folder` có cả ảnh và folder con, behavior phụ thuộc vào text AI:

- Không có `requested_color`: BE random giữa nhóm ảnh root và nhóm folder con. Nếu random chọn nhóm ảnh, BE chọn tối đa 3 ảnh root. Nếu random chọn nhóm folder, BE đi tiếp vào một folder con.
- Có `requested_color`: BE so sánh key màu của ảnh root và folder con. Ảnh match màu thì có thể được chọn trực tiếp; folder con match màu thì có thể được chọn để đi sâu. Nếu cả hai nhóm cùng match hoặc cùng không match, BE random giữa hai nhóm.

AI cũng có thể trả Drive folder link trỏ tới folder cha, bên trong có folder con:

```text
Em gửi chị album mẫu này tham khảo ạ

https://drive.google.com/drive/folders/root_folder
```

Ví dụ cấu trúc Drive:

```text
root_folder
  └── mau_do_folder
      ├── vay_da_hoi_do_1.jpg
      └── vay_da_hoi_do_2.jpg
```

Sau khi parse và lookup, nếu `root_folder` không có ảnh nhưng `mau_do_folder` có ảnh, BE cần chuẩn bị object nội bộ tương đương:

```json
{
  "text": "Em gửi chị album mẫu này tham khảo ạ",
  "drive_file_urls": [
    "https://drive.google.com/file/d/file_1/view",
    "https://drive.google.com/file/d/file_2/view"
  ],
  "drive_file_ids": ["file_1", "file_2"],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/root_folder"
  ],
  "drive_folder_results": [
    {
      "folder_id": "root_folder",
      "lookup_depth": 2,
      "visited_folder_ids": ["root_folder", "mau_do_folder"],
      "selected_child_folder_ids": ["mau_do_folder"],
      "images": [
        {
          "id": "file_1",
          "name": "vay_da_hoi_do_1.jpg",
          "mimeType": "image/jpeg"
        },
        {
          "id": "file_2",
          "name": "vay_da_hoi_do_2.jpg",
          "mimeType": "image/jpeg"
        }
      ]
    }
  ],
  "drive_folder_error_count": 0
}
```

Nếu traversal dừng mà không tìm được ảnh, BE vẫn giữ text reply nếu text hợp lệ và ghi lỗi cấp folder:

```json
{
  "text": "Em gửi chị album mẫu này tham khảo ạ",
  "drive_file_urls": [],
  "drive_file_ids": [],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/root_folder"
  ],
  "drive_folder_results": [
    {
      "folder_id": "root_folder",
      "lookup_depth": 3,
      "visited_folder_ids": ["root_folder", "child_a", "child_b"],
      "selected_child_folder_ids": ["child_a", "child_b"],
      "images": [],
      "error": "drive_folder_no_images_within_depth_limit"
    }
  ],
  "drive_folder_error_count": 1
}
```

Quy tắc:

- AI không cần trả folder con.
- AI không cần biết depth.
- AI không cần biết Drive API query.
- BE tự quyết định traversal sau khi nhận Drive folder link.
- Raw Drive folder link vẫn bị tách khỏi bot reply text trước khi gửi khách.
- Nếu response không có Drive file/folder link, flow Pancake text reply hiện tại không đổi.

## Tách Drive folder id và lookup folder con

Drive folder link mẫu:

```text
https://drive.google.com/drive/folders/root_folder
```

`drive_folder_id`:

```text
root_folder
```

BE tiếp tục dùng rule extract folder id hiện tại:

- URL phải dùng `https`.
- Host phải là `drive.google.com`.
- Path phải có segment `/drive/folders/{drive_folder_id}`.
- Folder id chỉ gồm ký tự hợp lệ theo pattern hiện tại.
- Link không hợp lệ tạo lỗi theo từng folder, không làm hỏng toàn bộ reply.

Sau khi có `drive_folder_id`, BE list children của folder bằng Google Drive API:

```text
GET https://www.googleapis.com/drive/v3/files
```

Query đề xuất:

```text
'{drive_folder_id}' in parents and trashed=false and (
  mimeType='image/jpeg'
  or mimeType='image/png'
  or mimeType='application/vnd.google-apps.folder'
)
```

Fields tối thiểu:

```text
nextPageToken,files(id,name,mimeType,size)
```

Quy tắc:

- Chỉ nhận ảnh `image/jpeg` và `image/png`.
- Chỉ nhận folder con `application/vnd.google-apps.folder`.
- Bỏ qua item thiếu `id`.
- Giữ `name`, `mimeType`, `size` để debug và color filter.
- Chỉ dùng page đầu tiên của response.
- Nếu response có `nextPageToken`, không gọi page tiếp theo; chỉ log/debug `page_truncated=true`.
- Không log `GOOGLE_DRIVE_API_KEY`; request Google Drive phải suppress log URL đầy đủ có query `key`.

## Quy tắc traversal folder

Root folder được tính là tầng 1.

BE truy cập tối đa 3 tầng:

```text
Tầng 1: root folder từ AI link
Tầng 2: folder con được chọn từ tầng 1 nếu cần đi sâu
Tầng 3: folder con được chọn từ tầng 2 nếu cần đi sâu
```

Traversal cần giữ lại các nhóm ảnh đã thấy trong `visited branch` để phục vụ fallback màu. `visited branch` chỉ gồm các folder đã thực sự lookup, không bao gồm sibling folder chưa mở.

### Dynamic color phrase matching

Phase 6.1 không phụ thuộc bắt buộc vào `DEFAULT_PANCAKE_IMAGE_COLOR_MAP` để hiểu màu. AI Agent thực tế thường trả màu ngay trong text sau chữ `màu`, ví dụ:

```text
Mẫu có màu **Đỏ đô, Kem** ạ.
```

```text
Dạ em gửi chị ảnh lookbook mẫu W2651713 màu **Hồng sen** ạ.
```

BE nên bắt cụm màu động từ text AI theo rule:

- Chỉ kích hoạt khi reply có Drive link và text có chữ `màu`.
- Không bắt trigger không dấu `mau`, vì chuỗi này có thể xuất hiện trong ngữ cảnh không phải màu.
- Lấy phần sau trigger màu cho tới dấu câu/ngắt câu/link tiếp theo.
- Bỏ markdown như `**`, `<...>`, khoảng trắng thừa.
- Bỏ từ đệm/cuối cụm như `ạ`, `nhé`, `nha` nếu chúng nằm sau tên màu.
- Nếu cụm màu có dấu phẩy, tách thành nhiều màu, ví dụ `Đỏ đô, Kem` -> `["Đỏ đô", "Kem"]`.
- Nếu cụm màu chỉ có một màu, ví dụ `Hồng sen`, giữ nguyên phrase đó.
- Không yêu cầu màu phải nằm trong `DEFAULT_PANCAKE_IMAGE_COLOR_MAP`.
- `PANCAKE_IMAGE_COLOR_MAP` nếu có chỉ đóng vai trò alias bổ trợ, không phải nguồn bắt buộc.

Với mỗi `requested_color_phrase`, BE tạo `color_match_terms` để match với tên ảnh và tên folder. Ví dụ `Hồng sen` nên tạo các term:

```text
hồng sen
hong sen
hongsen
hồng_sen
hong-sen
hồng
hong
sen
```

Rule match:

- Normalize text match theo hướng case-insensitive, bỏ dấu để có dạng không dấu, và coi separator `_`, `-`, khoảng trắng là tương đương.
- Ưu tiên match phrase đầy đủ trước: `hồng sen`, `hong sen`, `hongsen`, `hồng_sen`, `hong-sen`.
- Nếu không có match phrase đầy đủ, cho phép match từng từ lẻ: `hồng`, `hong`, `sen`.
- Áp dụng cùng một bộ `color_match_terms` cho cả tên ảnh và tên folder.
- Với nhiều màu trong text, ví dụ `Đỏ đô, Kem`, BE dùng union của tất cả `color_match_terms` để quyết định ảnh/folder nào là candidate đúng màu trong lúc traversal.
- Ở bước chọn ảnh gửi cho khách, nếu `requested_color_phrases` có nhiều hơn 1 màu, BE cần cố gắng cover đủ các màu AI nói trong phạm vi ảnh đã tìm thấy và trong giới hạn `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` vẫn là giới hạn tổng số ảnh cho mỗi Drive folder link. Nếu mặc định là 3 và AI nói `Đỏ đô, Kem`, BE chọn ngẫu nhiên tối đa 3 ảnh; nếu số candidate đủ 3 và cả hai màu đều có ảnh candidate thì kết quả phải có cả `Đỏ đô` và `Kem`, phân bổ có thể là 2 ảnh kem + 1 ảnh đỏ đô hoặc 2 ảnh đỏ đô + 1 ảnh kem.
- Nếu trong nhánh đã lookup không tìm thấy ảnh cho một màu còn lại, BE mới được gửi ảnh của một màu tìm thấy được, tối đa theo `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- Nếu số màu AI nói nhiều hơn `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`, BE ưu tiên cover màu theo thứ tự xuất hiện trong text AI cho đến khi hết slot.
- BE không mở sibling folder hoặc page sau chỉ để cover đủ màu; rule cover nhiều màu chỉ áp dụng trên ảnh candidate đã có trong nhánh/nhóm kết quả hiện tại hoặc fallback `visited branch`.
- Nếu tên ảnh/folder match nhiều màu, ưu tiên theo thứ tự màu xuất hiện trong text AI.

Ví dụ:

| Text AI | `requested_color_phrase` | Match tên ảnh/folder hợp lệ |
|---|---|---|
| `màu **Hồng sen**` | `Hồng sen` | `hong sen`, `hongsen`, `hồng_sen`, `hong-sen`, `hồng`, `hong`, `sen` |
| `màu **Đỏ đô, Kem**` | `Đỏ đô`, `Kem` | `do do`, `dodo`, `đỏ`, `do`, `kem` |

### Không có requested_color

Nếu AI reply chỉ có Drive folder link và không có key màu ảnh, BE xử lý như sau:

- Folder chỉ có ảnh: chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh.
- Folder chỉ có folder con: random một folder con để đi tiếp nếu chưa quá 3 tầng.
- Root folder có cả ảnh và folder con: random giữa hai nhóm `images` và `child_folders`.
- Nếu root random chọn `images`: chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh ở tầng 1 và dừng.
- Nếu root random chọn `child_folders`: random một folder con rồi lookup tiếp.
- Random giữa `images` và `child_folders` chỉ xảy ra tại tầng 1.
- Từ tầng 2 trở đi, nếu folder hiện tại có ảnh thì chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh ở folder đó và dừng.
- Từ tầng 2 trở đi, nếu folder hiện tại không có ảnh nhưng có folder con thì random một folder con để đi tiếp.

Pseudo-code không có màu:

```python
MAX_DEPTH = 3

current_folder_id = root_folder_id
visited_folder_ids = []
selected_child_folder_ids = []

for depth in range(1, MAX_DEPTH + 1):
    visited_folder_ids.append(current_folder_id)
    children = fetch_first_page_children(current_folder_id)

    images = [item for item in children if item.mimeType in {"image/jpeg", "image/png"}]
    child_folders = [
        item for item in children
        if item.mimeType == "application/vnd.google-apps.folder" and item.id
    ]

    if depth == 1 and images and child_folders:
        selected_group = random.choice(["images", "child_folders"])
        if selected_group == "images":
            return random_sample(images, limit=PANCAKE_INBOX_IMAGE_MAX_COUNT / PANCAKE_COMMENT_IMAGE_MAX_COUNT)
        selected_child = random.choice(child_folders)
        selected_child_folder_ids.append(selected_child.id)
        current_folder_id = selected_child.id
        continue

    if images:
        return random_sample(images, limit=PANCAKE_INBOX_IMAGE_MAX_COUNT / PANCAKE_COMMENT_IMAGE_MAX_COUNT)

    if not child_folders:
        return error("drive_folder_no_images")

    if depth == MAX_DEPTH:
        return error("drive_folder_no_images_within_depth_limit")

    selected_child = random.choice(child_folders)
    selected_child_folder_ids.append(selected_child.id)
    current_folder_id = selected_child.id
```

### Có requested_color

Nếu AI reply có Drive folder link và có màu ảnh, BE xử lý màu trên cả tên ảnh và tên folder con:

- Phase hiện tại: `matched_images` là ảnh trong folder hiện tại có `drive_file_color == requested_color`.
- Phase hiện tại: `matched_child_folders` là folder con trong folder hiện tại có `drive_folder_color == requested_color`.
- Update dynamic color phrase: `matched_images` là ảnh có tên match một trong các `color_match_terms`.
- Update dynamic color phrase: `matched_child_folders` là folder con có tên match một trong các `color_match_terms`.
- `fallback_images`: ảnh hợp lệ trong các folder thuộc `visited branch`, dùng khi không tìm được ảnh đúng màu.

Root folder có cả ảnh và folder con:

- Nếu ảnh có key màu, folder con không có key màu: chọn ảnh đúng màu.
- Nếu folder con có key màu, ảnh không có key màu: chọn một folder con đúng màu để đi tiếp.
- Nếu cả ảnh và folder con đều có key màu: random giữa nhóm ảnh đúng màu và nhóm folder con đúng màu.
- Nếu cả ảnh và folder con đều không có key màu: random giữa nhóm ảnh hiện có và nhóm folder con hiện có.
- Nếu random chọn ảnh nhưng ảnh không match màu, đây là fallback theo nhánh tầng 1; chọn ngẫu nhiên ảnh tầng 1.
- Nếu random chọn folder con, BE lookup tiếp trong folder con đó.

Từ tầng 2 trở đi:

- Nếu folder hiện tại có ảnh đúng màu: chọn ảnh đúng màu và dừng.
- Nếu folder hiện tại không có ảnh đúng màu nhưng có folder con đúng màu: chọn một folder con đúng màu để đi tiếp.
- Nếu không có match màu nào nhưng folder hiện tại có ảnh: lưu ảnh vào `fallback_images`.
- Nếu không có match màu nào nhưng còn folder con và chưa quá tầng 3: random một folder con để đi tiếp.
- Nếu không còn folder con, hoặc đã đến tầng 3, BE fallback chọn ngẫu nhiên ảnh từ `fallback_images`.

Pseudo-code có màu:

```python
MAX_DEPTH = 3

current_folder_id = root_folder_id
visited_folder_ids = []
selected_child_folder_ids = []
fallback_images = []

for depth in range(1, MAX_DEPTH + 1):
    visited_folder_ids.append(current_folder_id)
    children = fetch_first_page_children(current_folder_id)

    images = [item for item in children if item.mimeType in {"image/jpeg", "image/png"}]
    child_folders = [
        item for item in children
        if item.mimeType == "application/vnd.google-apps.folder" and item.id
    ]
    fallback_images.extend(images)

    matched_images = [image for image in images if image_name_matches_color_terms(image.name, color_match_terms)]
    matched_child_folders = [
        folder for folder in child_folders
        if folder_name_matches_color_terms(folder.name, color_match_terms)
    ]

    if depth == 1 and images and child_folders:
        if matched_images and not matched_child_folders:
            return select_color_images(matched_images)
        if matched_child_folders and not matched_images:
            selected_child = random.choice(matched_child_folders)
            selected_child_folder_ids.append(selected_child.id)
            current_folder_id = selected_child.id
            continue

        if matched_images and matched_child_folders:
            selected_group = random.choice(["images", "child_folders"])
            if selected_group == "images":
                return select_color_images(matched_images)
            selected_child = random.choice(matched_child_folders)
            selected_child_folder_ids.append(selected_child.id)
            current_folder_id = selected_child.id
            continue

        selected_group = random.choice(["images", "child_folders"])
        if selected_group == "images":
            return random_sample(images, limit=PANCAKE_INBOX_IMAGE_MAX_COUNT / PANCAKE_COMMENT_IMAGE_MAX_COUNT)
        selected_child = random.choice(child_folders)
        selected_child_folder_ids.append(selected_child.id)
        current_folder_id = selected_child.id
        continue

    if matched_images:
        return select_color_images(matched_images)

    if matched_child_folders and depth < MAX_DEPTH:
        selected_child = random.choice(matched_child_folders)
        selected_child_folder_ids.append(selected_child.id)
        current_folder_id = selected_child.id
        continue

    if child_folders and depth < MAX_DEPTH:
        selected_child = random.choice(child_folders)
        selected_child_folder_ids.append(selected_child.id)
        current_folder_id = selected_child.id
        continue

    if fallback_images:
        return random_sample(fallback_images, limit=PANCAKE_INBOX_IMAGE_MAX_COUNT / PANCAKE_COMMENT_IMAGE_MAX_COUNT)

    if child_folders and depth == MAX_DEPTH:
        return error("drive_folder_no_images_within_depth_limit")

    return error("drive_folder_no_images")
```

Quy tắc chung:

- BE không mở tất cả folder con để tìm folder nào có ảnh.
- BE không thử folder sibling nếu nhánh random không có ảnh.
- BE không truy cập tầng 4.
- BE không đọc page thứ hai trở đi.
- Nếu fallback màu chạy, chỉ dùng ảnh trong `visited branch`.
- Nếu Google Drive API trả `nextPageToken`, BE chỉ log `page_truncated=true`.

## Chọn ảnh gửi cho khách

Sau khi traversal tìm được danh sách ảnh hợp lệ, flow cache/download/upload/reuse Pancake giữ nguyên. Phần thay đổi chỉ nằm ở cách chọn danh sách ảnh trước khi đưa vào flow đó.

Nếu không có `requested_color`:

- Folder chỉ có ảnh: chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh.
- Root folder có cả ảnh và folder con: random giữa nhóm ảnh root và nhóm folder con.
- Nếu random chọn nhóm ảnh: chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh root.
- Nếu random chọn nhóm folder con: đi sâu vào một folder con; từ tầng 2 trở đi folder nào có ảnh thì lấy ảnh ở folder đó.

Nếu có `requested_color`:

- Folder chỉ có ảnh và toàn bộ ảnh không có key màu tương ứng: chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh.
- Folder chỉ có ảnh và có ảnh đúng màu: nếu số ảnh đúng màu `<= PANCAKE_INBOX_IMAGE_MAX_COUNT / PANCAKE_COMMENT_IMAGE_MAX_COUNT` thì chọn hết, nếu lớn hơn thì random theo giới hạn.
- Folder có cả ảnh và folder con: chọn nhóm ảnh hoặc nhóm folder theo key màu như phần traversal.
- Từ tầng 2 trở đi vẫn check key màu ở cả ảnh và folder con.
- Nếu đi hết nhánh đã chọn mà không có ảnh đúng màu, fallback chọn ngẫu nhiên ảnh trong `visited branch`.

Với update dynamic color phrase, các dòng trên vẫn giữ nguyên về traversal, nhưng khái niệm "đúng màu" đổi từ `drive_file_color == requested_color` sang "tên ảnh/folder match `color_match_terms` sinh từ cụm màu AI nói".

Nếu AI nói nhiều màu trong cùng cụm, bước chọn ảnh cuối cùng cần dùng strategy cover màu:

- Tách candidate ảnh theo từng `requested_color_phrase`, ví dụ `Đỏ đô` và `Kem`.
- Nếu số màu tìm thấy `<= PANCAKE_INBOX_IMAGE_MAX_COUNT / PANCAKE_COMMENT_IMAGE_MAX_COUNT`, chọn ít nhất 1 ảnh ngẫu nhiên cho mỗi màu tìm thấy.
- Sau khi đã cover mỗi màu tìm thấy 1 ảnh, fill các slot còn lại bằng ảnh ngẫu nhiên trong toàn bộ candidate đúng màu, không vượt `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- Với `PANCAKE_INBOX_IMAGE_MAX_COUNT=3 / PANCAKE_COMMENT_IMAGE_MAX_COUNT=3` và AI nói `Đỏ đô, Kem`, nếu cả hai màu đều có ảnh và tổng candidate đủ 3 thì BE gửi 3 ảnh có đủ cả hai màu; kết quả hợp lệ có thể là `2 đỏ đô + 1 kem` hoặc `1 đỏ đô + 2 kem`.
- Nếu chỉ tìm thấy ảnh `Đỏ đô` nhưng không có ảnh `Kem` trong nhánh/kết quả hiện tại, BE gửi ảnh `Đỏ đô` theo limit; ngược lại cũng tương tự.
- Nếu không có candidate đúng màu nào, mới dùng fallback ngẫu nhiên theo rule fallback hiện tại.

Nếu traversal không tìm được ảnh, BE không chạy cache/download/upload ảnh cho folder đó.

## Cache và local storage

Cache JSON dùng chung với flow Pancake Drive image hiện tại:

```text
storage/pancake_image_cache.json
```

File ảnh local vẫn lưu theo `drive_file_id`:

```text
storage/pancake_images/{drive_file_id}.jpg
```

Nested folder lookup không thay đổi key cache. Dù ảnh nằm ở folder con, cache vẫn dùng `drive_file_id`.

Metadata folder traversal chỉ dùng để debug và không bắt buộc là cache key.

Cache vẫn cần giữ các metadata hiện có:

- `drive_file_id`
- `drive_file_name`
- `drive_file_color`
- `drive_url`
- `direct_download_url`
- `local_path`
- `content_id`
- `mime_type`
- `size_bytes`
- `local_present`

Cache JSON vẫn cần atomic write hoặc lock để tránh hỏng file khi nhiều webhook chạy cùng lúc.

## Download ảnh từ Google Drive

Download ảnh vẫn dùng flow hiện tại sau khi BE đã chọn xong danh sách ảnh cần gửi.

Với ảnh đến từ nested Drive folder lookup, `drive_file_name`, `mimeType` và `size` đã có từ metadata Google Drive trước khi download.

BE chuyển `drive_file_id` tìm được thành Drive file link nội bộ:

```text
https://drive.google.com/file/d/{drive_file_id}/view
```

Các bước sau đó giữ nguyên:

- Convert Drive file link thành direct download URL.
- Download ảnh nếu local file chưa tồn tại hoặc cache chưa đủ điều kiện reuse.
- Validate content type ảnh.
- Resize/compress ảnh về dưới ngưỡng Pancake nếu cần.
- Lưu local theo `storage/pancake_images/{drive_file_id}.jpg`.
- Update cache theo `drive_file_id`.

## Reuse hoặc upload ảnh lên Pancake

Logic reuse/upload không đổi so với tài liệu gốc.

Trước khi upload file local, BE kiểm tra cache theo `drive_file_id`. Nếu cache đã có `content_id` và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, BE đưa `content_id` đó vào danh sách gửi ảnh, không upload lại.

Nếu chưa có `content_id` reusable hoặc reuse đang tắt, BE upload file local lên Pancake để lấy `content_id`, lưu lại vào cache, rồi gửi ảnh bằng `content_ids`.

Khi ghi `content_id` vào cache, BE cần merge vào entry hiện tại để không mất:

- `drive_file_name`
- `drive_file_color`
- `drive_url`
- `direct_download_url`
- `local_path`
- metadata size/mime

Nếu reuse bật và BE xóa file local sau upload thành công, cache vẫn giữ metadata ảnh để các lần sau debug và filter màu.

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
  "message": "Em gửi chị album mẫu này tham khảo ạ"
}
```

### Tin nhắn 2: ảnh

Nếu traversal tìm được ảnh, cache/download/upload/reuse thành công và có `content_ids`, BE gửi image message:

```json
{
  "action": "reply_inbox",
  "content_ids": [
    "CONTENT_ID_1",
    "CONTENT_ID_2"
  ]
}
```

Nếu traversal không tìm được ảnh hoặc tất cả ảnh lỗi, BE không gửi image message.

## Object nội bộ sau khi chuẩn bị reply

Object nội bộ sau khi BE parse response AI và lookup nested folder nên có dạng ổn định để dễ test:

| Field | Ý nghĩa |
|---|---|
| `text` | Text gửi ở tin nhắn đầu tiên, đã tách raw Drive link |
| `drive_file_urls` | Danh sách Drive file link extract trực tiếp hoặc tạo từ folder images |
| `drive_file_ids` | Danh sách id extract được từ `drive_file_urls` và folder selection |
| `drive_folder_urls` | Danh sách Drive folder link extract từ AI response |
| `drive_folder_results` | Kết quả lookup folder rút gọn để debug traversal |
| `drive_folder_error_count` | Số folder lookup có lỗi |
| `selected_drive_file_ids` | Danh sách ảnh được chọn sau filter/random |
| `image_limit` | Số ảnh tối đa được chọn cho mỗi Drive folder link |
| `content_ids` | Danh sách content id sau khi upload/reuse thành công |
| `errors` | Danh sách lỗi cấp link/folder/download/upload để log và debug |

Ví dụ:

```json
{
  "text": "Em gửi chị album mẫu này tham khảo ạ",
  "drive_file_urls": [
    "https://drive.google.com/file/d/file_1/view"
  ],
  "drive_file_ids": [
    "file_1"
  ],
  "drive_folder_urls": [
    "https://drive.google.com/drive/folders/root_folder"
  ],
  "drive_folder_results": [
    {
      "folder_id": "root_folder",
      "lookup_depth": 2,
      "visited_folder_ids": ["root_folder", "child_folder"],
      "selected_child_folder_ids": ["child_folder"],
      "root_selected_group": "child_folders",
      "selected_group": "color_images",
      "page_truncated": false,
      "images": [
        {
          "id": "file_1",
          "name": "vay_da_hoi_do.jpg",
          "mimeType": "image/jpeg",
          "drive_file_color": "do",
          "selected": true
        }
      ]
    }
  ],
  "drive_folder_error_count": 0,
  "selected_drive_file_ids": [
    "file_1"
  ],
  "image_limit": 3,
  "content_ids": [
    "CONTENT_ID_1"
  ],
  "errors": []
}
```

## Quy tắc xử lý message

BE nên áp dụng các rule sau:

Các rule bên dưới mô tả behavior đã implement tới Phase 6. Với Phase 7, các rule random một nhánh được thay bằng rule đa màu khi root có folder con detect được màu.

- Chỉ chạy nested folder lookup sau khi AI trả response thành công và response có Drive folder link.
- Drive file link trực tiếp không bị ảnh hưởng.
- Raw Drive link chỉ được tách khỏi bot reply text, không tách khỏi user message đã lưu.
- Mỗi Drive folder link được xử lý độc lập.
- Với mỗi Drive folder link, BE truy cập tối đa 3 tầng.
- Ở mỗi tầng, BE chỉ list current folder và chỉ lấy page đầu.
- Nếu không có `requested_color`, root folder có cả ảnh và folder con thì BE random giữa nhóm ảnh và nhóm folder con.
- Nếu có `requested_color`, BE xét key màu ở cả tên ảnh và tên folder con để quyết định chọn ảnh hay đi sâu.
- Với update dynamic color phrase, `requested_color` được sinh từ cụm màu sau chữ `màu`; tên ảnh/folder được match bằng `color_match_terms` thay vì bắt buộc phải có key trong color map.
- Random giữa nhóm ảnh và nhóm folder chỉ áp dụng tại tầng 1.
- Từ tầng 2 trở đi, nếu current folder có ảnh phù hợp với rule hiện tại thì BE dùng ảnh đó và dừng traversal cho folder link đó.
- Nếu current folder không có ảnh và có nhiều folder con, BE random một folder con.
- BE không thử sibling folder nếu nhánh random không có ảnh.
- Nếu color filter không tìm được ảnh đúng màu, fallback chỉ dùng ảnh trong `visited branch`.
- Nếu không tìm được ảnh, BE vẫn gửi text nếu text hợp lệ.
- Không gửi `content_ids` rỗng.
- Không lưu token hoặc direct auth data vào `Message.meta`.

## Lỗi và fallback

BE nên xử lý lỗi theo hướng không làm mất text reply:

- Folder link không hợp lệ: gửi text nếu text hợp lệ, log folder error.
- Thiếu `GOOGLE_DRIVE_API_KEY`: gửi text nếu text hợp lệ, log `missing_google_drive_api_key`.
- Google Drive API timeout/request error/HTTP error/invalid JSON: gửi text nếu text hợp lệ, log folder error.
- Folder không có ảnh và không có folder con: gửi text nếu text hợp lệ, log `drive_folder_no_images`.
- Tầng 3 không có ảnh nhưng vẫn còn folder con: gửi text nếu text hợp lệ, log `drive_folder_no_images_within_depth_limit`.
- Có `requested_color` nhưng nhánh đã lookup không có ảnh đúng màu: fallback random ảnh trong `visited branch` nếu nhánh đó từng có ảnh hợp lệ.
- Có `requested_color` nhưng nhánh đã lookup không có ảnh đúng màu và không có fallback image: gửi text nếu text hợp lệ, log folder error.
- Folder có nhiều page: chỉ dùng page đầu, log `page_truncated=true` nếu có `nextPageToken`.
- Download lỗi: bỏ qua ảnh đó, tiếp tục ảnh khác.
- Upload lỗi: bỏ qua `content_id` đó, tiếp tục ảnh khác.
- Tất cả ảnh lỗi: không gửi image message.
- Pancake gửi image message lỗi: log response rút gọn, không log token.

Nếu đã gửi text thành công nhưng traversal không tìm được ảnh, download lỗi, upload lỗi hoặc gửi ảnh lỗi, khách vẫn nhận được câu trả lời text. Đây là behavior chấp nhận được cho phase đầu.

## Lưu message vào database

User message vẫn lưu như flow Pancake hiện tại.

Bot text message nên lưu với `content` là text đã tách raw Drive link.

Metadata nên lưu rút gọn trong `meta` của bot message:

- `drive_folder_urls`
- `drive_folder_results`
- `drive_folder_error_count`
- `selected_drive_file_ids`
- `content_ids`
- response Pancake rút gọn

Không lưu file binary vào database.

Không lưu token Google Drive hoặc Pancake vào database.

## Cấu hình backend

Các cấu hình nên bổ sung:

- `GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH`: số tầng tối đa được phép truy cập khi lookup Drive folder, mặc định 3.

Giá trị `GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH` phải được clamp để tránh crawl sâu ngoài ý muốn:

- Min: 1.
- Max: 3 trong phase đầu.
- Default: 3.

Các cấu hình hiện có vẫn dùng chung:

- `GOOGLE_DRIVE_API_KEY`: dùng để lookup danh sách ảnh và folder con.
- `PANCAKE_IMAGE_CACHE_PATH`: mặc định `storage/pancake_image_cache.json`.
- `PANCAKE_IMAGE_STORAGE_DIR`: mặc định `storage/pancake_images`.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`: số ảnh tối đa chọn cho mỗi Drive folder link, mặc định 3.
- `PANCAKE_IMAGE_DOWNLOAD_TIMEOUT_SECONDS`: timeout download ảnh Drive.
- `PANCAKE_IMAGE_UPLOAD_TIMEOUT_SECONDS`: timeout upload ảnh Pancake.
- `PANCAKE_IMAGE_MAX_BYTES`: giới hạn kích thước ảnh tải về.
- `PANCAKE_IMAGE_STORAGE_MAX_BYTES`: giới hạn kích thước file ảnh lưu local để upload Pancake.
- `PANCAKE_REUSE_UPLOADED_CONTENT_ID`: bật/tắt việc dùng lại `content_id` đã lưu trong cache.

Các cấu hình Phase 7:

- `PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY`: strategy chọn ảnh Drive folder. Giá trị đề xuất mới là `color_diverse`; có thể giữ giá trị cũ như `single_branch_random` để rollback.
- `PANCAKE_DRIVE_COLOR_FOLDER_MAX_COUNT`: số folder màu tối đa được mở cho mỗi Drive folder link, mặc định 5.

Pagination không cấu hình trong phase đầu: chỉ lấy page đầu tiên.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/services/google_drive_image_service.py](../app/services/google_drive_image_service.py)
- [app/services/pancake_drive_image_service.py](../app/services/pancake_drive_image_service.py)
- [app/core/config.py](../app/core/config.py)
- [tests/test_google_drive_image_service.py](../tests/test_google_drive_image_service.py)
- [tests/test_pancake_drive_image_service.py](../tests/test_pancake_drive_image_service.py)
- [tests/test_pancake_webhook.py](../tests/test_pancake_webhook.py)

Nếu tách helper riêng để dễ test:

- `app/services/google_drive_folder_traversal_service.py`
- `tests/test_google_drive_folder_traversal_service.py`

## Checklist implementation tổng hợp

Các phase 0-5 bên dưới phản ánh phần nested lookup đã hoàn thành trước update rule chọn ảnh/folder theo màu. Yêu cầu mới trong tài liệu này cần thêm phase 6 để cập nhật selection behavior, chưa coi là đã implement.

### Phase 0. Chốt giải pháp

- [x] Chốt chỉ áp dụng nested folder lookup cho flow Pancake.
- [x] Chốt root folder là tầng 1.
- [x] Chốt max depth là 3 tầng.
- [x] Chốt behavior phase đầu: nếu current folder có ảnh thì dùng ảnh ở current folder và dừng traversal.
- [x] Chốt behavior phase đầu: nếu current folder không có ảnh và có nhiều folder con thì random 1 folder con.
- [x] Chốt không đọc hết tất cả folder con.
- [x] Chốt nếu Google Drive API phân trang thì chỉ lấy page đầu.
- [x] Chốt không fallback gửi raw Drive folder link cho khách trong phase này.

### Phase 1. List ảnh và folder con từ Google Drive

- [x] Thêm MIME type `application/vnd.google-apps.folder`.
- [x] Thêm query lấy cả JPG, PNG và folder con.
- [x] Chỉ fetch page đầu tiên của mỗi folder.
- [x] Giữ xử lý timeout, request error, HTTP error và invalid JSON như hiện tại.
- [x] Không log `GOOGLE_DRIVE_API_KEY` hoặc URL đầy đủ có query `key`.

### Phase 2. Traversal một nhánh tối đa 3 tầng

- [x] Implement traversal từ root folder với max depth 3.
- [x] Implement behavior phase đầu: nếu có ảnh ở current folder, return ảnh ngay.
- [x] Nếu không có ảnh và không có folder con, return `drive_folder_no_images`.
- [x] Nếu depth 3 vẫn không có ảnh nhưng còn folder con, return `drive_folder_no_images_within_depth_limit`.
- [x] Nếu còn depth và có folder con, random 1 folder con để đi tiếp.
- [x] Không thử sibling folder khác.
- [x] Ghi metadata `lookup_depth`, `visited_folder_ids`, `selected_child_folder_ids`, `page_truncated`.

### Phase 3. Tích hợp Pancake prepare reply

- [x] Pancake gọi nested folder lookup service từ prepare reply.
- [x] Ảnh tìm được ở folder con vẫn được chuyển thành Drive file view URL.
- [x] `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` vẫn áp dụng sau khi tìm được folder có ảnh.
- [x] Color filter vẫn dùng `drive_file_name` từ ảnh tìm được.
- [x] Nếu traversal không có ảnh, ghi lỗi vào `pancake_drive_reply.errors`.
- [x] Không chạy cache/download/upload nếu không tạo được `drive_file_urls`.

### Phase 4. Lưu message, fallback và logging

- [x] Lưu `drive_folder_results`, `drive_folder_error_count`, `selected_drive_file_ids` vào meta rút gọn.
- [x] Log `drive_folder_id`, `lookup_depth`, `visited_folder_ids`, `selected_child_folder_ids`, `image_count`, `child_folder_count`, `page_truncated`.
- [x] Log reason `drive_folder_no_images` và `drive_folder_no_images_within_depth_limit`.
- [x] Đảm bảo text vẫn gửi được khi nested lookup lỗi hoặc không có ảnh.
- [x] Không log token hoặc Google Drive API URL đầy đủ có `key`.

### Phase 5. Test và rollout

- [x] Test root folder có ảnh trực tiếp.
- [x] Test ảnh nằm ở child folder tầng 2.
- [x] Test ảnh nằm ở grandchild folder tầng 3.
- [x] Test không gọi tầng 4.
- [x] Test nhiều folder con chỉ random 1 folder con.
- [x] Test không thử sibling folder khác.
- [x] Test `nextPageToken` không tạo request page 2.
- [x] Test Pancake vẫn gửi text nếu nested lookup không có ảnh.
- [x] Test Pancake không cache/download/upload khi không có `drive_file_urls`.
- [x] Chạy `pytest -q`.

### Phase 6. Root random và color-aware folder selection

- [x] Nếu không có `requested_color` và root có cả ảnh/folder con, random giữa nhóm ảnh root và nhóm folder con.
- [x] Nếu không có `requested_color`, random giữa ảnh/folder chỉ xảy ra ở tầng 1.
- [x] Nếu không có `requested_color`, từ tầng 2 trở đi folder nào có ảnh thì chọn ảnh ở folder đó.
- [x] Nếu có `requested_color`, parse màu từ cả tên ảnh và tên folder con.
- [x] Nếu root có ảnh match màu nhưng folder con không match màu, chọn ảnh match màu.
- [x] Nếu root có folder con match màu nhưng ảnh không match màu, chọn folder con match màu.
- [x] Nếu root có cả ảnh và folder con cùng match màu, random giữa hai nhóm match.
- [x] Nếu root có cả ảnh và folder con cùng không match màu, random giữa hai nhóm hiện có.
- [x] Từ tầng 2 trở đi vẫn ưu tiên ảnh/folder con match màu.
- [x] Nếu không tìm được ảnh đúng màu trong nhánh đã lookup, fallback random ảnh trong `visited branch`.
- [x] Không mở sibling folder hoặc page sau để fallback màu.
- [x] Bổ sung test cho các case root random, color-aware folder name, và fallback trong visited branch.

### Phase 6.1. Dynamic color phrase extraction

- [x] Extract cụm màu động sau chữ `màu` trong text AI.
- [x] Không bắt trigger không dấu `mau`.
- [x] Hỗ trợ nhiều màu trong một cụm, ví dụ `Đỏ đô, Kem`.
- [x] Không yêu cầu màu phải có trong `DEFAULT_PANCAKE_IMAGE_COLOR_MAP`.
- [x] Tạo `color_match_terms` gồm phrase đầy đủ, dạng không dấu, dạng liền, dạng separator và token lẻ.
- [x] `Hồng sen` phải match được `hong sen`, `hongsen`, `hồng_sen`, `hong-sen`, `hồng sen`, `hồng`, `hong`, `sen`.
- [x] Dùng cùng `color_match_terms` để match tên ảnh và tên folder.
- [x] Nếu có nhiều màu, ưu tiên màu theo thứ tự xuất hiện trong text AI.
- [x] Nếu AI trả nhiều hơn 1 màu, bước chọn ảnh cuối cần cover đủ các màu tìm thấy trong candidate, không vượt `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- [x] Với `PANCAKE_INBOX_IMAGE_MAX_COUNT=3 / PANCAKE_COMMENT_IMAGE_MAX_COUNT=3` và AI trả `Đỏ đô, Kem`, nếu cả hai màu đều có ảnh candidate và tổng candidate đủ 3 thì gửi 3 ảnh có đủ cả hai màu, ví dụ `2 đỏ đô + 1 kem` hoặc `1 đỏ đô + 2 kem`.
- [x] Nếu chỉ tìm thấy ảnh cho một trong các màu AI nói, gửi ảnh màu tìm thấy theo limit thay vì ép lỗi hoặc mở sibling/page sau.
- [x] Giữ `PANCAKE_IMAGE_COLOR_MAP` như alias bổ trợ optional.
- [x] Bổ sung test cho mẫu AI trả `Đỏ đô, Kem` và `Hồng sen`.

### Phase 7. Color-diverse multi-folder selection

- [x] Không tạo `requested_color` từ câu hỏi `màu nào`.
- [x] Không coi danh sách màu trong text AI, ví dụ `Mẫu này có 3 màu: Be, Xanh biển, Tím`, là điều kiện bắt buộc để chọn ảnh.
- [x] Detect màu từ tên folder con như `be`, `xanh`, `tím`, `S2650543 BE`, `S2650543 HỒNG`.
- [x] Nếu root có nhiều folder con có màu, mở tất cả folder màu trong giới hạn depth/page/cap thay vì random một folder.
- [x] Ảnh trong folder màu được kế thừa màu folder khi filename không có màu.
- [x] Ưu tiên folder màu hơn ảnh root khi chọn ảnh đại diện màu.
- [x] Pass 1 chọn ngẫu nhiên 1 ảnh cho mỗi màu tìm được, không vượt image limit.
- [x] Pass 2 fill random từ ảnh còn lại cho đủ `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- [x] Nếu không có folder màu, dùng ảnh root và group theo màu filename nếu detect được.
- [x] Nếu một folder màu không có ảnh hợp lệ hoặc lookup lỗi, bỏ qua folder đó và tiếp tục các folder/fallback khác.
- [x] Log metadata mới: số folder màu detect được, folder màu đã mở, màu đã cover, số ảnh fill random, và reason khi scan bị truncate.
- [x] Bổ sung config rollback/cap để kiểm soát latency: `PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY`, `PANCAKE_DRIVE_COLOR_FOLDER_MAX_COUNT`.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp Pancake nested Drive folder lookup](pancake-drive-folder-nested-image-lookup-task-list/phase-0.md)
- [Phase 1. List ảnh và folder con từ Google Drive](pancake-drive-folder-nested-image-lookup-task-list/phase-1.md)
- [Phase 2. Traversal một nhánh tối đa 3 tầng](pancake-drive-folder-nested-image-lookup-task-list/phase-2.md)
- [Phase 3. Tích hợp Pancake prepare reply](pancake-drive-folder-nested-image-lookup-task-list/phase-3.md)
- [Phase 4. Lưu message, fallback và logging](pancake-drive-folder-nested-image-lookup-task-list/phase-4.md)
- [Phase 5. Test và rollout](pancake-drive-folder-nested-image-lookup-task-list/phase-5.md)
- [Phase 6. Root random và color-aware folder selection](pancake-drive-folder-nested-image-lookup-task-list/phase-6.md)
- [Phase 7. Color-diverse multi-folder selection](pancake-drive-folder-nested-image-lookup-task-list/phase-7.md)

## Test cần có khi implement

- Root folder chỉ có ảnh trực tiếp thì chỉ gọi Drive API 1 lần và chọn ngẫu nhiên tối đa 3 ảnh root.
- Không có `requested_color`, root folder có cả ảnh và folder con, random chọn nhóm ảnh thì trả ảnh root và không đi sâu.
- Không có `requested_color`, root folder có cả ảnh và folder con, random chọn nhóm folder thì đi vào một folder con.
- Không có `requested_color`, từ tầng 2 trở đi nếu folder có ảnh thì trả ảnh ở folder đó, không random giữa ảnh và folder con nữa.
- Root folder không có ảnh, có một child folder chứa ảnh thì gọi 2 lần và trả ảnh child.
- Root folder không có ảnh, child folder không có ảnh, grandchild folder có ảnh thì gọi 3 lần và trả ảnh grandchild.
- Root folder không có ảnh, có nhiều child folders thì chỉ chọn 1 child folder để đi tiếp.
- Nếu child folder được chọn không có ảnh, BE không thử sibling folder khác.
- Tối đa 3 tầng; không gọi tầng 4.
- Nếu folder hiện tại trả `nextPageToken`, BE không gọi page 2.
- Nếu folder không có ảnh và không có folder con, trả `drive_folder_no_images`.
- Nếu tầng 3 không có ảnh nhưng vẫn còn folder con chưa được mở, trả `drive_folder_no_images_within_depth_limit`.
- Pancake vẫn gửi text nếu nested lookup không tìm được ảnh.
- Pancake không chạy cache/download/upload khi nested lookup không tạo được `drive_file_urls`.
- Có `requested_color`, folder chỉ có ảnh và không ảnh nào match màu thì chọn ngẫu nhiên tối đa 3 ảnh.
- Có `requested_color`, folder chỉ có ảnh và số ảnh match màu `<= 3` thì chọn hết ảnh match.
- Có `requested_color`, folder chỉ có ảnh và số ảnh match màu `> 3` thì random 3 ảnh match.
- Có `requested_color`, root có ảnh match màu và folder con không match màu thì chọn ảnh.
- Có `requested_color`, root có folder con match màu và ảnh không match màu thì chọn folder con.
- Có `requested_color`, root có cả ảnh và folder con match màu thì random giữa nhóm ảnh match và folder match.
- Có `requested_color`, root có cả ảnh và folder con nhưng không nhóm nào match màu thì random giữa nhóm ảnh và folder, sau đó fallback chỉ trong nhánh đã lookup.
- Có `requested_color`, từ tầng 2 trở đi vẫn dùng `drive_file_name` và `drive_folder_name` để detect màu.
- Dynamic color phrase: `màu Hồng sen` match được tên ảnh/folder có `hong sen`, `hongsen`, `hồng_sen`, `hong-sen`, `hồng sen`, `hồng`, `hong`, `sen`.
- Dynamic color phrase: `màu Đỏ đô, Kem` tạo được nhiều màu và match tên ảnh/folder theo từng màu.
- Dynamic color phrase: `màu Đỏ đô, Kem` với limit 3 và có ảnh cả hai màu thì chọn 3 ảnh có đủ cả `Đỏ đô` và `Kem`.
- Dynamic color phrase: `màu Đỏ đô, Kem` với limit 3 nhưng chỉ có ảnh `Đỏ đô` trong nhánh/kết quả hiện tại thì gửi tối đa 3 ảnh `Đỏ đô`, không mở sibling/page sau chỉ để tìm `Kem`.
- Dynamic color phrase: nếu số màu AI nói nhiều hơn limit thì ưu tiên cover màu theo thứ tự xuất hiện trong text AI.
- Dynamic color phrase không phụ thuộc màu có sẵn trong `DEFAULT_PANCAKE_IMAGE_COLOR_MAP`.
- Color fallback không mở sibling folder và không đọc page sau.
- Phase 7: câu `Chị thích màu nào để em check size/còn hàng...` không tạo màu `conhangchominh` hoặc bất kỳ `requested_color` nào.
- Phase 7: root có folder `be`, `xanh`, `tím` thì mở cả 3 folder và chọn ít nhất 1 ảnh mỗi màu nếu mỗi folder có ảnh hợp lệ.
- Phase 7: root có `S2650543 BE`, `S2650543 HỒNG`, `S2650543 ĐEN` và một số ảnh root thì chọn ảnh từ 3 folder màu trước, sau đó fill random từ ảnh còn lại nếu chưa đủ limit.
- Phase 7: với limit 5, có 3 ảnh xanh và 4 ảnh đỏ thì chọn 1 xanh + 1 đỏ + 3 ảnh random còn lại.
- Phase 7: folder màu rỗng không làm fail toàn bộ lookup; BE vẫn gửi text và các ảnh hợp lệ tìm được.
- Phase 7: nếu không có folder màu, root images được group theo `drive_file_color` từ filename rồi chọn đa màu.
- Phase 7: nếu số màu tìm được nhiều hơn limit, chọn tối đa limit màu theo thứ tự ổn định hoặc thứ tự folder/file trong Drive response sau khi shuffle trong từng màu.
- Cache item sau nested lookup vẫn dùng key `drive_file_id`.
- Ghi `content_id` sau upload không làm mất metadata ảnh.

## Ghi chú production

- Cấu trúc Google Drive folder là yếu tố quan trọng. Nếu ảnh nằm ở sibling folder khác với nhánh random, phase đầu có thể không tìm thấy ảnh dù folder cha vẫn có ảnh ở nhánh khác.
- Quyết định chỉ random một nhánh giúp giới hạn latency và số request, nhưng không đảm bảo tìm ảnh nếu folder tree không đồng đều.
- Khi root folder có cả ảnh và folder con, request không có key màu có thể trả ảnh root hoặc ảnh trong folder con tùy kết quả random.
- Khi request có key màu, tên folder con có thể ảnh hưởng hướng traversal giống như tên file ảnh ảnh hưởng selection.
- Dynamic color phrase giúp giảm nhu cầu update code/config mỗi khi AI nói màu mới như `Đỏ đô`, `Hồng sen`, `Xanh mint`.
- Với nhiều màu trong một reply, BE cố cover đủ màu trong số ảnh candidate đã tìm thấy và trong giới hạn gửi ảnh; rule này không đảm bảo cover màu nằm ở sibling folder hoặc page sau chưa được lookup.
- Cho phép match token lẻ như `hong`, `hồng`, `sen` giúp folder/file cũ vẫn được chọn dù naming không đầy đủ phrase, nhưng có thể tăng khả năng match rộng hơn mong muốn nếu tên file/folder chứa từ lẻ không phải màu.
- Fallback màu chỉ dựa trên ảnh trong `visited branch`; nếu ảnh đúng màu nằm ở sibling folder chưa mở thì phase này không tìm thấy.
- Quyết định chỉ lấy page đầu giúp tránh đọc folder quá lớn, nhưng nếu ảnh hoặc folder con cần tìm nằm ở page sau thì phase đầu sẽ không thấy.
- Với một Drive folder link, số request Google Drive API tối đa là 3.
- Với nhiều Drive folder link trong một reply, số request tối đa xấp xỉ `folder_count * 3`.
- Nên log đủ `visited_folder_ids` và `selected_child_folder_ids` để debug tại sao không gửi ảnh.
- Cache JSON cần atomic write hoặc lock vì webhook có thể xử lý đồng thời.
- Khi `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, file local có thể bị xóa sau upload; metadata ảnh trong cache vẫn cần được giữ.
- Nếu sau rollout thấy nhiều lỗi do random chọn nhánh không có ảnh trong khi sibling có ảnh, cần mở rộng requirement sang scan nhiều nhánh có giới hạn.
- Phase 7 giải quyết chính limitation random một nhánh bằng cách scan các folder có màu trước. Rủi ro mới là số request Google Drive tăng theo số folder màu, nên cần log/cap để tránh latency cao.
