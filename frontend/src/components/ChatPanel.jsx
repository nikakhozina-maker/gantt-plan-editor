import React, { useState, useRef, useEffect } from 'react';

export default function ChatPanel({ tasks, dependencies, onPlanUpdate, onToggleChat, apiUrl }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', text: '👋 Привет! Я AI-агент. Могу добавлять/редактировать задачи, менять сроки, перестраивать зависимости. Попробуй: «Добавь задачу Тестирование на 3 дня после Разработки фронтенда»' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [apiOnline, setApiOnline] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => {
    fetch(apiUrl + '/api/health').then(r => r.ok ? setApiOnline(true) : setApiOnline(false)).catch(() => setApiOnline(false));
  }, [apiUrl]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text }]);
    setLoading(true);

    try {
      const resp = await fetch(apiUrl + '/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, tasks, dependencies }),
      });
      if (!resp.ok) throw new Error('API error');
      const data = await resp.json();
      setMessages(prev => [...prev, { role: 'assistant', text: data.reply || 'Готово.' }]);
      if (data.tasks || data.dependencies) {
        onPlanUpdate(data.tasks || tasks, data.dependencies || dependencies);
      }
    } catch {
      const { reply, tasks: newTasks, deps: newDeps } = localFallback(text, tasks, dependencies);
      setMessages(prev => [...prev, { role: 'assistant', text: reply + '\n⚠️ Локальный режим (бэкенд недоступен)' }]);
      if (newTasks || newDeps) {
        onPlanUpdate(newTasks || tasks, newDeps || dependencies);
      }
    }
    setLoading(false);
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <span>🤖 AI-агент {apiOnline === true ? '✅' : apiOnline === false ? '⚠️ локально' : '…'}</span>
        <button onClick={onToggleChat} style={{background:'none',border:'none',cursor:'pointer',fontSize:16}}>✕</button>
      </div>
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>{m.text}</div>
        ))}
        {loading && <div className="chat-msg assistant">⏳ Думаю...</div>}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-area">
        <input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Опиши изменение плана..." />
        <button onClick={send} disabled={loading}>→</button>
      </div>
    </div>
  );
}

function localFallback(message, tasks, deps) {
  const msg = message.toLowerCase();
  const maxId = Math.max(0, ...tasks.map(t => t.id));
  let depId = Math.max(0, ...deps.map(d => d.id));

  // "добавь задачу X длительностью N дней после Y"
  const addMatch = msg.match(/добавь\s+(?:задачу\s+)?["«]?(.+?)["»]?(?:\s+длительностью\s+(\d+)\s+(?:дня|дней|день))?(?:\s+после\s+["«]?(.+?)["»]?)?/i);
  if (addMatch) {
    const title = addMatch[1].trim();
    const dur = parseInt(addMatch[2]) || 3;
    const afterTitle = addMatch[3]?.trim();
    const newId = maxId + 1;
    const newTasks = [...tasks, { id: newId, title, description: '', assignee: '', duration: dur, startDay: 0, endDay: 0 }];
    let newDeps = [...deps];
    if (afterTitle) {
      const pred = tasks.find(t => t.title.toLowerCase().includes(afterTitle.toLowerCase()));
      if (pred) newDeps.push({ id: ++depId, predecessorId: pred.id, successorId: newId });
    }
    return { reply: `✅ Задача «${title}» добавлена${afterTitle ? ` после «${afterTitle}»` : ''}.`, tasks: newTasks, deps: newDeps };
  }

  // "удали задачу X"
  const delMatch = msg.match(/удал(?:и|ить)\s+(?:задачу\s+)?["«]?(.+?)["»]?/i);
  if (delMatch) {
    const title = delMatch[1].trim();
    const target = tasks.find(t => t.title.toLowerCase().includes(title.toLowerCase()));
    if (target) {
      return { reply: `🗑 Задача «${target.title}» удалена.`, tasks: tasks.filter(t => t.id !== target.id), deps: deps.filter(d => d.predecessorId !== target.id && d.successorId !== target.id) };
    }
  }

  // "увеличь/уменьши длительность X до/на N"
  const durMatch = msg.match(/(?:увелич|уменьш|измени)\s+(?:длительность\s+)?(?:задачи\s+)?["«]?(.+?)["»]?\s+(?:до|на)\s+(\d+)/i);
  if (durMatch) {
    const target = tasks.find(t => t.title.toLowerCase().includes(durMatch[1].trim().toLowerCase()));
    if (target) {
      return { reply: `⏱ Длительность «${target.title}» изменена на ${durMatch[2]}.`, tasks: tasks.map(t => t.id === target.id ? { ...t, duration: parseInt(durMatch[2]) } : t) };
    }
  }

  // "назначь X на задачу Y"
  const assignMatch = msg.match(/назнач(?:ь|ить)\s+(.+?)\s+на\s+(?:задачу\s+)?["«]?(.+?)["»]?/i);
  if (assignMatch) {
    const target = tasks.find(t => t.title.toLowerCase().includes(assignMatch[2].trim().toLowerCase()));
    if (target) {
      return { reply: `👤 На задачу «${target.title}» назначен ${assignMatch[1].trim()}.`, tasks: tasks.map(t => t.id === target.id ? { ...t, assignee: assignMatch[1].trim() } : t) };
    }
  }

  return { reply: '🤔 Не поняла. Попробуй:\n• «Добавь задачу Тестирование на 3 дня после Разработки бэкенда»\n• «Удали задачу …»\n• «Увеличь длительность … до 5»\n• «Назначь Анну на задачу …»' };
}
