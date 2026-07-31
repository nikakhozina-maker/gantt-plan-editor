import React, { useState } from 'react';

export default function TaskModal({ task, allTasks, allDeps, scheduled, onClose, onSave, onDelete }) {
  const [title, setTitle] = useState(task.title || '');
  const [desc, setDesc] = useState(task.description || '');
  const [assignee, setAssignee] = useState(task.assignee || '');
  const [duration, setDuration] = useState(task.duration || 1);
  const [predStr, setPredStr] = useState(
    allDeps.filter(d => d.successorId === task.id).map(d => d.predecessorId).join(', ')
  );

  const handleSave = () => {
    const updated = { ...task, title, description: desc, assignee, duration: Math.max(1, parseInt(duration) || 1) };
    const newDeps = allDeps.filter(d => d.successorId !== task.id);
    let depId = Math.max(0, ...allDeps.map(d => d.id)) + 1;
    if (predStr.trim()) {
      predStr.split(/[,;]+/).forEach(pid => {
        const p = parseInt(pid.trim());
        if (p && allTasks.find(t => t.id === p)) {
          newDeps.push({ id: depId++, predecessorId: p, successorId: task.id });
        }
      });
    }
    onSave(updated, newDeps);
  };

  const incoming = allDeps.filter(d => d.successorId === task.id);
  const outgoing = allDeps.filter(d => d.predecessorId === task.id);

  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">
        <h2>📋 {task.title || 'Задача'}</h2>
        <label>Название</label>
        <input value={title} onChange={e => setTitle(e.target.value)} />
        <label>Описание</label>
        <textarea value={desc} onChange={e => setDesc(e.target.value)} />
        <label>Исполнитель</label>
        <input value={assignee} onChange={e => setAssignee(e.target.value)} />
        <label>Длительность (дни)</label>
        <input type="number" min={1} value={duration} onChange={e => setDuration(e.target.value)} />
        <label>Предшественники (ID через запятую)</label>
        <input value={predStr} onChange={e => setPredStr(e.target.value)} />
        
        <div style={{marginTop:12,fontSize:12,color:'#64748b'}}>
          <div>Старт: день {task.startDay + 1} · Финиш: день {task.endDay}</div>
          {incoming.length > 0 && <div>← Зависит от: {incoming.map(d => allTasks.find(t=>t.id===d.predecessorId)?.title || d.predecessorId).join(', ')}</div>}
          {outgoing.length > 0 && <div>→ Блокирует: {outgoing.map(d => allTasks.find(t=>t.id===d.successorId)?.title || d.successorId).join(', ')}</div>}
        </div>

        <div className="modal-actions">
          <button className="danger" onClick={() => onDelete(task.id)}>Удалить</button>
          <button onClick={onClose}>Отмена</button>
          <button className="primary" onClick={handleSave}>Сохранить</button>
        </div>
      </div>
    </div>
  );
}
