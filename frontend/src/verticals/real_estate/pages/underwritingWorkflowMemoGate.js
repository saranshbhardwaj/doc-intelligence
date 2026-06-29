const SELF_STORAGE_LOADING_MESSAGE = 'Self-storage workflow is still loading. Memo generation unlocks once the workflow is ready.';
const SELF_STORAGE_ERROR_MESSAGE = 'Workflow state failed to load. Reload the run before generating a memo.';

function getWorkflowAssetType(currentRun) {
  return currentRun?.asset_type || currentRun?.workflow_type || currentRun?.inputs?.project?.asset_type || null;
}

export function isSelfStorageWorkflowRun(currentRun) {
  return getWorkflowAssetType(currentRun) === 'self_storage';
}

export function getMemoActionState(currentRun, workflowStatus, workflow = null) {
  const requiresWorkflowState = isSelfStorageWorkflowRun(currentRun);
  const workflowAllowed = workflow?.memo_generation?.allowed;
  const workflowRequiresOverride = workflow?.memo_generation?.requires_override;
  const backendBlocked = requiresWorkflowState
    && workflowStatus === 'ready'
    && workflowAllowed === false
    && !workflowRequiresOverride;

  const disabled = requiresWorkflowState && (workflowStatus !== 'ready' || backendBlocked);
  const helperText = !requiresWorkflowState
    ? null
    : workflowStatus === 'error'
      ? SELF_STORAGE_ERROR_MESSAGE
      : backendBlocked
        ? workflow?.memo_generation?.disabled_reason || 'Memo generation is blocked until workflow gates are cleared.'
        : workflowStatus === 'ready'
          ? null
          : SELF_STORAGE_LOADING_MESSAGE;

  return {
    requiresWorkflowState,
    disabled,
    helperText,
  };
}