
This repository contains the AI conversation orchestration service for Xoai
Studio. It is a FastAPI backend that processes incoming user messages through
an intent/branch/slot state pipeline, then decides the next business action
for the conversation.

## What this service does

- Detects user intent from the latest message and conversation context.
- Detects the active branch (conversation scenario) for downstream handling.
- Extracts structured slots from free-form Vietnamese messages.
- Updates conversation state after each turn.
- Tracks missing and asked slots to avoid repeating questions.
- Selects the next action for the orchestrator (`ask_slot`, `call_rag`,
  `recommend`, `quote`, `handoff`).

## Processing pipeline

Conversation turns are processed in this order:

```text
message
  -> intent detection
  -> branch detection
  -> slot extraction
  -> state update
  -> missing slot check
  -> decide next action
       |- ask slot
       |- call RAG
```

When required slots are fully collected (`missing_slots == []`), the next action
is `call_rag`. If required slots are still missing, the next action remains
`ask_slot`.

### RAG behavior when slots are complete

- Trigger condition: `missing_slots` is empty.
- Request target (production API endpoint):
  `POST https://ragbrain-production.up.railway.app/api/v1/qna/question_and_answer`
- Swagger docs URL (reference only, not request target):
  `https://ragbrain-production.up.railway.app/docs`
- Fallback behavior:
  - If RAG returns no useful answer marker, action falls back to `handoff`.
  - If RAG returns HTTP 4xx/5xx or request fails, action falls back to
    `handoff`.

### Conversation state shape

```json
{
  "branch": null,
  "intent": null,
  "slots": {},
  "missing_slots": [],
  "asked_slots": [],
  "next_action": null,
  "next_slot": null
}
```

## High-level architecture

```text
┌──────────────────────────┐
│ Client (Chat/Facebook)       │
└──────────────┬───────────┘
               │
               ▼
      ┌─────────────────────┐
      │ /api/v1/intent/*    │
      └──────────┬──────────┘
                 │
                 ▼
      ┌─────────────────────┐
      │ AI Orchestrator     │
      │ intent/branch/slots │
      └──────────┬──────────┘
                 │
      ┌──────────┼───────────────────────────────────┐
      │          │                                   │
      ▼          ▼                                   ▼
┌───────────┐ ┌──────────────┐                ┌───────────────┐
│ MongoDB   │ │ Search/RAG   │                │ Response Layer│
│ state/log │ │ integrations │                │ user replies  │
└───────────┘ └──────────────┘                └───────────────┘
```

## API surface

Base path: `/api/v1/intent`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/extract-intent` | POST | Full pipeline + trả về intent chính (có lưu state vào DB). |
| `/analyze-branch-slots` | POST | API tái sử dụng cho branch detection + slot extraction. |
| `/response-message` | POST | Chạy full orchestration pipeline và lưu toàn bộ state tables. |

Supported intents:

- `greeting`
- `provide_information`
- `ask_service_info`
- `price_request`

### Example: extract intent

```bash
curl -X POST "http://localhost:8000/api/v1/intent/extract-intent" \
  -H "Content-Type: application/json" \
  -d '{
        "text": "Bên mình có gói chụp prewedding ở studio không?",
        "channel": "facebook",
        "customer_name": "Nguyen Van A",
        "customer_id": "fb_user_123",
        "message_mid": "m_001",
        "metadata": {
          "source": "fanpage"
        }
      }'
```

### Example: process full message

```bash
curl -X POST "http://localhost:8000/api/v1/intent/response-message" \
  -H "Content-Type: application/json" \
  -d '{
        "text": "Mình cưới ngày 15/10/2026 và đang quan tâm cả pre-wedding lẫn ngày cưới",
        "conversation_id": null,
        "channel": "facebook",
        "customer_name": "Nguyen Van A",
        "customer_id": "fb_user_123",
        "metadata": {
          "campaign": "wedding_q4"
        }
      }'
