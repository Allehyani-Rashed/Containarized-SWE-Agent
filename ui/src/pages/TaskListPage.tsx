import { ChangeEvent, FormEvent, useEffect, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import CredentialBanner from './taskList/components/CredentialBanner';
import ConcurrencyBanner from './taskList/components/ConcurrencyBanner';
import TaskFilterToolbar from './taskList/components/TaskFilterToolbar';
import TaskTable from './taskList/components/TaskTable';
import TaskDetailDrawer from './taskList/components/TaskDetailDrawer';
import TaskLookupPanel from './taskList/components/TaskLookupPanel';
import QuickAbortModal from './taskList/components/QuickAbortModal';
import { TASK_STATUS_OPTIONS } from './taskList/constants';
import { useTaskList } from './taskList/useTaskList';
import { useTaskLogs } from './taskList/useTaskLogs';
import { useProjects } from '../hooks/useProjectsData';
import { buildProjectLookup, getProjectDisplayName } from './taskList/taskSelectors';
import './TaskListPage.css';

type LocationState = {
  focusTaskId?: number;
};

function TaskListPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const taskList = useTaskList({ navigate });
  const {
    tasks,
    models,
    modelsError,
    error,
    filterDraft,
    filtersApplied,
    filterDraftMatchesApplied,
    isLoading,
    isLoadingMore,
    listMeta,
    canLoadMore,
    reachedPageLimit,
    selectedTaskId,
    taskDetail,
    taskLookupId,
    isDrawerOpen,
    quickActionLoading,
    actionNotice,
    actionError,
    confirmAction,
    confirmQuickAbort,
    isActionLoading,
    toggleStatusFilter,
    updateModelDraft,
    updateBranchDraft,
    submitFilters,
    resetFilters,
    loadMore,
    setTaskLookupId,
    lookupTask,
    selectTask,
    requestAbortTask,
    requestDeleteTask,
    cancelConfirmation,
    executeConfirmation,
    requestQuickAbort,
    clearQuickAbort,
    performQuickAbort,
    refreshTaskDetail,
    fetchTasks,
    updateSelectedTaskId,
    applyTaskDetail,
    updateTaskCredentials,
    clearTaskDetail,
    closeDrawer,
    openDrawer,
    navigateToSubmit,
    setActionNoticeMessage,
    setErrorMessage,
  } = taskList;

  const { projects, error: projectsError, refreshProjects } = useProjects();

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  const projectLookup = useMemo(() => buildProjectLookup(projects), [projects]);

  useEffect(() => {
    const state = location.state as LocationState | null;
    if (state?.focusTaskId) {
      const focusId = state.focusTaskId;
      updateSelectedTaskId(focusId);
      setTaskLookupId(String(focusId));
      void (async () => {
        const detail = await refreshTaskDetail(focusId, true);
        if (detail) {
          applyTaskDetail(detail);
          openDrawer();
        }
      })();
      navigate('.', { replace: true, state: {} });
    }
  }, [location.state, navigate, updateSelectedTaskId, setTaskLookupId, refreshTaskDetail, applyTaskDetail, openDrawer]);

  const logState = useTaskLogs({
    taskId: selectedTaskId,
    taskDetail,
    isDrawerOpen,
    refreshTaskDetail,
    fetchTasks,
    updateTaskCredentials,
    clearTaskDetail,
    closeDrawer,
    setActionNotice: setActionNoticeMessage,
    setErrorMessage,
  });

  const combinedError = error || modelsError || projectsError;

  const canAbortTask = taskDetail ? taskDetail.status === 'pending' || taskDetail.status === 'running' : false;
  const canDeleteTask = taskDetail ? ['done', 'failed', 'aborted'].includes(taskDetail.status) : false;
  const abortPending = taskDetail
    ? taskDetail.abort_requested && (taskDetail.status === 'pending' || taskDetail.status === 'running')
    : false;
  const selectedProjectName = taskDetail
    ? getProjectDisplayName(projectLookup, taskDetail.project_id)
    : '--';

  const handleLookupChange = (event: ChangeEvent<HTMLInputElement>) => {
    setTaskLookupId(event.target.value);
  };

  const handleLookupSubmit = (event: FormEvent<HTMLFormElement>) => {
    void lookupTask(event);
  };

  const handleSubmitTaskNavigation = () => {
    navigate('/');
  };

  return (
    <div className="layout-page">
      {combinedError && (
        <div className="error-banner" role="alert">
          {combinedError}
        </div>
      )}

      <CredentialBanner />
      <ConcurrencyBanner projects={projects} />

      <TaskFilterToolbar
        filterDraft={filterDraft}
        filtersApplied={filtersApplied}
        filterDraftMatchesApplied={filterDraftMatchesApplied}
        models={models}
        statusOptions={TASK_STATUS_OPTIONS}
        onStatusToggle={toggleStatusFilter}
        onModelChange={updateModelDraft}
        onBranchChange={updateBranchDraft}
        onSubmit={(event) => submitFilters(event)}
        onReset={resetFilters}
      />

      <TaskTable
        tasks={tasks}
        models={models}
        projectLookup={projectLookup}
        isLoading={isLoading}
        isLoadingMore={isLoadingMore}
        listMeta={listMeta}
        filtersApplied={filtersApplied}
        canLoadMore={canLoadMore}
        reachedPageLimit={reachedPageLimit}
        selectedTaskId={selectedTaskId}
        quickActionLoading={quickActionLoading}
        onSelectTask={selectTask}
        onLoadMore={loadMore}
        onResetFilters={resetFilters}
        onSubmitTask={handleSubmitTaskNavigation}
        onQuickAbortRequest={requestQuickAbort}
        onQuickRetry={(task) => navigateToSubmit(task, 'retry')}
        onQuickClone={(task) => navigateToSubmit(task, 'clone')}
      />

      <TaskLookupPanel
        taskLookupId={taskLookupId}
        onLookupChange={handleLookupChange}
        onLookupSubmit={handleLookupSubmit}
        taskDetail={taskDetail}
        isDrawerOpen={isDrawerOpen}
        onOpenDrawer={openDrawer}
      />

      <TaskDetailDrawer
        isOpen={isDrawerOpen}
        task={taskDetail}
        projectName={selectedProjectName}
        abortPending={abortPending}
        canAbort={canAbortTask}
        canDelete={canDeleteTask}
        isActionLoading={isActionLoading}
        actionNotice={actionNotice}
        actionError={actionError}
        confirmAction={confirmAction}
        onRequestAbort={requestAbortTask}
        onRequestDelete={requestDeleteTask}
        onCancelAction={cancelConfirmation}
        onConfirmAction={executeConfirmation}
        onClose={closeDrawer}
        logs={logState.logs}
        logMetadata={logState.metadata}
        isStreaming={logState.isStreaming}
        copyState={logState.copyState}
        onCopyLogs={logState.copyLogs}
        onResetCopyFeedback={logState.resetCopyFeedback}
      />

      <QuickAbortModal
        taskId={confirmQuickAbort}
        isLoading={confirmQuickAbort !== null && quickActionLoading === confirmQuickAbort}
        onConfirm={performQuickAbort}
        onCancel={clearQuickAbort}
      />
    </div>
  );
}

export default TaskListPage;
