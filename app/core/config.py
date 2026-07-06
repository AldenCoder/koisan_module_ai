from typing import Optional

from pydantic.v1 import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_uri: Optional[str] = None
    secret_key: Optional[str] = None
    openai_api_key: str
    ADMIN_ROLE_NAME: str = "Quản trị hệ thống"
    DEFAULT_ROLE_NAME: str = "Người dùng"
    llama_data_dir: Optional[str] = None
    llama_collection_name: str = "qa_collection"
    llama_embed_model: Optional[str] = "VoVanPhuc/sup-SimCSE-VietNamese-phobert-base"
    llama_window_size: int = 3
    llama_vector_similarity_top_k: int = 30
    llama_keyword_similarity_top_k: int = 30
    llama_fusion_similarity_top_k: int = 15
    llama_num_queries: int = 1
    llama_chroma_persist_dir: Optional[str] = None
    base_url: Optional[str] = None
    workflow_base_url: Optional[str] = None
    ai_conversation_version: str = "1.1"
    fb_sender_buffer_seconds: int = 15
    fb_page_access_token: Optional[str] = None
    fb_page_id: Optional[str] = None
    fb_webhook_verify_token: Optional[str] = None
    fb_ai_chat_url: Optional[str] = "https://openclaw-production-ecec.up.railway.app/api/chat"
    fb_ai_bearer_token: Optional[str] = None
    fb_ai_retry_attempts: int = 3
    fb_ai_retry_backoff_seconds: float = 1.0
    fb_ai_requeue_delay_seconds: int = 10
    fb_admin_takeover_pause_minutes: int = 10
    pancake_page_access_token: Optional[str] = None
    pancake_page_access_tokens_by_page_id: Optional[str] = None
    pancake_api_timeout_seconds: float = 30.0
    pancake_api_retry_attempts: int = 3
    pancake_api_retry_backoff_seconds: float = 1.0
    pancake_admin_takeover_pause_minutes: Optional[int] = None
    pancake_sender_buffer_seconds: float = 5.0
    pancake_handover_context_max_messages: int = 30
    pancake_auto_consult_enabled: bool = False
    pancake_comment_auto_reply_enabled: bool = False
    pancake_auto_consult_product_code_regex: str = r"(?<![A-Za-z0-9])(?:[A-Za-z]?\d{6,8})(?:(?:[A-Za-z0-9]{1,3})|(?:[^\S\r\n]*-[^\S\r\n]*[A-Za-z0-9]{1,3}))?(?![A-Za-z0-9])"
    pancake_image_cache_path: str = "storage/pancake_image_cache.json"
    pancake_image_storage_dir: str = "storage/pancake_images"
    pancake_inbox_image_max_count: int = 3
    pancake_comment_image_max_count: int = 3
    pancake_image_download_timeout_seconds: float = 15.0
    pancake_image_upload_timeout_seconds: float = 30.0
    pancake_image_max_bytes: int = 10 * 1024 * 1024
    pancake_image_storage_max_bytes: int = 500_000
    pancake_reuse_uploaded_content_id: bool = True
    pancake_image_color_filter_enabled: bool = True
    pancake_image_color_map: Optional[str] = None
    pancake_drive_image_selection_strategy: str = "color_diverse"
    pancake_drive_color_folder_max_count: int = 5
    google_drive_api_key: Optional[str] = None
    google_drive_folder_lookup_max_depth: int = 3
    rag_auth_login_url: Optional[str] = "https://ragbrain-production.up.railway.app/api/v1/auth/login"
    rag_auth_email: Optional[str] = None
    rag_auth_password: Optional[str] = None
    rag_auth_headers: Optional[str] = None
    rag_token_refresh_days: int = 6
    rag_image_storage_dir: str = "storage/rag_images"
    rag_image_public_path: str = "/rag-images"
    rag_image_target_max_bytes: int = 1_000_000
    public_image_crop_search_timeout_seconds: float = 15.0
    public_image_crop_search_max_bytes: int = 10 * 1024 * 1024
    public_image_crop_search_min_confidence: float = 0.9
    chroma_persist_dir: str = "data/chroma"
    chroma_image_search_collection: str = "image_search_crop_views_v1"
    clip_crop_aware_output_dir: str = "data/query_crop_aware_v4"
    clip_crop_aware_source_dir: str = "data/source_images"
    clip_crop_aware_foreground_dir: str = "data/foregrounds"
    clip_crop_aware_metadata_path: str = "data/source_images_metadata.csv"
    clip_crop_aware_clip_model: str = "openai/clip-vit-base-patch32"
    clip_crop_aware_rembg_model: str = "u2net_human_seg"
    clip_crop_aware_background: str = "#f2f2f2"
    clip_crop_aware_max_side: int = 1280

    class Config:
        env_file = (".env",)
        extra = "allow"


settings = Settings()
