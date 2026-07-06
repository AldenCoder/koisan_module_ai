# Task List Phase 6: Root random và color-aware folder selection

## Mục tiêu

Phase 6 cập nhật logic chọn ảnh/folder cho Pancake nested Drive folder lookup sau khi `BE` đã list được cả ảnh và folder con trong mỗi tầng.

Kết quả mong muốn:

- Nếu AI reply không có key màu, root folder có cả ảnh và folder con thì `BE` random giữa nhóm ảnh root và nhóm folder con.
- Nếu AI reply có key màu, `BE` dùng key màu từ cả tên ảnh và tên folder con để quyết định chọn ảnh hay đi sâu.
- Random giữa nhóm ảnh và nhóm folder chỉ xảy ra tại tầng 1.
- Từ tầng 2 trở đi, folder nào có ảnh phù hợp với rule hiện tại thì lấy ảnh ở folder đó.
- Fallback màu chỉ dùng ảnh trong nhánh đã lookup, không scan toàn bộ cây folder.

## Đầu vào đã chốt

- Chỉ áp dụng cho flow Pancake.
- Max depth là 3 tầng, root folder là tầng 1.
- Mỗi folder lookup chỉ lấy page đầu tiên.
- Không thử sibling folder khác nếu nhánh đang đi không có ảnh đúng màu.
- Không mở page sau để fallback.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` mặc định là 3 và vẫn là giới hạn số ảnh chọn.
- `requested_color` hiện tại detect từ text reply theo rule của [pancake-drive-image-color-filter.md](../pancake-drive-image-color-filter.md).
- Update tiếp theo cần đổi sang dynamic color phrase extraction: bắt cụm màu sau chữ `màu`, không bắt chữ không dấu `mau`, không yêu cầu màu có sẵn trong `DEFAULT_PANCAKE_IMAGE_COLOR_MAP`.
- Fallback "lấy ngẫu nhiên ảnh ở tầng 1/2/3" chỉ dùng ảnh trong `visited branch`, không dùng toàn bộ cây folder.

## Ngoài phạm vi Phase 6

- Không đổi flow Drive file link trực tiếp.
- Không đổi endpoint gửi Pancake message.
- Không đổi cache key theo `drive_file_id`.
- Không scan toàn bộ folder tree.
- Không đọc tất cả sibling folder để tìm ảnh đúng màu.
- Không đọc page thứ hai trở đi khi Google Drive API trả `nextPageToken`.
- Không dùng computer vision để nhận diện màu trong ảnh.
- Không yêu cầu AI trả structured color hoặc folder field mới.
- Không yêu cầu update code/config mỗi khi AI nói một tên màu mới nếu tên màu đó có thể match trực tiếp với tên ảnh/folder sau normalize.

## File chính dự kiến sửa

- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_drive_image_service.py](../../app/services/pancake_drive_image_service.py), nếu cần cập nhật metadata ảnh/folder.
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

Nếu tách helper để dễ test:

- `app/services/google_drive_folder_selection_service.py`
- `tests/test_google_drive_folder_selection_service.py`

## Checklist

### 1. Chuẩn hóa dữ liệu ảnh và folder con

- [x] Giữ danh sách `images` và `child_folders` sau mỗi lần list children.
- [x] Với ảnh, giữ `id`, `name`, `mimeType`, `size`.
- [x] Với folder con, giữ `id`, `name`, `mimeType`.
- [x] Parse `drive_file_color` từ tên ảnh bằng logic màu hiện có.
- [x] Parse `drive_folder_color` từ tên folder con bằng cùng bảng màu.
- [x] Bỏ qua ảnh/folder thiếu `id`.
- [x] Không log Google Drive API key hoặc URL đầy đủ có query `key`.

Kết quả mong muốn:
  Selection layer có đủ metadata để quyết định theo ảnh, folder và màu.

### 2. Logic không có requested_color

- [x] Folder chỉ có ảnh: chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh.
- [x] Folder chỉ có folder con: random một folder con để đi tiếp nếu chưa quá depth 3.
- [x] Root folder có cả ảnh và folder con: random giữa nhóm `images` và nhóm `child_folders`.
- [x] Nếu root random chọn nhóm `images`, chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh root và dừng.
- [x] Nếu root random chọn nhóm `child_folders`, random một folder con rồi lookup tiếp.
- [x] Random giữa `images` và `child_folders` chỉ chạy tại depth 1.
- [x] Từ depth 2 trở đi, nếu folder hiện tại có ảnh thì chọn ảnh ở folder đó và dừng.
- [x] Từ depth 2 trở đi, nếu folder hiện tại không có ảnh nhưng có folder con thì random một folder con để đi tiếp.

Kết quả mong muốn:
  Request không có màu có thể trả ảnh root hoặc ảnh trong folder con khi root có cả hai nhóm, nhưng không random ảnh/folder từ tầng 2 trở đi.

### 3. Logic có requested_color tại root folder

- [x] Tính `matched_images` từ ảnh root có `drive_file_color == requested_color`.
- [x] Tính `matched_child_folders` từ folder con root có `drive_folder_color == requested_color`.
- [x] Nếu ảnh root match màu và folder con không match màu, chọn ảnh match màu.
- [x] Nếu folder con match màu và ảnh root không match màu, chọn một folder con match màu để đi tiếp.
- [x] Nếu cả ảnh root và folder con đều match màu, random giữa nhóm ảnh match và nhóm folder match.
- [x] Nếu cả ảnh root và folder con đều không match màu, random giữa nhóm ảnh hiện có và nhóm folder hiện có.
- [x] Nếu random chọn nhóm ảnh không match màu, chọn ngẫu nhiên tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh root như fallback tầng 1.
- [x] Nếu random chọn nhóm folder, lookup tiếp trong folder con được chọn.

Kết quả mong muốn:
  Root folder dùng được cả tên ảnh và tên folder để chọn đúng hướng khi AI có key màu.

### 4. Logic có requested_color từ depth 2 trở đi

- [x] Ở mỗi tầng, vẫn tính `matched_images` theo tên ảnh.
- [x] Ở mỗi tầng, vẫn tính `matched_child_folders` theo tên folder con.
- [x] Nếu có ảnh đúng màu, chọn ảnh đúng màu và dừng.
- [x] Nếu không có ảnh đúng màu nhưng có folder con đúng màu và còn depth, chọn một folder con đúng màu để đi tiếp.
- [x] Nếu không có match màu nào nhưng có folder con và còn depth, random một folder con để đi tiếp.
- [x] Nếu không có match màu nào và không còn folder con, chuyển sang fallback màu.
- [x] Nếu đang ở depth 3 và vẫn cần đi sâu hơn để tìm match màu, không gọi depth 4.

Kết quả mong muốn:
  Từ tầng 2 trở đi vẫn color-aware, nhưng vẫn giữ giới hạn một nhánh và tối đa 3 tầng.

### 5. Fallback màu trong visited branch

- [x] Trong quá trình lookup, lưu ảnh hợp lệ của từng folder đã truy cập vào `fallback_images`.
- [x] `fallback_images` chỉ gồm ảnh trong `visited_folder_ids`.
- [x] Nếu không tìm được ảnh đúng màu sau khi đi hết nhánh, random tối đa `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` ảnh từ `fallback_images`.
- [x] Không mở sibling folder để tìm fallback image.
- [x] Không gọi page 2 để tìm fallback image.
- [x] Nếu `fallback_images` rỗng, trả folder error như hiện tại.
- [x] Ghi `color_filter_reason` hoặc metadata tương ứng để biết đã dùng fallback.

Kết quả mong muốn:
  Fallback đúng theo chốt: chỉ lấy ảnh trong nhánh đã lookup, không phải toàn bộ cây folder.

### 6. Metadata và logging

- [x] Ghi `lookup_depth` theo folder cuối cùng được dùng hoặc depth dừng traversal.
- [x] Ghi `visited_folder_ids`.
- [x] Ghi `selected_child_folder_ids`.
- [x] Ghi `root_selected_group` tại root nếu root random giữa ảnh/folder.
- [x] Ghi `selected_group` cho nhóm ảnh cuối cùng được dùng.
- [x] Ghi `requested_color` nếu có.
- [x] Ghi số lượng `matched_images` và `matched_child_folders` ở các điểm quyết định chính.
- [x] Ghi `color_fallback_used=true` nếu fallback màu chạy.
- [x] Ghi `page_truncated=true` nếu Google Drive trả `nextPageToken`.
- [x] Không log token hoặc dữ liệu nhạy cảm.

Kết quả mong muốn:
  Debug được vì sao BE chọn ảnh root, đi vào folder con, hoặc fallback ảnh trong nhánh.

### 7. Tích hợp Pancake prepare reply

- [x] `PreparedPancakeDriveReply.drive_file_urls` chỉ nhận ảnh đã được selection layer chọn.
- [x] `selected_drive_file_ids` phản ánh đúng ảnh sau root random/color/fallback.
- [x] `drive_file_metadata` giữ `drive_file_name` và `drive_file_color`.
- [x] Nếu selection chọn folder con, ảnh tìm được ở folder con vẫn chuyển thành Drive file view URL.
- [x] Nếu selection không tìm được ảnh, không chạy cache/download/upload.
- [x] Drive file link trực tiếp vẫn không bị ảnh hưởng.

Kết quả mong muốn:
  Pancake flow phía sau không cần biết ảnh được chọn từ root, folder con, color match hay fallback.

### 8. Test không có requested_color

- [x] Test folder chỉ có ảnh chọn ngẫu nhiên tối đa 3 ảnh.
- [x] Test folder có ít hơn 3 ảnh thì chọn hết số ảnh có.
- [x] Test root có cả ảnh và folder con, random chọn ảnh thì không lookup folder con.
- [x] Test root có cả ảnh và folder con, random chọn folder thì lookup folder con.
- [x] Test random giữa ảnh/folder chỉ xảy ra tại root.
- [x] Test depth 2 có cả ảnh và folder con thì chọn ảnh depth 2, không random đi sâu.
- [x] Test depth 3 có ảnh thì chọn ảnh depth 3.
- [x] Test depth 3 không có ảnh nhưng có folder con không gọi depth 4.

Kết quả mong muốn:
  Behavior request không màu đúng với rule root-only random.

### 9. Test có requested_color

- [x] Test root ảnh match màu, folder con không match màu thì chọn ảnh.
- [x] Test root folder con match màu, ảnh không match màu thì đi vào folder con.
- [x] Test root cả ảnh và folder con match màu thì random giữa hai nhóm match.
- [x] Test root cả ảnh và folder con không match màu thì random giữa hai nhóm hiện có.
- [x] Test folder chỉ có ảnh, không ảnh nào match màu thì random tối đa 3 ảnh.
- [x] Test folder chỉ có ảnh, số ảnh match màu `<= 3` thì chọn hết.
- [x] Test folder chỉ có ảnh, số ảnh match màu `> 3` thì random 3.
- [x] Test depth 2 folder con match màu được ưu tiên khi chưa có ảnh đúng màu.
- [x] Test depth 2 ảnh đúng màu được chọn và không đi sâu.
- [x] Test depth 3 không có ảnh đúng màu thì fallback trong visited branch.
- [x] Test fallback không mở sibling folder.
- [x] Test fallback không gọi page 2.

Kết quả mong muốn:
  Behavior request có màu đúng với rule color-aware theo tên ảnh và tên folder.

### 10. Regression và command verify

- [x] Test Drive file link trực tiếp không đổi.
- [x] Test AI reply không Drive link không gọi Drive lookup.
- [x] Test text vẫn gửi được khi folder lookup không tìm được ảnh.
- [x] Test cache/download/upload chỉ chạy khi có `drive_file_urls`.
- [x] Test cache reuse `content_id` không đổi.
- [x] Chạy `pytest -q`.

Kết quả mong muốn:
  Thay đổi selection không làm hỏng flow Pancake hiện tại.

### 11. Dynamic color phrase extraction

- [x] Bắt cụm màu sau chữ `màu` trong text AI khi reply có Drive link.
- [x] Không bắt trigger không dấu `mau` để tránh hiểu sai ngữ nghĩa.
- [x] Bỏ markdown như `**`, wrapper link `<...>` và khoảng trắng thừa trước khi parse màu.
- [x] Dừng cụm màu ở dấu câu hoặc đoạn text kết thúc cụm màu.
- [x] Bỏ từ đệm/cuối cụm như `ạ`, `nhé`, `nha` nếu chúng nằm sau tên màu.
- [x] Hỗ trợ cụm nhiều màu tách bằng dấu phẩy, ví dụ `Đỏ đô, Kem` -> `["Đỏ đô", "Kem"]`.
- [x] Hỗ trợ cụm một màu nhiều từ, ví dụ `Hồng sen` -> `["Hồng sen"]`.
- [x] Không yêu cầu màu nằm trong `DEFAULT_PANCAKE_IMAGE_COLOR_MAP`.
- [x] Tạo `color_match_terms` từ mỗi màu gồm phrase đầy đủ có dấu, phrase không dấu, dạng liền, dạng separator `_`/`-`, và từng từ lẻ.
- [x] Với `Hồng sen`, match được `hồng sen`, `hong sen`, `hongsen`, `hồng_sen`, `hong-sen`, `hồng`, `hong`, `sen`.
- [x] Với `Đỏ đô`, match được phrase đầy đủ và token lẻ như `đỏ`, `đô`, `do`.
- [x] Dùng cùng `color_match_terms` để match tên ảnh và tên folder.
- [x] Nếu nhiều màu cùng xuất hiện, ưu tiên màu theo thứ tự AI nói.
- [x] Nếu AI trả nhiều hơn 1 màu, selection layer cần cố cover đủ các màu tìm thấy trong candidate, không vượt `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- [x] Với `PANCAKE_INBOX_IMAGE_MAX_COUNT=3 / PANCAKE_COMMENT_IMAGE_MAX_COUNT=3` và AI trả `Đỏ đô, Kem`, nếu cả hai màu đều có ảnh candidate và tổng candidate đủ 3 thì gửi 3 ảnh có đủ cả hai màu; phân bổ có thể là `2 đỏ đô + 1 kem` hoặc `1 đỏ đô + 2 kem`.
- [x] Nếu chỉ tìm thấy ảnh cho một trong các màu AI nói, gửi ảnh màu tìm thấy theo limit; không mở sibling folder hoặc page sau chỉ để tìm màu còn lại.
- [x] Nếu số màu AI nói nhiều hơn `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`, ưu tiên cover màu theo thứ tự xuất hiện trong text AI.
- [x] Nếu tên ảnh/folder match phrase đầy đủ và token lẻ cùng lúc, ưu tiên phrase đầy đủ.
- [x] Giữ `PANCAKE_IMAGE_COLOR_MAP` như alias bổ trợ optional cho synonym đặc biệt.
- [x] Nếu không match được dynamic term nào trong nhánh đã lookup, fallback vẫn chỉ dùng ảnh trong `visited branch`.
- [x] Bổ sung test cho mẫu AI `Mẫu có màu **Đỏ đô, Kem** ạ`.
- [x] Bổ sung test multi-color coverage cho `Mẫu có màu **Đỏ đô, Kem** ạ` với limit 3 và có ảnh cả hai màu.
- [x] Bổ sung test multi-color partial coverage cho case chỉ có ảnh một màu trong nhánh/kết quả hiện tại.
- [x] Bổ sung test cho mẫu AI `màu **Hồng sen**`.
- [x] Bổ sung test tên ảnh/folder chỉ có token lẻ `hong` vẫn match `Hồng sen`.
- [x] Bổ sung regression test màu cũ trong `DEFAULT_PANCAKE_IMAGE_COLOR_MAP` vẫn hoạt động.

