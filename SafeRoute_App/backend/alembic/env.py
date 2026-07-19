import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Proje modellerini ve ayarlarını içe aktar
from config import settings
from models import Base

# Bu, Alembic Config nesnesi; alembic.ini içindeki değerlere erişim sağlar.
config = context.config

# Veritabanı URL'sini .env / config.py üzerinden dinamik olarak ayarla
config.set_main_option("sqlalchemy.url", settings.database_url)

# Python logging ayarlarını yükle
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate'in karşılaştıracağı model metadata'sı
target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """
    PostGIS/Tiger Geocoder eklentisinin oluşturduğu sistem tablolarını
    (direction_lookup, faces, county_lookup, tract, edges, vb.) ve
    onlara ait index'leri migration karşılaştırmasından hariç tut.

    Mantık: Eğer bir tablo veritabanında fiziksel olarak VAR (reflected=True)
    ama bizim models.py içindeki Base.metadata'da hiç TANIMLI DEĞİLSE
    (compare_to is None), bu bizim uygulamamıza ait değildir - dokunma.
    """
    if reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """'Offline' modda migration çalıştır (DB bağlantısı olmadan SQL üretir)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async engine üzerinden migration çalıştır."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()