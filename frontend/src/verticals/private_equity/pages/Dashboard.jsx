/**
 * Private Equity Dashboard
 * Main entry point for PE vertical
 */
import { useVertical } from '../../../core/hooks/useVertical';

export default function PEDashboard() {
  const { config } = useVertical();

  return (
    <div className="pe-dashboard">
      <h1>{config?.name} Dashboard</h1>
      <p>{config?.description}</p>
      {/* Dashboard content to be implemented */}
    </div>
  );
}
