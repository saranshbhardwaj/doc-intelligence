import { describe, expect, it } from 'vitest';
import { getMemoActionState } from './underwritingWorkflowMemoGate';

describe('underwritingWorkflowMemoGate', () => {
  it('blocks self-storage memo generation until workflow state is ready', () => {
    const currentRun = { asset_type: 'self_storage' };

    expect(getMemoActionState(currentRun, 'idle')).toEqual({
      requiresWorkflowState: true,
      disabled: true,
      helperText: 'Self-storage workflow is still loading. Memo generation unlocks once the workflow is ready.',
    });

    expect(getMemoActionState(currentRun, 'error')).toEqual({
      requiresWorkflowState: true,
      disabled: true,
      helperText: 'Workflow state failed to load. Reload the run before generating a memo.',
    });

    expect(getMemoActionState(currentRun, 'ready')).toEqual({
      requiresWorkflowState: true,
      disabled: false,
      helperText: null,
    });
  });

  it('does not block non-self-storage runs', () => {
    expect(getMemoActionState({ asset_type: 'multifamily' }, 'idle')).toEqual({
      requiresWorkflowState: false,
      disabled: false,
      helperText: null,
    });
  });
  
  it('hard-blocks self-storage memo generation when the backend disallows it', () => {
    const state = getMemoActionState(
      { id: 'run-3', workflow_type: 'self_storage' },
      'ready',
      {
        memo_generation: {
          allowed: false,
          requires_override: false,
          disabled_reason: 'A memo is already generating for this run.',
        },
      },
    );

    expect(state).toEqual({
      requiresWorkflowState: true,
      disabled: true,
      helperText: 'A memo is already generating for this run.',
    });
  });
  
  it('leaves the memo button enabled when the backend requires an override', () => {
    const state = getMemoActionState(
      { id: 'run-4', workflow_type: 'self_storage' },
      'ready',
      {
        memo_generation: {
          allowed: false,
          requires_override: true,
        },
      },
    );

    expect(state).toEqual({
      requiresWorkflowState: true,
      disabled: false,
      helperText: null,
    });
  });
  
  it('keeps the memo button enabled when the backend allows generation', () => {
    const state = getMemoActionState(
      { id: 'run-5', workflow_type: 'self_storage' },
      'ready',
      {
        memo_generation: {
          allowed: true,
          requires_override: false,
        },
      },
    );

    expect(state).toEqual({
      requiresWorkflowState: true,
      disabled: false,
      helperText: null,
    });
  });
});