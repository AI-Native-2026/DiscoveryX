import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import { useProject } from "./projectContext";
import type { TaskState } from "../api/types";

interface TaskContextValue {
  activeTask: TaskState | null;
  setActiveTask: (t: TaskState | null) => void;
}

const TaskContext = createContext<TaskContextValue>({
  activeTask: null,
  setActiveTask: () => {},
});

export function TaskProvider({ children }: { children: ReactNode }) {
  const [activeTask, setActiveTask] = useState<TaskState | null>(null);
  return <TaskContext.Provider value={{ activeTask, setActiveTask }}>{children}</TaskContext.Provider>;
}

export function useActiveTask(): TaskContextValue {
  return useContext(TaskContext);
}

/** The project pages operate on the active project's latest run (empty until one exists). */
export function useProjectTask(): { task: TaskState | null; loading: boolean; refresh: () => void } {
  const { activeTask, setActiveTask } = useActiveTask();
  const { activeProject } = useProject();
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);

  // A new project starts empty: drop any run carried over from another project.
  useEffect(() => {
    setActiveTask(null);
  }, [activeProject?.id, setActiveTask]);

  useEffect(() => {
    if (!activeProject) {
      setActiveTask(null);
      return;
    }
    if (activeTask && activeTask.project === activeProject.id) return;
    setLoading(true);
    api
      .listTasks(activeProject.id)
      .then((tasks) => {
        const t = tasks.find((x) => x.status === "succeeded") ?? tasks[0] ?? null;
        setActiveTask(t);
      })
      .catch(() => setActiveTask(null))
      .finally(() => setLoading(false));
  }, [activeProject, activeTask, setActiveTask, tick]);

  return { task: activeTask, loading, refresh: () => setTick((v) => v + 1) };
}

