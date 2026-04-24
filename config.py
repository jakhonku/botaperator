import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    admin_ids: list[int] = field(default_factory=list)
    db_path: str = "bot.db"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN .env faylida berilmagan")

    raw_admins = os.getenv("ADMIN_IDS", "")
    admin_ids: list[int] = []
    for part in raw_admins.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            admin_ids.append(int(part))
        except ValueError:
            raise RuntimeError(f"ADMIN_IDS noto'g'ri format: {part!r}")

    db_path = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"
    return Config(bot_token=token, admin_ids=admin_ids, db_path=db_path)
