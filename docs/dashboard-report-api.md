# API báo cáo dashboard

## Mục tiêu

Tài liệu này mô tả phương án để `BE` cung cấp API báo cáo cho màn hình dashboard. `FE` tự thiết kế giao diện, còn `BE` trả dữ liệu đã aggregate sẵn từ các collection hiện có để vẽ card, biểu đồ và danh sách cảnh báo.

Điểm thay đổi chính: thêm một nhóm API dashboard gồm API list `page_id`, API lấy dữ liệu JSON và API export Excel. API JSON và API export dùng chung bộ lọc thời gian `from_date` / `to_date` và dùng chung service tính toán để số liệu trên màn hình và file Excel không bị lệch.

MVP chỉ tập trung các dữ liệu đang có sẵn:

- Tổng số tin nhắn.
- Tổng tin nhắn text.
- Tổng tin nhắn ảnh.
- Biểu đồ tin nhắn theo ngày.
- Cảnh báo hội thoại cần nhân viên hỗ trợ.
- Cảnh báo hội thoại có đơn hàng/chờ xử lý đơn.
- Export báo cáo ra file `.xlsx`.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `FE`: dashboard frontend gọi API để hiển thị báo cáo.
- `Dashboard report`: dữ liệu tổng hợp phục vụ màn hình báo cáo.
- `Message`: document trong collection `messages`.
- `Conversation`: document trong collection `conversations`.
- `text message`: message có nội dung text thật.
- `image message`: message có attachment hoặc URL ảnh trong metadata.
- `needs support`: hội thoại cần nhân viên hỗ trợ.
- `order alert`: hội thoại có thông tin đơn hàng/chờ xử lý đơn.

## Luồng tổng thể

FE mở màn hình dashboard.

FE gọi API lấy danh sách page đang có dữ liệu để render dropdown filter:

```http
GET /api/v1/dashboard/report/page-ids
```

FE gọi API:

```http
GET /api/v1/dashboard/report?from_date=2026-06-01&to_date=2026-06-26
```

`BE` validate query params, chuẩn hóa khoảng thời gian theo timezone Việt Nam, rồi aggregate dữ liệu từ `messages` và `conversations`.

`BE` trả JSON gồm:

- `summary`: số liệu tổng quan.
- `messages_by_day`: dữ liệu biểu đồ theo ngày.
- `conversation_status`: số hội thoại theo trạng thái.
- `alerts.needs_support`: danh sách hội thoại cần hỗ trợ.
- `alerts.orders`: danh sách hội thoại có đơn hàng.

Khi người dùng bấm export, FE gọi API:

```http
GET /api/v1/dashboard/report/export?from_date=2026-06-01&to_date=2026-06-26
```

`BE` dùng cùng service tạo report, render workbook Excel bằng `openpyxl`, rồi trả file `.xlsx` cho FE tải xuống.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Cung cấp API list `page_id` đang có dữ liệu để FE render filter.
- Cung cấp API JSON để FE render dashboard.
- Cung cấp API export Excel.
- Validate `from_date` và `to_date`.
- Áp dụng filter thời gian cho dữ liệu biểu đồ và summary.
- Aggregate tổng tin nhắn, tin nhắn text, tin nhắn ảnh.
- Aggregate tin nhắn theo ngày.
- Aggregate hội thoại theo trạng thái.
- Query danh sách hội thoại cần hỗ trợ.
- Query danh sách hội thoại có đơn hàng.
- Dùng cùng logic tính report cho JSON và Excel.
- Không trả full conversation/message history trong report.
- Không log dữ liệu nhạy cảm từ nội dung tin nhắn hoặc order note.

### FE

FE chịu trách nhiệm:

- Thiết kế giao diện dashboard.
- Gọi API list `page_id` để hiển thị dropdown/chọn page.
- Truyền `from_date` và `to_date` khi gọi API.
- Render card tổng quan.
- Render biểu đồ tin nhắn theo ngày.
- Render bảng cảnh báo cần hỗ trợ.
- Render bảng cảnh báo có đơn hàng.
- Gọi export endpoint khi người dùng muốn tải Excel.
- Xử lý trạng thái loading/error/empty state.

### Database

Database chịu trách nhiệm lưu dữ liệu nguồn hiện có:

