"""
core/site_parser.py — Парсинг сайта клиента
Обходит все страницы, собирает текст → передаёт в AI для анализа ниши.
"""
import requests, re, logging, sys, os
from urllib.parse import urljoin, urlparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("site_parser")

MAX_PAGES   = 30
MAX_TEXT    = 8000   # символов суммарного текста
TIMEOUT     = 10
SKIP_EXTS   = {".pdf",".jpg",".jpeg",".png",".gif",".svg",
               ".zip",".doc",".xls",".mp4",".mp3"}
SKIP_PATHS  = {"#", "javascript:", "mailto:", "tel:",
               "/wp-admin", "/admin", "/login", "/cart"}


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _same_domain(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def _should_skip(url: str) -> bool:
    u = url.lower()
    if any(s in u for s in SKIP_PATHS):
        return True
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext in SKIP_EXTS


def _fetch(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOFarm/1.0)"}
        r = requests.get(url, headers=headers, timeout=TIMEOUT,
                         allow_redirects=True)
        if "text/html" not in r.headers.get("Content-Type", ""):
            return ""
        return r.text
    except Exception as e:
        logger.debug(f"[parser] {url}: {e}")
        return ""


def _extract_links(html: str, base_url: str) -> list:
    links = re.findall(r'href=["\']([^"\'#\s]+)["\']', html)
    result = []
    for link in links:
        full = urljoin(base_url, link)
        if (_same_domain(full, base_url)
                and not _should_skip(full)
                and full not in result):
            result.append(full)
    return result


def _extract_text(html: str) -> str:
    # Убираем скрипты и стили
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    # Заменяем теги на пробелы
    text = _clean(html)
    # Убираем слишком короткие куски
    words = [w for w in text.split() if len(w) > 1]
    return " ".join(words)


def _extract_contacts(html: str) -> dict:
    phones = re.findall(
        r"(?:\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", html)
    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
    return {
        "phone": phones[0].strip() if phones else "",
        "email": emails[0] if emails else "",
    }


def parse_site(url: str) -> dict:
    """
    Обходит все страницы сайта.
    Возвращает: {url, text, contacts, pages_visited, error}
    """
    if not url.startswith("http"):
        url = "https://" + url

    logger.info(f"[parser] Начинаю обход: {url}")

    visited = set()
    queue   = [url]
    all_text = []
    contacts = {}
    errors   = 0

    while queue and len(visited) < MAX_PAGES:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        html = _fetch(current)
        if not html:
            errors += 1
            continue

        # Контакты берём с любой страницы
        if not contacts.get("phone"):
            contacts = _extract_contacts(html)

        # Текст страницы
        page_text = _extract_text(html)
        if len(page_text) > 100:
            all_text.append(f"[{current}]\n{page_text[:1500]}")

        # Добавляем новые ссылки в очередь
        if len(all_text) < 20:  # не ищем ссылки если уже много текста
            new_links = _extract_links(html, url)
            for link in new_links:
                if link not in visited and link not in queue:
                    queue.append(link)

    combined_text = "\n\n".join(all_text)[:MAX_TEXT]

    logger.info(f"[parser] Обошёл {len(visited)} страниц, {len(combined_text)} символов")

    return {
        "url":           url,
        "text":          combined_text,
        "contacts":      contacts,
        "pages_visited": len(visited),
        "error":         None if all_text else "Не удалось получить текст сайта",
    }