```

## Getting started

### Prerequisites

- Python 3.11
- MongoDB (for clients, orders, messages)
- OpenAI API key (for intent and extraction models)
- Access to Xoai Studio internal backend APIs (search and enrichment)

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment configuration

Copy the example file and set required values:

```bash
cp .env.example .env
```

Key variables used by this service:

| Variable | Description |
|----------|-------------|
| `MONGO_URI` | MongoDB connection string. |
| `ENVIRONMENT` | `development` enables docs; `production` disables them. |
| `OPENAI_API_KEY` | OpenAI API key for all AI calls. |
| `EXTRACT_INTENT_MODEL` | Model for intent classification. |
| `EXTRACT_INFO_ORDER_MODEL` | Model for order and feedback extraction. |
| `CHATBOT_RESPONSE_MODEL` | Model for natural Vietnamese responses. |
| `EXTRACT_QUANTITY_FROM_PRODUCT_NAME_AND_USER_INPUT_MODEL` | Model for product quantity composition. |
| `RAG_SERVICE_URL` | RAG Brain API URL (use `/api/v1/qna/question_and_answer`, not `/docs`). |
| `RAG_SERVICE_METHOD` | HTTP method for RAG request (default `POST`). |
| `RAG_SERVICE_HEADERS` | JSON headers for RAG request (default `{}`). |
| `RAG_AUTH_LOGIN_URL` | RAG auth login endpoint (default `/api/v1/auth/login` on production RAG). |
| `RAG_AUTH_EMAIL` | Email used to login and fetch RAG bearer token. |
| `RAG_AUTH_PASSWORD` | Password used to login and fetch RAG bearer token. |
| `RAG_AUTH_HEADERS` | JSON headers for login request (default includes `accept` and `Content-Type`). |
| `RAG_TOKEN_REFRESH_DAYS` | Refresh threshold by token `updated_at` age in days (default `6`). |
| `BACKEND_BASE_URL` | Xoai Studio backend base URL for internal search. |
| `ENABLE_API_V0` | Toggle legacy `/api/v0` routes. |
| `ENABLE_API_V1` | Toggle `/api/v1` routes. |
| `FB_PAGE_ACCESS_TOKEN` | Facebook page access token (also used as default verify token fallback). |
| `FB_PAGE_ID` | Facebook page id used to filter webhook events. |
| `FB_WEBHOOK_VERIFY_TOKEN` | Optional verify token for webhook handshake. |
| `FB_SENDER_BUFFER_SECONDS` | Delay window (seconds) to buffer messages per sender before forwarding them to AI chat (default `15`). |
| `FB_ADMIN_TAKEOVER_PAUSE_MINUTES` | Minutes to pause bot replies after an admin sends a Page Inbox message (default `10`). |
| `FB_AI_CHAT_URL` | AI chat endpoint used by Facebook webhook forward flow (default `https://openclaw-production-ecec.up.railway.app/api/chat`). |
| `FB_AI_BEARER_TOKEN` | Bearer token used when calling `FB_AI_CHAT_URL`. |
| `FB_AI_RETRY_ATTEMPTS` | Retry attempts per AI chat request before requeue (default `3`). |
| `FB_AI_RETRY_BACKOFF_SECONDS` | Base exponential backoff seconds for AI chat retries (default `1`). |
| `FB_AI_REQUEUE_DELAY_SECONDS` | Delay before requeueing failed Facebook messages for another processing run (default `10`). |
| `PANCAKE_SENDER_BUFFER_SECONDS` | Delay window (seconds) to buffer Pancake inbox customer messages by `(page_id, conversation_id, sender_id)` before forwarding one merged text/image payload to AI (default `5`, set `0` to disable). |

### Running the service

```bash
uvicorn app.main:app --reload
```

API docs are available at `http://localhost:8000/docs` in development mode.

## Facebook fanpage webhook (realtime)

Base path: `/api/v1/facebook`

- `GET /webhook`: endpoint for Facebook webhook verification.
- `POST /webhook`: receives realtime page messaging events.
- `GET /latest-message`: returns the latest incoming message captured in memory.

Forwarding behavior:
- Each incoming Facebook user message is forwarded to `FB_AI_CHAT_URL` with payload `{user,messages,stream:false}`.
- Authorization header uses `Bearer <FB_AI_BEARER_TOKEN>` from environment variables.
- On first message of each Facebook user, the webhook sends a one-time init message:
  `Hãy đọc file markdown tại /data/workspace/xoai_module_ai/TEST_XOAI_CHATBOT.md và bắt đầu test xoài chatbot.`
- The user message content is forwarded without content rewrite.
- Failed AI calls are retried and failed messages are requeued with logs to reduce message loss risk.

## Dataset cleaning

Base path: `/api/v1/dataset`

- `POST /clean-training-pairs`: uploads a `.jsonl` training-pairs file, filters out invalid or system-like assistant rows, and writes cleaned/rejected artifacts under `artifacts/training_data/`.

Example:

