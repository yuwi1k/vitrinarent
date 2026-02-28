from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Создаем файл базы данных SQLite прямо в папке проекта
SQLALCHEMY_DATABASE_URL = "sqlite:///./vitrina.db"

# Настройка движка базы данных
# check_same_thread=False нужен только для SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


def ensure_property_main_page_columns():
    """Добавляет недостающие служебные столбцы в таблицу properties."""
    with engine.connect() as conn:
        r = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='properties'"))
        if not r.fetchone():
            return  # таблица ещё не создана (create_all создаст с нужными колонками)
        r = conn.execute(text("PRAGMA table_info(properties)"))
        names = [row[1] for row in r.fetchall()]
        if "show_on_main" not in names:
            conn.execute(text("ALTER TABLE properties ADD COLUMN show_on_main BOOLEAN DEFAULT 0"))
            conn.commit()
        if "main_page_order" not in names:
            conn.execute(text("ALTER TABLE properties ADD COLUMN main_page_order INTEGER"))
            conn.commit()
        if "parent_id" not in names:
            conn.execute(text("ALTER TABLE properties ADD COLUMN parent_id INTEGER REFERENCES properties(id)"))
            conn.commit()

# Создаем фабрику сессий для работы с БД
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для всех наших моделей
Base = declarative_base()

# Функция для получения сессии (понадобится позже)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()