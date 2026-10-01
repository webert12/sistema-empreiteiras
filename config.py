import os

class Config:
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'chave-temporaria-construtora-pro')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///construtora_pro.db').replace('postgres://','postgresql://',1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
