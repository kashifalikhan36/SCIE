"use client";

import { useEffect, useState, useRef } from "react";
import { getStoredServerUrl, setStoredServerUrl, getStoredState, ExtensionState } from "../storage/store";

interface LogEntry {
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR";
  message: string;
}

export default function Popup() {
  // Extension states
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
  const [showLogs, setShowLogs] = useState(false);
  const [uiError, setUiError] = useState<string | null>(null);
  const [isExtension, setIsExtension] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, showLogs]);

  // Initial load and state sync
  useEffect(() => {
    const isChromExt = typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id;
    setIsExtension(!!isChromExt);

    if (isChromExt) {
      // Load stored configurations
      getStoredServerUrl().then((url) => {
        setServerUrl(url);
      });

      getStoredState().then((storedState) => {
        setState((prev) => ({
          ...prev,
          ...storedState,
        }));
      });

      // Load active logs
      chrome.runtime.sendMessage({ action: "get_logs" }, (response) => {
        if (response && response.logs) {
          setLogs(response.logs);
        }
      });

      // Listen for local storage updates
      const handleStorageChange = (changes: { [key: string]: chrome.storage.StorageChange }) => {
        const newState: Partial<ExtensionState> = {};
        let changed = false;

        const keys: (keyof ExtensionState)[] = [
          "isServerConnected",
          "isMeetConnected",
          "isMonitoring",
          "activeMeetingId",
          "activeMeetingUrl",
          "participantCount",
        ];

        keys.forEach((key) => {
          if (changes[key]) {
            (newState as any)[key] = changes[key].newValue;
            changed = true;
          }
        });

        if (changed) {
          setState((prev) => ({
            ...prev,
            ...newState,
          }));
        }
      };

      chrome.storage.onChanged.addListener(handleStorageChange);

      // Listen for message events (like real-time logs)
      const handleRuntimeMessage = (message: any) => {
        if (message.type === "LOG_EVENT") {
          setLogs((prev) => [...prev, message.log].slice(-300));
        }
      };

      chrome.runtime.onMessage.addListener(handleRuntimeMessage);

      return () => {
        chrome.storage.onChanged.removeListener(handleStorageChange);
        chrome.runtime.onMessage.removeListener(handleRuntimeMessage);
      };
    } else {
      // Mock logs for static browser preview
      setLogs([
        { timestamp: new Date().toISOString(), level: "INFO", message: "Static preview mode. Chrome API not available." },
        { timestamp: new Date().toISOString(), level: "WARN", message: "Load as unpacked extension in Chrome to use full features." }
      ]);
    }
  }, []);

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setServerUrl(val);
    if (isExtension) {
      setStoredServerUrl(val);
    }
  };

  const connectServer = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "connect_ws" }, (res) => {
        if (res && !res.success) {
          setUiError(res.error || "Failed to connect to server");
        }
      });
    } else {
      // Mock connection for preview
      setState((prev) => ({ ...prev, isServerConnected: true }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock Connected to Server." }]);
    }
  };

  const disconnectServer = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "disconnect_ws" }, (res) => {
        if (res && !res.success) {
          setUiError(res.error || "Failed to disconnect");
        }
      });
    } else {
      setState((prev) => ({ ...prev, isServerConnected: false, isMonitoring: false }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock Disconnected from Server." }]);
    }
  };

  const startMonitoring = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "start_monitoring" }, (res) => {
        if (res && !res.success) {
          setUiError(res.error || "Failed to start monitoring");
        }
      });
    } else {
      setState((prev) => ({ ...prev, isMonitoring: true }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock Monitoring Started." }]);
    }
  };

  const stopMonitoring = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "stop_monitoring" }, (res) => {
        if (res && !res.success) {
          setUiError(res.error || "Failed to stop monitoring");
        }
      });
    } else {
      setState((prev) => ({ ...prev, isMonitoring: false }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock Monitoring Stopped." }]);
    }
  };

  const clearLogs = () => {
    setLogs([]);
  };

  return (
    <div className="flex flex-col w-[400px] min-h-[480px] bg-slate-50 text-slate-800 antialiased p-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-md shadow-blue-500/20">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-900 leading-none">Sherlock AI</h1>
            <span className="text-[10px] text-slate-400 font-medium tracking-wider uppercase">Ingestion Console</span>
          </div>
        </div>
        
        {/* Active streaming badge */}
        {state.isMonitoring && (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-500 pulse-indicator"></span>
            Streaming
          </span>
        )}
      </div>

      {/* Error alert */}
      {uiError && (
        <div className="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-lg flex items-start gap-2 animate-fadeIn">
          <svg className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="font-medium">{uiError}</div>
        </div>
      )}

      {/* Connection Config Card */}
      <div className="glass-card rounded-xl p-4 mt-4 flex flex-col gap-3">
        <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Server Configuration</h2>
        
        <div>
          <label className="text-[11px] font-semibold text-slate-500 block mb-1">FastAPI WebSocket URL</label>
          <input
            type="text"
            className="w-full bg-slate-50 border border-slate-200 text-slate-800 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-all font-mono"
            placeholder="ws://localhost:8000/ws/meeting"
            value={serverUrl}
            onChange={handleUrlChange}
            disabled={state.isServerConnected}
          />
        </div>

        <div className="grid grid-cols-2 gap-3 mt-1">
          {!state.isServerConnected ? (
            <button
              onClick={connectServer}
              className="col-span-2 w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-md shadow-blue-600/10 hover:shadow-blue-600/20 active:translate-y-[1px] transition-all flex items-center justify-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Connect Server
            </button>
          ) : (
            <button
              onClick={disconnectServer}
              disabled={state.isMonitoring}
              className="col-span-2 w-full py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 text-xs font-semibold active:translate-y-[1px] transition-all flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:pointer-events-none"
            >
              <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Disconnect
            </button>
          )}
        </div>
      </div>

      {/* Connection & Meet Status Card */}
      <div className="grid grid-cols-2 gap-3 mt-3">
        <div className="glass-card rounded-xl p-3 flex flex-col gap-1.5 justify-center">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Server Status</span>
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${state.isServerConnected ? "bg-emerald-500" : "bg-rose-500"}`}></span>
            <span className="text-xs font-semibold text-slate-700">
              {state.isServerConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>

        <div className="glass-card rounded-xl p-3 flex flex-col gap-1.5 justify-center">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Google Meet</span>
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${state.isMeetConnected ? "bg-emerald-500" : "bg-rose-500"}`}></span>
            <span className="text-xs font-semibold text-slate-700">
              {state.isMeetConnected ? "Detected" : "Not Found"}
            </span>
          </div>
        </div>
      </div>

      {/* Meeting Details Card */}
      <div className="glass-card rounded-xl p-4 mt-3 flex flex-col gap-2.5">
        <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Active Meeting Information</h2>
        
        {state.isMeetConnected && state.activeMeetingId ? (
          <div className="flex flex-col gap-2">
            <div className="flex justify-between items-center py-1 border-b border-slate-100">
              <span className="text-xs text-slate-500 font-medium">Meeting ID</span>
              <span className="text-xs font-semibold text-slate-800 font-mono bg-slate-100 px-2 py-0.5 rounded">
                {state.activeMeetingId}
              </span>
            </div>

            <div className="flex justify-between items-center py-1 border-b border-slate-100">
              <span className="text-xs text-slate-500 font-medium">Active Participants</span>
              <span className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
                {state.participantCount}
              </span>
            </div>

            <div className="flex flex-col gap-1 mt-1">
              <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider">Meeting URL</span>
              <a
                href={state.activeMeetingUrl || "#"}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] font-semibold text-blue-600 hover:underline truncate"
              >
                {state.activeMeetingUrl}
              </a>
            </div>
          </div>
        ) : (
          <div className="py-4 text-center text-xs text-slate-400 font-medium italic">
            Waiting for active Google Meet session...
          </div>
        )}
      </div>

      {/* Monitoring Actions */}
      <div className="mt-4 flex flex-col gap-3">
        {!state.isMonitoring ? (
          <button
            onClick={startMonitoring}
            disabled={!state.isServerConnected || !state.isMeetConnected}
            className="w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-md shadow-blue-500/10 hover:shadow-blue-500/25 active:translate-y-[0.5px] transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:pointer-events-none disabled:shadow-none"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Start Monitoring
          </button>
        ) : (
          <button
            onClick={stopMonitoring}
            className="w-full py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-md shadow-rose-500/10 hover:shadow-rose-500/25 active:translate-y-[0.5px] transition-all flex items-center justify-center gap-2"
          >
            <svg className="w-4 h-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H10a1 1 0 01-1-1v-4z" />
            </svg>
            Stop Monitoring
          </button>
        )}
      </div>

      {/* Logs Trigger */}
      <div className="mt-4 flex items-center justify-between">
        <button
          onClick={() => setShowLogs(!showLogs)}
          className="text-xs font-bold text-slate-500 hover:text-slate-700 flex items-center gap-1.5 transition-colors focus:outline-none"
        >
          <svg className={`w-4 h-4 transition-transform duration-200 ${showLogs ? "rotate-90" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
          </svg>
          Console Logs
        </button>

        {showLogs && (
          <button
            onClick={clearLogs}
            className="text-[11px] font-semibold text-slate-400 hover:text-rose-500 transition-colors"
          >
            Clear Console
          </button>
        )}
      </div>

      {/* Logs Drawer */}
      {showLogs && (
        <div className="mt-2.5 rounded-xl border border-slate-200 bg-slate-900 text-[11px] font-mono text-slate-300 p-3 h-48 overflow-y-auto flex flex-col gap-1.5 shadow-inner">
          {logs.length === 0 ? (
            <div className="text-center text-slate-500 italic py-8">Console is empty</div>
          ) : (
            logs.map((log, index) => {
              let colorClass = "text-slate-400";
              if (log.level === "ERROR") colorClass = "text-rose-400 font-semibold";
              if (log.level === "WARN") colorClass = "text-amber-400";
              
              const dateStr = log.timestamp.split("T")[1]?.substring(0, 8) || log.timestamp;
              return (
                <div key={index} className="leading-relaxed break-all">
                  <span className="text-slate-600 font-semibold">[{dateStr}]</span>{" "}
                  <span className={colorClass}>[{log.level}]</span>{" "}
                  <span>{log.message}</span>
                </div>
              );
            })
          )}
          <div ref={logsEndRef} />
        </div>
      )}
    </div>
  );
}
