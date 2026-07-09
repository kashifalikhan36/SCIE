export interface LogEntry {
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR";
  message: string;
}

class ExtensionLogger {
  private logs: LogEntry[] = [];
  private readonly maxLogs = 500;
  private listeners: ((log: LogEntry) => void)[] = [];

  log(message: string, level: "INFO" | "WARN" | "ERROR" = "INFO") {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
    };
    
    this.logs.push(entry);
    if (this.logs.length > this.maxLogs) {
      this.logs.shift();
    }

    // Print to developer console
    const logStr = `[SCIE] [${entry.timestamp}] [${level}] ${message}`;
    if (level === "ERROR") {
      console.error(logStr);
    } else if (level === "WARN") {
      console.warn(logStr);
    } else {
      console.log(logStr);
    }

    // Notify memory listeners
    this.listeners.forEach((l) => l(entry));

    // Try to notify popup or background via chrome runtime messaging
    try {
      chrome.runtime.sendMessage({
        type: "LOG_EVENT",
        log: entry,
      }).catch(() => {
        // Expected if receiver is not active
      });
    } catch (e) {
      // Ignored
    }
  }

  info(message: string) {
    this.log(message, "INFO");
  }

  warn(message: string) {
    this.log(message, "WARN");
  }

  error(message: string) {
    this.log(message, "ERROR");
  }

  getLogs(): LogEntry[] {
    return this.logs;
  }

  clear() {
    this.logs = [];
  }

  addListener(listener: (log: LogEntry) => void) {
    this.listeners.push(listener);
  }

  removeListener(listener: (log: LogEntry) => void) {
    this.listeners = this.listeners.filter((l) => l !== listener);
  }
}

export const logger = new ExtensionLogger();
