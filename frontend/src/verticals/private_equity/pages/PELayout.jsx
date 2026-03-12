/**
 * PELayout — Context-switching sidebar layout for all PE Diligence pages.
 *
 * Rooms mode  (/app/pe/rooms):            room list + new room
 * Room mode   (/app/pe/rooms/:roomId/*):  room-scoped nav (Dashboard/Docs/Analysis/Investigations)
 */

import { useState, useEffect, useRef } from "react";
import { Link, useParams, useLocation, useNavigate } from "react-router-dom";
import {
  Plus, ChevronLeft, ChevronRight, Circle,
  LayoutDashboard, FileText, BarChart3, Search,
} from "lucide-react";
import AppLayout from "../../../components/layout/AppLayout";
import { Card } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Button } from "../../../components/ui/button";
import { useAppAuth } from "@/hooks/useAppAuth";
import { listRooms, createRoom, getRoom } from "../../../api/pe-diligence";

const STATUS_COLORS = {
  completed: "text-green-500",
  running:   "text-yellow-500",
  failed:    "text-red-500",
};

function StatusDot({ status }) {
  const color = STATUS_COLORS[status] || "text-muted-foreground/30";
  return <Circle className={`w-1.5 h-1.5 fill-current shrink-0 ${color}`} />;
}

const ROOM_NAV = [
  { label: "Dashboard",      path: "dashboard",      Icon: LayoutDashboard },
  { label: "Documents",      path: "documents",      Icon: FileText },
  { label: "Analysis",       path: "analysis",       Icon: BarChart3 },
  { label: "Investigations", path: "investigations", Icon: Search },
];

export default function PELayout({ children }) {
  const { roomId } = useParams();
  const location  = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <AppLayout>
      <div className="pe-shell" style={{ height: "calc(100vh - 57px)" }}>
        <aside
          className={`pe-sidebar transition-all duration-300 overflow-hidden ${
            sidebarCollapsed ? "w-0 border-r-0" : "w-64"
          }`}
        >
          {!sidebarCollapsed && (
            <Card className="flex-1 flex flex-col overflow-hidden p-4 rounded-none border-0 bg-transparent">
              {roomId
                ? <RoomSidebar roomId={roomId} location={location} onCollapse={() => setSidebarCollapsed(true)} />
                : <RoomsSidebar location={location} onCollapse={() => setSidebarCollapsed(true)} />
              }
            </Card>
          )}
        </aside>
        {sidebarCollapsed && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarCollapsed(false)}
            className="h-9 w-9 rounded-r-lg rounded-l-none border border-l-0 bg-card shadow-sm hover:bg-muted absolute left-0 top-3 z-20"
            title="Expand sidebar"
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        )}
        <main className="pe-main overflow-y-auto">{children}</main>
      </div>
    </AppLayout>
  );
}

/* ── Rooms sidebar ─────────────────────────────────────────────────────────── */

