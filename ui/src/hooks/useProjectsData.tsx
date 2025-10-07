import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  createProject as createProjectApi,
  deleteProject as deleteProjectApi,
  listProjects,
  updateProject as updateProjectApi,
} from '../api/projects';
import {
  Project,
  ProjectCreatePayload,
  ProjectDeletePayload,
  ProjectUpdatePayload,
} from '../types';

type ProjectsContextValue = {
  projects: Project[];
  isLoading: boolean;
  error: string | null;
  refreshProjects: () => Promise<void>;
  createProject: (_payload: ProjectCreatePayload) => Promise<Project>;
  updateProject: (_projectId: number, _payload: ProjectUpdatePayload) => Promise<Project>;
  deleteProject: (_projectId: number, _payload?: ProjectDeletePayload) => Promise<void>;
  clearError: () => void;
};

const ProjectsContext = createContext<ProjectsContextValue | undefined>(undefined);

type ProviderProps = {
  children: ReactNode;
};

export function ProjectsProvider({ children }: ProviderProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const refreshProjects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (refreshError) {
      const message = refreshError instanceof Error ? refreshError.message : 'Failed to load projects';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  const createProject = useCallback(
    async (payload: ProjectCreatePayload) => {
      setError(null);
      try {
        const project = await createProjectApi(payload);
        setProjects((prev) => [...prev, project].sort((a, b) => a.id - b.id));
        return project;
      } catch (createError) {
        const message = createError instanceof Error ? createError.message : 'Failed to create project';
        setError(message);
        throw createError;
      }
    },
    [],
  );

  const updateProject = useCallback(
    async (projectId: number, payload: ProjectUpdatePayload) => {
      setError(null);
      try {
        const project = await updateProjectApi(projectId, payload);
        setProjects((prev) =>
          prev
            .map((item) => (item.id === project.id ? project : item))
            .sort((a, b) => a.id - b.id),
        );
        return project;
      } catch (updateError) {
        const message = updateError instanceof Error ? updateError.message : 'Failed to update project';
        setError(message);
        throw updateError;
      }
    },
    [],
  );

  const deleteProject = useCallback(
    async (projectId: number, payload?: ProjectDeletePayload) => {
      setError(null);
      try {
        await deleteProjectApi(projectId, payload);
        setProjects((prev) => prev.filter((item) => item.id !== projectId));
      } catch (deleteError) {
        const message = deleteError instanceof Error ? deleteError.message : 'Failed to delete project';
        setError(message);
        throw deleteError;
      }
    },
    [],
  );

  const value = useMemo<ProjectsContextValue>(
    () => ({
      projects,
      isLoading,
      error,
      refreshProjects,
      createProject,
      updateProject,
      deleteProject,
      clearError: () => setError(null),
    }),
    [projects, isLoading, error, refreshProjects, createProject, updateProject, deleteProject],
  );

  return <ProjectsContext.Provider value={value}>{children}</ProjectsContext.Provider>;
}

export function useProjects() {
  const context = useContext(ProjectsContext);
  if (!context) {
    throw new Error('useProjects must be used within a ProjectsProvider');
  }
  return context;
}
