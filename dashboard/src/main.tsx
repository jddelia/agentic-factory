import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Activity,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  FileText,
  GitBranch,
  Lock,
  MessageSquareText,
  Radio,
  RefreshCw,
  Send,
  Shield,
  TerminalSquare,
  TriangleAlert,
} from "lucide-react";
import "./styles.css";

type JsonObject = Record<string, unknown>;

type FactoryRun = {
  id: string;
  objective: string;
  work_mode: string;
  topology: string;
  status: string;
  started_at: string;
};

type Baton = {
  id: string;
  title: string;
  owner: string;
  status: string;
  scope: string;
  acceptance_tier: string;
  verification_level: string;
  assigned_at: string;
  commit_sha: string;
  summary: string;
};

type FactoryEvent = {
  id: number;
  occurred_at: string;
  event_type: string;
  actor: string;
  baton_id: string | null;
  summary: string;
  payload?: JsonObject;
};

type VerificationRun = {
  id: number;
  baton_id: string | null;
  command: string;
  result: string;
  summary: string;
  created_at: string;
};

type Review = {
  id: number;
  baton_id: string;
  reviewer: string;
  status: string;
  summary: string;
  created_at: string;
  findings?: Array<JsonObject>;
};

type AgentSession = {
  id: string;
  baton_id: string | null;
  role: string;
  adapter: string;
  label: string;
  status: string;
  control_mode: string;
  control_ref: string;
  packet_path: string;
  command?: string[];
  started_at: string | null;
  last_seen_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
  summary: string;
  metadata?: {
    stdout?: string;
    stderr?: string;
    duration_ms?: number;
    stdout_truncated?: boolean;
    stderr_truncated?: boolean;
    control_note?: string;
  };
  control_capabilities?: {
    can_record_message: boolean;
    can_deliver_live_message: boolean;
    mode: string;
  };
};

type Operator = {
  id: number | string;
  role: string;
  name: string;
  status: string;
  priority: number;
  authority: string[];
  operator_summary: string;
  is_primary: boolean;
  updated_at?: string;
  thread_id?: string;
  model?: string;
  reasoning?: string;
  control_capabilities?: {
    can_record_message: boolean;
    can_deliver_live_message: boolean;
    mode: string;
  };
};

type DashboardSnapshot = {
  initialized: boolean;
  generated_at: string;
  root: string;
  db: string;
  error?: string;
  server?: {
    control_enabled: boolean;
    live_terminal_supported: boolean;
    control_note: string;
  };
  status: null | {
    run: FactoryRun;
    active_batons: Baton[];
    held_locks: Array<JsonObject>;
    latest_event: FactoryEvent | null;
    git: {
      available: boolean;
      head: string;
      status: string;
    };
  };
  metrics: {
    active_batons?: number;
    active_sessions?: number;
    pending_reviews?: number;
    patch_required_reviews?: number;
    failed_verification?: number;
    blocked_verification?: number;
    recent_events?: number;
  };
  batons: Baton[];
  events: FactoryEvent[];
  verification: VerificationRun[];
  reviews: Review[];
  sessions: AgentSession[];
  operators: Operator[];
  primary_operator: Operator | null;
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1500,
    },
  },
});

function tokenFromLocation(): string {
  const params = new URLSearchParams(window.location.search);
  const queryToken = params.get("token");
  if (queryToken) {
    window.sessionStorage.setItem("factory-dashboard-token", queryToken);
    return queryToken;
  }
  return window.sessionStorage.getItem("factory-dashboard-token") ?? "";
}

async function apiFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "content-type": "application/json",
      "x-factory-token": token,
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : detail;
    } catch {
      // Keep the HTTP status text.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function useSnapshot(token: string) {
  return useQuery({
    queryKey: ["snapshot"],
    enabled: Boolean(token),
    queryFn: () => apiFetch<DashboardSnapshot>("/api/snapshot", token),
    refetchInterval: 15000,
  });
}