- `messages`: lịch sử tin nhắn.
- `conversations`: thông tin hội thoại, trạng thái, link Pancake và order note.

Phase đầu không yêu cầu migration bắt buộc.

### Ngoài phạm vi phương án này

- Không build UI dashboard trong task BE.
- Không tạo bảng/order collection mới.
- Không thay đổi cách lưu `order_note` hiện tại.
- Không thêm nhóm `mixed` trong response/export.
- Không export toàn bộ raw message history.
- Không thêm chart nâng cao như conversion rate, SLA, response time trong phase đầu.
- Không thêm dashboard realtime/websocket.
- Không thêm cache hoặc materialized view trong phase đầu.
- Không thay đổi Pancake webhook contract.

## Dữ liệu hiện có

### Collection `messages`

Model hiện tại: `app.models.messages.Message`.

Field dùng cho báo cáo:

| Field | Ý nghĩa |
|---|---|
| `_id` | ID message |
| `conversation_id` | Liên kết conversation |
| `message_mid` | ID message từ platform nếu có |
| `role` | `user`, `staff`, `bot`, `system` |
| `content` | Nội dung text hoặc URL ảnh được lưu làm content trong một số flow |
| `meta.source` | Nguồn message, ví dụ Pancake webhook |
| `meta.page_id` | Page ID từ Pancake |
| `meta.pancake_conversation_id` | ID hội thoại Pancake |
| `meta.message_type` | Loại message Pancake, ví dụ `INBOX`, `COMMENT` |
| `meta.image_urls` | Danh sách URL ảnh nếu webhook có ảnh |
| `meta.image_url_count` | Số URL ảnh đã extract |
| `meta.image_attachment_count` | Số attachment ảnh |
| `created_at` | Thời điểm message |

Lưu ý metric text/ảnh của dashboard phân loại theo `content`:

- `content` là URL ảnh có đuôi `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.svg`, `.avif`, `.heic`, `.heif` thì tính là tin nhắn ảnh.
- `content` có nội dung khác URL ảnh thì tính là tin nhắn text.

### Collection `conversations`

Model hiện tại: `app.models.conversations.Conversation`.

Field dùng cho báo cáo:

| Field | Ý nghĩa |
|---|---|
| `_id` | ID conversation |
| `channel` | Legacy channel/page name nếu có, màn report không dùng filter riêng |
| `customer_name` | Tên khách |
| `customer_id` | ID khách |
| `pancake_page_id` | Page ID |
| `pancake_conversation_id` | ID hội thoại Pancake |
| `pancake_thread_type` | `inbox` hoặc `comment` nếu có |
| `pancake_info_url` | Link mở hội thoại Pancake |
| `status` | `new`, `handover`, `apilimit`, `confirmed`, `order_pending` |
| `order_note` | Ghi chú đơn hàng |
| `is_active` | Conversation còn active hay đã soft delete |
| `bot_paused_at` | Thời điểm bot bị pause |
| `bot_paused_until` | Thời điểm pause hết hạn |
| `bot_paused_reason` | Lý do pause |
| `bot_paused_by` | Actor pause |
| `created_at` | Thời điểm tạo conversation |
| `updated_at` | Thời điểm cập nhật conversation |

## Quy ước lọc thời gian

API bắt buộc có `from_date` và `to_date`.

Quy tắc:

- Nhận `from_date` và `to_date` dạng `YYYY-MM-DD` hoặc ISO datetime.
- Diễn giải theo timezone Việt Nam `Asia/Bangkok`.
- Nếu truyền date không có giờ:
  - `from_date=2026-06-01` tương đương `2026-06-01T00:00:00+07:00`.
  - `to_date=2026-06-26` tương đương hết ngày `2026-06-26T23:59:59.999999+07:00`.
- Query database nên dùng range dạng `created_at >= start` và `created_at < end_exclusive`.
- Nếu `from_date > to_date`, trả `400`.
- Giới hạn range tối đa mặc định: 366 ngày. Nếu lớn hơn trả `400`.

Quy tắc áp dụng range:

- `summary.total_messages`, `summary.text_messages`, `summary.image_messages` dùng `Message.created_at`.
- `messages_by_day` dùng `Message.created_at`.
- `summary.total_conversations` và `conversation_status` dùng `Conversation.created_at`.
- `alerts.needs_support` và `alerts.orders` lấy theo trạng thái hiện tại, nhưng vẫn áp dụng filter `page_id`, `thread_type`, `include_inactive` nếu có.

