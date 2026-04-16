import os
from pathlib import Path


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(Path(__file__).parent / "instance" / "portal.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    USER_CREDENTIALS = os.environ.get("USER_CREDENTIALS", "{}")

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return f"sqlite:///{self.DATABASE_PATH}"


class DevConfig(Config):
    DEBUG = True
    ENV = "development"


class ProdConfig(Config):
    DEBUG = False
    ENV = "production"


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    if env == "production":
        return ProdConfig()
    return DevConfig()
