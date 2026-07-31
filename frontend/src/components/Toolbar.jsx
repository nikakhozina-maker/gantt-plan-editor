import React, { useRef } from 'react';
import * as XLSX from 'xlsx';

export default function Toolbar({
  projects, activeProjectId, onSelectProject, onAddProject, onDeleteProject, onRenameProject,
  tasks, deps, scheduled, onImport, onToggleChat, chatVisible
}) {
  const fileRef = useRef(null);

  const handleExport = () => {
    const data = scheduled.map(t => {
      const preds = deps.filter(d => d.successorId === t.id).map(d => d.predecessorId).join(', ');
      return {
        Задача: t.title,
        Описание: t.description || '',
        Исполнитель: t.assignee || '',
        Длительность: t.duration,
        Старт: t.startDay + 1,
        Финиш: t.endDay,
        Предшественники: preds,
      };
    });
    const ws = XLSX.utils.json_to_sheet(data);
    ws['!cols'] = [{wch:22},{wch:30},{wch:16},{wch:12},{wch:8},{wch:8},{wch:18}];
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'План');
    XLSX.writeFile(wb, 'gantt_export.xlsx');
  };

  const handleFile = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const wb = XLSX.read(ev.target.result, { type: 'array' });
      const ws = wb.Sheets[wb.SheetNames[0]];
      const rows = XLSX.utils.sheet_to_json(ws, { header: 1 });
      if (rows.length < 2) return;
      const impTasks = [], impDeps = [];
      let nextId = 1, depId = 1;
      rows.slice(1).forEach((r, i) => {
        if (!r[0]) return;
        const title = String(r[0] || '').trim();
        if (!title) return;
        const id = nextId++;
        impTasks.push({
          id, title,
          description: String(r[1] || ''),
          assignee: String(r[2] || ''),
          duration: parseInt(r[3]) || 1,
        });
        const predStr = String(r[4] || '');
        if (predStr) {
          predStr.split(/[,;]+/).forEach(pid => {
            const p = parseInt(pid.trim());
            if (p && p <= impTasks.length) {
              impDeps.push({ id: depId++, predecessorId: impTasks[p-1].id, successorId: id });
            }
          });
        }
      });
      onImport(impTasks, impDeps);
    };
    reader.readAsArrayBuffer(f);
    e.target.value = '';
  };

  const activeProj = projects.find(p => p.id === activeProjectId);

  return (
    <div className="toolbar">
      <select value={activeProjectId} onChange={e => onSelectProject(Number(e.target.value))}>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <button onClick={onAddProject} title="Новый проект">＋ Проект</button>
      {projects.length > 1 && (
        <button className="danger" onClick={() => onDeleteProject(activeProjectId)} title="Удалить проект">✕</button>
      )}
      <span className="spacer" />
      <input ref={fileRef} type="file" accept=".xlsx,.xls" onChange={handleFile} style={{display:'none'}} />
      <button onClick={() => fileRef.current?.click()}>📥 Импорт Excel</button>
      <button onClick={handleExport}>📤 Экспорт Excel</button>
      <button className={chatVisible ? 'primary' : ''} onClick={onToggleChat}>
        {chatVisible ? '✕ Закрыть чат' : '💬 AI-агент'}
      </button>
    </div>
  );
}