## Định nghĩa metric

### Tổng tin nhắn

`total_messages` là số lượng `Message` trong khoảng thời gian đã chọn, sau khi áp dụng filter.

Phase đầu tính mọi role nếu không truyền `role`.

Nếu FE truyền `role=user`, metric chỉ tính message role `user`.

### Tin nhắn text

`text_messages` là số message có text thật.

Quy tắc phase đầu:

```text
has_text =
  content.strip() != ""
  AND content không phải URL ảnh
```

Ví dụ `content = "Mình muốn mẫu này"` được tính là tin nhắn text.

### Tin nhắn ảnh

`image_messages` là số message có ảnh.

Quy tắc:

```text
has_image =
  content là URL ảnh có đuôi jpg/jpeg/png/webp/gif/bmp/svg/avif/heic/heif
```

Ví dụ `content = "https://content.pancake.vn/.../sample.jpg"` được tính là tin nhắn ảnh và không tính là tin nhắn text.

Phase đầu không tạo nhóm `mixed`. Với quy tắc theo `content`, một message chỉ có một `content` sẽ được phân vào text hoặc ảnh.

### Tin nhắn theo role

Các metric theo role:

- `user_messages`: role `user`.
- `staff_messages`: role `staff`.
- `bot_messages`: role `bot`.

Role `system` không cần card riêng trong MVP, nhưng có thể tính nếu FE cần sau.

### Cảnh báo cần hỗ trợ

Một conversation được coi là cần hỗ trợ nếu thỏa một trong các điều kiện:

- `status == "handover"`.
- `status == "apilimit"`.
- `bot_paused_until` còn ở tương lai.

Reason trả về:

| Reason | Điều kiện |
|---|---|
| `handover` | `status == "handover"` |
| `apilimit` | `status == "apilimit"` |
| `bot_paused` | `bot_paused_until > now` |

Nếu một conversation thỏa nhiều điều kiện, ưu tiên reason theo thứ tự:

1. `apilimit`
2. `handover`
3. `bot_paused`

### Cảnh báo có đơn hàng

Một conversation được coi là có đơn hàng/chờ xử lý đơn nếu:

- `status == "order_pending"`, hoặc
- `order_note` có nội dung.

Phase đầu không tách bảng order riêng vì repo hiện đang lưu order note trên `Conversation.order_note`.

## API 1: List page_id cho filter

### Endpoint

```http
GET /api/v1/dashboard/report/page-ids
```

### Permission

```text
conversations:view
```

### Query params

| Param | Bắt buộc | Kiểu | Ghi chú |
|---|---:|---|---|
| `include_inactive` | Không | bool | Mặc định `false`; nếu `true` sẽ tính cả conversation inactive |

### Response đề xuất

```json
{
  "items": [
    {
      "page_id": "970198996185881",
      "conversation_count": 180,
      "message_count": 1234,
      "latest_activity_at": "2026-06-26T10:05:00+07:00"
    }
  ]
}
```

Nguồn dữ liệu:

- `conversations.pancake_page_id`
- `messages.meta.page_id`

FE dùng `items[].page_id` để render dropdown. Khi user chọn page, FE truyền lại cùng giá trị vào query param `page_id` của API report/export.

## API 2: Lấy data dashboard

### Endpoint

```http
GET /api/v1/dashboard/report
```

### Permission

Đề xuất dùng permission hiện có:

```text
conversations:view
```

Nếu sau này cần tách quyền riêng, thêm `dashboard:view`.

### Query params

| Param | Bắt buộc | Kiểu | Ghi chú |
|---|---:|---|---|
| `from_date` | Có | date/datetime string | Ngày bắt đầu |
| `to_date` | Có | date/datetime string | Ngày kết thúc |
| `page_id` | Không | string | Filter `pancake_page_id` / `messages.meta.page_id` |
| `thread_type` | Không | string | `inbox`, `comment` |
| `role` | Không | string | Filter message role: `user`, `staff`, `bot`, `system` |
| `include_inactive` | Không | bool | Mặc định `false` |
| `alert_limit` | Không | int | Mặc định `20`, max `100` |

### Response đề xuất

