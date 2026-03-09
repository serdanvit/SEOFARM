"""
get_token.py — Получение токена пользователя VK
Запускай: python get_token.py
"""
import webbrowser, re, os

CLIENT_ID = "2685278"  # Kate Mobile
SCOPE = "groups,wall,photos,video,offline"
AUTH_URL = (
    f"https://oauth.vk.com/authorize?client_id={CLIENT_ID}"
    f"&display=page&redirect_uri=https://oauth.vk.com/blank.html"
    f"&scope={SCOPE}&response_type=token&v=5.131"
)

print("=" * 55)
print("  SEO FARM — Получение токена пользователя VK")
print("=" * 55)
print()
print("1. Откроется браузер → войди в нужный аккаунт VK")
print("2. Нажми 'Разрешить'")
print("3. Скопируй ВЕСЬ адрес из адресной строки браузера")
print("4. Вставь его сюда")
print()
input("Нажми ENTER чтобы открыть браузер...")
webbrowser.open(AUTH_URL)
print()

while True:
    url = input("Вставь адрес из браузера: ").strip()
    m = re.search(r'access_token=([^&]+)', url)
    uid = re.search(r'user_id=([^&]+)', url)
    if m:
        token = m.group(1)
        user_id = uid.group(1) if uid else "?"
        print()
        print("=" * 55)
        print(f"✅ ТОКЕН ПОЛУЧЕН! User ID: {user_id}")
        print("=" * 55)
        print()
        print(token)
        print()
        print("Скопируй токен выше и добавь в раздел 'Аккаунты VK'")
        print("на панели: http://localhost:5000")
        # Сохраняем в файл
        fname = f"token_uid{user_id}.txt"
        open(fname,"w").write(f"user_id={user_id}\ntoken={token}\n")
        print(f"\n💾 Также сохранён в {fname}")
        break
    else:
        print("❌ Токен не найден. Скопируй ВЕСЬ адрес целиком.\n")
        if input("Попробовать ещё раз? (y/n): ").lower() != 'y':
            break