Kết quả mong muốn:
  BE chọn được ảnh/folder theo màu AI nói mà không phải update map/code thường xuyên cho các màu mới; khi AI nói nhiều màu, ảnh gửi ra cố cover đủ các màu tìm thấy trong candidate và vẫn giữ giới hạn gửi ảnh.

## Acceptance criteria

- [x] Request không màu xử lý đúng 2 case: folder có cả ảnh/folder con và folder chỉ có ảnh.
- [x] Request có màu xử lý đúng rule chọn ảnh/folder theo key màu ở root.
- [x] Từ depth 2 trở đi vẫn check key màu trên cả ảnh và folder.
- [x] Fallback màu chỉ dùng ảnh trong `visited branch`.
- [x] Không scan sibling folder, không đọc page sau, không truy cập depth 4.
- [x] `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` vẫn giới hạn số ảnh gửi.
- [x] Test mới pass và regression test pass.
- [x] Dynamic color phrase không phụ thuộc màu có trong `DEFAULT_PANCAKE_IMAGE_COLOR_MAP`.
- [x] Dynamic color phrase match được cả phrase đầy đủ và token lẻ theo rule đã chốt.

## Ghi chú mở

- Nên inject hoặc mock random trong test để kiểm soát branch chọn ảnh/folder.
- Nếu production cần ưu tiên folder màu hơn ảnh màu khi cả hai cùng match, đó là requirement khác; phase này đang chốt random giữa hai nhóm.
- Nếu cần fallback tìm ảnh đúng màu ở sibling folder, phải mở rộng sang scan nhiều nhánh có giới hạn và đánh giá lại latency.
- Multi-color coverage chỉ cover trong candidate đã tìm thấy; nếu màu còn lại nằm ở sibling folder hoặc page sau thì phase này vẫn không mở thêm để tìm.
- Match token lẻ giúp tăng recall cho dữ liệu Drive cũ, nhưng có thể tạo match rộng hơn. Nếu production gặp false positive, cần thêm scoring: phrase đầy đủ > token màu chính > token lẻ phụ.
