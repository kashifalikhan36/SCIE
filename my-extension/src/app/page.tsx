"use client";

import { useEffect, useState, useRef } from "react";
import {
  getStoredServerUrl,
  setStoredServerUrl,
  getStoredState,
  ExtensionState,
} from "../storage/store";
import { Fingerprint, Play, Square, Trash2, Activity, Server, Radio, Wifi, WifiOff, ChevronDown, ChevronUp } from "lucide-react";

interface LogEntry {
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR";
  message: string;
}

function StatusDot({ active, pulse }: { active: boolean; pulse?: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
        active
          ? pulse
            ? "bg-green-400 animate-pulse"
            : "bg-green-400"
          : "bg-slate-600"
      }`}
    />
  );
}

export default function Popup() {
  const [serverUrl, setServerUrl] = useState("ws://localhost:8000/ws/meeting");
  const [state, setState] = useState<ExtensionState>({
    serverUrl: "ws://localhost:8000/ws/meeting",
    isServerConnected: false,
    isMeetConnected: false,
    isMonitoring: false,
    activeMeetingId: null,
    activeMeetingUrl: null,
    participantCount: 0,
  });

  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [uiError, setUiError] = useState<string | null>(null);
  const [isExtension, setIsExtension] = useState(false);
  const [logsOpen, setLogsOpen] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logsEndRef.current && logsOpen) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, logsOpen]);

  useEffect(() => {
    const isChromExt =
      typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id;
    setIsExtension(!!isChromExt);

    if (isChromExt) {
      getStoredServerUrl().then(setServerUrl);
      getStoredState().then((storedState) => {
        setState((prev) => ({ ...prev, ...storedState }));
      });
      chrome.runtime.sendMessage({ action: "get_logs" }, (response) => {
        if (response?.logs) setLogs(response.logs);
      });

      const handleStorageChange = (
        changes: { [key: string]: chrome.storage.StorageChange }
      ) => {
        const newState: Partial<ExtensionState> = {};
        let changed = false;
        const keys: (keyof ExtensionState)[] = [
          "isServerConnected", "isMeetConnected", "isMonitoring",
          "activeMeetingId", "activeMeetingUrl", "participantCount",
        ];
        keys.forEach((key) => {
          if (changes[key]) {
            (newState as any)[key] = changes[key].newValue;
            changed = true;
          }
        });
        if (changed) setState((prev) => ({ ...prev, ...newState }));
      };

      const handleRuntimeMessage = (message: any) => {
        if (message.type === "LOG_EVENT") {
          setLogs((prev) => [...prev, message.log].slice(-200));
        }
      };

      chrome.storage.onChanged.addListener(handleStorageChange);
      chrome.runtime.onMessage.addListener(handleRuntimeMessage);
      return () => {
        chrome.storage.onChanged.removeListener(handleStorageChange);
        chrome.runtime.onMessage.removeListener(handleRuntimeMessage);
      };
    }
  }, []);

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newUrl = e.target.value;
    setServerUrl(newUrl);
    if (isExtension) setStoredServerUrl(newUrl);
  };

  const connectServer = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "connect_server", url: serverUrl }, (res) => {
        if (res && !res.success) setUiError(res.error || "Failed to connect");
      });
    } else {
      setState((prev) => ({ ...prev, isServerConnected: true }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock: Connected to server." }]);
    }
  };

  const disconnectServer = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "disconnect_server" });
    } else {
      setState((prev) => ({ ...prev, isServerConnected: false }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock: Disconnected from server." }]);
    }
  };

  const startMonitoring = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "start_monitoring" }, (res) => {
        if (res && !res.success) setUiError(res.error || "Failed to start monitoring");
      });
    } else {
      setState((prev) => ({ ...prev, isMonitoring: true }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock: Monitoring started." }]);
    }
  };

  const stopMonitoring = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "stop_monitoring" }, (res) => {
        if (res && !res.success) setUiError(res.error || "Failed to stop monitoring");
      });
    } else {
      setState((prev) => ({ ...prev, isMonitoring: false }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock: Monitoring stopped." }]);
    }
  };

  const clearLogs = () => setLogs([]);

  return (
    <div className="flex flex-col w-full" style={{ background: "var(--background)" }}>

      {/* ── Header ── */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: "var(--border)", background: "var(--background)" }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: "var(--primary)" }}
          >
            <Fingerprint className="w-4.5 h-4.5 text-white" style={{ width: 18, height: 18, color: "white" }} />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-bold leading-none" style={{ color: "var(--foreground)" }}>
              Sherlock AI
            </div>
            <div className="text-[10px] mt-0.5 font-medium tracking-widest uppercase" style={{ color: "var(--muted-foreground)" }}>
              Ingestion Console
            </div>
          </div>
        </div>

        {/* Live badge */}
        {state.isMonitoring && (
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold"
            style={{ background: "rgba(34,197,94,0.12)", color: "#4ade80", border: "1px solid rgba(74,222,128,0.3)" }}
          >
            <Radio style={{ width: 11, height: 11 }} />
            Live
          </div>
        )}
      </div>

      {/* ── Error banner ── */}
      {uiError && (
        <div
          className="mx-3 mt-3 px-3 py-2 rounded-lg text-xs font-medium flex items-start gap-2"
          style={{ background: "rgba(220,38,38,0.12)", color: "#f87171", border: "1px solid rgba(248,113,113,0.25)" }}
        >
          <span className="mt-0.5 flex-shrink-0">⚠</span>
          <span>{uiError}</span>
        </div>
      )}

      {/* ── Status row ── */}
      <div
        className="mx-3 mt-3 px-3 py-2 rounded-xl flex items-center gap-4 text-[11px]"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-1.5">
          <StatusDot active={state.isServerConnected} />
          <span style={{ color: "var(--muted-foreground)" }}>Server</span>
        </div>
        <div className="flex items-center gap-1.5">
          <StatusDot active={state.isMeetConnected} />
          <span style={{ color: "var(--muted-foreground)" }}>Meet</span>
        </div>
        <div className="flex items-center gap-1.5">
          <StatusDot active={state.isMonitoring} pulse />
          <span style={{ color: "var(--muted-foreground)" }}>Streaming</span>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <span style={{ color: "var(--muted-foreground)" }}>Participants:</span>
          <span className="font-bold" style={{ color: "var(--primary)" }}>{state.participantCount}</span>
        </div>
      </div>

      {/* ── Server Config Card ── */}
      <div
        className="mx-3 mt-3 rounded-xl overflow-hidden"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
      >
        <div
          className="flex items-center gap-2 px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--muted-foreground)", borderBottom: "1px solid var(--border)" }}
        >
          <Server style={{ width: 11, height: 11 }} />
          Server Connection
        </div>
        <div className="p-3 space-y-2.5">
          <div>
            <div className="text-[10px] mb-1" style={{ color: "var(--muted-foreground)" }}>WebSocket Endpoint</div>
            <input
              type="text"
              value={serverUrl}
              onChange={handleUrlChange}
              disabled={state.isServerConnected}
              placeholder="ws://localhost:8000/ws/meeting"
              className="w-full text-[11px] font-mono px-3 py-2 rounded-lg outline-none transition-all disabled:opacity-50"
              style={{
                background: "var(--input)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
                lineHeight: "1.4",
              }}
            />
          </div>
          {!state.isServerConnected ? (
            <button
              onClick={connectServer}
              className="w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
              style={{ background: "var(--primary)", color: "var(--primary-foreground)" }}
            >
              <Wifi style={{ width: 13, height: 13 }} />
              Connect Server
            </button>
          ) : (
            <button
              onClick={disconnectServer}
              disabled={state.isMonitoring}
              className="w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-40"
              style={{ background: "var(--secondary)", color: "var(--secondary-foreground)", border: "1px solid var(--border)" }}
            >
              <WifiOff style={{ width: 13, height: 13 }} />
              Disconnect
            </button>
          )}
        </div>
      </div>

      {/* ── Meeting Card ── */}
      <div
        className="mx-3 mt-3 rounded-xl overflow-hidden"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
      >
        <div
          className="flex items-center justify-between px-3 py-2.5"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div
            className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--muted-foreground)" }}
          >
            <Activity style={{ width: 11, height: 11 }} />
            Target Meeting
          </div>
          <div
            className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
            style={
              state.isMeetConnected
                ? { background: "rgba(34,197,94,0.12)", color: "#4ade80", border: "1px solid rgba(74,222,128,0.3)" }
                : { background: "var(--secondary)", color: "var(--muted-foreground)", border: "1px solid var(--border)" }
            }
          >
            {state.isMeetConnected ? "Attached" : "No Meeting"}
          </div>
        </div>

        <div className="p-3 space-y-2.5">
          {state.activeMeetingId && (
            <div>
              <div className="text-[10px] mb-1" style={{ color: "var(--muted-foreground)" }}>Meeting ID</div>
              <div
                className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg truncate"
                style={{ background: "var(--secondary)", color: "var(--foreground)", border: "1px solid var(--border)" }}
              >
                {state.activeMeetingId}
              </div>
            </div>
          )}

          {!state.isMonitoring ? (
            <button
              onClick={startMonitoring}
              disabled={!state.isServerConnected || !state.isMeetConnected}
              className="w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-40"
              style={{
                background: "rgba(34,197,94,0.15)",
                color: "#4ade80",
                border: "1px solid rgba(74,222,128,0.35)",
              }}
            >
              <Play style={{ width: 13, height: 13 }} />
              Start Injection
            </button>
          ) : (
            <button
              onClick={stopMonitoring}
              className="w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
              style={{ background: "rgba(220,38,38,0.15)", color: "#f87171", border: "1px solid rgba(248,113,113,0.3)" }}
            >
              <Square style={{ width: 13, height: 13 }} />
              Stop Injection
            </button>
          )}
        </div>
      </div>

      {/* ── Console Logs Card ── */}
      <div
        className="mx-3 mt-3 mb-4 rounded-xl overflow-hidden"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
      >
        <button
          onClick={() => setLogsOpen(!logsOpen)}
          className="w-full flex items-center justify-between px-3 py-2.5 text-left transition-colors hover:bg-white/5"
          style={{ borderBottom: logsOpen ? "1px solid var(--border)" : "none" }}
        >
          <div
            className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--muted-foreground)" }}
          >
            <span className="font-mono">{">"}_</span>
            Console
            {logs.length > 0 && (
              <span
                className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
                style={{ background: "var(--primary)", color: "var(--primary-foreground)" }}
              >
                {logs.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {logs.length > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); clearLogs(); }}
                className="p-1 rounded hover:bg-white/10 transition-colors"
                title="Clear logs"
              >
                <Trash2 style={{ width: 11, height: 11, color: "var(--muted-foreground)" }} />
              </button>
            )}
            {logsOpen
              ? <ChevronUp style={{ width: 13, height: 13, color: "var(--muted-foreground)" }} />
              : <ChevronDown style={{ width: 13, height: 13, color: "var(--muted-foreground)" }} />
            }
          </div>
        </button>

        {logsOpen && (
          <div
            className="overflow-y-auto p-2 space-y-0.5"
            style={{ maxHeight: 180, minHeight: 64 }}
          >
            {logs.length === 0 ? (
              <div className="text-center py-6 text-[11px]" style={{ color: "var(--muted-foreground)" }}>
                No events yet…
              </div>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="text-[10px] font-mono leading-relaxed px-1 flex gap-2">
                  <span className="flex-shrink-0" style={{ color: "var(--muted-foreground)", opacity: 0.5 }}>
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                  <span
                    className="flex-shrink-0 font-bold"
                    style={{
                      color: log.level === "ERROR" ? "#f87171" : log.level === "WARN" ? "#fbbf24" : "#60a5fa",
                    }}
                  >
                    [{log.level}]
                  </span>
                  <span className="break-all" style={{ color: "var(--muted-foreground)" }}>
                    {log.message}
                  </span>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}