```json
{
  "filters": {
    "from_date": "2026-06-01T00:00:00+07:00",
    "to_date": "2026-06-26T23:59:59.999999+07:00",
    "page_id": "970198996185881",
    "thread_type": null,
    "role": null,
    "include_inactive": false,
    "alert_limit": 20
  },
  "summary": {
    "total_messages": 1234,
    "text_messages": 900,
    "image_messages": 250,
    "user_messages": 650,
    "staff_messages": 120,
    "bot_messages": 464,
    "total_conversations": 180,
    "new_conversations": 90,
    "confirmed_conversations": 20,
    "handover_conversations": 8,
    "apilimit_conversations": 2,
    "order_pending_conversations": 5,
    "needs_support_count": 10,
    "order_alert_count": 5
  },
  "messages_by_day": [
    {
      "date": "2026-06-01",
      "total": 80,
      "text": 60,
      "image": 15,
      "user": 40,
      "staff": 10,
      "bot": 30
    }
  ],
  "conversation_status": [
    {"status": "new", "count": 90},
    {"status": "confirmed", "count": 20},
    {"status": "handover", "count": 8},
    {"status": "apilimit", "count": 2},
    {"status": "order_pending", "count": 5}
  ],
  "alerts": {
    "needs_support": [
      {
        "conversation_id": "6a3c7dcead6606c1f8d8326e",
        "customer_name": "Nguyen Van A",
        "customer_id": "customer-1",
        "status": "handover",
        "reason": "handover",
        "pancake_page_id": "970198996185881",
        "pancake_conversation_id": "970198996185881_27060574493629431",
        "pancake_info_url": "https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431",
        "order_note": null,
        "bot_paused_until": "2026-06-26T10:10:00+07:00",
        "updated_at": "2026-06-26T10:05:00+07:00",
        "message_count": 12
      }
    ],
    "orders": [
      {
        "conversation_id": "6a3c7dcead6606c1f8d8326e",
        "customer_name": "Nguyen Van A",
        "customer_id": "customer-1",
        "status": "order_pending",
        "pancake_page_id": "970198996185881",
        "pancake_conversation_id": "970198996185881_27060574493629431",
        "pancake_info_url": "https://pancake.vn/970198996185881?c_id=970198996185881_27060574493629431",
        "order_note": "1. [10:05] Khách muốn đặt màu đen size M",
        "updated_at": "2026-06-26T10:05:00+07:00",
        "message_count": 12
      }
    ]
  }
}
```

## API 3: Export Excel

### Endpoint

```http
GET /api/v1/dashboard/report/export
```

Query params giống `GET /api/v1/dashboard/report`.

### Response

Backend trả file `.xlsx`.

Headers:

```http
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="dashboard-report-2026-06-01-to-2026-06-26.xlsx"
```

### Nội dung workbook

Đề xuất dùng `openpyxl`, dependency đã có trong `requirements.txt`.

Workbook gồm các sheet:

1. `Summary`
   - Filter đã dùng.
   - Tổng tin nhắn.
   - Tổng tin nhắn text.
   - Tổng tin nhắn ảnh.
   - Tổng user/staff/bot.
   - Tổng conversation theo status.
   - Tổng cảnh báo.

2. `Messages by day`
   - `date`
   - `total`
   - `text`
   - `image`
   - `user`
   - `staff`
   - `bot`

3. `Needs support`
   - `conversation_id`
   - `customer_name`
   - `customer_id`
   - `status`
   - `reason`
   - `pancake_page_id`
   - `pancake_conversation_id`
   - `pancake_info_url`
   - `bot_paused_until`
   - `updated_at`
   - `message_count`

4. `Orders`
   - `conversation_id`
   - `customer_name`
   - `customer_id`
   - `status`
   - `pancake_page_id`
   - `pancake_conversation_id`
   - `pancake_info_url`
   - `order_note`
   - `updated_at`
   - `message_count`

Excel export phải dùng cùng service với API JSON để đảm bảo số liệu không lệch.

## Contract object nội bộ

Service dashboard report nên trả object ổn định để API JSON và Excel dùng chung:

```json
{
  "filters": {},
  "summary": {},
  "messages_by_day": [],
  "conversation_status": [],
  "alerts": {
    "needs_support": [],
    "orders": []
  }
}
```

Không đưa full raw message content vào object report.

