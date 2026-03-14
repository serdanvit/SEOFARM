"""
core/wordstat.py — Интеграция Яндекс.Wordstat через API Директа
Основан на wsparser.py из архива пользователя.
Если токен не задан — возвращает ключи из keyword_base.
"""
import json, time, logging, os, sys
import urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("wordstat")

DIRECT_API_URL = "https://api.direct.yandex.ru/v4/json/"
SANDBOX_URL    = "https://api-sandbox.direct.yandex.ru/v4/json/"

# Частотность: берём ключи в диапазоне 50-500 (низкие частоты)
MIN_SHOWS = 50
MAX_SHOWS = 2000


class WordstatClient:
    def __init__(self, token: str, username: str, sandbox: bool = False):
        self.token    = token
        self.username = username
        self.url      = SANDBOX_URL if sandbox else DIRECT_API_URL

    def _request(self, method: str, param=None) -> dict:
        data = {"method": method, "token": self.token}
        if self.username:
            data["login"] = self.username
        if param is not None:
            data["param"] = param
        body = json.dumps(data, ensure_ascii=False).encode("utf8")
        try:
            req  = urllib.request.Request(self.url, body)
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode("utf8"))
        except Exception as e:
            logger.error(f"[wordstat] Ошибка запроса {method}: {e}")
            return {"error": str(e)}

    def create_report(self, phrases: list, geo: list = []) -> int | None:
        r = self._request("CreateNewWordstatReport",
                          {"Phrases": phrases, "GeoID": geo})
        if "data" in r:
            return r["data"]
        logger.error(f"[wordstat] create_report: {r}")
        return None

    def wait_report(self, report_id: int, max_wait: int = 60) -> bool:
        for _ in range(max_wait // 3):
            time.sleep(3)
            r = self._request("GetWordstatReportList")
            if "data" not in r:
                return False
            for rep in r["data"]:
                if rep["ReportID"] == report_id:
                    if rep["StatusReport"] == "Done":
                        return True
                    break
        return False

    def read_report(self, report_id: int) -> list:
        r = self._request("GetWordstatReport", report_id)
        if "data" not in r:
            return []
        results = []
        for item in r["data"]:
            for kw in item.get("SearchedWith", []):
                results.append({
                    "phrase": kw["Phrase"],
                    "shows":  kw["Shows"],
                })
        return results

    def delete_report(self, report_id: int):
        self._request("DeleteWordstatReport", report_id)


def get_keywords_with_frequency(phrases: list, token: str,
                                 username: str, region_id: int = 0,
                                 min_shows: int = MIN_SHOWS,
                                 max_shows: int = MAX_SHOWS) -> list:
    """
    Получает ключи с частотностью из Wordstat.
    Фильтрует по диапазону — оставляет только низкие частоты.
    Возвращает список строк (ключевых слов).
    """
    if not token:
        logger.warning("[wordstat] Токен не задан — пропускаем Wordstat")
        return []

    client = WordstatClient(token, username)
    geo    = [region_id] if region_id else []

    logger.info(f"[wordstat] Запрашиваем {len(phrases)} фраз...")
    report_id = client.create_report(phrases, geo)
    if not report_id:
        return []

    logger.info(f"[wordstat] Ожидаем отчёт #{report_id}...")
    if not client.wait_report(report_id):
        logger.error("[wordstat] Таймаут ожидания отчёта")
        return []

    data = client.read_report(report_id)
    client.delete_report(report_id)

    # Фильтруем по частотности
    filtered = [
        item["phrase"]
        for item in sorted(data, key=lambda x: x["shows"], reverse=False)
        if min_shows <= item["shows"] <= max_shows
    ]

    logger.info(f"[wordstat] Получено {len(filtered)} ключей "
                f"с частотностью {min_shows}-{max_shows}")
    return filtered


# Таблица регионов Яндекса (основные города России)
YANDEX_REGIONS = {
    "москва":            1,
    "санкт-петербург":   2,
    "питер":             2,
    "новосибирск":       65,
    "екатеринбург":      54,
    "нижний новгород":   47,
    "казань":            43,
    "челябинск":         56,
    "омск":              66,
    "самара":            51,
    "ростов-на-дону":    39,
    "уфа":               172,
    "красноярск":        62,
    "воронеж":           193,
    "пермь":             50,
    "волгоград":         38,
    "краснодар":         36,
    "тюмень":            152,
    "саратов":           194,
    "тольятти":          51,
    "ижевск":            44,
    "барнаул":           197,
    "ульяновск":         195,
    "иркутск":           63,
    "хабаровск":         76,
    "ярославль":         16,
    "владивосток":       75,
    "махачкала":         106,
    "томск":             67,
    "оренбург":          48,
    "новокузнецк":       65,
    "кемерово":          64,
    "рязань":            10,
    "астрахань":         37,
    "набережные челны":  43,
    "пенза":             49,
    "липецк":            9,
    "тула":              15,
    "киров":             46,
    "чебоксары":         45,
    "калининград":       22,
}


def get_region_id(region_name: str) -> int:
    """Возвращает ID региона Яндекса по названию города"""
    name = region_name.lower().strip()
    return YANDEX_REGIONS.get(name, 0)
