from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite 数据库文件路径。相对于「运行目录」，即 back_end/chat_history.db。
DATABASE_URL = "sqlite:///./chat_history.db"

# check_same_thread=False：SQLite 默认只允许创建连接的线程使用它，
# FastAPI 的同步接口会在线程池里跑，不同请求可能用不同线程，所以需要放开这个限制。
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# SessionLocal 是一个「会话工厂」，每次调用它都会得到一个独立的数据库会话。
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Base 是所有 ORM 模型（表）的父类，models.py 里的类都继承它。
Base = declarative_base()


def get_db():
    """FastAPI 依赖：每个请求拿一个数据库会话，用完自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
