import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from app.models import Base

# 确保 data 目录存在，避免首次启动建库失败
os.makedirs("data", exist_ok=True)

DATABASE_URL = "sqlite+aiosqlite:///./data/tubehub.db"
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# v3.0+ 字段升级：旧库 ALTER TABLE 新增列（新列若已存在则跳过）
_MIGRATION_COLUMNS = {
    "videos": [
        ("video_format_id", "VARCHAR(32)"),
        ("audio_format_id", "VARCHAR(32)"),
    ],
    "download_tasks": [
        ("video_format_id", "VARCHAR(32) NOT NULL DEFAULT ''"),
        ("audio_format_id", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ],
}


async def _ensure_columns(conn) -> None:
    """逐表逐列检查，存在则跳过，不存在则 ALTER TABLE ADD COLUMN。

    关键：AsyncConnection 不能直接 inspect，必须用 run_sync 把同步 inspect
    操作代理到事件循环内部执行。"""
    from sqlalchemy import inspect

    def _inspect_tables(sync_conn) -> dict:
        inspector = inspect(sync_conn)
        result = {}
        for table in _MIGRATION_COLUMNS:
            if inspector.has_table(table):
                result[table] = {c["name"] for c in inspector.get_columns(table)}
        return result

    table_columns = await conn.run_sync(_inspect_tables)

    for table, existing_cols in table_columns.items():
        for col_name, col_type in _MIGRATION_COLUMNS[table]:
            if col_name not in existing_cols:
                await conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                )


async def init_db() -> None:
    """启动时建表 + 启用外键 + 兼容旧库字段升级"""
    async with engine.begin() as conn:
        # 关键：SQLite 必须在每次连接时启用外键，否则 CASCADE 不生效
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.run_sync(Base.metadata.create_all)
        # v3.0 兼容：若旧库表已存在，补充新字段
        await _ensure_columns(conn)
