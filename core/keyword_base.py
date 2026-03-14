"""
core/keyword_base.py — Встроенная база ниш и шаблонов ключевых слов
Используется когда Яндекс.Wordstat недоступен.
AI берёт отсюда шаблоны и подставляет реальные данные с сайта.
"""

# Суффиксы которые превращают общий запрос в низкочастотный
LOW_FREQ_SUFFIXES = [
    "цена", "цены", "стоимость", "сколько стоит",
    "недорого", "дешево", "дешевле",
    "отзывы", "отзыв", "рейтинг",
    "адрес", "где находится", "как добраться",
    "телефон", "контакты", "записаться",
    "акция", "скидка", "акции", "скидки",
    "рядом", "рядом со мной", "ближайший",
    "хороший", "лучший", "топ",
    "круглосуточно", "выходные",
    "онлайн", "дистанционно",
    "срочно", "быстро",
    "без очереди", "без записи",
]

# База ниш: каждая ниша содержит ключевые услуги и шаблоны
NICHE_BASE = {

    "стоматология": {
        "keywords": ["стоматология", "стоматолог", "зубной врач",
                     "зубная клиника", "стоматологическая клиника"],
        "services": ["имплантация зубов", "брекеты", "протезирование зубов",
                     "отбеливание зубов", "лечение кариеса", "удаление зуба",
                     "виниры", "коронки", "детский стоматолог",
                     "чистка зубов", "исправление прикуса"],
        "templates": [
            "{service} {region}",
            "{service} {region} {suffix}",
            "{keyword} {region} {suffix}",
            "детская {keyword} {region}",
            "платная {keyword} {region}",
            "семейная {keyword} {region}",
        ]
    },

    "ремонт квартир": {
        "keywords": ["ремонт квартир", "ремонт квартиры", "отделка квартиры"],
        "services": ["ремонт под ключ", "косметический ремонт",
                     "капитальный ремонт", "дизайн интерьера",
                     "укладка плитки", "натяжные потолки",
                     "поклейка обоев", "покраска стен",
                     "электрика", "сантехника", "монтаж гипсокартона"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} {suffix}",
            "{keyword} {region} под ключ",
            "бригада {keyword} {region}",
        ]
    },

    "образование": {
        "keywords": ["репетитор", "курсы", "обучение", "школа",
                     "подготовка", "занятия"],
        "services": ["репетитор математика", "репетитор английский",
                     "подготовка к ЕГЭ", "подготовка к ОГЭ",
                     "подготовка к школе", "курсы английского",
                     "частная школа", "детский сад",
                     "кружки для детей", "дополнительное образование"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} {suffix}",
            "онлайн {keyword} {region}",
            "{keyword} для детей {region}",
        ]
    },

    "медицина": {
        "keywords": ["клиника", "медцентр", "врач", "доктор",
                     "медицинский центр"],
        "services": ["терапевт", "педиатр", "гинеколог", "уролог",
                     "кардиолог", "невролог", "эндокринолог",
                     "УЗИ", "анализы", "МРТ", "диагностика",
                     "вакцинация", "медосмотр"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "частная {keyword} {region}",
            "платный {service} {region}",
            "{service} {region} без очереди",
        ]
    },

    "юридические услуги": {
        "keywords": ["юрист", "адвокат", "юридическая консультация",
                     "юридические услуги"],
        "services": ["юрист по разводу", "юрист по алиментам",
                     "юрист по наследству", "юрист по ДТП",
                     "юрист по трудовым спорам", "банкротство физлиц",
                     "юрист по недвижимости", "адвокат по уголовным делам",
                     "юридическое сопровождение бизнеса"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "бесплатная {keyword} {region}",
            "онлайн {keyword} {region}",
            "{service} {region} {suffix}",
        ]
    },

    "красота": {
        "keywords": ["салон красоты", "парикмахерская", "студия красоты",
                     "салон"],
        "services": ["стрижка", "окрашивание волос", "маникюр", "педикюр",
                     "наращивание ресниц", "оформление бровей",
                     "шугаринг", "восковая депиляция", "лазерная эпиляция",
                     "массаж", "чистка лица", "перманентный макияж"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} {suffix}",
            "мастер {service} {region}",
            "{service} на дому {region}",
        ]
    },

    "фитнес": {
        "keywords": ["фитнес", "спортзал", "тренажерный зал",
                     "фитнес-клуб"],
        "services": ["фитнес-клуб", "тренажерный зал", "йога",
                     "пилатес", "бассейн", "групповые тренировки",
                     "персональный тренер", "бокс", "единоборства",
                     "похудение", "набор мышечной массы", "кроссфит"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} {suffix}",
            "{keyword} для женщин {region}",
            "{service} для начинающих {region}",
        ]
    },

    "автосервис": {
        "keywords": ["автосервис", "СТО", "автомастерская",
                     "техническое обслуживание авто"],
        "services": ["ремонт двигателя", "кузовной ремонт",
                     "покраска авто", "шиномонтаж", "балансировка",
                     "замена масла", "диагностика авто",
                     "ремонт ходовой", "автоэлектрик",
                     "детейлинг", "полировка авто", "техосмотр"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} {suffix}",
            "недорогой {keyword} {region}",
            "{keyword} {region} срочно",
        ]
    },

    "недвижимость": {
        "keywords": ["риелтор", "агентство недвижимости",
                     "купить квартиру", "аренда квартиры"],
        "services": ["купить квартиру", "продать квартиру",
                     "аренда квартиры", "аренда офиса",
                     "новостройки", "вторичное жилье",
                     "ипотека", "оценка недвижимости",
                     "сопровождение сделки"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} {suffix}",
            "{service} в {region} без посредников",
            "{keyword} {region} недорого",
        ]
    },

    "доставка еды": {
        "keywords": ["доставка еды", "доставка", "заказ еды"],
        "services": ["доставка пиццы", "доставка суши", "доставка роллов",
                     "доставка бургеров", "доставка обедов",
                     "доставка шашлыка", "доставка торта",
                     "кейтеринг", "готовая еда на дом"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} быстро",
            "{service} {region} круглосуточно",
            "бесплатная {keyword} {region}",
        ]
    },

    "строительство": {
        "keywords": ["строительство", "строительная компания",
                     "строительство домов"],
        "services": ["строительство домов", "строительство коттеджей",
                     "каркасные дома", "дома из бруса",
                     "дома из газобетона", "фундамент",
                     "кровля", "монтаж кровли", "забор",
                     "баня под ключ", "проект дома"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} под ключ",
            "{service} {region} {suffix}",
            "бригада {service} {region}",
        ]
    },

    "грузоперевозки": {
        "keywords": ["грузоперевозки", "газель", "переезд",
                     "грузовое такси"],
        "services": ["квартирный переезд", "офисный переезд",
                     "грузоперевозки по городу",
                     "грузоперевозки межгород",
                     "аренда газели", "грузчики",
                     "перевозка мебели", "перевозка пианино"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "{service} {region} недорого",
            "{keyword} {region} срочно",
            "{service} с грузчиками {region}",
        ]
    },

    "ветеринария": {
        "keywords": ["ветеринар", "ветклиника", "ветеринарная клиника",
                     "ветеринарный врач"],
        "services": ["лечение кошек", "лечение собак",
                     "вакцинация животных", "стерилизация кошек",
                     "кастрация котов", "стоматология для животных",
                     "УЗИ для животных", "ветеринар на дому",
                     "зоомагазин", "груминг"],
        "templates": [
            "{service} {region}",
            "{keyword} {region} {suffix}",
            "круглосуточная {keyword} {region}",
            "{service} {region} {suffix}",
            "{keyword} на дому {region}",
        ]
    },

}

