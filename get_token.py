"""
get_token.py — Получение VK токена через браузер
Запусти: python get_token.py
"""
import webbrowser, sys, os

CLIENT_ID = "51685390"
SCOPE = "groups,wall,photos,video,offline"
REDIRECT = "https://oauth.vk.com/blank.html"

url = (f"https://oauth.vk.com/authorize"
       f"?client_id={CLIENT_ID}"
       f"&display=page"
       f"&redirect_uri={REDIRECT}"
       f"&scope={SCOPE}"
       f"&response_type=token"
       f"&v=5.131")

print("\n  ╔══════════════════════════════════════════╗")
print("  ║       VK TOKEN — Получение токена        ║")
print("  ╚══════════════════════════════════════════╝\n")
print("  Шаг 1: Сейчас откроется браузер с VK OAuth.")
print("  Шаг 2: Войди в аккаунт VK и нажми 'Разрешить'.")
print("  Шаг 3: Скопируй токен из адресной строки браузера.")
print("         Ищи: access_token=XXXXXXXX\n")

webbrowser.open(url)
print(f"  Если браузер не открылся, перейди по ссылке:")
print(f"  {url}\n")

token = input("  Вставь access_token сюда: ").strip()
token = token.split("access_token=")[-1].split("&")[0].strip()

if not token or len(token) < 50:
    print("\n  Токен слишком короткий. Попробуй ещё раз.\n")
    sys.exit(1)

# Сохраняем в файл
fname = f"token_new.txt"
with open(fname, "w") as f:
    f.write(token)

print(f"\n  Токен сохранён в {fname}")
print(f"  Токен: ...{token[-6:]}\n")
print("  Теперь добавь его в SEO FARM:")
print("  → Раздел Настройки → Аккаунты VK → Добавить токен\n")
