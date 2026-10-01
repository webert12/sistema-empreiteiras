import os


def database_uri():
    url = os.getenv("DATABASE_URL", "sqlite:///construtora_pro.db")

    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)

    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


class Config:
    SECRET_KEY = os.getenv(
        "FLASK_SECRET_KEY",
        "chave-temporaria-construtora-pro"
    )
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
