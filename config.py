import os
from dataclasses import dataclass, field
from typing import List
from typing import Optional

@dataclass
class Config:
    """Конфігурація бота"""
    
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")

    CHANNEL_ID: str = os.getenv("CHANNEL_ID")
    
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///dd_bot.db")
    
    # AI Services
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GOOGLE_VISION_KEY: str = os.getenv("GOOGLE_VISION_KEY", "")
    API_LOGIN: str = os.getenv("API_LOGIN", "")
    API_PASSWORD: str = os.getenv("API_PASSWORD", "")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://ddwonder.com.ua/api")
    
    # Admin Settings
    ADMIN_IDS: List[int] = field(
        default_factory=lambda: [
            int(x.strip())
            for x in os.getenv("ADMIN_IDS", "").split(",")
            if x.strip().isdigit()
        ]
    )
    
    # Limits
    TRUSTED_DAILY_LIMIT: int = 10
    UNTRUSTED_DAILY_LIMIT: int = 5
    MAX_PHOTOS_PER_LOT: int = 3
    
    WATERMARK_PATH: str = "assets/watermark.png"
    # Watermark Settings
    WATERMARK_OPACITY: float = 0.7  # 70%
    WATERMARK_POSITION: str = "bottom_right"
    WATERMARK_TEMP_CHAT_ID: Optional[str] = field(default_factory=lambda: os.getenv("WATERMARK_TEMP_CHAT_ID"))

    # File Paths
    
    WATERMARK_PATH: str = "assets/watermark.png"
    BANNER_PATH: str = "assets/banner.jpg"
    
    def __post_init__(self):
        """Перевірка обов'язкових параметрів"""
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не встановлено")
        if not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY не встановлено")
        if not self.GOOGLE_VISION_KEY:
            raise ValueError("GOOGLE_VISION_KEY не встановлено")