import React, { useState } from 'react';

const BAR_HEIGHT = 32, ROW_GAP = 6, LEFT_COL = 280, DAY_W = 38, HEADER_H = 36;

export default function GanttChart({ scheduled, deps, criticalPathIds, projectDuration, onTaskClick, showAllDeps, onToggleDeps }) {
  const [colWidths, setColWidths] = useState({ task:180, assignee:100 });
  const [resizing, setResizing] = useState(null);
  const [resizeStart, setResizeStart] = useState(0);

  const days = Math.max(projectDuration, 1);
  const svgW = LEFT_COL + days * DAY_W + 60;
  const svgH = HEADER_H + scheduled.length * (BAR_HEIGHT + ROW_GAP) + 40;

  const onMouseDown = (col, e) => { setResizing(col); setResizeStart(e.clientX); };
  React.useEffect(() => {
    if (!resizing) return;
    const onMove = (e) => {
      const delta = e.clientX - resizeStart;
      setColWidths(prev => ({ ...prev, [resizing]: Math.max(60, prev[resizing] + delta) }));
      setResizeStart(e.clientX);
    };
    const onUp = () => setResizing(null);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [resizing, resizeStart]);

  const depPairs = deps.map(d => [d.predecessorId, d.successorId]);

  return (
    <div>
      <table className="task-table">
        <thead>
          <tr>
            <th style={{width:colWidths.task, position:'relative'}}>
              Задача
              <div onMouseDown={e => onMouseDown('task', e)} style={{position:'absolute',right:0,top:0,bottom:0,width:4,cursor:'col-resize'}} />
            </th>
            <th>Описание</th>
            <th style={{width:colWidths.assignee, position:'relative'}}>
              Исполнитель
              <div onMouseDown={e => onMouseDown('assignee', e)} style={{position:'absolute',right:0,top:0,bottom:0,width:4,cursor:'col-resize'}} />
            </th>
            <th>Дни</th>
            <th>Старт</th>
            <th>Финиш</th>
          </tr>
        </thead>
        <tbody>
          {scheduled.map(t => (
            <tr key={t.id} className={criticalPathIds.has(t.id) ? 'critical' : ''} onClick={() => onTaskClick(t)} style={{cursor:'pointer'}}>
              <td>{criticalPathIds.has(t.id) ? '🔴 ' : ''}{t.title}</td>
              <td style={{color:'#64748b',fontSize:12}}>{t.description || ''}</td>
              <td>{t.assignee || '—'}</td>
              <td>{t.duration}</td>
              <td>{t.startDay + 1}</td>
              <td>{t.endDay}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{marginBottom:4, fontSize:12, color:'#64748b'}}>
        <label style={{cursor:'pointer'}}>
          <input type="checkbox" checked={showAllDeps} onChange={onToggleDeps} /> Показать все зависимости
        </label>
        {' · '}🔴 критический путь
      </div>

      <svg className="gantt-svg" viewBox={`0 0 ${svgW} ${svgH}`} width="100%" height={svgH}>
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#94a3b8" />
          </marker>
          <marker id="arrowhead-critical" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#dc2626" />
          </marker>
        </defs>

        {/* Grid */}
        {Array.from({length: days + 1}, (_, i) => (
          <g key={`grid-${i}`}>
            <line x1={LEFT_COL + i * DAY_W} y1={HEADER_H} x2={LEFT_COL + i * DAY_W} y2={svgH} stroke="#f1f5f9" />
          </g>
        ))}

        {/* Header */}
        {Array.from({length: days}, (_, i) => (
          <text key={`h-${i}`} x={LEFT_COL + i * DAY_W + DAY_W/2} y={HEADER_H - 10} textAnchor="middle" fontSize={11} fill="#64748b">
            {i + 1}
          </text>
        ))}

        {/* Dependencies */}
        {deps.filter(d => showAllDeps || (criticalPathIds.has(d.predecessorId) && criticalPathIds.has(d.successorId)))
          .map(d => {
            const pred = scheduled.find(t => t.id === d.predecessorId);
            const succ = scheduled.find(t => t.id === d.successorId);
            if (!pred || !succ) return null;
            const pIdx = scheduled.indexOf(pred), sIdx = scheduled.indexOf(succ);
            const y1 = HEADER_H + pIdx * (BAR_HEIGHT + ROW_GAP) + BAR_HEIGHT/2;
            const y2 = HEADER_H + sIdx * (BAR_HEIGHT + ROW_GAP) + BAR_HEIGHT/2;
            const x1 = LEFT_COL + pred.endDay * DAY_W;
            const x2 = LEFT_COL + succ.startDay * DAY_W;
            const isCrit = criticalPathIds.has(pred.id) && criticalPathIds.has(succ.id);
            return (
              <line key={`dep-${d.id}`} x1={x1} y1={y1} x2={x2} y2={y2}
                className={`dep-line${isCrit ? ' critical' : ''}`}
                markerEnd={isCrit ? 'url(#arrowhead-critical)' : 'url(#arrowhead)'} />
            );
          })}

        {/* Bars */}
        {scheduled.map((t, idx) => {
          const y = HEADER_H + idx * (BAR_HEIGHT + ROW_GAP);
          const x = LEFT_COL + t.startDay * DAY_W;
          const w = t.duration * DAY_W;
          const isCrit = criticalPathIds.has(t.id);
          return (
            <g key={`bar-${t.id}`} className="gantt-row" onClick={() => onTaskClick(t)}>
              <rect x={x} y={y} width={w} height={BAR_HEIGHT} rx={4}
                className={`gantt-bar ${isCrit ? 'critical' : 'normal'}`} />
              <text x={x + 6} y={y + BAR_HEIGHT/2 + 4} fontSize={12} fill="#fff" fontWeight={600}>
                {t.title}
              </text>
              <text x={x + w + 6} y={y + BAR_HEIGHT/2 + 4} fontSize={11} fill="#64748b">
                {t.startDay + 1}–{t.endDay} · {t.assignee || ''}
              </text>
            </g>
          );
        })}

        {/* Today line */}
        <line x1={LEFT_COL} y1={svgH - 2} x2={LEFT_COL + days * DAY_W} y2={svgH - 2} stroke="#e2e8f0" />
      </svg>
    </div>
  );
}
