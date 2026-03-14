"""
core/ai_content.py — AI генерация контента через Ollama (локально)
Использует модель seofarm-ai (qwen3:4b + наш Modelfile)
Fallback: если Ollama недоступна — шаблонная генерация
"""
import json, requests, logging, re, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("ai_content")

OLLAMA_URL   = "http://localhost:11434"
MODEL_NAME   = "seofarm-ai"
FALLBACK_MODEL = "qwen3:4b"
TIMEOUT      = 120  # секунд


def _is_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _get_model() -> str:
    """Возвращает имя модели — наша или fallback"""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        if MODEL_NAME in models or any(MODEL_NAME in m for m in models):
            return MODEL_NAME
        if any(FALLBACK_MODEL in m for m in models):
            return FALLBACK_MODEL
        # Берём первую доступную
        return models[0] if models else FALLBACK_MODEL
    except Exception:
        return FALLBACK_MODEL


def _ask(prompt: str, system: str = None) -> str:
    """Отправляет запрос в Ollama, возвращает текст ответа"""
    if not _is_ollama_running():
        logger.warning("[AI] Ollama недоступна — используем шаблоны")
        return ""

    model = _get_model()
    payload = {
        "model": model,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_ctx": 4096,
        }
    }

    if system:
        payload["system"] = system

    payload["prompt"] = prompt

    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate",
                         json=payload, timeout=TIMEOUT)
        data = r.json()
        return data.get("response", "").strip()
    except requests.exceptions.Timeout:
        logger.error("[AI] Таймаут Ollama")
        return ""
    except Exception as e:
        logger.error(f"[AI] Ошибка: {e}")
        return ""


def _parse_json(text: str) -> dict | list | None:
    """Извлекает JSON из ответа модели"""
    if not text:
        return None
    # Убираем markdown блоки если модель их добавила
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    # Убираем <think>...</think> блоки (qwen3 думает вслух)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    # Ищем JSON объект или массив
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    # Последняя попытка — весь текст
    try:
        return json.loads(text)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# ПУБЛИЧНЫЙ API — функции которые использует система
# ══════════════════════════════════════════════════════════════

def generate_keywords(niche: str, region: str, services: list,
                      brand: str = "", count: int = 30) -> list:
    """
    Генерирует список низкочастотных ключевых слов.
    Возвращает список строк.
    """
    services_str = ", ".join(services[:10]) if services else niche

    prompt = f"""Сгенерируй {count} низкочастотных ключевых слов для продвижения в ВКонтакте и Яндексе.

Ниша: {niche}
Регион: {region}
Услуги: {services_str}
Бренд: {brand or "не указан"}

Требования:
- Частотность 50-500 запросов/месяц (низкая конкуренция)
- Каждый ключ уникален, не повторяется
- Формат: "услуга регион" + уточнение
- Уточнения: цена, недорого, отзывы, где, рядом, адрес, запись, телефон, акция, скидка, хороший, лучший, круглосуточно, детский, взрослый

Ответь ТОЛЬКО валидным JSON массивом строк:
["ключ 1", "ключ 2", "ключ 3", ...]"""

    response = _ask(prompt)
    result = _parse_json(response)

    if isinstance(result, list) and len(result) > 0:
        # Очищаем и берём нужное количество
        keywords = [str(k).strip() for k in result if k and len(str(k)) > 3]
        logger.info(f"[AI] Сгенерировано {len(keywords)} ключей для '{niche} {region}'")
        return keywords[:count]

    # Fallback — шаблонная генерация
    logger.warning("[AI] Fallback генерация ключей")
    return _fallback_keywords(niche, region, services, count)


def generate_group_name(keyword: str, brand: str = "",
                        region: str = "") -> str:
    """
    Генерирует SEO-оптимизированное название группы (до 48 символов).
    Название = Title страницы в Яндексе.
    """
    prompt = f"""Придумай 5 вариантов названия VK группы для ключевого слова.

Ключевое слово: {keyword}
Бренд: {brand or "не указан"}
Регион: {region or "не указан"}

Правила:
- Максимум 48 символов ОБЯЗАТЕЛЬНО
- Ключевое слово должно быть в названии точно или близко
- Естественный русский язык
- Без восклицательных знаков и капса

Ответь ТОЛЬКО валидным JSON:
{{"names": ["вариант 1", "вариант 2", "вариант 3", "вариант 4", "вариант 5"]}}"""

    response = _ask(prompt)
    data = _parse_json(response)

    if data and isinstance(data.get("names"), list):
        names = [n for n in data["names"] if n and len(n) <= 48]
        if names:
            import random
            return random.choice(names)

    # Fallback
    return _fallback_name(keyword, brand, region)


