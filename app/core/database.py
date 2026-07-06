import datetime
import logging
import os

import motor.motor_asyncio
from beanie import init_beanie
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_tac_nhan import NguoiDungTacNhan
from app.models.quyen_han import QuyenHan
from app.models.tac_nhan import TacNhan
from app.models.tac_nhan_quyen_han import TacNhanQuyenHan

from app.models.branch_slots import BranchSlot
from app.models.branches import Branch
from app.models.conversation_states import ConversationState
from app.models.conversations import Conversation
from app.models.image_assets import ImageAsset
from app.models.messages import Message
from app.models.rag_service_tokens import RagServiceToken
from app.models.slot_catalog import SlotCatalog
from app.models.state_asked_slots import StateAskedSlot
from app.models.state_missing_slots import StateMissingSlot
from app.models.state_slots import StateSlot

load_dotenv()

logger = logging.getLogger(__name__)

INIT_FILE_PATH = ".initdb"

DOCUMENT_MODELS = [
    Conversation,
    Message,
    Branch,
    SlotCatalog,
    BranchSlot,
    ConversationState,
    StateSlot,
    StateMissingSlot,
    StateAskedSlot,
    ImageAsset,
    RagServiceToken,
    NguoiDung,
    TacNhan,
    NguoiDungTacNhan,
    QuyenHan,
    TacNhanQuyenHan,
]


class Database:    
    client: motor.motor_asyncio.AsyncIOMotorClient = None
    
    @classmethod
    def get_client(cls) -> motor.motor_asyncio.AsyncIOMotorClient:
        if cls.client is None:
            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/xoai")
            cls.client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
        return cls.client
    
    @classmethod
    def get_database(cls):
        """Get database instance."""
        client = cls.get_client()
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/xoai")
        db_name = mongo_uri.split("/")[-1].split("?")[0] or "xoai"
        return client[db_name]
    
    @classmethod
    async def close_connection(cls):
        """Close database connection."""
        if cls.client:
            cls.client.close()
            cls.client = None


async def _ensure_default_permissions() -> None:
    default_actions = ("view", "create", "edit", "delete")

    existing_perms = await QuyenHan.find_all().to_list()
    existing_perms_set = {perm.ten for perm in existing_perms}

    perms_to_create = []

    for model in DOCUMENT_MODELS:
        model_settings = getattr(model, "Settings", None)
        model_name = getattr(model_settings, "name", model.__name__)

        for action in default_actions:
            perm_name = f"{model_name}:{action}"

            if perm_name not in existing_perms_set:
                perms_to_create.append(
                    QuyenHan(ten=perm_name, mo_ta=f"Quyền {action} cho {model_name}")
                )
                existing_perms_set.add(perm_name)

    if perms_to_create:
        try:
            await QuyenHan.insert_many(perms_to_create)
            logger.info("Đã tạo %s quyền mới.", len(perms_to_create))
        except DuplicateKeyError:
            logger.info("Một số quyền đã được tạo bởi tiến trình khác, bỏ qua.")
    else:
        logger.info("Không có quyền mới nào cần tạo.")


