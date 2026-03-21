/**
 * DealRoomsPage — Landing page for PE Diligence.
 * Shows all deal rooms for the org as a card grid.
 */

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, ChevronRight } from "lucide-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import PELayout from "./PELayout";
import { listRooms } from "../../../api/pe-diligence";

const STATUS_STYLES = {
  completed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  running:   "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  failed:    "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  pending:   "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  draft:     "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  active:    "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
};

function StatusBadge({ status }) {
  const label = status || "draft";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize shrink-0 ${STATUS_STYLES[label] || STATUS_STYLES.draft}`}>
      {label}
    </span>
  );
}

export default function DealRoomsPage() {
  const { getToken } = useAppAuth();
  const navigate = useNavigate();
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listRooms(getToken)
      .then(setRooms)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <PELayout>
      <div className="pe-page min-h-full">
        {/* Header */}
        <div className="pe-header mb-6">
          <div>
            <h1 className="pe-title font-display">Deal Rooms</h1>
            <p className="pe-subtitle mt-1">
            Diligence workspaces for acquisition targets
            </p>
          </div>
          <span className="pe-chip">Private Equity</span>
        </div>

        {loading && (
          <p className="text-sm text-muted-foreground">Loading rooms…</p>
        )}

        {!loading && rooms.length === 0 && (
          <div className="pe-card-muted p-16 text-center">
            <Briefcase className="w-10 h-10 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-sm font-semibold">No deal rooms yet</p>
            <p className="text-xs text-muted-foreground mt-1">
              Click "+ New Room" in the sidebar to get started.
            </p>
          </div>
        )}

        {!loading && rooms.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {rooms.map((room) => (
              <div
                key={room.id}
                onClick={() => navigate(`/app/pe/rooms/${room.id}/dashboard`)}
                className="pe-card p-5 hover:border-primary/40 hover:shadow-md transition-all cursor-pointer group"
              >
                {/* Card top */}
                <div className="flex items-start justify-between gap-2 mb-4">
                  <div className="flex-1 min-w-0">
                    <p className="font-bold text-base leading-tight truncate group-hover:text-primary transition-colors">
                      {room.name}
                    </p>
                    {room.target_company ? (
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">
                        {room.target_company}
                      </p>
                    ) : room.description ? (
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">
                        {room.description}
                      </p>
                    ) : null}
                  </div>
                  <StatusBadge status={room.status} />
                </div>

                {/* Card footer */}
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>
                    {room.documents_count ?? 0} document{room.documents_count !== 1 ? "s" : ""}
                    {room.created_at && (
                      <span className="ml-2 text-muted-foreground/60">
                        · {new Date(room.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </span>
                  <span className="flex items-center gap-0.5 text-primary font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                    Open
                    <ChevronRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </PELayout>
  );
}