def generate_group_description(keyword: str, brand: str, region: str,
                                site_url: str, services: list,
                                utp: str = "") -> str:
    """
    Генерирует SEO-описание группы с ключами и тегами.
    """
    services_str = ", ".join(services[:5]) if services else keyword

    prompt = f"""Напиши SEO-оптимизированное описание для VK группы.

Ключевое слово: {keyword}
Бренд: {brand}
Регион: {region}
Сайт: {site_url}
Услуги: {services_str}
УТП (преимущества): {utp or "профессионально, качественно, быстро"}

Требования:
- 400-600 символов
- Первое предложение содержит точный ключ "{keyword}"
- В конце теги: #ключевое_слово #регион #услуга
- Ссылка на сайт {site_url}
- Живой разговорный тон

Ответь ТОЛЬКО валидным JSON:
{{"description": "текст описания", "tags": ["тег1", "тег2", "тег3"]}}"""

    response = _ask(prompt)
    data = _parse_json(response)

    if data and data.get("description"):
        desc = data["description"]
        tags = data.get("tags", [])
        if tags:
            tags_str = " ".join(f"#{t.replace(' ', '_').replace('#', '')}"
                               for t in tags[:10])
            if tags_str not in desc:
                desc = f"{desc}\n\n{tags_str}"
        return desc[:4096]

    return _fallback_description(keyword, brand, region, site_url)


def generate_pinned_post(keyword: str, brand: str, region: str,
                          site_url: str, services: list,
                          utp: str = "") -> str:
    """Генерирует закреплённый пост для новой группы"""
    services_str = ", ".join(services[:5]) if services else keyword

    prompt = f"""Напиши закреплённый пост для VK группы. Это первое что увидит посетитель.

Ключевое слово: {keyword}
Бренд: {brand}
Регион: {region}
Сайт: {site_url}
Услуги: {services_str}
УТП: {utp or "профессионально, качественно, доступно"}

Требования:
- 300-500 символов
- Привлекательный заголовок первой строкой
- Ключ "{keyword}" в тексте естественно
- Призыв к действию + ссылка {site_url}
- Хэштеги в конце: #ключ #регион

Ответь ТОЛЬКО валидным JSON:
{{"text": "текст поста"}}"""

    response = _ask(prompt)
    data = _parse_json(response)

    if data and data.get("text"):
        return data["text"][:4096]

    return _fallback_post(keyword, brand, region, site_url)


def generate_warmup_post(keyword: str, brand: str, region: str,
                          site_url: str, day: int,
                          services: list) -> str:
    """
    Генерирует пост для прогрева группы.
    day: 1-7 — день прогрева, каждый день разная тема.
    """
    topics = {
        2: f"Расскажи подробнее об услуге '{keyword}': что входит, сколько стоит, как записаться",
        4: f"Напиши пост с ответами на частые вопросы о '{keyword}'",
        5: f"Напиши вовлекающий пост-вопрос к аудитории о теме '{keyword}'",
        7: f"Напиши пост с отзывом довольного клиента о '{keyword}' (придумай реалистичный)",
    }
    topic = topics.get(day, f"Напиши полезный пост о '{keyword}' для жителей {region}")

    prompt = f"""{topic}

Бренд: {brand}
Регион: {region}
Сайт: {site_url}

Требования:
- 200-400 символов
- Живой разговорный тон
- Хэштеги в конце
- Ссылка {site_url}

Ответь ТОЛЬКО валидным JSON:
{{"text": "текст поста"}}"""

    response = _ask(prompt)
    data = _parse_json(response)

    if data and data.get("text"):
        return data["text"][:4096]

    return _fallback_post(keyword, brand, region, site_url, day=day)


def generate_discussion(keyword: str, topic_num: int,
                        brand: str, region: str) -> dict:
    """
    Генерирует тему обсуждения для VK группы.
    Обсуждения индексируются Яндексом отдельно — дополнительные страницы.
    """
    topic_types = [
        f"Вопрос-ответ о {keyword}",
        f"Цены на {keyword} в {region}",
        f"Отзывы о {keyword}",
        f"Как выбрать {keyword}",
        f"Акции и скидки на {keyword}",
    ]
    topic_type = topic_types[topic_num % len(topic_types)]

    prompt = f"""Создай тему обсуждения для VK группы. Темы обсуждений индексируются Яндексом как отдельные страницы.

Тип темы: {topic_type}
Ключевое слово: {keyword}
Регион: {region}
Бренд: {brand}

Требования:
- Заголовок: 30-60 символов, содержит ключ
- Текст: 200-400 символов, полезная информация
- Призыв оставить комментарий

Ответь ТОЛЬКО валидным JSON:
{{"title": "заголовок темы", "text": "текст первого сообщения"}}"""

    response = _ask(prompt)
    data = _parse_json(response)

    if data and data.get("title") and data.get("text"):
        return data

    return {
        "title": f"{keyword} в {region} — вопросы и ответы",
        "text": f"Здесь вы можете задать любой вопрос о {keyword}. "
                f"Отвечаем быстро! Также смотрите наш сайт: {brand}"
    }


