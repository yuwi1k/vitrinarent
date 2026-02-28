from lxml import etree
from datetime import datetime

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
        etree.SubElement(ad, "OperationType").text = "Сдам"  # Или "Продам"
        etree.SubElement(ad, "Price").text = str(prop.price)
        etree.SubElement(ad, "Title").text = prop.title
        etree.SubElement(ad, "Description").text = prop.description or "Описание отсутствует"
        
        # Адрес (пока просто текстом, для Авито в идеале нужны координаты)
        etree.SubElement(ad, "Address").text = prop.address or "Москва, Кремль"

        # Площадь
        etree.SubElement(ad, "Square").text = str(prop.area)
        
        # Контакты (заглушки, потом вынесем в настройки)
        etree.SubElement(ad, "ContactPhone").text = "+79990000000"
        etree.SubElement(ad, "ManagerName").text = "Менеджер Vitrina"

        # Картинки
        if prop.main_image:
            images = etree.SubElement(ad, "Images")
            # Авито требует полные ссылки (с http), поэтому добавляем домен
            # Замени 'http://mysite.com' на свой реальный домен при деплое
            full_url = "http://127.0.0.1:8000" + prop.main_image
            etree.SubElement(images, "Image", url=full_url)

    # Превращаем в строку
    return etree.tostring(root, pretty_print=True, encoding="UTF-8", xml_declaration=True)