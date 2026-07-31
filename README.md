# REPKA — Gantt Project Editor

Интерактивный редактор диаграмм Гантта с AI-агентом на естественном языке.

## 🎬 Демо

**[Смотреть демо основного сценария](https://www.loom.com/share/c0a686fcc5cc44a0963411c7b817c04d)**  
Загрузка Excel → правка через чат (AI-агент) → экспорт.

## 🚀 Развёрнутое приложение

**[gantt-plan-editor.onrender.com](https://gantt-plan-editor.onrender.com)**

## 🔗 Репозиторий

**[github.com/nikakhozina-maker/gantt-plan-editor](https://github.com/nikakhozina-maker/gantt-plan-editor)**

---

## 📦 Стек технологий

| Слой | Технология |
|------|-----------|
| Фронтенд | **React** (Vite + JSX-компоненты) |
| Бэкенд | **Python / FastAPI** |
| MCP | 6 инструментов: add_task, update_task, delete_task, add_dependency, remove_dependency, complete_task |
| LLM | **OpenRouter API** → GPT-4o-mini |
| Диаграмма | SVG, критические пути, резолвер зависимостей |
| Excel | SheetJS (импорт/экспорт) |
| Деплой | Render |

## 🏗️ Архитектура

```
Браузер (React SPA)
  │  POST /api/chat  {message, tasks, dependencies}
  ▼
FastAPI (main.py)
  │  Формирует system prompt + контекст плана
  │  Определяет MCP-инструменты
  ▼
OpenRouter API
  │  LLM возвращает JSON-массив действий
  ▼
MCP-рантайм
  │  Применяет действия к плану
  ▼
Ответ {reply, tasks, dependencies}
  │
  ▼
React обновляет диаграмму Гантта
```

### MCP-инструменты

| Инструмент | Параметры | Описание |
|-----------|-----------|----------|
| `add_task` | id, name, duration, assignee, description, predecessors | Создать задачу |
| `update_task` | id, name?, duration?, assignee?, description? | Изменить задачу |
| `delete_task` | id | Удалить задачу |
| `add_dependency` | from_id, to_id | Добавить зависимость |
| `remove_dependency` | from_id, to_id | Удалить зависимость |
| `complete_task` | id | Отметить задачу выполненной |

### Ключевые алгоритмы

- **Планировщик**: топологическая сортировка → расчёт early start / early finish
- **Критический путь**: обратный проход → late start / late finish → задачи с нулевым slack
- **Чат fallback**: NLP-парсер на регулярных выражениях для русского языка (падежи, опечатки, частичные совпадения)

---

## ⚡ Быстрый старт

### Локально

```bash
# 1. Клонировать репо
git clone https://github.com/nikakhozina-maker/gantt-plan-editor.git
cd gantt-plan-editor

# 2. Создать .env с ключом OpenRouter (получить на openrouter.ai/keys)
cp .env.example .env
# Вписать свой OPENROUTER_API_KEY

# 3. Установить бэкенд
python -m venv venv
venv\Scripts\activate.bat     # Windows
# source venv/bin/activate    # macOS/Linux
pip install -r requirements.txt

# 4. Собрать фронтенд (нужен Node.js)
cd frontend
npm install
npm run build
cd ..

# 5. Запустить
uvicorn main:app --host 0.0.0.0 --port 8000
# Или на Windows: start.bat

# 6. Открыть http://localhost:8000
```

---

## 📂 Структура проекта

```
gantt-project-editor/
├── main.py                    # FastAPI, MCP, OpenRouter, раздача статики
├── requirements.txt           # Зависимости Python
├── start.bat                  # Запуск на Windows
├── render.yaml                # Конфиг Render
├── .env.example               # Шаблон .env (без ключа)
├── .gitignore
├── README.md                  # ← этот файл
├── roadmap_to_production.md   # Дорожная карта до production
├── example_project.xlsx       # Пример Excel для теста
├── gantt_editor_final.html    # Исходный фронтенд (HTML)
│
└── frontend/                  # Vite + React проект
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── App.css
        ├── components/
        │   ├── Toolbar.jsx
        │   ├── GanttChart.jsx
        │   ├── TaskModal.jsx
        │   └── ChatPanel.jsx
        ├── data/
        │   └── seed.js
        └── utils/
            └── scheduler.js
```

---

## 📋 Принятые решения

1. **React через Vite** — быстрая сборка, HMR, современный JSX без CDN-зависимостей
2. **Local NLP fallback** — чат работает даже без бэкенда (регулярные выражения для русского)
3. **Мульти-проектность** — несколько проектов в табах с изоляцией данных
4. **SVG-диаграмма** — чистый SVG вместо canvas для идеального масштабирования
5. **OpenRouter** — единый API к разным LLM, дёшево ($0.15/1M токенов для GPT-4o-mini)
6. **Resizable колонки таблицы** — drag-to-resize для удобства

---

## 🤖 Использование AI-ассистентов при разработке

AI (Claude, ChatGPT) использовался на всех этапах:

- **Архитектура**: AI помог спроектировать разделение на компоненты, MCP-спецификацию, контракт API `/api/chat`
- **Алгоритмы**: топологическая сортировка, расчёт критического пути и early/late start спроектированы с помощью AI
- **Визуализация зависимостей**: AI спроектировал генерацию кривых Безье с закруглёнными углами для стрелок между задачами
- **NLP-парсер**: локальный fallback на регулярных выражениях для обработки русских падежей, опечаток, частичных совпадений
- **MCP-сервер**: AI предложил спецификацию инструментов и их интеграцию с LLM
- **Excel импорт/экспорт**: SheetJS обёртка спроектирована с учётом формата тестового задания (задача, описание, исполнитель, длительность, предшественники)
- **Стилизация**: тёмная/светлая тема, CSS-переменные, адаптивная вёрстка, confetti-анимация
- **Деплой**: AI помог настроить Render, исправить версии зависимостей для Python 3.14

---

## 📊 Roadmap to Production

Подробно в [`roadmap_to_production.md`](roadmap_to_production.md). Ключевые пункты:

- **Фаза 1** (2–3 недели): TypeScript, тесты, БД, авторизация, rate-limit
- **Фаза 2** (2–4 недели): WebSocket, CI/CD, мониторинг, резервное копирование
- **Фаза 3** (2–4 недели): мульти-проектные листы, шаблоны, ролевая модель, корпоративная авторизация
