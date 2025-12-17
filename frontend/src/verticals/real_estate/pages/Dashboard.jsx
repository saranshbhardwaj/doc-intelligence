/**
 * Real Estate Dashboard
 * Main entry point for RE vertical
 */
import { useVertical } from '../../../core/hooks/useVertical';

export default function REDashboard() {
  const { config } = useVertical();

  return (
    <div className="re-dashboard">
      <h1>{config?.name} Dashboard</h1>
      <p>{config?.description}</p>
      {/* Dashboard content to be implemented */}
    </div>
  );
}
