from datetime import datetime, timezone

from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, Text, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship, backref
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)

class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    # Цена может быть больше int4, используем BigInteger
    price = Column(BigInteger, index=True)
    area = Column(Float, index=True)
    address = Column(String)
    
    # Главное фото (превью). В БД храним путь, всегда начинающийся с /static/ (например /static/uploads/properties/...)
    main_image = Column(String, nullable=True) 
    is_active = Column(Boolean, default=True)

    # Показывать на главной (ровно 3 объекта), порядок: меньше main_page_order — выше в списке
    show_on_main = Column(Boolean, default=False)
    main_page_order = Column(Integer, nullable=True)
    
    # Поля для агентства
    deal_type = Column(String, default="Аренда", index=True) 
    category = Column(String, default="Офис", index=True)
    # Тип объекта для фида Авито (если пусто — подставляется по category)
    avito_object_type = Column(String, nullable=True)
    # Доп. поля шаблона Авито (ключи — имена тегов, значения — строки/числа для XML)
    avito_data = Column(JSON, nullable=True)
    # Данные по объявлению на Циан (CianOfferId, status и т.д.)
    cian_data = Column(JSON, nullable=True)

    # Координаты для карты
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Базовые характеристики здания/помещения
    floors_total = Column(Integer, nullable=True)
    floor_number = Column(Integer, nullable=True)
    power_kw = Column(Float, nullable=True)
    ceiling_height = Column(Float, nullable=True)

    # Единые поля для всех площадок (Avito + CIAN)
    building_type = Column(String, nullable=True)       # "Бизнес-центр", "Торговый центр", ...
    building_class = Column(String, nullable=True)      # "A", "B", "C"
    decoration = Column(String, nullable=True)          # "Без отделки", "Чистовая", "Офисная"
    parking_type = Column(String, nullable=True)        # "Нет", "На улице", "В здании"
    entrance_type = Column(String, nullable=True)       # "С улицы", "Со двора"
    layout_type = Column(String, nullable=True)         # "Кабинетная", "Открытая", "Смешанная", "Коридорная"
    heating_type = Column(String, nullable=True)        # "Нет", "Центральное", "Автономное"
    property_rights = Column(String, nullable=True)     # "Собственник", "Посредник"
    rental_type = Column(String, nullable=True)         # "Прямая", "Субаренда"
    parking_spaces = Column(Integer, nullable=True)
    distance_from_road = Column(String, nullable=True)  # "Первая линия", "Вторая линия и дальше"

    # Статистика с площадок (заполняется scheduler)
    stats_data = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True)

    # Родительский объект (для иерархии "матрешек")
    parent_id = Column(Integer, ForeignKey("properties.id"), nullable=True)

    # --- СВЯЗИ С НОВЫМИ ТАБЛИЦАМИ ---
    # lazy="selectin" подходит для асинхронной работы (предзагрузка связей). order_by — порядок фото в галерее.
    images = relationship(
        "PropertyImage", back_populates="property", cascade="all, delete-orphan", lazy="selectin",
        order_by="PropertyImage.sort_order",
    )
    documents = relationship(
        "PropertyDocument", back_populates="property", cascade="all, delete-orphan", lazy="selectin"
    )

    # Иерархия "Здание → Этаж → Офис"
    children = relationship(
        "Property",
        backref=backref("parent", remote_side="Property.id"),
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def children_count_badge(self) -> str:
        """Короткое текстовое представление состава объекта для админки."""
        count = len(self.children or [])
        return f"Помещений: {count}" if count > 0 else "Целиком"

    # Поля только для формы админки (загрузка доп. фото/документов); не колонки БД
    @property
    def extra_images(self):
        return []

    @property
    def extra_documents(self):
        return []

    @property
    def avito_id(self) -> str:
        data = self.avito_data or {}
        v = data.get("AvitoId") if isinstance(data, dict) else None
        return str(v).strip() if v is not None else ""

    @property
    def is_on_avito(self) -> bool:
        return bool(self.avito_id)

    @property
    def cian_offer_id(self) -> str:
        data = self.cian_data or {}
        v = data.get("CianOfferId") if isinstance(data, dict) else None
        return str(v).strip() if v is not None else ""

    @property
    def is_on_cian(self) -> bool:
        return bool(self.cian_offer_id)

    @property
    def cian_status(self) -> str:
        data = self.cian_data or {}
        v = data.get("CianStatus") if isinstance(data, dict) else None
        return str(v).strip() if v is not None else ""


# ТАБЛИЦА ДЛЯ ГАЛЕРЕИ (МНОГО ФОТО). image_url хранит путь, начинающийся с /static/
class PropertyImage(Base):
    __tablename__ = "property_images"
    
    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"))
    image_url = Column(String)  # URL картинки, например /static/uploads/properties/1_xxx/images/uuid.jpg
    sort_order = Column(Integer, default=0, nullable=False)  # порядок вывода в галерее (меньше — выше)

    property = relationship("Property", back_populates="images", lazy="selectin")


# ТАБЛИЦА ДЛЯ ДОКУМЕНТОВ
class PropertyDocument(Base):
    __tablename__ = "property_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"))
    title = Column(String) # Например: "План БТИ" или "Договор"
    document_url = Column(String)
    
    property = relationship("Property", back_populates="documents", lazy="selectin")