```bash
curl -X POST "http://localhost:8000/api/v1/dataset/clean-training-pairs" \
  -F "file=@training_pairs_20260316_093222.jsonl"
```

## CLIP Crop-Aware Image Search

This feature handles cases where the query image is a crop from a product image
that already exists in the index. Instead of storing one global embedding per
product image, it stores multiple foreground views per image:

- `full`
- `upper_65`
- `upper_50`
- `neck_40`
- `torso_15_75`

Search embeds the same query views and scores each indexed view by the best
matching query view. Product scores are aggregated from the best image-view
matches.

The runtime pipeline is split into services under `app/services`:

- `foreground_common.py`
- `crop_views.py`
- `export_foregrounds.py`
- `crop_aware_index_common.py`
- `chroma_crop_aware_index.py`

ChromaDB is the only vector backend. It stores its persistent files under
`CHROMA_PERSIST_DIR=data/chroma` and uses collection
`CHROMA_IMAGE_SEARCH_COLLECTION=image_search_crop_views_v1`.

Image-search data should live under the project-root `data/` directory:

- `data/source_images/`: imported source images resized for search
- `data/foregrounds/`: optional foreground cache for manual build/debug jobs
- `data/chroma/`: persistent Chroma vector index
- `data/query_crop_aware_v4/`: optional debug output when explicitly enabled

Import original product images:

- Endpoint: `POST /api/v1/image-search-import`
- Auth: requires `image_assets:create`
- Body: multipart form with `code`, optional `description`, and one or more
  `files`
- Default source dir: `CLIP_CROP_AWARE_SOURCE_DIR=data/source_images`
- Default foreground cache:
  `CLIP_CROP_AWARE_FOREGROUND_DIR=data/foregrounds`
- Default metadata CSV:
  `CLIP_CROP_AWARE_METADATA_PATH=data/source_images_metadata.csv`
- The API stores source image files after resizing them to
  `CLIP_CROP_AWARE_MAX_SIDE`, appends one CSV row per file, extracts
  foregrounds in memory, creates crop views, embeds them with CLIP, and upserts
  the vectors into ChromaDB. Foreground images are not kept on disk for API
  imports.

To create the Chroma collection from source images already listed in the CSV:

```bash
python -m scripts.build_chroma_image_search_index
```

On Railway, mount the persistent volume at `/app/data`. Run the bootstrap
command at runtime after the volume is mounted, not during build or pre-deploy.

Example:

```bash
curl -X POST "http://localhost:8000/api/v1/image-search-import" \
  -H "Authorization: Bearer <token>" \
  -F "code=S12345" \
  -F "description=Ao dai mau do" \
  -F "files=@/path/to/source-1.jpg" \
  -F "files=@/path/to/source-2.png"
```

API search:

- Endpoint: `POST /api/v1/image-search/crop-aware`
- Auth: requires `image_assets:view`
- Body: multipart form, field `file` is the query image
- Query optional: `top_k`, `aggregate_k`
- Chroma storage: `CHROMA_PERSIST_DIR=data/chroma`
- Query debug images are not kept on disk by the API.

Example:

```bash
curl -X POST "http://localhost:8000/api/v1/image-search/crop-aware?top_k=10&aggregate_k=1" \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/query.jpg"
```

The API runs the same search logic: extract foreground from the uploaded image
in memory, create crop views, embed with CLIP, compare against the crop-aware
index, then return `ranking` and `top_images`.

Quick local test for incoming message simulation:

```bash
curl -X POST "http://localhost:8000/api/v1/facebook/webhook" \
  -H "Content-Type: application/json" \
  -d '{
        "object": "page",
        "entry": [
          {
            "id": "<FB_PAGE_ID>",
            "messaging": [
              {
                "sender": {"id": "user_123"},
                "recipient": {"id": "<FB_PAGE_ID>"},
                "timestamp": 1750000000000,
                "message": {"mid": "m_1", "text": "Xin chao fanpage"}
              }
            ]
          }
        ]
      }'
```

Check latest message:

```bash
curl "http://localhost:8000/api/v1/facebook/latest-message"
```

### Running tests

```bash
pytest -q
```

## Notes

- The service stores conversation history and order data in MongoDB via Beanie.
- SlowAPI middleware is wired; add per-route limits with decorators when needed.
- All customer-facing responses are generated in Vietnamese and tuned for a
  polite sales-assistant tone.

## License

This project is distributed under the [Business Source License 1.1](LICENSE).
