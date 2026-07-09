"use strict";
(() => {
  // src/utils/logger.ts
  var ExtensionLogger = class {
    constructor() {
      this.logs = [];
      this.maxLogs = 500;
      this.listeners = [];
    }
    log(message, level = "INFO") {
      const entry = {
        timestamp: (/* @__PURE__ */ new Date()).toISOString(),
        level,
        message
      };
      this.logs.push(entry);
      if (this.logs.length > this.maxLogs) {
        this.logs.shift();
      }
      const logStr = `[Sherlock AI] [${entry.timestamp}] [${level}] ${message}`;
      if (level === "ERROR") {
        console.error(logStr);
      } else if (level === "WARN") {
        console.warn(logStr);
      } else {
        console.log(logStr);
      }
      this.listeners.forEach((l) => l(entry));
      try {
        chrome.runtime.sendMessage({
          type: "LOG_EVENT",
          log: entry
        }).catch(() => {
        });
      } catch (e) {
      }
    }
    info(message) {
      this.log(message, "INFO");
    }
    warn(message) {
      this.log(message, "WARN");
    }
    error(message) {
      this.log(message, "ERROR");
    }
    getLogs() {
      return this.logs;
    }
    clear() {
      this.logs = [];
    }
    addListener(listener) {
      this.listeners.push(listener);
    }
    removeListener(listener) {
      this.listeners = this.listeners.filter((l) => l !== listener);
    }
  };
  var logger = new ExtensionLogger();

  // src/storage/store.ts
  var DEFAULT_SERVER_URL = "ws://localhost:8000/ws/meeting";
  var getStoredServerUrl = async () => {
    return new Promise((resolve) => {
      if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.local) {
        resolve(DEFAULT_SERVER_URL);
        return;
      }
      chrome.storage.local.get(["serverUrl"], (result) => {
        resolve(result.serverUrl || DEFAULT_SERVER_URL);
      });
    });
  };
  var updateStoredState = async (state) => {
    return new Promise((resolve) => {
      if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.local) {
        resolve();
        return;
      }
      chrome.storage.local.set(state, () => {
        resolve();
      });
    });
  };

  // src/network/websocket.ts
  var WebSocketManager = class {
    constructor() {
      this.ws = null;
      this.url = "";
      this.isConnecting = false;
      this.reconnectTimeoutId = null;
      this.reconnectDelay = 1e3;
      // start with 1s
      this.maxReconnectDelay = 3e4;
      // max 30s
      this.heartbeatIntervalId = null;
      this.heartbeatTimeoutId = null;
      this.lastHeartbeatAck = Date.now();
      this.messageQueue = [];
      this.onStatusChangeCallback = null;
      this.activeMeetingId = null;
    }
    setMeetingId(meetingId) {
      this.activeMeetingId = meetingId;
    }
    onStatusChange(callback) {
      this.onStatusChangeCallback = callback;
    }
    async connect(url) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        logger.info("WebSocket already connected.");
        return;
      }
      if (this.isConnecting) {
        logger.info("WebSocket connection attempt already in progress.");
        return;
      }
      this.url = url;
      this.isConnecting = true;
      logger.info(`Connecting to WebSocket server: ${url}`);
      updateStoredState({ isServerConnected: false });
      if (this.reconnectTimeoutId) {
        clearTimeout(this.reconnectTimeoutId);
        this.reconnectTimeoutId = null;
      }
      try {
        this.ws = new WebSocket(url);
        this.ws.binaryType = "arraybuffer";
        this.ws.onopen = () => {
          this.isConnecting = false;
          this.reconnectDelay = 1e3;
          logger.info("WebSocket connection established successfully.");
          updateStoredState({ isServerConnected: true });
          if (this.onStatusChangeCallback) {
            this.onStatusChangeCallback(true);
          }
          this.startHeartbeat();
          this.flushQueue();
        };
        this.ws.onclose = (event) => {
          this.isConnecting = false;
          logger.warn(`WebSocket closed: Code ${event.code}, Reason: ${event.reason}`);
          this.handleDisconnect();
        };
        this.ws.onerror = (error) => {
          this.isConnecting = false;
          logger.error(`WebSocket error occurred.`);
        };
        this.ws.onmessage = (event) => {
          if (typeof event.data === "string") {
            try {
              const data = JSON.parse(event.data);
              if (data.type === "heartbeat" && data.status === "ack") {
                this.lastHeartbeatAck = Date.now();
                if (this.heartbeatTimeoutId) {
                  clearTimeout(this.heartbeatTimeoutId);
                  this.heartbeatTimeoutId = null;
                }
              }
            } catch (e) {
              logger.error(`Failed to parse text message from server: ${event.data}`);
            }
          }
        };
      } catch (e) {
        this.isConnecting = false;
        logger.error(`Failed to create WebSocket instance: ${e.message}`);
        this.handleDisconnect();
      }
    }
    disconnect() {
      logger.info("Manually disconnecting WebSocket.");
      if (this.reconnectTimeoutId) {
        clearTimeout(this.reconnectTimeoutId);
        this.reconnectTimeoutId = null;
      }
      this.stopHeartbeat();
      if (this.ws) {
        this.ws.onopen = null;
        this.ws.onclose = null;
        this.ws.onerror = null;
        this.ws.onmessage = null;
        if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
          this.ws.close();
        }
        this.ws = null;
      }
      updateStoredState({ isServerConnected: false });
      if (this.onStatusChangeCallback) {
        this.onStatusChangeCallback(false);
      }
    }
    isConnected() {
      return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }
    sendText(type, payload) {
      if (!this.activeMeetingId) {
        logger.warn(`Attempted to send text message of type ${type} but no active meeting ID is set.`);
        return;
      }
      const message = {
        type,
        timestamp: Date.now(),
        meeting_id: this.activeMeetingId,
        payload
      };
      if (this.isConnected()) {
        this.ws.send(JSON.stringify(message));
      } else {
        logger.info(`Socket disconnected. Queueing message of type ${type}.`);
        this.messageQueue.push(message);
      }
    }
    sendBinary(type, timestamp, chunkPayload) {
      if (!this.activeMeetingId) {
        logger.warn(`Attempted to send binary of type ${type} but no active meeting ID is set.`);
        return;
      }
      const packet = this.buildBinaryPacket(type, timestamp, this.activeMeetingId, chunkPayload);
      if (this.isConnected()) {
        this.ws.send(packet);
      } else {
        logger.warn(`Socket disconnected. Discarding ${type} binary chunk of size ${chunkPayload.byteLength} bytes.`);
      }
    }
    buildBinaryPacket(type, timestamp, meetingId, payload) {
      const headerJson = JSON.stringify({ type, timestamp, meeting_id: meetingId });
      const headerBytes = new TextEncoder().encode(headerJson);
      const headerLen = headerBytes.byteLength;
      const totalBuffer = new ArrayBuffer(4 + headerLen + payload.byteLength);
      const view = new DataView(totalBuffer);
      view.setUint32(0, headerLen, false);
      const uint8View = new Uint8Array(totalBuffer);
      uint8View.set(headerBytes, 4);
      uint8View.set(new Uint8Array(payload), 4 + headerLen);
      return totalBuffer;
    }
    handleDisconnect() {
      updateStoredState({ isServerConnected: false });
      if (this.onStatusChangeCallback) {
        this.onStatusChangeCallback(false);
      }
      this.stopHeartbeat();
      if (this.reconnectTimeoutId) return;
      logger.info(`Scheduling reconnection in ${this.reconnectDelay}ms...`);
      this.reconnectTimeoutId = setTimeout(() => {
        this.reconnectTimeoutId = null;
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
        this.connect(this.url);
      }, this.reconnectDelay);
    }
    startHeartbeat() {
      this.stopHeartbeat();
      this.lastHeartbeatAck = Date.now();
      this.heartbeatIntervalId = setInterval(() => {
        if (this.isConnected() && this.activeMeetingId) {
          const heartbeatMsg = JSON.stringify({
            type: "heartbeat",
            timestamp: Date.now(),
            meeting_id: this.activeMeetingId,
            payload: {}
          });
          try {
            this.ws.send(heartbeatMsg);
            this.heartbeatTimeoutId = setTimeout(() => {
              logger.error("Heartbeat timed out (no response in 3s). Reconnecting.");
              this.ws.close();
            }, 3e3);
          } catch (e) {
            logger.error("Failed to send heartbeat message.");
          }
        }
      }, 5e3);
    }
    stopHeartbeat() {
      if (this.heartbeatIntervalId) {
        clearInterval(this.heartbeatIntervalId);
        this.heartbeatIntervalId = null;
      }
      if (this.heartbeatTimeoutId) {
        clearTimeout(this.heartbeatTimeoutId);
        this.heartbeatTimeoutId = null;
      }
    }
    flushQueue() {
      if (this.messageQueue.length === 0) return;
      logger.info(`Flushing ${this.messageQueue.length} queued messages...`);
      while (this.messageQueue.length > 0 && this.isConnected()) {
        const msg = this.messageQueue.shift();
        if (msg) {
          if (msg instanceof ArrayBuffer) {
            this.ws.send(msg);
          } else {
            if (this.activeMeetingId) {
              msg.meeting_id = this.activeMeetingId;
            }
            this.ws.send(JSON.stringify(msg));
          }
        }
      }
    }
  };

  // src/background/background.ts
  var wsManager = new WebSocketManager();
  var meetTabId = null;
  var currentMeetingId = null;
  var currentMeetingUrl = null;
  var isMonitoring = false;
  function setMonitoringState(active) {
    isMonitoring = active;
    updateStoredState({ isMonitoring: active });
    logger.info(`Monitoring state changed: ${active ? "STARTED" : "STOPPED"}`);
  }
  function checkGoogleMeetTab(tab) {
    if (!tab || !tab.url || !tab.id) {
      updateStoredState({
        isMeetConnected: false,
        activeMeetingId: null,
        activeMeetingUrl: null
      });
      meetTabId = null;
      currentMeetingId = null;
      currentMeetingUrl = null;
      wsManager.setMeetingId(null);
      return;
    }
    const url = new URL(tab.url);
    const isMeet = url.hostname === "meet.google.com" && url.pathname.length > 1;
    if (isMeet) {
      const meetId = url.pathname.substring(1);
      meetTabId = tab.id;
      currentMeetingId = meetId;
      currentMeetingUrl = tab.url;
      wsManager.setMeetingId(meetId);
      updateStoredState({
        isMeetConnected: true,
        activeMeetingId: meetId,
        activeMeetingUrl: tab.url
      });
      logger.info(`Detected Google Meet tab active. Meeting ID: ${meetId}`);
    } else {
      if (isMonitoring && meetTabId === tab.id) {
        logger.warn("Active monitored Google Meet tab changed URL. Stopping monitoring.");
        stopMonitoring();
      }
      updateStoredState({
        isMeetConnected: false,
        activeMeetingId: null,
        activeMeetingUrl: null
      });
      meetTabId = null;
      currentMeetingId = null;
      currentMeetingUrl = null;
      wsManager.setMeetingId(null);
    }
  }
  chrome.tabs.onActivated.addListener((activeInfo) => {
    chrome.tabs.get(activeInfo.tabId, (tab) => {
      if (chrome.runtime.lastError) return;
      checkGoogleMeetTab(tab);
    });
  });
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" || changeInfo.url) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const activeTab = tabs[0];
        if (activeTab && activeTab.id === tabId) {
          checkGoogleMeetTab(activeTab);
        }
      });
    }
  });
  wsManager.onStatusChange((connected) => {
    if (!connected && isMonitoring) {
      logger.warn("WebSocket disconnected while monitoring. Capture remains active, chunks will be dropped.");
    }
  });
  async function ensureOffscreenDocument() {
    const hasDoc = await chrome.offscreen.hasDocument();
    if (hasDoc) return;
    logger.info("Creating offscreen document for media capture...");
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: [chrome.offscreen.Reason.USER_MEDIA],
      justification: "Capture tab audio and video for real-time streaming ingestion"
    });
  }
  async function closeOffscreenDocument() {
    const hasDoc = await chrome.offscreen.hasDocument();
    if (!hasDoc) return;
    logger.info("Closing offscreen document...");
    await chrome.offscreen.closeDocument();
  }
  async function startMonitoring() {
    if (isMonitoring) {
      logger.warn("Monitoring is already running.");
      return;
    }
    if (!wsManager.isConnected()) {
      logger.error("Cannot start monitoring: WebSocket is not connected.");
      throw new Error("Server not connected");
    }
    if (!currentMeetingId || !meetTabId) {
      logger.error("Cannot start monitoring: No active Google Meet tab detected.");
      throw new Error("Google Meet not connected");
    }
    try {
      logger.info(`Requesting tabCapture stream ID for tab ${meetTabId}`);
      const streamId = await new Promise((resolve, reject) => {
        chrome.tabCapture.getMediaStreamId(
          { targetTabId: meetTabId },
          (id) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else if (!id) {
              reject(new Error("Failed to get media stream ID"));
            } else {
              resolve(id);
            }
          }
        );
      });
      await ensureOffscreenDocument();
      logger.info("Sending stream token to offscreen document...");
      const response = await chrome.runtime.sendMessage({
        action: "start_capture",
        streamId
      });
      if (!response || !response.success) {
        throw new Error(response?.error || "Offscreen capture initialization failed");
      }
      setMonitoringState(true);
      wsManager.sendText("metadata", {
        action: "init",
        meeting_id: currentMeetingId,
        url: currentMeetingUrl,
        started_at: Date.now()
      });
    } catch (err) {
      logger.error(`Failed to start monitoring: ${err.message}`);
      await closeOffscreenDocument();
      throw err;
    }
  }
  async function stopMonitoring() {
    if (!isMonitoring) return;
    try {
      logger.info("Stopping monitoring...");
      await chrome.runtime.sendMessage({ action: "stop_capture" }).catch(() => {
      });
      await closeOffscreenDocument();
    } catch (e) {
    }
    setMonitoringState(false);
    if (wsManager.isConnected() && currentMeetingId) {
      wsManager.sendText("metadata", {
        action: "stop",
        meeting_id: currentMeetingId,
        stopped_at: Date.now()
      });
    }
  }
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "OFFSCREEN_LOG") {
      logger.log(message.message, message.level);
      return;
    }
    if (message.type === "CAPTURE_ENDED_EVENT") {
      logger.warn("Tab capture stream ended unexpectedly. Stopping monitoring.");
      stopMonitoring();
      return;
    }
    if (message.type === "AUDIO_CHUNK") {
      if (isMonitoring) {
        wsManager.sendBinary("audio", message.timestamp, message.data);
      }
      return;
    }
    if (message.type === "VIDEO_CHUNK") {
      if (isMonitoring) {
        wsManager.sendBinary("video", message.timestamp, message.data);
      }
      return;
    }
    if (message.type === "MEET_DOM_EVENT") {
      if (isMonitoring) {
        wsManager.sendText("event", message.payload);
        if (message.payload.type === "participants_list") {
          updateStoredState({ participantCount: message.payload.count });
        }
      }
      return;
    }
    if (message.action === "connect_ws") {
      getStoredServerUrl().then((url) => {
        wsManager.connect(url).then(() => sendResponse({ success: true })).catch((err) => sendResponse({ success: false, error: err.message }));
      });
      return true;
    }
    if (message.action === "disconnect_ws") {
      if (isMonitoring) {
        stopMonitoring().then(() => {
          wsManager.disconnect();
          sendResponse({ success: true });
        });
      } else {
        wsManager.disconnect();
        sendResponse({ success: true });
      }
      return true;
    }
    if (message.action === "start_monitoring") {
      startMonitoring().then(() => sendResponse({ success: true })).catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }
    if (message.action === "stop_monitoring") {
      stopMonitoring().then(() => sendResponse({ success: true })).catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }
    if (message.action === "get_logs") {
      sendResponse({ logs: logger.getLogs() });
    }
  });
  logger.info("Sherlock AI Extension Background worker initialized.");
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      checkGoogleMeetTab(tabs[0]);
    }
  });
})();
