// Сидированные данные — 8 задач, 9 зависимостей
export const SEED_TASKS = [
  { id: 1, title: 'Анализ требований', description: 'Собрать и задокументировать требования', assignee: 'Анна', duration: 3 },
  { id: 2, title: 'Проектирование архитектуры', description: 'Спроектировать архитектуру системы', assignee: 'Иван', duration: 4 },
  { id: 3, title: 'Дизайн интерфейса', description: 'Разработать макеты интерфейса', assignee: 'Мария', duration: 5 },
  { id: 4, title: 'Разработка бэкенда', description: 'Реализовать серверную часть', assignee: 'Пётр', duration: 8 },
  { id: 5, title: 'Разработка фронтенда', description: 'Реализовать клиентскую часть', assignee: 'Мария', duration: 7 },
  { id: 6, title: 'Интеграционное тестирование', description: 'Провести интеграционные тесты', assignee: 'Анна', duration: 4 },
  { id: 7, title: 'Развёртывание', description: 'Развернуть приложение в production', assignee: 'Иван', duration: 2 },
  { id: 8, title: 'Обучение пользователей', description: 'Провести обучение пользователей', assignee: 'Пётр', duration: 3 },
];

export const SEED_DEPENDENCIES = [
  { id: 1, predecessorId: 1, successorId: 2 },
  { id: 2, predecessorId: 1, successorId: 3 },
  { id: 3, predecessorId: 2, successorId: 4 },
  { id: 4, predecessorId: 2, successorId: 5 },
  { id: 5, predecessorId: 3, successorId: 5 },
  { id: 6, predecessorId: 4, successorId: 6 },
  { id: 7, predecessorId: 5, successorId: 6 },
  { id: 8, predecessorId: 6, successorId: 7 },
  { id: 9, predecessorId: 7, successorId: 8 },
];

export function createProjectObj(name, tasks, deps) {
  return {
    id: Date.now(),
    name,
    tasks: (tasks || SEED_TASKS).map(t => ({ ...t })),
    dependencies: (deps || SEED_DEPENDENCIES).map(d => ({ ...d })),
  };
}