function useFactoryEvents(token: string) {
  const client = useQueryClient();
  useEffect(() => {
    if (!token) return undefined;
    const source = new EventSource(`/api/events/stream?token=${encodeURIComponent(token)}`);
    source.addEventListener("factory", () => {
      void client.invalidateQueries({ queryKey: ["snapshot"] });
    });
    source.onerror = () => {
      source.close();
      window.setTimeout(() => void client.invalidateQueries({ queryKey: ["snapshot"] }), 3000);
    };
    return () => source.close();
  }, [client, token]);
}

function formatTime(value?: string | null): string {
  if (!value) return "none";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function statusClass(status?: string | null): string {
  const normalized = (status ?? "").toLowerCase();
  if (["active", "assigned", "running", "in_progress", "handed_off", "review"].includes(normalized)) {
    return "status active";
  }
  if (["accepted", "completed", "pass", "ok"].includes(normalized)) return "status good";
  if (["fail", "failed", "rejected", "timed_out"].includes(normalized)) return "status bad";
  if (["blocked", "patch_required", "paused", "not_run"].includes(normalized)) return "status warn";
  return "status";
}

function groupBatons(batons: Baton[]): Record<string, Baton[]> {
  return batons.reduce<Record<string, Baton[]>>((groups, baton) => {
    const key = baton.status || "unknown";
    groups[key] = groups[key] ?? [];
    groups[key].push(baton);
    return groups;
  }, {});
}

function shellPreview(command?: string[]): string {
  if (!command?.length) return "No command recorded.";
  return command.map((part) => (/\s/.test(part) ? `"${part.replaceAll('"', '\\"')}"` : part)).join(" ");
}

function Header({
  snapshot,
  token,
  onRefresh,
  refreshing,
}: {
  snapshot?: DashboardSnapshot;
  token: string;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const run = snapshot?.status?.run;
  return (
    <header className="topbar">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          <Boxes size={20} strokeWidth={1.8} />
        </div>
        <div>
          <p className="eyebrow">Agentic Factory</p>
          <h1>Factory Floor</h1>
        </div>
      </div>
      <div className="topbar-meta">
        <span className={statusClass(run?.status)}>{run?.status ?? "not initialized"}</span>
        <span className="meta-chip" title={snapshot?.db ?? "No DB loaded"}>
          <Lock size={14} strokeWidth={1.8} />
          {token ? "tokened" : "missing token"}
        </span>
        <button className="icon-button" type="button" title="Refresh dashboard" onClick={onRefresh}>
          <RefreshCw className={refreshing ? "spin" : ""} size={18} strokeWidth={1.8} />
        </button>
      </div>
    </header>
  );
}

function Metrics({ snapshot }: { snapshot: DashboardSnapshot }) {
  const metrics = snapshot.metrics;
  const items = [
    { label: "Active Batons", value: metrics.active_batons ?? 0, icon: ClipboardCheck },
    { label: "Agent Sessions", value: metrics.active_sessions ?? 0, icon: TerminalSquare },
    { label: "Pending Review", value: metrics.pending_reviews ?? 0, icon: Shield },
    {
      label: "Verification Issues",
      value: (metrics.failed_verification ?? 0) + (metrics.blocked_verification ?? 0),
      icon: TriangleAlert,
    },
  ];
  return (
    <section className="metric-strip" aria-label="Factory metrics">
      {items.map((item) => (
        <div className="metric" key={item.label}>
          <item.icon size={18} strokeWidth={1.8} />
          <div>
            <strong>{item.value}</strong>
            <span>{item.label}</span>
          </div>
        </div>
      ))}
    </section>
  );
}

function RunPanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  const run = snapshot.status?.run;
  return (
    <section className="panel run-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Current Run</p>
          <h2>{run?.id ?? "No active run"}</h2>
        </div>
        <GitBranch size={18} strokeWidth={1.8} />
      </div>
      {run ? (
        <dl className="detail-grid">
          <div>
            <dt>Mode</dt>
            <dd>{run.work_mode}</dd>
          </div>
          <div>
            <dt>Topology</dt>
            <dd>{run.topology}</dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>{formatTime(run.started_at)}</dd>
          </div>
          <div>
            <dt>Git</dt>
            <dd>{snapshot.status?.git.head || "unavailable"}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted">{snapshot.error ?? "Run factory.py init before opening the dashboard."}</p>
      )}
      {run?.objective ? <p className="objective">{run.objective}</p> : null}
    </section>
  );
}

function CommandSeat({
  operator,
  snapshot,
  token,
  controlEnabled,
}: {
  operator?: Operator | null;
  snapshot: DashboardSnapshot;
  token: string;
  controlEnabled: boolean;
}) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const run = snapshot.status?.run;
  const mutation = useMutation({
    mutationFn: async () => {
      if (!operator) throw new Error("No operator selected.");
      return apiFetch(`/api/operators/${encodeURIComponent(String(operator.id))}/message`, token, {
        method: "POST",
        body: JSON.stringify({ actor: "Dashboard", message }),
      });
    },
    onSuccess: () => {
      setMessage("");
      void client.invalidateQueries({ queryKey: ["snapshot"] });
    },
  });
  const canRecord = Boolean(operator?.control_capabilities?.can_record_message);
  const disabled = !operator || !controlEnabled || !canRecord || mutation.isPending;

  return (
    <section className="command-seat">
      <div className="command-seat-main">
        <div className="seat-kicker">
          <Shield size={16} strokeWidth={1.8} />
          <span>Factory Command</span>
        </div>
        <div className="seat-title-row">
          <div>
            <h2>{operator?.name ?? "No operator"}</h2>
            <p>{operator?.role ?? "Run factory.py up to create the command seat."}</p>
          </div>
          <span className={statusClass(operator?.status ?? run?.status)}>{operator?.status ?? run?.status ?? "setup"}</span>
        </div>
        <p className="seat-summary">
          {operator?.operator_summary ||
            "The command seat is created during factory bootstrap and remains the top-level control context."}
        </p>
        <div className="authority-strip">
          {(operator?.authority?.length ? operator.authority : ["configure", "pause", "begin operations"]).map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </div>
      <div className="seat-control">
        <label htmlFor="operator-message">Message command seat</label>
        <textarea
          id="operator-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={
            controlEnabled
              ? "Tell the lead operator to begin, pause, summarize, or adjust the factory plan."
              : "Dashboard is read-only."
          }
          disabled={!controlEnabled}
        />
        <div className="message-actions">
          <span>{controlEnabled ? "Recorded as an operator event for the lead agent to consume." : "Read-only dashboard mode."}</span>
          <button
            type="button"
            className="primary-button"
            disabled={disabled || !message.trim()}
            onClick={() => mutation.mutate()}
            title="Record command-seat message"
          >
            <Send size={16} strokeWidth={1.8} />
            Send
          </button>
        </div>
        {mutation.error ? <p className="error-text">{mutation.error.message}</p> : null}
      </div>
    </section>
  );
}

