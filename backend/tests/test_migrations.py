from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db import BACKEND_DIR, Base, engine


def _config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["skip_logging"] = True
    return cfg


def test_migrations_build_the_same_schema_as_the_models(db):
    Base.metadata.drop_all(engine)
    cfg = _config()
    command.upgrade(cfg, "head")
    command.check(cfg)  # raises if models and migrations disagree
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    assert current == ScriptDirectory.from_config(cfg).get_current_head()
    command.downgrade(cfg, "base")
