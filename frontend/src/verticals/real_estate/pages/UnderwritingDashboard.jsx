/**
 * Underwriting Dashboard
 * Portfolio-style list of underwriting runs.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, MapPin, Plus, Search, Trash2, TrendingUp } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import AppLayout from '../../../components/layout/AppLayout';
import { useAppAuth } from '../../../hooks/useAppAuth';
import { useUnderwriting, useUnderwritingActions } from '../../../store';
import { deleteUnderwritingRun } from '../../../api/re-underwriting';
import {
  UnderwritingEmptyState,
  UnderwritingMetricCard,
  UnderwritingStatusBadge,
} from '../components/underwriting';

function formatPercent(value) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function formatMoneyCompact(value) {
  if (value == null) return '—';
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function getStatusMeta(status) {
  switch (status) {
    case 'extracting':
      return { tone: 'active', label: 'Extracting' };
    case 'calculating':
      return { tone: 'active', label: 'Calculating' };
    case 'needs_review':
      return { tone: 'warning', label: 'Needs Review' };
    case 'completed':
      return { tone: 'success', label: 'Completed' };
    case 'failed':
      return { tone: 'danger', label: 'Failed' };
    default:
      return { tone: 'neutral', label: status || 'Draft' };
  }
}

function getVerdictMeta(verdict) {
  if (verdict === 'worth_pursuing') return { tone: 'success', label: 'Passes Screen' };
  if (verdict === 'needs_review') return { tone: 'warning', label: 'Review Needed' };
  if (verdict) return { tone: 'danger', label: 'Below Screen' };
  return null;
}

function RunRow({ run, onOpen, onDelete }) {
  const status = getStatusMeta(run.status);
  const verdict = getVerdictMeta(run.result_artifact?.verdict?.status);

  return (
    <div className="underwriting-panel p-4 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <button
          type="button"
          onClick={onOpen}
          className="min-w-0 flex-1 text-left"
        >
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-display text-xl font-semibold tracking-tight text-foreground">
              {run.name || 'Untitled analysis'}
            </p>
            <UnderwritingStatusBadge tone={status.tone}>{status.label}</UnderwritingStatusBadge>
            {verdict ? <UnderwritingStatusBadge tone={verdict.tone}>{verdict.label}</UnderwritingStatusBadge> : null}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5" />
              {run.address || 'Address not added'}
            </span>
            <span>{run.asset_type?.replaceAll('_', ' ') || 'Asset type not set'}</span>
          </div>
        </button>

        <div className="flex shrink-0 items-center gap-2 self-start">
          <Button variant="outline" size="sm" onClick={onOpen}>
            Open
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full text-destructive hover:bg-destructive/10 hover:text-destructive">
                <Trash2 className="h-4 w-4" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete analysis?</AlertDialogTitle>
                <AlertDialogDescription>
                  "{run.name || 'Untitled analysis'}" will be permanently deleted. This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={onDelete} className="bg-destructive hover:bg-destructive/90">
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <UnderwritingMetricCard
          label="IRR"
          value={formatPercent(run.irr)}
          detail="Target return"
          tone={run.result_artifact?.verdict?.status === 'worth_pursuing' ? 'success' : run.result_artifact?.verdict?.status === 'needs_review' ? 'warning' : 'default'}
          className="p-4"
        />
        <UnderwritingMetricCard
          label="Cash-on-Cash"
          value={formatPercent(run.cash_on_cash)}
          detail="Year-one cash yield"
          className="p-4"
        />
        <UnderwritingMetricCard
          label="Equity Multiple"
          value={run.equity_multiple == null ? '—' : `${run.equity_multiple.toFixed(2)}×`}
          detail="Total return multiple"
          className="p-4"
        />
        <UnderwritingMetricCard
          label="Monthly Cash Flow"
          value={formatMoneyCompact(run.monthly_cashflow)}
          detail="Stabilized cash flow"
          className="p-4"
        />
      </div>
    </div>
  );
}

export default function UnderwritingDashboard() {
  const navigate = useNavigate();
  const { getToken } = useAppAuth();
  const { runs } = useUnderwriting();
  const { loadRuns } = useUnderwritingActions();
  const [query, setQuery] = useState('');

  useEffect(() => {
    loadRuns(getToken);
  }, [getToken, loadRuns]);

  const filteredRuns = runs
    ? runs.filter((r) => {
        const q = query.trim().toLowerCase();
        if (!q) return true;
        return (
          r.name?.toLowerCase().includes(q) ||
          r.address?.toLowerCase().includes(q)
        );
      })
    : null;

  const handleDelete = async (runId) => {
    try {
      await deleteUnderwritingRun(getToken, runId);
      loadRuns(getToken);
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  const newAnalysisBtn = (
    <Button onClick={() => navigate('/app/re/underwriting/new')}>
      <Plus className="mr-1.5 h-4 w-4" />
      New Analysis
    </Button>
  );

  const pageHeader = {
    eyebrow: 'Real Estate',
    title: 'Underwriting',
    actions: newAnalysisBtn,
  };

  if (!runs) {
    return (
      <AppLayout pageHeader={pageHeader}>
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
          <div className="underwriting-shell page-enter p-5 sm:p-6">
            <div className="mb-6">
              <p className="underwriting-kicker">Underwriting</p>
              <h1 className="underwriting-title mt-2">Deal pipeline</h1>
              <p className="underwriting-subtitle mt-2">
                Track live extractions, open completed analyses, and keep a clean view of the deals worth a second look.
              </p>
            </div>
            <div className="space-y-4">
              {[...Array(3)].map((_, index) => (
                <div key={index} className="underwriting-panel p-5">
                  <Skeleton className="h-6 w-56" />
                  <Skeleton className="mt-3 h-4 w-72" />
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {[...Array(4)].map((__, cellIndex) => (
                      <Skeleton key={cellIndex} className="h-28 rounded-3xl" />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout pageHeader={pageHeader}>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="underwriting-shell page-enter p-5 sm:p-6">
          <div className="flex flex-col gap-4 border-b border-border/60 pb-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0">
              <p className="underwriting-kicker">Underwriting</p>
              <h1 className="underwriting-title mt-2">Deal pipeline</h1>
              <p className="underwriting-subtitle mt-2">
                Review active analyses, reopen completed work, and move quickly from AI extraction into investment judgment.
              </p>
            </div>
            <UnderwritingStatusBadge tone="neutral">
              {runs.length} {runs.length === 1 ? 'deal' : 'deals'}
            </UnderwritingStatusBadge>
          </div>

          <div className="mt-5">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <input
                type="text"
                placeholder="Search by deal name or address…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full rounded-lg border border-border/70 bg-background/80 py-2 pl-9 pr-4 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-primary/50 focus:ring-2 focus:ring-primary/15 transition-colors"
              />
            </div>
          </div>

          <div className="mt-4">
            {runs.length === 0 ? (
              <UnderwritingEmptyState
                icon={Building2}
                title="No underwriting analyses yet"
                description="Start a new analysis to upload source documents, review AI-populated inputs, and generate a decision-ready underwriting view."
                action={(
                  <Button onClick={() => navigate('/app/re/underwriting/new')}>
                    <TrendingUp className="mr-1.5 h-4 w-4" />
                    Start first analysis
                  </Button>
                )}
              />
            ) : filteredRuns.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                No deals match <span className="font-medium text-foreground">"{query}"</span>
              </p>
            ) : (
              <div className="space-y-4">
                {filteredRuns.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    onOpen={() => navigate(`/app/re/underwriting/${run.id}`)}
                    onDelete={() => handleDelete(run.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
