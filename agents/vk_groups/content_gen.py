"""
agents/vk_groups/content_gen.py — Генератор контента для VK групп
Взят из VKGA (полная версия с 14 шаблонами)
"""
import random, re

NAME_TEMPLATES = [
    "{keyword} | {region}",
    "{keyword} — официальный набор",
    "{keyword} рядом с центром",
    "{keyword} | официальная страница",
    "{keyword} {region} — подробности здесь",
    "{keyword}: всё что нужно знать",
    "{brand} | {keyword}",
    "{keyword} — {brand}",
    "Лучший {keyword} в {region}",
    "{keyword} | запись онлайн",
    "{keyword} {region} | актуально",
    "О нас | {keyword} {region}",
    "{keyword} — узнать больше",
    "{brand} — {keyword} {region}",
]

INTRO_BLOCKS = [
    "Добро пожаловать! Здесь вы найдёте всю информацию о {keyword} в {region}.",
    "Эта группа создана для тех, кто ищет {keyword}.",
    "Вы искали {keyword}? Вы пришли по адресу!",
    "Мы расскажем всё о {keyword} — актуально, честно, подробно.",
    "Официальная информация о {keyword} в {region}.",
]

UTP_BLOCKS = [
    "{brand} — это надёжность и качество, проверенные временем.",
    "{brand} — лидер в своей сфере с многолетним опытом.",
    "Мы гордимся результатами наших клиентов.",
    "Наш подход: индивидуально, профессионально, с заботой о каждом.",
    "{brand} — ваш выбор для лучшего старта.",
]

KEYWORD_BLOCKS = [
    "Если вы ищете {keyword} — здесь самая свежая информация.",
    "Всё о {keyword}: условия, цены, запись — в одном месте.",
    "Задайте вопрос о {keyword} прямо здесь — ответим быстро!",
    "Узнать о {keyword} проще простого — пишите в сообщения группы.",
    "{keyword} в {region} — мы знаем всё об этом.",
]

ADVANTAGES_BLOCKS = [
    "Опытные специалисты\nИндивидуальный подход\nПрозрачные условия",
    "Профессиональная команда\nГибкий график\nСовременные методики",
    "Высокий уровень сервиса\nУдобное расположение\nДоступные цены",
]

CTA_BLOCKS = [
    "Подробности на сайте: {site_url}",
    "Вся информация: {site_url} — заходите!",
    "Запишитесь прямо сейчас: {site_url}",
]

PINNED_TITLES = [
    "Добро пожаловать!",
    "Важная информация",
    "О нас — коротко и ясно",
    "Привет! Рады вам здесь",
    "Для новых подписчиков",
]

PINNED_INTROS = [
    "Мы рады, что вы нашли нас! Расскажем самое важное:",
    "Эта группа создана специально для вас. Вот что вы должны знать:",
    "Несколько слов о нас — чтобы вы знали, куда попали:",
]


def _title_case(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


def generate_name(keyword: str, brand: str = "", region: str = "") -> str:
    kw = _title_case(keyword)
    br = brand.strip() if brand else ""
    rg = _title_case(region) if region else ""

    tmpl = random.choice(NAME_TEMPLATES)
    if "{brand}" in tmpl and not br:
        tmpl = random.choice([t for t in NAME_TEMPLATES if "{brand}" not in t])
    if "{region}" in tmpl and not rg:
        safe = [t for t in NAME_TEMPLATES if "{region}" not in t and "{brand}" not in t]
        if safe: tmpl = random.choice(safe)

    return tmpl.format(keyword=kw, brand=br, region=rg)[:80].strip()


def generate_description(keyword: str, base_description: str = "",
                          brand: str = "", region: str = "",
                          site_url: str = "") -> str:
    ctx = {
        "keyword": keyword,
        "brand": brand or "Наша компания",
        "region": region or "вашем городе",
        "site_url": site_url or ""
    }
    parts = [random.choice(INTRO_BLOCKS).format(**ctx)]
    if base_description:
        adapted = base_description
        if keyword.lower() not in base_description.lower():
            adapted += f"\n\nМы специализируемся на: {keyword}."
        parts.append(adapted)
    parts.append(random.choice(UTP_BLOCKS).format(**ctx))
    parts.append(random.choice(KEYWORD_BLOCKS).format(**ctx))
    parts.append(random.choice(ADVANTAGES_BLOCKS))
    if site_url:
        parts.append(random.choice(CTA_BLOCKS).format(**ctx))
    middle = parts[1:-1] if site_url else parts[1:]
    random.shuffle(middle)
    final = [parts[0]] + middle
    if site_url: final.append(parts[-1])
    return "\n\n".join(final)[:4096]


def generate_pinned_post_text(keyword: str, base_text: str = "",
                               brand: str = "", site_url: str = "",
                               region: str = "") -> str:
    ctx = {"keyword": keyword, "brand": brand or "Наша компания",
           "site_url": site_url, "region": region or ""}
    title = random.choice(PINNED_TITLES)
    intro = random.choice(PINNED_INTROS)
    if base_text:
        main = base_text
        if keyword.lower() not in base_text.lower():
            main += f"\n\nМы специализируемся на: {keyword}."
    else:
        main = f"Мы занимаемся {keyword}" + (f" в {region}" if region else "") + ". Наша цель — дать вам лучший сервис."
    cta = f"Все подробности: {site_url}" if site_url else ""
    parts = [title, intro, main]
    if cta: parts.append(cta)
    return "\n\n".join(parts)[:4096]