function RoomsSidebar({ location, onCollapse }) {
  const { getToken } = useAppAuth();
  const navigate = useNavigate();
  const inputRef = useRef(null);

  const [rooms, setRooms]             = useState([]);
  const [creating, setCreating]       = useState(false);
  const [newName, setNewName]         = useState("");
  const [createError, setCreateError] = useState(null);

  useEffect(() => {
    listRooms(getToken).then(setRooms).catch(console.error);
  }, []);

  useEffect(() => {
    if (creating) inputRef.current?.focus();
  }, [creating]);

  function cancelCreate() {
    setCreating(false);
    setNewName("");
    setCreateError(null);
  }

  async function handleCreate(e) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    try {
      const room = await createRoom(getToken, { name });
      setCreateError(null);
      cancelCreate();
      navigate(`/app/pe/rooms/${room.id}/dashboard`);
    } catch (err) {
      setCreateError(err.response?.data?.detail || "Failed to create room");
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Private Equity
          </p>
          <div className="flex items-center gap-1 mt-1">
            <h2 className="text-sm font-semibold text-foreground">Deal Rooms</h2>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setCreating(true)}
              className="h-6 w-6 p-0"
              title="New Room"
            >
              <Plus className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
        {onCollapse && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onCollapse}
            className="h-7 w-7"
            title="Collapse sidebar"
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* Room list */}
      <div className="flex-1 overflow-y-auto space-y-1 min-h-0 scrollbar-thin pr-1">
        {rooms.length === 0 && !creating && (
          <div className="text-center py-6">
            <p className="text-xs text-muted-foreground">No rooms yet</p>
          </div>
        )}

        {rooms.map((room) => {
          const active = location.pathname.startsWith(`/app/pe/rooms/${room.id}`);
          return (
            <Link
              key={room.id}
              to={`/app/pe/rooms/${room.id}/dashboard`}
              className={`group flex items-center gap-2 py-2.5 px-3 rounded-xl transition-all ${
                active
                  ? "pe-nav-link-active"
                  : "pe-nav-link border border-transparent"
              }`}
            >
              <StatusDot status={room.status} />
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium truncate ${active ? "text-primary" : "text-foreground"}`}>
                  {room.name}
                </p>
              </div>
            </Link>
          );
        })}

        {/* New room inline form */}
        {creating && (
          <form onSubmit={handleCreate} className="pt-1 px-1">
            <Input
              ref={inputRef}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onBlur={() => { if (!newName.trim()) cancelCreate(); }}
              onKeyDown={(e) => e.key === "Escape" && cancelCreate()}
              placeholder="Room name…"
              className="h-9 text-sm mb-2"
              autoFocus
            />
            {createError && (
              <p className="text-xs text-destructive mb-1 px-1">{createError}</p>
            )}
            <div className="flex gap-2">
              <Button size="sm" type="submit" className="flex-1 h-8 rounded-full">
                Create
              </Button>
              <Button size="sm" variant="outline" type="button" onClick={cancelCreate} className="flex-1 h-8 rounded-full">
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>

      {/* Footer */}
      <div className="pe-divider mt-4 pt-3">
        <Link
          to="/app/library"
          className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-foreground transition-colors"
        >
          <ChevronLeft className="w-3 h-3" />
          Back to Core
        </Link>
      </div>
    </div>
  );
}

/* ── Room-scoped sidebar ───────────────────────────────────────────────────── */

function RoomSidebar({ roomId, location, onCollapse }) {
  const { getToken } = useAppAuth();
  const [room, setRoom] = useState(null);

  useEffect(() => {
    getRoom(getToken, roomId).then(setRoom).catch(console.error);
  }, [roomId]);

  return (
    <div className="flex flex-col h-full">
      {/* Back link */}
      <div className="mb-2 flex items-center justify-between">
        <Link
          to="/app/pe/rooms"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-foreground transition-colors"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          All Rooms
        </Link>
        {onCollapse && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onCollapse}
            className="h-7 w-7"
            title="Collapse sidebar"
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
        )}
      </div>

      <div className="pe-divider mb-3" />

      {/* Room info */}
      <div className="mb-3">
        <p className="text-sm font-semibold leading-tight truncate">
          {room?.name ?? "—"}
        </p>
        {room?.target_company && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {room.target_company}
          </p>
        )}
        {room && (
          <div className="flex items-center gap-1.5 mt-1.5">
            <StatusDot status={room.status} />
            <span className="text-xs text-muted-foreground capitalize">{room.status}</span>
          </div>
        )}
      </div>

      <div className="pe-divider mb-3" />

      {/* Section label */}
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground mb-2 px-1">
        Navigation
      </p>

      {/* Nav links */}
      <nav className="flex-1 space-y-1 overflow-y-auto scrollbar-thin pr-1">
        {ROOM_NAV.map(({ label, path, Icon }) => {
          const href   = `/app/pe/rooms/${roomId}/${path}`;
          const active = location.pathname === href
            || location.pathname.startsWith(href + "/")
            || (path === "investigations" && location.pathname.startsWith(`/app/pe/rooms/${roomId}/investigations`));
          return (
            <Link
              key={path}
              to={href}
              className={`flex items-center gap-2.5 py-2.5 px-3 rounded-xl text-sm transition-all border ${
                active
                  ? "pe-nav-link-active border-primary/30"
                  : "border-transparent text-foreground/70 hover:bg-muted/50 hover:text-foreground"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="pe-divider mt-4 pt-3">
        <Link
          to="/app/library"
          className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-foreground transition-colors"
        >
          <ChevronLeft className="w-3 h-3" />
          Back to Core
        </Link>
      </div>
    </div>
  );
}
