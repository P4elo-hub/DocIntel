import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_models import Base
from app.chat.repositories.pg_repo import PostgresChatRepository


def _to_asyncpg_url(sync_url: str) -> str:
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    if async_url == sync_url:
        async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://")
    return async_url


@pytest.fixture(params=["json", "postgres"])
async def chat_repository(request, tmp_path):
    if request.param == "json":
        yield JsonChatRepository(base_dir=tmp_path)
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers не установлен")

    try:
        with PostgresContainer("postgres:16-alpine") as postgres:
            engine = create_async_engine(_to_asyncpg_url(postgres.get_connection_url()))
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                await session.execute(text("TRUNCATE chat_messages, chats RESTART IDENTITY CASCADE"))
                await session.commit()
                yield PostgresChatRepository(session=session)

            await engine.dispose()
    except Exception as exc:
        pytest.skip(f"Postgres testcontainer недоступен: {exc}")