`order_note` được phép trả trong `alerts.orders` vì đây là dữ liệu FE cần hiển thị cảnh báo đơn hàng.

## Lỗi và fallback

### Thiếu date filter

Nếu thiếu `from_date` hoặc `to_date`:

- FastAPI có thể trả `422`, hoặc service trả `400` nếu validate thủ công.
- Không chạy query aggregate.

### Date range không hợp lệ

Nếu `from_date > to_date`:

- Trả `400`.
- Response detail nên rõ: `from_date_must_be_before_to_date`.

### Date range quá dài

Nếu khoảng ngày vượt giới hạn cấu hình phase đầu, ví dụ 366 ngày:

- Trả `400`.
- Response detail nên rõ: `date_range_too_large`.

### Không có dữ liệu

Nếu không có dữ liệu trong range:

- Trả summary toàn số `0`.
- Trả `messages_by_day` rỗng hoặc có đủ ngày với `0`, tùy FE cần.
- Phase đầu đề xuất trả rỗng để payload gọn.
- `alerts.needs_support` và `alerts.orders` vẫn trả theo trạng thái hiện tại nếu có.

### Export Excel lỗi

Nếu lỗi khi tạo workbook:

- Log error rút gọn.
- Trả `500`.
- Không ghi file tạm ra disk nếu không cần.

## Logging

Log đề xuất khi gọi report:

```text
DASHBOARD_REPORT_REQUEST from_date=%s to_date=%s page_id=%s thread_type=%s role=%s
```

Log đề xuất khi export:

```text
DASHBOARD_REPORT_EXPORT_REQUEST from_date=%s to_date=%s page_id=%s thread_type=%s role=%s
```

Không log:

- Full message content.
- Full order note.
- Pancake token hoặc secret.
- Raw Excel bytes.

Có thể log count sau khi aggregate:

```text
DASHBOARD_REPORT_DONE total_messages=%s total_conversations=%s needs_support_count=%s order_alert_count=%s
```

## Cấu hình backend

Phase đầu không bắt buộc thêm env.

Các hằng số có thể đặt trong service:

```text
DEFAULT_DASHBOARD_ALERT_LIMIT=20
MAX_DASHBOARD_ALERT_LIMIT=100
MAX_DASHBOARD_REPORT_RANGE_DAYS=366
```

Nếu team muốn cấu hình qua env ở phase sau, có thể thêm:

```env
DASHBOARD_REPORT_MAX_RANGE_DAYS=366
DASHBOARD_REPORT_DEFAULT_ALERT_LIMIT=20
DASHBOARD_REPORT_MAX_ALERT_LIMIT=100
```

## Index nên cân nhắc

Hiện `messages` có index `conversation_id`, `role`, `updated_at`; `conversations` có `status`, `bot_paused_until`, `updated_at`, một số index Pancake.

Nếu báo cáo chạy trên dữ liệu lớn, nên thêm index:

- `messages.created_at`
- `messages.meta.page_id`
- `messages.meta.message_type`
- compound `messages.created_at + role`
- compound `conversations.status + updated_at`
- compound `conversations.pancake_page_id + updated_at`

Phase đầu có thể chưa thêm index nếu data nhỏ, nhưng cần theo dõi khi dashboard query chậm.

## Danh sách file dự kiến thay đổi khi implement

- `app/api/schemas/dashboard_report.py`
- `app/services/dashboard_report_service.py`
- `app/api/v1/dashboard_reports.py`
- [app/api/router_v1.py](../app/api/router_v1.py)
- `tests/test_dashboard_report_service.py`
- `tests/test_dashboard_reports_api.py`

Không cần migration dữ liệu ở phase đầu.

## Checklist implementation tổng hợp

Trạng thái hiện tại: đã implement Phase 0-5 cho dashboard report. BE đã có schema response, router `GET /api/v1/dashboard/report/page-ids`, router `GET /api/v1/dashboard/report`, router `GET /api/v1/dashboard/report/export`, service aggregate dữ liệu từ `messages` và `conversations`, filter `from_date` / `to_date`, filter `page_id`, metric text/image, biểu đồ theo ngày, alert cần hỗ trợ/đơn hàng, export Excel, logging/error handling và test coverage. `pytest -q` đã pass.

### Phase 0. Chốt giải pháp dashboard report