function OperatorsPanel({
  operators,
  sessions,
  selectedOperator,
  selectedSession,
  onSelectOperator,
  onSelectSession,
}: {
  operators: Operator[];
  sessions: AgentSession[];
  selectedOperator?: string;
  selectedSession?: string;
  onSelectOperator: (id: string) => void;
  onSelectSession: (id: string) => void;
}) {
  return (
    <section className="panel operators-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Operators</p>
          <h2>Command hierarchy</h2>
        </div>
        <Radio size={18} strokeWidth={1.8} />
      </div>
      <div className="operator-list">
        {operators.map((operator) => (
          <button
            className={`operator-row ${selectedOperator === String(operator.id) ? "selected" : ""}`}
            key={operator.id}
            type="button"
            onClick={() => onSelectOperator(String(operator.id))}
          >
            <span className={operator.is_primary ? "operator-rank primary" : "operator-rank"}>{operator.priority}</span>
            <div>
              <strong>{operator.name}</strong>
              <small>{operator.role}</small>
            </div>
            <span className={statusClass(operator.status)}>{operator.status}</span>
          </button>
        ))}
        {!operators.length ? <p className="muted">No operators recorded.</p> : null}
      </div>
      <div className="worker-divider">
        <span>Worker sessions</span>
        <b>{sessions.length}</b>
      </div>
      <div className="session-list compact">
        {sessions.map((session) => (
          <button
            className={`session-row ${selectedSession === session.id ? "selected" : ""}`}
            key={session.id}
            type="button"
            onClick={() => onSelectSession(session.id)}
          >
            <span className={statusClass(session.status)}>{session.status}</span>
            <div>
              <strong>{session.label}</strong>
              <small>
                {session.role} · {session.adapter} · {session.baton_id ?? "factory"}
              </small>
            </div>
            <span className="time">{formatTime(session.last_seen_at ?? session.started_at)}</span>
          </button>
        ))}
        {!sessions.length ? (
          <div className="empty-state compact">
            <TerminalSquare size={22} strokeWidth={1.8} />
            <p>No worker sessions yet.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function BatonBoard({ batons, selected, onSelect }: {
  batons: Baton[];
  selected?: string;
  onSelect: (id: string) => void;
}) {
  const grouped = groupBatons(batons);
  const columns = ["assigned", "in_progress", "handed_off", "review", "accepted", "blocked"];
  return (
    <section className="panel board-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Baton Board</p>
          <h2>Scoped work lanes</h2>
        </div>
        <Activity size={18} strokeWidth={1.8} />
      </div>
      <div className="baton-board">
        {columns.map((column) => (
          <div className="lane" key={column}>
            <div className="lane-heading">
              <span>{column.replaceAll("_", " ")}</span>
              <b>{grouped[column]?.length ?? 0}</b>
            </div>
            <div className="lane-list">
              {(grouped[column] ?? []).map((baton) => (
                <button
                  className={`baton-card ${selected === baton.id ? "selected" : ""}`}
                  key={baton.id}
                  type="button"
                  onClick={() => onSelect(baton.id)}
                >
                  <span className={statusClass(baton.status)}>{baton.status}</span>
                  <strong>{baton.id}</strong>
                  <span>{baton.title}</span>
                  <small>{baton.owner || "unassigned"}</small>
                </button>
              ))}
              {!grouped[column]?.length ? <p className="empty-lane">No batons</p> : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SessionsPanel({
  sessions,
  selected,
  onSelect,
}: {
  sessions: AgentSession[];
  selected?: string;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="panel sessions-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Agent Sessions</p>
          <h2>Visible workers</h2>
        </div>
        <Radio size={18} strokeWidth={1.8} />
      </div>
      <div className="session-list">
        {sessions.map((session) => (
          <button
            className={`session-row ${selected === session.id ? "selected" : ""}`}
            key={session.id}
            type="button"
            onClick={() => onSelect(session.id)}
          >
            <span className={statusClass(session.status)}>{session.status}</span>
            <div>
              <strong>{session.label}</strong>
              <small>
                {session.role} · {session.adapter} · {session.baton_id ?? "factory"}
              </small>
            </div>
            <span className="time">{formatTime(session.last_seen_at ?? session.started_at)}</span>
          </button>
        ))}
        {!sessions.length ? (
          <div className="empty-state">
            <TerminalSquare size={24} strokeWidth={1.8} />
            <p>No agent sessions have been recorded yet.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function SessionDetail({
  session,
  token,
  controlEnabled,
}: {
  session?: AgentSession;
  token: string;
  controlEnabled: boolean;
}) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const mutation = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("No session selected.");
      return apiFetch(`/api/sessions/${encodeURIComponent(session.id)}/message`, token, {
        method: "POST",
        body: JSON.stringify({ actor: "Dashboard", message }),
      });
    },
    onSuccess: () => {
      setMessage("");
      void client.invalidateQueries({ queryKey: ["snapshot"] });
    },
  });

  if (!session) {
    return (
      <section className="panel detail-panel">
        <div className="empty-state tall">
          <MessageSquareText size={28} strokeWidth={1.8} />
          <p>Select a session to inspect packet path, command, output, and message controls.</p>
        </div>
      </section>
    );
  }

  const canRecord = Boolean(session.control_capabilities?.can_record_message);
  const liveDelivery = Boolean(session.control_capabilities?.can_deliver_live_message);
  const disabled = !controlEnabled || !canRecord || mutation.isPending;

  return (
    <section className="panel detail-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Session Detail</p>
          <h2>{session.label}</h2>
        </div>
        <span className={statusClass(session.status)}>{session.status}</span>
      </div>
      <dl className="detail-grid">
        <div>
          <dt>Control</dt>
          <dd>{liveDelivery ? "live delivery" : "event request"}</dd>
        </div>
        <div>
          <dt>Exit</dt>
          <dd>{session.exit_code ?? "running"}</dd>
        </div>
        <div>
          <dt>Packet</dt>
          <dd className="truncate" title={session.packet_path}>{session.packet_path || "none"}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{session.metadata?.duration_ms ? `${session.metadata.duration_ms} ms` : "unknown"}</dd>
        </div>
      </dl>
      <div className="command-block">
        <span>Command</span>
        <code>{shellPreview(session.command)}</code>
      </div>
      <div className="message-box">
        <label htmlFor="session-message">Send message</label>
        <textarea
          id="session-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={controlEnabled ? "Ask this worker to pause, summarize, or adjust scope." : "Dashboard is read-only."}
          disabled={!controlEnabled}
        />
        <div className="message-actions">
          <span>{controlEnabled ? "Recorded as a factory event unless live transport is available." : "Read-only dashboard mode."}</span>
          <button
            type="button"
            className="primary-button"
            disabled={disabled || !message.trim()}
            onClick={() => mutation.mutate()}
            title="Record dashboard message request"
          >
            <Send size={16} strokeWidth={1.8} />
            Send
          </button>
        </div>
        {mutation.error ? <p className="error-text">{mutation.error.message}</p> : null}
      </div>
      <OutputPane title="stdout" value={session.metadata?.stdout} truncated={session.metadata?.stdout_truncated} />
      <OutputPane title="stderr" value={session.metadata?.stderr} truncated={session.metadata?.stderr_truncated} />
    </section>
  );
}

function OutputPane({ title, value, truncated }: { title: string; value?: string; truncated?: boolean }) {
  if (!value) return null;
  return (
    <div className="output-pane">
      <div>
        <span>{title}</span>
        {truncated ? <b>truncated</b> : null}
      </div>
      <pre>{value}</pre>
    </div>
  );
}

function EvidencePanel({
  verification,
  reviews,
}: {
  verification: VerificationRun[];
  reviews: Review[];
}) {
  return (
    <section className="panel evidence-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Verification</p>
          <h2>Checks and review</h2>
        </div>
        <CheckCircle2 size={18} strokeWidth={1.8} />
      </div>
      <div className="evidence-grid">
        <div>
          <h3>Recent checks</h3>
          {verification.slice(0, 6).map((item) => (
            <div className="evidence-row" key={item.id}>
              <span className={statusClass(item.result)}>{item.result}</span>
              <div>
                <strong>{item.command}</strong>
                <small>{item.summary || item.baton_id || "factory-level check"}</small>
              </div>
            </div>
          ))}
          {!verification.length ? <p className="muted">No verification recorded.</p> : null}
        </div>
        <div>
          <h3>Recent reviews</h3>
          {reviews.slice(0, 6).map((item) => (
            <div className="evidence-row" key={item.id}>
              <span className={statusClass(item.status)}>{item.status}</span>
              <div>
                <strong>{item.baton_id}</strong>
                <small>{item.summary || item.reviewer}</small>
              </div>
            </div>
          ))}
          {!reviews.length ? <p className="muted">No reviews recorded.</p> : null}
        </div>
      </div>
    </section>
  );
}

function EventStream({ events }: { events: FactoryEvent[] }) {
  return (
    <section className="panel event-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Live Ledger</p>
          <h2>Recent events</h2>
        </div>
        <Clock3 size={18} strokeWidth={1.8} />
      </div>
      <div className="event-list">
        {events.map((event) => (
          <div className="event-row" key={event.id}>
            <span className="event-dot" />
            <div>
              <strong>{event.event_type}</strong>
              <p>{event.summary || "No summary"}</p>
              <small>
                {formatTime(event.occurred_at)} · {event.actor || "unknown"} · {event.baton_id ?? "factory"}
              </small>
            </div>
          </div>
        ))}
        {!events.length ? <p className="muted">No events yet.</p> : null}
      </div>
    </section>
  );
}

function LedgerPanel({ token }: { token: string }) {
  const [expanded, setExpanded] = useState(false);
  const ledger = useQuery({
    queryKey: ["ledger"],
    enabled: expanded && Boolean(token),
    queryFn: () => apiFetch<{ markdown: string }>("/api/ledger", token),
  });
  return (
    <section className="panel ledger-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Ledger Preview</p>
          <h2>Markdown state</h2>
        </div>
        <button className="text-button" type="button" onClick={() => setExpanded((value) => !value)}>
          <FileText size={16} strokeWidth={1.8} />
          {expanded ? "Hide" : "Load"}
        </button>
      </div>
      {expanded ? (
        <pre className="ledger-preview">{ledger.data?.markdown ?? (ledger.isLoading ? "Loading..." : "No ledger available.")}</pre>
      ) : (
        <p className="muted">Load the generated markdown ledger without writing a file.</p>
      )}
    </section>
  );
}

function DashboardApp() {
  const [token] = useState(tokenFromLocation);
  const snapshot = useSnapshot(token);
  useFactoryEvents(token);

  const data = snapshot.data;
  const [selectedOperatorId, setSelectedOperatorId] = useState<string | undefined>();
  const [selectedSessionId, setSelectedSessionId] = useState<string | undefined>();
  const [selectedBatonId, setSelectedBatonId] = useState<string | undefined>();

  useEffect(() => {
    if (!selectedSessionId && data?.sessions[0]) setSelectedSessionId(data.sessions[0].id);
  }, [data?.sessions, selectedSessionId]);

  useEffect(() => {
    const primaryId = data?.primary_operator?.id;
    if (!selectedOperatorId && primaryId !== undefined && primaryId !== null) {
      setSelectedOperatorId(String(primaryId));
    }
  }, [data?.primary_operator, selectedOperatorId]);

  const selectedSession = useMemo(
    () => data?.sessions.find((session) => session.id === selectedSessionId),
    [data?.sessions, selectedSessionId],
  );
  const selectedOperator = useMemo(
    () => data?.operators.find((operator) => String(operator.id) === selectedOperatorId) ?? data?.primary_operator,
    [data?.operators, data?.primary_operator, selectedOperatorId],
  );

  if (!token) {
    return (
      <main className="auth-shell">
        <Shield size={32} strokeWidth={1.8} />
        <h1>Dashboard token required</h1>
        <p>Open the URL printed by factory.py dashboard serve. It includes a one-time local token.</p>
      </main>
    );
  }

  if (snapshot.isLoading) {
    return (
      <main className="auth-shell">
        <RefreshCw className="spin" size={30} strokeWidth={1.8} />
        <h1>Loading factory state</h1>
      </main>
    );
  }

  if (snapshot.error || !data) {
    return (
      <main className="auth-shell">
        <TriangleAlert size={32} strokeWidth={1.8} />
        <h1>Unable to load dashboard</h1>
        <p>{snapshot.error?.message ?? "Unknown error."}</p>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <Header
        snapshot={data}
        token={token}
        refreshing={snapshot.isFetching}
        onRefresh={() => void snapshot.refetch()}
      />
      <main className="dashboard-grid">
        <section className="main-column">
          <CommandSeat
            operator={selectedOperator}
            snapshot={data}
            token={token}
            controlEnabled={Boolean(data.server?.control_enabled)}
          />
          <Metrics snapshot={data} />
          <RunPanel snapshot={data} />
          <BatonBoard batons={data.batons} selected={selectedBatonId} onSelect={setSelectedBatonId} />
          <EvidencePanel verification={data.verification} reviews={data.reviews} />
        </section>
        <aside className="side-column">
          <OperatorsPanel
            operators={data.operators}
            sessions={data.sessions}
            selectedOperator={selectedOperatorId}
            selectedSession={selectedSessionId}
            onSelectOperator={setSelectedOperatorId}
            onSelectSession={setSelectedSessionId}
          />
          <SessionDetail
            session={selectedSession}
            token={token}
            controlEnabled={Boolean(data.server?.control_enabled)}
          />
          <LedgerPanel token={token} />
          <EventStream events={data.events} />
        </aside>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <DashboardApp />
    </QueryClientProvider>
  </React.StrictMode>,
);
