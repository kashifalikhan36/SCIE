"use client";

import { useEffect, useState, useRef } from "react";
import { getStoredServerUrl, setStoredServerUrl, getStoredState, ExtensionState } from "../storage/store";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Fingerprint, Play, Square, Settings2, Trash2, Activity, Server, Radio, Loader2 } from "lucide-react";

interface LogEntry {
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR";
  message: string;
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
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  useEffect(() => {
    const isChromExt = typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id;
    setIsExtension(!!isChromExt);

    if (isChromExt) {
      getStoredServerUrl().then(setServerUrl);

      getStoredState().then((storedState) => {
        setState((prev) => ({ ...prev, ...storedState }));
      });

      chrome.runtime.sendMessage({ action: "get_logs" }, (response) => {
        if (response?.logs) {
          setLogs(response.logs);
        }
      });

      const handleStorageChange = (changes: { [key: string]: chrome.storage.StorageChange }) => {
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

        if (changed) {
          setState((prev) => ({ ...prev, ...newState }));
        }
      };

      chrome.storage.onChanged.addListener(handleStorageChange);

      const handleRuntimeMessage = (message: any) => {
        if (message.type === "LOG_EVENT") {
          setLogs((prev) => [...prev, message.log].slice(-100));
        }
      };

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
    if (isExtension) {
      setStoredServerUrl(newUrl);
    }
  };

  const connectServer = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "connect_server", url: serverUrl }, (res) => {
        if (res && !res.success) {
          setUiError(res.error || "Failed to connect to server");
        }
      });
    } else {
      setState((prev) => ({ ...prev, isServerConnected: true }));
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), level: "INFO", message: "Mock Connected to Server." }]);
    }
  };

  const disconnectServer = () => {
    setUiError(null);
    if (isExtension) {
      chrome.runtime.sendMessage({ action: "disconnect_server" });
    } else {
      setState((prev) => ({ ...prev, isServerConnected: false }));
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
    <div className="flex flex-col w-[400px] min-h-[550px] max-h-[600px] bg-background text-foreground dark antialiased border border-border/40 relative">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-background pointer-events-none" />

      {/* Header */}
      <div className="relative z-10 flex items-center justify-between p-4 border-b border-border/40 bg-background/95 backdrop-blur">
        <div className="flex items-center gap-2">
          <Fingerprint className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-lg font-bold tracking-tight leading-none bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">Sherlock AI</h1>
            <span className="text-[10px] text-muted-foreground font-medium tracking-wider uppercase">Ingestion Console</span>
          </div>
        </div>
        {state.isMonitoring && (
          <Badge variant="default" className="bg-green-500 hover:bg-green-600 gap-1.5 animate-pulse">
            <Radio className="h-3 w-3" />
            Live
          </Badge>
        )}
      </div>

      <div className="relative z-10 flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
        {uiError && (
          <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-md font-medium">
            {uiError}
          </div>
        )}

        {/* Server Config */}
        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Server className="h-3 w-3" />
              Server Connection
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 space-y-3">
            <div className="space-y-1.5">
              <label className="text-[10px] text-muted-foreground">FastAPI Endpoint</label>
              <Input
                value={serverUrl}
                onChange={handleUrlChange}
                disabled={state.isServerConnected}
                className="h-8 text-xs font-mono bg-background/50"
                placeholder="ws://localhost:8000/ws/meeting"
              />
            </div>
            
            {!state.isServerConnected ? (
              <Button onClick={connectServer} className="w-full h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground">
                Connect Server
              </Button>
            ) : (
              <Button onClick={disconnectServer} disabled={state.isMonitoring} variant="secondary" className="w-full h-8 text-xs border border-border/40 hover:bg-muted">
                Disconnect
              </Button>
            )}
          </CardContent>
        </Card>

        {/* Meeting Target */}
        <Card className="bg-background/60 backdrop-blur border-border/40">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center justify-between">
              <div className="flex items-center gap-2"><Activity className="h-3 w-3" /> Target Meeting</div>
              {state.isMeetConnected ? (
                <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-green-500/30 text-green-500 bg-green-500/10">Attached</Badge>
              ) : (
                <Badge variant="outline" className="text-[9px] h-4 px-1.5">No Meeting</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 space-y-3">
             <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <div className="text-[10px] text-muted-foreground">Meeting ID</div>
                  <div className="font-mono text-xs font-medium truncate mt-1">
                    {state.activeMeetingId || "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-muted-foreground">Participants (Extracted)</div>
                  <div className="text-lg font-bold text-primary leading-none mt-1">
                    {state.participantCount}
                  </div>
                </div>
             </div>
             
             {!state.isMonitoring ? (
                <Button 
                  onClick={startMonitoring} 
                  disabled={!state.isServerConnected || !state.isMeetConnected}
                  className="w-full h-8 text-xs bg-green-500 hover:bg-green-600 text-white shadow-[0_0_15px_rgba(34,197,94,0.4)]"
                >
                  <Play className="h-3.5 w-3.5 mr-1.5" /> Start Injection
                </Button>
             ) : (
                <Button 
                  onClick={stopMonitoring} 
                  variant="destructive"
                  className="w-full h-8 text-xs"
                >
                  <Square className="h-3.5 w-3.5 mr-1.5" /> Stop Injection
                </Button>
             )}
          </CardContent>
        </Card>

        {/* Console Logs */}
        <Card className="bg-background/60 backdrop-blur border-border/40 flex-1 flex flex-col min-h-[150px]">
          <CardHeader className="p-3 pb-2 border-b border-border/40">
            <div className="flex items-center justify-between">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Console Logs</CardTitle>
              <Button variant="ghost" size="icon" className="h-5 w-5 rounded-full" onClick={clearLogs}>
                <Trash2 className="h-3 w-3 text-muted-foreground" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0 flex-1 h-[150px] relative">
            <ScrollArea className="h-full absolute inset-0">
               <div className="p-3 space-y-1">
                  {logs.length === 0 ? (
                    <div className="text-xs text-muted-foreground text-center pt-8">No events.</div>
                  ) : (
                    logs.map((log, i) => (
                      <div key={i} className="text-[10px] font-mono leading-tight">
                        <span className="text-muted-foreground/60">[{new Date(log.timestamp).toLocaleTimeString()}]</span>{" "}
                        <span className={log.level === 'ERROR' ? 'text-destructive font-bold' : log.level === 'WARN' ? 'text-yellow-500' : 'text-blue-400'}>[{log.level}]</span>{" "}
                        <span className="text-muted-foreground break-all">{log.message}</span>
                      </div>
                    ))
                  )}
                  <div ref={logsEndRef} />
               </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