- [x] Chốt phase đầu cần 3 API: list `page_id`, JSON report và Excel export.
- [x] Chốt FE tự thiết kế giao diện, BE chỉ cung cấp data.
- [x] Chốt API bắt buộc có `from_date` và `to_date`.
- [x] Chốt chỉ cần tổng tin nhắn text và tổng tin nhắn ảnh, không cần `mixed`.
- [x] Chốt cảnh báo cần hỗ trợ dựa trên `handover`, `apilimit`, bot đang pause.
- [x] Chốt cảnh báo đơn hàng dựa trên `order_pending` hoặc `order_note`.
- [x] Chốt export Excel dùng cùng service với JSON report.

### Phase 1. Schema và router

- [x] Tạo schema request/query và response cho dashboard report.
- [x] Tạo schema response list `page_id`.
- [x] Tạo router `app/api/v1/dashboard_reports.py`.
- [x] Thêm endpoint `GET /api/v1/dashboard/report/page-ids`.
- [x] Thêm endpoint `GET /api/v1/dashboard/report`.
- [x] Thêm endpoint `GET /api/v1/dashboard/report/export`.
- [x] Gắn router vào `app/api/router_v1.py`.
- [x] Dùng permission `conversations:view` trong phase đầu.

### Phase 2. Service aggregate report

- [x] Tạo `app/services/dashboard_report_service.py`.
- [x] Parse và validate `from_date`, `to_date`.
- [x] Chuẩn hóa timezone Việt Nam.
- [x] Validate `from_date <= to_date`.
- [x] Validate range không vượt giới hạn.
- [x] Build filter theo `page_id`, `thread_type`, `role`, `include_inactive`.
- [x] Aggregate list `page_id` đang có từ `conversations` và `messages`.
- [x] Aggregate `summary.total_messages`.
- [x] Aggregate `summary.text_messages`.
- [x] Aggregate `summary.image_messages`.
- [x] Aggregate message theo role `user`, `staff`, `bot`.
- [x] Aggregate `messages_by_day`.
- [x] Aggregate `conversation_status`.
- [x] Query `alerts.needs_support`.
- [x] Query `alerts.orders`.
- [x] Đảm bảo không trả raw message history.

### Phase 3. Export Excel

- [x] Tạo helper export workbook bằng `openpyxl`.
- [x] Sheet `Summary` có filter và metric tổng.
- [x] Sheet `Messages by day` có dữ liệu biểu đồ theo ngày.
- [x] Sheet `Needs support` có danh sách cảnh báo cần hỗ trợ.
- [x] Sheet `Orders` có danh sách cảnh báo đơn hàng.
- [x] Endpoint export trả đúng content type `.xlsx`.
- [x] Filename có range ngày.
- [x] Export dùng cùng service với API JSON.

### Phase 4. Logging, lỗi và an toàn dữ liệu

- [x] Log request dashboard report với metadata filter.
- [x] Log request export với metadata filter.
- [x] Không log full message content.
- [x] Không log full order note.
- [x] Không log raw Excel bytes.
- [x] Thiếu date filter trả lỗi rõ ràng.
- [x] Date range sai trả `400`.
- [x] Date range quá dài trả `400`.
- [x] Không có data vẫn trả payload rỗng hợp lệ.

### Phase 5. Test

- [x] Test thiếu `from_date` hoặc `to_date`.
- [x] Test API list `page_id`.
- [x] Test `from_date > to_date`.
- [x] Test date range quá dài.
- [x] Test tổng message theo range.
- [x] Test `messages_by_day` group đúng ngày theo timezone Việt Nam.
- [x] Test đếm `text_messages`.
- [x] Test đếm `image_messages`.
- [x] Test URL ảnh trong `content` được tính là ảnh và không tính là text.
- [x] Test filter `page_id`.
- [x] Test filter `thread_type`.
- [x] Test filter `role`.
- [x] Test cảnh báo cần hỗ trợ gồm `handover`, `apilimit`, pause còn hiệu lực.
- [x] Test cảnh báo đơn hàng gồm `order_pending` hoặc có `order_note`.
- [x] Test export Excel trả đúng content type và filename.
- [x] Test workbook có đủ sheet `Summary`, `Messages by day`, `Needs support`, `Orders`.
- [x] Chạy `pytest -q`.
- [x] Không chạy `pre-commit` theo guideline repo.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp dashboard report](dashboard-report-api-task-list/phase-0.md)
- [Phase 1. Schema và router dashboard report](dashboard-report-api-task-list/phase-1.md)
- [Phase 2. Service aggregate dashboard report](dashboard-report-api-task-list/phase-2.md)
- [Phase 3. Export Excel dashboard report](dashboard-report-api-task-list/phase-3.md)
- [Phase 4. Logging, lỗi và an toàn dữ liệu dashboard report](dashboard-report-api-task-list/phase-4.md)
- [Phase 5. Test dashboard report](dashboard-report-api-task-list/phase-5.md)

