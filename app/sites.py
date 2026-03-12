"""
Multi-site configuration.
Each site has its own branding, templates, contacts, and styling.
"""
import os
from dataclasses import dataclass, field


@dataclass
class SiteConfig:
    id: str
    name: str
    title_suffix: str
    description: str
    template_prefix: str
    css_file: str
    logo_text: str
    contacts: dict = field(default_factory=dict)
    show_contacts: bool = False
    nav_items: list = field(default_factory=list)


SITES: dict[str, SiteConfig] = {
    "vitrina": SiteConfig(
        id="vitrina",
        name="Vitrina",
        title_suffix="Vitrina",
        description="Каталог коммерческой недвижимости для агентов",
        template_prefix="",
        css_file="/static/css/vitrina-asset.css",
        logo_text="Vitrina",
        show_contacts=False,
        nav_items=[
            {"url": "/", "label": "Главная", "id": "home"},
            {"url": "/search", "label": "Поиск", "id": "search"},
            {"url": "/map", "label": "Карта", "id": "map"},
            {"url": "/faq", "label": "FAQ", "id": "faq"},
        ],
    ),
    "diapazon": SiteConfig(
        id="diapazon",
        name='АО «Диапазон»',
        title_suffix="АО Диапазон",
        description="Аренда и продажа коммерческой недвижимости от АО Диапазон",
        template_prefix="diapazon/",
        css_file="/static/diapazon/css/diapazon-asset.css",
        logo_text="Диапазон",
        show_contacts=True,
        contacts={
            "phone": "+7 (XXX) XXX-XX-XX",
            "email": "info@diapazon.ru",
            "address": "г. Москва",
            "manager_name": "Менеджер",
        },
        nav_items=[
            {"url": "/", "label": "Главная", "id": "home"},
            {"url": "/search", "label": "Каталог", "id": "search"},
            {"url": "/map", "label": "Карта", "id": "map"},
            {"url": "/about", "label": "О компании", "id": "about"},
            {"url": "/contacts", "label": "Контакты", "id": "contacts"},
        ],
    ),
}

_DOMAIN_MAP: dict[str, str] = {}


def _build_domain_map():
    global _DOMAIN_MAP
    _DOMAIN_MAP = {}
    for site_id in SITES:
        env_key = f"SITE_DOMAINS_{site_id.upper()}"
        domains = os.getenv(env_key, "").strip()
        if domains:
            for d in domains.split(","):
                d = d.strip().lower()
                if d:
                    _DOMAIN_MAP[d] = site_id


_build_domain_map()

DEFAULT_SITE_ID = os.getenv("DEFAULT_SITE", "vitrina")


def get_site_by_host(host: str) -> SiteConfig:
    """Determine site config from request Host header."""
    host_clean = host.lower().split(":")[0].strip()
    site_id = _DOMAIN_MAP.get(host_clean, DEFAULT_SITE_ID)
    return SITES.get(site_id, SITES["vitrina"])
