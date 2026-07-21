from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.config import settings
from app.database import Base
import app.models  # noqa: F401  autogenerate가 모델을 인식하도록 등록

config = context.config

# DB URL 은 alembic.ini 가 아니라 앱 설정에서 읽는다.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    # PostGIS 관리 스키마 제외 — public 만 autogenerate.
    if type_ == "schema":
        return name in (None, "public")
    return True


def include_object(object, name, type_, reflected, compare_to):
    # 우리 모델에 정의된 테이블만 관리한다. DB에만 있는 PostGIS
    # 내장 객체는 autogenerate에서 제외.
    if reflected:
        owner = name if type_ == "table" else getattr(getattr(object, "table", None), "name", None)
        if owner is not None and owner not in target_metadata.tables:
            return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