def analyze_niche(text: str) -> dict:
    """
    Определяет нишу, бренд, услуги из текста сайта.
    Вызывается после парсинга сайта.
    """
    prompt = f"""Проанализируй текст сайта и извлеки информацию о бизнесе.

ТЕКСТ САЙТА:
{text[:3000]}

Ответь ТОЛЬКО валидным JSON:
{{
  "niche": "название ниши одним словом (стоматология, ремонт, школа и т.д.)",
  "brand": "название компании/бренда",
  "region": "город или регион",
  "services": ["услуга 1", "услуга 2", "услуга 3"],
  "utp": "уникальное торговое предложение (1-2 предложения)",
  "phone": "телефон если есть",
  "address": "адрес если есть"
}}"""

    response = _ask(prompt)
    data = _parse_json(response)

    if data and data.get("niche"):
        logger.info(f"[AI] Определена ниша: {data.get('niche')} / {data.get('brand')}")
        return data

    return {
        "niche": "", "brand": "", "region": "",
        "services": [], "utp": "", "phone": "", "address": ""
    }


def check_ollama_status() -> dict:
    """Проверяет статус Ollama и доступные модели"""
    if not _is_ollama_running():
        return {"running": False, "models": [], "active_model": None}

    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        active = _get_model()
        return {"running": True, "models": models, "active_model": active}
    except Exception as e:
        return {"running": False, "models": [], "error": str(e)}


# ══════════════════════════════════════════════════════════════
# FALLBACK — шаблонная генерация если Ollama недоступна
# ══════════════════════════════════════════════════════════════

def _fallback_keywords(niche: str, region: str,
                       services: list, count: int) -> list:
    import random
    suffixes = ["цена", "недорого", "отзывы", "адрес", "телефон",
                "записаться", "акция", "скидка", "рядом", "хороший",
                "лучший", "круглосуточно", "вызов", "онлайн"]
    results = []
    base_services = services[:5] if services else [niche]
    for svc in base_services:
        results.append(f"{svc} {region}")
        for sfx in random.sample(suffixes, min(4, len(suffixes))):
            results.append(f"{svc} {region} {sfx}")
            if len(results) >= count:
                return results[:count]
    return results[:count]


def _fallback_name(keyword: str, brand: str, region: str) -> str:
    import random
    templates = [
        f"{keyword} {region}",
        f"{keyword} | {region}",
        f"{brand} — {keyword}",
        f"{keyword} {region} — запись",
        f"{keyword} в {region}",
    ]
    for t in templates:
        if len(t) <= 48:
            return t
    return keyword[:48]


def _fallback_description(keyword: str, brand: str,
                           region: str, site_url: str) -> str:
    return (f"{keyword.capitalize()} в {region} — {brand}.\n\n"
            f"Профессиональный подход, опытные специалисты, доступные цены.\n"
            f"Работаем для вас каждый день.\n\n"
            f"Подробнее: {site_url}\n\n"
            f"#{keyword.replace(' ', '_')} #{region.replace(' ', '_')}")


def _fallback_post(keyword: str, brand: str, region: str,
                   site_url: str, day: int = 1) -> str:
    messages = [
        f"Добро пожаловать в группу {brand}!\n\n"
        f"Мы занимаемся {keyword} в {region}.\n"
        f"Все подробности на нашем сайте: {site_url}\n\n"
        f"#{keyword.replace(' ', '_')} #{region.replace(' ', '_')}",

        f"Хотите узнать больше о {keyword}?\n\n"
        f"Пишите нам прямо здесь или заходите на сайт: {site_url}\n\n"
        f"#{keyword.replace(' ', '_')} #{region.replace(' ', '_')}",

        f"{keyword.capitalize()} в {region} — это наша специализация.\n\n"
        f"Качество, опыт, доступные цены.\n"
        f"{site_url}\n\n"
        f"#{keyword.replace(' ', '_')} #{region.replace(' ', '_')}",
    ]
    return messages[(day - 1) % len(messages)]
