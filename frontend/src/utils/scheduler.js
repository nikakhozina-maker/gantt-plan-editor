// Планировщик: рассчитывает startDay, endDay, criticalPath
// Алгоритм: топологическая сортировка + ранний старт

export function scheduleAll(tasks, dependencies) {
  if (!tasks.length) return { scheduled: [], criticalPathIds: new Set(), projectDuration: 0 };

  const taskMap = new Map(tasks.map(t => [t.id, { ...t, startDay: 0, endDay: 0 }]));

  // Adjacency
  const successors = new Map();
  const predecessors = new Map();
  tasks.forEach(t => {
    successors.set(t.id, []);
    predecessors.set(t.id, []);
  });
  dependencies.forEach(d => {
    successors.get(d.predecessorId)?.push(d.successorId);
    predecessors.get(d.successorId)?.push(d.predecessorId);
  });

  // Kahn's algorithm for topological sort
  const inDegree = new Map();
  tasks.forEach(t => inDegree.set(t.id, predecessors.get(t.id).length));

  const queue = [];
  tasks.forEach(t => { if (inDegree.get(t.id) === 0) queue.push(t.id); });

  const order = [];
  while (queue.length) {
    const id = queue.shift();
    order.push(id);
    (successors.get(id) || []).forEach(succ => {
      inDegree.set(succ, inDegree.get(succ) - 1);
      if (inDegree.get(succ) === 0) queue.push(succ);
    });
  }

  // Forward pass (early start = 0-based)
  order.forEach(id => {
    const task = taskMap.get(id);
    let es = 0;
    (predecessors.get(id) || []).forEach(predId => {
      const pred = taskMap.get(predId);
      es = Math.max(es, pred.endDay);
    });
    task.startDay = es;
    task.endDay = es + task.duration;
  });

  // Backward pass
  const projectDuration = Math.max(...Array.from(taskMap.values()).map(t => t.endDay));
  order.reverse();
  order.forEach(id => {
    const task = taskMap.get(id);
    let lf = projectDuration;
    (successors.get(id) || []).forEach(succId => {
      lf = Math.min(lf, taskMap.get(succId).startDay);
    });
    task.lateStart = lf - task.duration;
  });

  // Critical path: float = 0
  const criticalPathIds = new Set();
  order.reverse();
  order.forEach(id => {
    const task = taskMap.get(id);
    if (task.lateStart === task.startDay) {
      criticalPathIds.add(id);
    }
  });

  return {
    scheduled: Array.from(taskMap.values()),
    criticalPathIds,
    projectDuration,
  };
}

// For backward compat
export function scheduleTasks(tasks, dependencies) {
  const { scheduled } = scheduleAll(tasks, dependencies);
  return scheduled;
}