# Универсальные шаблоны для любой ниши
UNIVERSAL_TEMPLATES = [
    "{keyword} {region}",
    "{keyword} {region} {suffix}",
    "{keyword} в {region}",
    "лучший {keyword} в {region}",
    "{keyword} {region} отзывы",
    "{keyword} {region} цены",
    "{keyword} {region} недорого",
    "{keyword} {region} адрес",
]


def get_niche_data(niche_name: str) -> dict:
    """
    Возвращает данные по нише. Ищет по вхождению слова.
    Если не найдена — возвращает универсальные шаблоны.
    """
    niche_lower = niche_name.lower()
    for key, data in NICHE_BASE.items():
        if key in niche_lower or niche_lower in key:
            return data
        # Ищем по ключевым словам ниши
        if any(kw in niche_lower or niche_lower in kw
               for kw in data.get("keywords", [])):
            return data

    # Универсальные шаблоны для неизвестной ниши
    return {
        "keywords": [niche_name],
        "services": [niche_name],
        "templates": UNIVERSAL_TEMPLATES,
    }


def expand_keywords(niche: str, region: str,
                    services: list = None, count: int = 30) -> list:
    """
    Быстрая генерация ключей из базы без AI.
    Используется как запасной вариант.
    """
    import random
    data     = get_niche_data(niche)
    all_svcs = services if services else data.get("services", [niche])
    tmpls    = data.get("templates", UNIVERSAL_TEMPLATES)
    suffixes = random.sample(LOW_FREQ_SUFFIXES, min(8, len(LOW_FREQ_SUFFIXES)))
    keywords = set()

    for service in all_svcs:
        for tmpl in tmpls:
            for sfx in suffixes:
                kw = (tmpl
                      .replace("{service}", service)
                      .replace("{keyword}", niche)
                      .replace("{region}", region)
                      .replace("{suffix}", sfx)
                      .strip())
                if 5 < len(kw) <= 60:
                    keywords.add(kw)
                if len(keywords) >= count * 2:
                    break

    result = list(keywords)
    random.shuffle(result)
    return result[:count]


def detect_niche(text: str) -> str:
    """
    Определяет нишу по тексту без AI.
    Грубый эвристический метод.
    """
    text_lower = text.lower()
    scores = {}
    for niche, data in NICHE_BASE.items():
        score = 0
        for kw in data.get("keywords", []):
            score += text_lower.count(kw.lower()) * 3
        for svc in data.get("services", []):
            score += text_lower.count(svc.lower())
        scores[niche] = score

    if not scores:
        return ""
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def list_niches() -> list:
    return list(NICHE_BASE.keys())
