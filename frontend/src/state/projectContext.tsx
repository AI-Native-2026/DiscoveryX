import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { ProjectOut } from "../api/types";

interface ProjectContextValue {
  projects: ProjectOut[];
  activeProject: ProjectOut | null;
  setActiveProject: (p: ProjectOut) => void;
  refresh: () => void;
}

const ProjectContext = createContext<ProjectContextValue>({
  projects: [],
  activeProject: null,
  setActiveProject: () => {},
  refresh: () => {},
});

const STORAGE_KEY = "discoveryx.activeProject";

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [activeProject, setActive] = useState<ProjectOut | null>(null);

  const refresh = useCallback(() => {
    api
      .listProjects()
      .then((r) => {
        setProjects(r.items);
        setActive((cur) => {
          if (cur) {
            const still = r.items.find((p) => p.id === cur.id);
            if (still) return still;
          }
          const saved = localStorage.getItem(STORAGE_KEY);
          return r.items.find((p) => p.id === saved) ?? r.items[0] ?? null;
        });
      })
      .catch(() => setProjects([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setActiveProject = useCallback((p: ProjectOut) => {
    setActive(p);
    localStorage.setItem(STORAGE_KEY, p.id);
  }, []);

  return (
    <ProjectContext.Provider value={{ projects, activeProject, setActiveProject, refresh }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject(): ProjectContextValue {
  return useContext(ProjectContext);
}