Tiến độ hiện tại:

- [x] Phase 0. Chốt giải pháp dashboard report.
- [x] Phase 1. Schema và router dashboard report.
- [x] Phase 2. Service aggregate dashboard report.
- [x] Phase 3. Export Excel dashboard report.
- [x] Phase 4. Logging, lỗi và an toàn dữ liệu.
- [x] Phase 5. Test dashboard report.

## Test cần có khi implement

- Gọi `GET /api/v1/dashboard/report` thiếu `from_date` thì trả lỗi.
- Gọi `GET /api/v1/dashboard/report` thiếu `to_date` thì trả lỗi.
- Gọi `GET /api/v1/dashboard/report/page-ids` trả list page đang có.
- Gọi `from_date > to_date` thì trả `400`.
- Gọi range quá dài thì trả `400`.
- Có message trong range thì `total_messages` đúng.
- Có message ngoài range thì không bị tính.
- Message có `content` text thường thì tăng `text_messages`.
- Message có `content` là URL ảnh thì tăng `image_messages`.
- Message có `content` là URL ảnh thì không tăng `text_messages`.
- `messages_by_day` group đúng theo ngày Việt Nam.
- Filter `page_id` chỉ tính dữ liệu đúng page.
- Filter `thread_type` chỉ tính đúng inbox/comment.
- Filter `role=user` chỉ tính message khách.
- Conversation `handover` xuất hiện trong `alerts.needs_support`.
- Conversation `apilimit` xuất hiện trong `alerts.needs_support`.
- Conversation có `bot_paused_until > now` xuất hiện trong `alerts.needs_support`.
- Conversation `order_pending` xuất hiện trong `alerts.orders`.
- Conversation có `order_note` xuất hiện trong `alerts.orders`.
- API export trả content type `.xlsx`.
- File Excel mở được bằng `openpyxl`.
- Workbook có đủ sheet `Summary`, `Messages by day`, `Needs support`, `Orders`.
- Chạy `pytest -q`.

## Ghi chú production

- Dashboard report có thể query nhiều dữ liệu, cần theo dõi thời gian response sau rollout.
- Nếu dữ liệu lớn, ưu tiên thêm index theo phần "Index nên cân nhắc".
- Không export raw message history để tránh file quá nặng và tránh lộ dữ liệu không cần thiết.
- `order_note` có thể chứa thông tin cá nhân, chỉ trả trong bảng cảnh báo đơn hàng cho user có quyền xem conversation.
- Nếu sau này FE cần realtime, nên mở task riêng cho cache hoặc materialized stats.
- Nếu FE cần thêm metric như tốc độ phản hồi, tỉ lệ đơn hàng, số hội thoại mới, nên mở phase riêng để định nghĩa công thức rõ ràng.

## Tiêu chí hoàn thành

- FE gọi được `GET /api/v1/dashboard/report` để render toàn bộ dashboard MVP.
- FE gọi được `GET /api/v1/dashboard/report/page-ids` để lấy danh sách page filter.
- API JSON bắt buộc hỗ trợ `from_date` và `to_date`.
- API JSON trả tổng số tin nhắn, tổng tin nhắn text, tổng tin nhắn ảnh.
- API JSON trả dữ liệu biểu đồ tin nhắn theo ngày.
- API JSON trả danh sách cảnh báo cần hỗ trợ.
- API JSON trả danh sách cảnh báo có đơn hàng.
- FE gọi được `GET /api/v1/dashboard/report/export` để tải file Excel.
- Excel dùng cùng filter và cùng số liệu với API JSON.
- Không có nhóm `mixed` trong response hoặc Excel.
- Tests pass bằng `pytest -q`.
