from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship, backref
from app.database import Base

class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True) 
    description = Column(Text, nullable=True) 
    price = Column(Integer, index=True) 
    area = Column(Float, index=True) 
    address = Column(String) 
    
    # Главное фото (превью), которое мы обрезаем через визуальный редактор
    main_image = Column(String, nullable=True) 
    is_active = Column(Boolean, default=True)

    # Показывать на главной (ровно 3 объекта), порядок: меньше main_page_order — выше в списке
    show_on_main = Column(Boolean, default=False)
    main_page_order = Column(Integer, nullable=True)
    
    # Поля для агентства
    deal_type = Column(String, default="Аренда", index=True) 
    category = Column(String, default="Офис", index=True) 
    
    # Координаты для карты
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Родительский объект (для иерархии "матрешек")
    parent_id = Column(Integer, ForeignKey("properties.id"), nullable=True)

    # --- СВЯЗИ С НОВЫМИ ТАБЛИЦАМИ ---
    # cascade="all, delete-orphan" означает, что если ты удалишь объект,
    # все его фотки и документы из базы удалятся автоматически
    images = relationship("PropertyImage", back_populates="property", cascade="all, delete-orphan")
    documents = relationship("PropertyDocument", back_populates="property", cascade="all, delete-orphan")

    # Иерархия "Здание → Этаж → Офис"
    children = relationship(
        "Property",
        backref=backref("parent", remote_side="Property.id"),
        cascade="all, delete-orphan",
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


# ТАБЛИЦА ДЛЯ ГАЛЕРЕИ (МНОГО ФОТО)
class PropertyImage(Base):
    __tablename__ = "property_images"
    
    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"))
    image_url = Column(String)
    
    property = relationship("Property", back_populates="images")


# ТАБЛИЦА ДЛЯ ДОКУМЕНТОВ
class PropertyDocument(Base):
    __tablename__ = "property_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"))
    title = Column(String) # Например: "План БТИ" или "Договор"
    document_url = Column(String)
    
    property = relationship("Property", back_populates="documents")