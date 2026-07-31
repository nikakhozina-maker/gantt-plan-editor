import React, { useState, useCallback, useRef } from 'react';
import { SEED_TASKS, SEED_DEPENDENCIES, createProjectObj } from './data/seed';
import { scheduleAll } from './utils/scheduler';
import Toolbar from './components/Toolbar';
import GanttChart from './components/GanttChart';
import TaskModal from './components/TaskModal';
import ChatPanel from './components/ChatPanel';
import './App.css';

const API_URL = 'http://localhost:8000';

export default function App() {
  const [projects, setProjects] = useState(() => [
    createProjectObj('Новый проект', SEED_TASKS, SEED_DEPENDENCIES),
  ]);
  const [activeProjectId, setActiveProjectId] = useState(() => projects[0]?.id || 0);
  const [chatVisible, setChatVisible] = useState(false);
  const [modalTask, setModalTask] = useState(null);
  const [showAllDeps, setShowAllDeps] = useState(false);

  const activeProject = projects.find(p => p.id === activeProjectId) || projects[0];
  const tasks = activeProject?.tasks || [];
  const deps = activeProject?.dependencies || [];

  const { scheduled, criticalPathIds, projectDuration } = scheduleAll(tasks, deps);

  const updateProject = useCallback((updater) => {
    setProjects(prev =>
      prev.map(p => (p.id === activeProjectId ? updater(p) : p))
    );
  }, [activeProjectId]);

  const setTasks = useCallback((newTasks) => {
    updateProject(p => ({ ...p, tasks: newTasks }));
  }, [updateProject]);

  const setDeps = useCallback((newDeps) => {
    updateProject(p => ({ ...p, dependencies: newDeps }));
  }, [updateProject]);

  const handlePlanUpdate = useCallback((newTasks, newDeps) => {
    if (newTasks) setTasks(newTasks);
    if (newDeps) setDeps(newDeps);
  }, [setTasks, setDeps]);

  const handleImportExcel = useCallback((impTasks, impDeps, name) => {
    const proj = createProjectObj(name || 'Импортированный проект', impTasks, impDeps);
    setProjects(prev => [...prev, proj]);
    setActiveProjectId(proj.id);
  }, []);

  const handleAddProject = useCallback(() => {
    const proj = createProjectObj('Новый проект', SEED_TASKS.map(t => ({ ...t })), SEED_DEPENDENCIES.map(d => ({ ...d })));
    setProjects(prev => [...prev, proj]);
    setActiveProjectId(proj.id);
  }, []);

  const handleDeleteProject = useCallback((id) => {
    if (projects.length <= 1) return;
    setProjects(prev => prev.filter(p => p.id !== id));
    if (activeProjectId === id) {
      setActiveProjectId(projects.find(p => p.id !== id)?.id || projects[0]?.id);
    }
  }, [projects, activeProjectId]);

  const handleRenameProject = useCallback((id, name) => {
    setProjects(prev => prev.map(p => (p.id === id ? { ...p, name } : p)));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>📊 REPKA Gantt Plan Editor</h1>
        <span className="badge">AI-powered</span>
      </header>

      <Toolbar
        projects={projects}
        activeProjectId={activeProjectId}
        onSelectProject={setActiveProjectId}
        onAddProject={handleAddProject}
        onDeleteProject={handleDeleteProject}
        onRenameProject={handleRenameProject}
        tasks={tasks}
        deps={deps}
        scheduled={scheduled}
        onImport={handleImportExcel}
        onToggleChat={() => setChatVisible(v => !v)}
        chatVisible={chatVisible}
      />

      <div className="main-area">
        <div className={`gantt-wrapper ${chatVisible ? 'with-chat' : ''}`}>
          <GanttChart
            scheduled={scheduled}
            deps={deps}
            criticalPathIds={criticalPathIds}
            projectDuration={projectDuration}
            onTaskClick={setModalTask}
            showAllDeps={showAllDeps}
            onToggleDeps={() => setShowAllDeps(d => !d)}
          />
        </div>
        {chatVisible && (
          <ChatPanel
            tasks={tasks}
            dependencies={deps}
            onPlanUpdate={handlePlanUpdate}
            onToggleChat={() => setChatVisible(false)}
            apiUrl={API_URL}
          />
        )}
      </div>

      {modalTask && (
        <TaskModal
          task={modalTask}
          allTasks={tasks}
          allDeps={deps}
          scheduled={scheduled}
          onClose={() => setModalTask(null)}
          onSave={(updatedTask, updatedDeps) => {
            const newTasks = tasks.map(t => (t.id === updatedTask.id ? updatedTask : t));
            setTasks(newTasks);
            if (updatedDeps) setDeps(updatedDeps);
            setModalTask(null);
          }}
          onDelete={(taskId) => {
            setTasks(tasks.filter(t => t.id !== taskId));
            setDeps(deps.filter(d => d.predecessorId !== taskId && d.successorId !== taskId));
            setModalTask(null);
          }}
        />
      )}

      <footer className="status-bar">
        <span>Проект: <strong>{activeProject?.name || '—'}</strong></span>
        <span>Задач: {tasks.length}</span>
        <span>Длительность: {projectDuration} дн.</span>
        <span>Крит. путь: {criticalPathIds.size} задач</span>
        <span className={`api-status ${chatVisible ? '' : 'hidden'}`} id="api-status">
          API: проверка...
        </span>
      </footer>
    </div>
  );
}
