# 🚀 Инструкция по деплою

## 1. GitHub репозиторий

```bash
# Инициализация
git init
git add .
git commit -m "Initial commit: Gantt Plan Editor (React + FastAPI + MCP + LLM)"

# Создай репозиторий на GitHub и запушь:
git remote add origin https://github.com/ТВОЙ_ЛОГИН/gantt-plan-editor.git
git branch -M main
git push -u origin main
```

### Структура репозитория:
```
gantt-plan-editor/
├── gantt_editor_final.html   # Фронтенд (React)
├── main.py                    # Бэкенд (FastAPI + MCP)
├── requirements.txt           # Python-зависимости
├── .env.example               # Пример .env файла
├── sample_plan.xlsx           # Пример Excel для теста
├── README.md                  # Документация
├── roadmap_to_production.md   # Roadmap to production
├── DEPLOY.md                  # Эта инструкция
├── render.yaml                # Конфиг Render
└── vercel.json                # Конфиг Vercel
```

---

## 2. Деплой бэкенда на Render

1. Зайди на [render.com](https://render.com) → **New** → **Web Service**
2. Подключи GitHub-репозиторий
3. Настройки:
   - **Name:** `gantt-plan-editor-api`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Plan:** Free
4. Добавь Environment Variable:
   - `OPENROUTER_API_KEY` = твой ключ (если есть)
   - `PORT` = 8000 (Render выставит автоматически)
5. Нажми **Deploy**

Бэкенд будет доступен по адресу: `https://gantt-plan-editor-api.onrender.com`

---

## 3. Деплой фронтенда на Vercel

### Способ А: Простой статический деплой

1. Зайди на [vercel.com](https://vercel.com) → **New Project**
2. Импортируй GitHub-репозиторий
3. Vercel сам подхватит `vercel.json`
4. **ПЕРЕД деплоем** отредактируй `gantt_editor_final.html`:
   - Найди строку `window.__GANTT_API_URL__ = 'http://localhost:8000';`
   - Замени на: `window.__GANTT_API_URL__ = 'https://gantt-plan-editor-api.onrender.com';`
5. Запушь изменения и Vercel автоматически передеплоит

### Способ Б: Vercel CLI

```bash
npm i -g vercel
vercel login
vercel --prod
```

---

## 4. Проверка

1. Открой фронтенд (Vercel URL)
2. Убедись что диаграмма загружается с тестовыми данными
3. Напиши в чат «Привет» — бот должен ответить
4. Попробуй: «Добавь задачу «Тест деплоя» на 2 дня»
5. Попробуй импорт Excel (`sample_plan.xlsx`)
6. Попробуй экспорт Excel

---

## 5. Важно про Render Free Tier

Render бесплатный план «засыпает» после 15 минут бездействия. Первый запрос после простоя может занять ~30 секунд. Чтобы избежать этого — используй платный план или настрой UptimeRobot для пингования.

---

## 6. Переменные API-ключей для .env

Создай файл `.env` (НЕ коммить в git!):

```env
# Хотя бы один из ключей:
OPENROUTER_API_KEY=sk-or-v1-...
# или
OPENAI_API_KEY=sk-...
# или
ANTHROPIC_API_KEY=sk-ant-...
# или
GEMINI_API_KEY=...
```

Без ключа бот работает на локальном NLP (regex) — базовые команды на русском.
