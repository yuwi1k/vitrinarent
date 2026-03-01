import os
from datetime import datetime
from lxml import etree

# Функция для создания XML
def generate_avito_feed(properties):
    # Корневой элемент <Ads>
    root = etree.Element("Ads", formatVersion="3", target="Avito.ru")

    for prop in properties:
        # Создаем объявление <Ad>
        ad = etree.SubElement(root, "Ad")

        # Обязательные поля для Авито (Коммерческая недвижимость)
        etree.SubElement(ad, "Id").text = str(prop.id)
        etree.SubElement(ad, "Category").text = "Коммерческая недвижимость"
        operation_type = "Сдам" if (getattr(prop, "deal_type", None) or "").strip() == "Аренда" else "Продам"
        etree.SubElement(ad, "OperationType").text = operation_type
        etree.SubElement(ad, "Price").text = str(prop.price)
        etree.SubElement(ad, "Title").text = prop.title
        etree.SubElement(ad, "Description").text = prop.description or "Описание отсутствует"
        
        # Адрес (пока просто текстом, для Авито в идеале нужны координаты)
        etree.SubElement(ad, "Address").text = prop.address or "Москва, Кремль"

        # Площадь
        etree.SubElement(ad, "Square").text = str(prop.area)
        
        # Контакты из настроек (.env)
        contact_phone = os.getenv("AVITO_CONTACT_PHONE", os.getenv("CONTACT_PHONE", "+79990000000"))
        manager_name = os.getenv("AVITO_MANAGER_NAME", os.getenv("MANAGER_NAME", "Менеджер Vitrina"))
        etree.SubElement(ad, "ContactPhone").text = contact_phone.strip() or "+79990000000"
        etree.SubElement(ad, "ManagerName").text = manager_name.strip() or "Менеджер Vitrina"

        # Картинки
        if prop.main_image:
            images = etree.SubElement(ad, "Images")
            site_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
            full_url = site_url + prop.main_image
            etree.SubElement(images, "Image", url=full_url)

    # Превращаем в строку
    return etree.tostring(root, pretty_print=True, encoding="UTF-8", xml_declaration=True)