async def _ensure_default_roles() -> None:
    admin_role_name = os.getenv("ADMIN_ROLE_NAME", "Quản trị hệ thống")
    admin_role = await TacNhan.find_one(TacNhan.ten == admin_role_name)

    if not admin_role:
        try:
            logger.info("Tạo tác nhân mặc định: %s", admin_role_name)
            admin_role = TacNhan(
                ten=admin_role_name,
                mo_ta="Quản trị viên có toàn quyền truy cập hệ thống",
                mac_dinh=True,
            )
            await admin_role.insert()
        except DuplicateKeyError:
            logger.info("Tác nhân '%s' đã được tạo, fetch lại...", admin_role_name)
            admin_role = await TacNhan.find_one(TacNhan.ten == admin_role_name)

    if admin_role:
        all_permissions = await QuyenHan.find_all().to_list()
        target_admin_perm_ids = {perm.id for perm in all_permissions if perm.id is not None}

        current_admin_links = await TacNhanQuyenHan.find(
            TacNhanQuyenHan.tac_nhan_id == admin_role.id
        ).to_list()
        current_admin_perm_ids = {
            link.quyen_han_id for link in current_admin_links if link.quyen_han_id is not None
        }

        missing_admin_perm_ids = target_admin_perm_ids - current_admin_perm_ids

        if missing_admin_perm_ids:
            links_to_create = [
                TacNhanQuyenHan(tac_nhan_id=admin_role.id, quyen_han_id=perm_id)
                for perm_id in missing_admin_perm_ids
            ]
            await TacNhanQuyenHan.insert_many(links_to_create)
            logger.info(
                "Đã gán %s quyền mới cho tác nhân '%s'.",
                len(links_to_create),
                admin_role_name,
            )
        else:
            logger.info("Tác nhân '%s' đã có đầy đủ quyền.", admin_role_name)

    staff_role_name = os.getenv("DEFAULT_ROLE_NAME", "Người dùng")
    staff_role = await TacNhan.find_one(TacNhan.ten == staff_role_name)

    if not staff_role:
        try:
            logger.info("Tạo tác nhân mặc định: '%s'.", staff_role_name)
            staff_role = TacNhan(
                ten=staff_role_name,
                mo_ta=f"Tác nhân mặc định cho người dùng là '{staff_role_name}'.",
                mac_dinh=True,
            )
            await staff_role.insert()
        except DuplicateKeyError:
            logger.info("Tác nhân '%s' đã được tạo, fetch lại...", staff_role_name)
            staff_role = await TacNhan.find_one(TacNhan.ten == staff_role_name)

    if staff_role:
        view_permissions = await QuyenHan.find({"ten": {"$regex": r":view$"}}).to_list()
        target_staff_perm_ids = {perm.id for perm in view_permissions if perm.id is not None}

        current_staff_links = await TacNhanQuyenHan.find(
            TacNhanQuyenHan.tac_nhan_id == staff_role.id
        ).to_list()
        current_staff_perm_ids = {
            link.quyen_han_id for link in current_staff_links if link.quyen_han_id is not None
        }

        missing_staff_perm_ids = target_staff_perm_ids - current_staff_perm_ids

        if missing_staff_perm_ids:
            links_to_create = [
                TacNhanQuyenHan(tac_nhan_id=staff_role.id, quyen_han_id=perm_id)
                for perm_id in missing_staff_perm_ids
            ]
            await TacNhanQuyenHan.insert_many(links_to_create)
            logger.info(
                "Đã gán %s quyền view mới cho tác nhân '%s'.",
                len(links_to_create),
                staff_role_name,
            )
        else:
            logger.info("Tác nhân '%s' đã có đầy đủ quyền view.", staff_role_name)


async def init_db():
    """Initialize database with Beanie ODM."""
    database = Database.get_database()
    
    await init_beanie(
        database=database,
        document_models=DOCUMENT_MODELS,
    )
    logger.info("Đã kết nối cơ sở dữ liệu và khởi tạo Beanie.")

    await _ensure_default_permissions()
    await _ensure_default_roles()

    if not os.path.exists(INIT_FILE_PATH):
        try:
            with open(INIT_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(f"Default data initialized on: {datetime.datetime.now(datetime.UTC)}")
            logger.info("Đã tạo file %s.", INIT_FILE_PATH)
        except IOError as e:
            logger.error(
                "Không thể tạo file %s. Dữ liệu mặc định vẫn đã được đảm bảo. Lỗi: %s",
                INIT_FILE_PATH,
                e,
            )


def get_conversations_collection():
    return Conversation.get_motor_collection()


def get_messages_collection():
    return Message.get_motor_collection()


def get_conversation_states_collection():
    return ConversationState.get_motor_collection()


# Compatibility helpers for legacy modules that may still import these names.
def get_users_collection():
    db = Database.get_database()
    return db["users"]


def get_user_groups_collection():
    db = Database.get_database()
    return db["user_groups"]


def get_orders_collection():
    db = Database.get_database()
    return db["orders"]


def get_order_items_collection():
    db = Database.get_database()
    return db["order_items"]
