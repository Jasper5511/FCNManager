import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
os.makedirs(instance_path, exist_ok=True)

# 預設 SQLite 路徑（絕對路徑）
DEFAULT_DB = 'sqlite:///' + os.path.join(instance_path, 'fcn_data.db')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', DEFAULT_DB)


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', DEFAULT_DB)

    @staticmethod
    def init_app(app):
        uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        # 修正 postgres:// → postgresql://
        if uri and uri.startswith('postgres://'):
            app.config['SQLALCHEMY_DATABASE_URI'] = uri.replace('postgres://', 'postgresql://', 1)
        # 如果 SQLite 相對路徑有問題，改用預設絕對路徑
        if uri and uri.startswith('sqlite:///') and not uri.startswith('sqlite:////'):
            if 'instance/fcn_data.db' in uri:
                app.config['SQLALCHEMY_DATABASE_URI'] = DEFAULT_DB


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
