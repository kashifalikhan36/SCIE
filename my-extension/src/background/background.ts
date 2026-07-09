import { logger } from "../utils/logger";
import { WebSocketManager } from "../network/websocket";
import { getStoredServerUrl, updateStoredState } from "../storage/store";

const wsManager = new WebSocketManager();

// Keep track of the active Google Meet tab
let meetTabId: number | null = null;
let currentMeetingId: string | null = null;
let currentMeetingUrl: string | null = null;
let isMonitoring = false;

// Update storage state and send log
function setMonitoringState(active: boolean) {
  isMonitoring = active;
  updateStoredState({ isMonitoring: active });
  logger.info(`Monitoring state changed: ${active ? "STARTED" : "STOPPED"}`);
}

// Check if tab is a Google Meet meeting
function checkGoogleMeetTab(tab: chrome.tabs.Tab | undefined) {
  if (!tab || !tab.url || !tab.id) {
    updateStoredState({
      isMeetConnected: false,
      activeMeetingId: null,
      activeMeetingUrl: null,
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
    // Extract meeting ID (e.g. abc-defg-hij)
    const meetId = url.pathname.substring(1);
    meetTabId = tab.id;
    currentMeetingId = meetId;
    currentMeetingUrl = tab.url;
    wsManager.setMeetingId(meetId);
    
    updateStoredState({
      isMeetConnected: true,
      activeMeetingId: meetId,
      activeMeetingUrl: tab.url,
    });
    logger.info(`Detected Google Meet tab active. Meeting ID: ${meetId}`);
  } else {
    // If we were monitoring and the user moved away, we should stop monitoring or alert
    if (isMonitoring && meetTabId === tab.id) {
      logger.warn("Active monitored Google Meet tab changed URL. Stopping monitoring.");
      stopMonitoring();
    }
    
    updateStoredState({
      isMeetConnected: false,
      activeMeetingId: null,
      activeMeetingUrl: null,
    });
    meetTabId = null;
    currentMeetingId = null;
    currentMeetingUrl = null;
    wsManager.setMeetingId(null);
  }
}

// Monitor active tab changes
chrome.tabs.onActivated.addListener((activeInfo) => {
  chrome.tabs.get(activeInfo.tabId, (tab) => {
    // Ignore error if tab is closed rapidly
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

// Websocket Status Change handler
wsManager.onStatusChange((connected) => {
  updateStoredState({ isServerConnected: connected });
  if (!connected && isMonitoring) {
    logger.warn("WebSocket disconnected while monitoring. Capture remains active, chunks will be dropped.");
  }
});

// Offscreen helper
async function ensureOffscreenDocument() {
  const hasDoc = await chrome.offscreen.hasDocument();
  if (hasDoc) return;
  
  logger.info("Creating offscreen document for media capture...");
  await chrome.offscreen.createDocument({
    url: "offscreen.html",
    reasons: [chrome.offscreen.Reason.USER_MEDIA],
    justification: "Capture tab audio and video for real-time streaming ingestion",
  });
}

async function closeOffscreenDocument() {
  const hasDoc = await chrome.offscreen.hasDocument();
  if (!hasDoc) return;
  
  logger.info("Closing offscreen document...");
  await chrome.offscreen.closeDocument();
}

// Start tab capture process
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
    
    // Get the stream token for the target tab
    const streamId = await new Promise<string>((resolve, reject) => {
      chrome.tabCapture.getMediaStreamId(
        { targetTabId: meetTabId! },
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
    
    // Send the stream token to the offscreen document
    logger.info("Sending stream token to offscreen document...");
    const response = await chrome.runtime.sendMessage({
      action: "start_capture",
      streamId,
    });

    if (!response || !response.success) {
      throw new Error(response?.error || "Offscreen capture initialization failed");
    }

    setMonitoringState(true);
    
    // Send meeting metadata init event
    wsManager.sendText("metadata", {
      action: "init",
      meeting_id: currentMeetingId,
      url: currentMeetingUrl,
      started_at: Date.now(),
    });

  } catch (err: any) {
    logger.error(`Failed to start monitoring: ${err.message}`);
    await closeOffscreenDocument();
    throw err;
  }
}

async function stopMonitoring() {
  if (!isMonitoring) return;
  
  try {
    logger.info("Stopping monitoring...");
    await chrome.runtime.sendMessage({ action: "stop_capture" }).catch(() => {});
    await closeOffscreenDocument();
  } catch (e) {}

  setMonitoringState(false);

  if (wsManager.isConnected() && currentMeetingId) {
    wsManager.sendText("metadata", {
      action: "stop",
      meeting_id: currentMeetingId,
      stopped_at: Date.now(),
    });
  }
}

// Receive messages from content script, offscreen page, and popup UI
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Handle log events from offscreen
  if (message.type === "OFFSCREEN_LOG") {
    logger.log(message.message, message.level);
    return;
  }

  // Handle capture ended event (e.g. if the tab is closed)
  if (message.type === "CAPTURE_ENDED_EVENT") {
    logger.warn("Tab capture stream ended unexpectedly. Stopping monitoring.");
    stopMonitoring();
    return;
  }

  // Handle media chunks from offscreen page
  // data arrives as number[] (Array.from(Uint8Array)) since Chrome cannot serialize raw ArrayBuffer
  if (message.type === "AUDIO_CHUNK") {
    if (isMonitoring && message.data) {
      const arrayBuffer = new Uint8Array(message.data).buffer;
      wsManager.sendBinary("audio", message.timestamp, arrayBuffer);
    }
    return;
  }

  if (message.type === "VIDEO_CHUNK") {
    if (isMonitoring && message.data) {
      const arrayBuffer = new Uint8Array(message.data).buffer;
      wsManager.sendBinary("video", message.timestamp, arrayBuffer);
    }
    return;
  }

  // Handle DOM events from Google Meet content script
  if (message.type === "MEET_DOM_EVENT") {
    // Always update participant count from DOM scan (even before monitoring starts)
    if (message.payload.type === "participants_list") {
      updateStoredState({ participantCount: message.payload.count });
    }
    if (isMonitoring) {
      wsManager.sendText("event", message.payload);
      if (message.payload.type === "participants_list") {
        // already updated above
      }
    }
    return;
  }

  // Handle action requests from Popup UI
  // connect_server is sent by the popup UI
  if (message.action === "connect_server" || message.action === "connect_ws") {
    const connectUrl = message.url || null;
    const doConnect = (url: string) => {
      wsManager.connect(url)
        .then(() => {
          updateStoredState({ isServerConnected: true });
          sendResponse({ success: true });
        })
        .catch((err) => {
          updateStoredState({ isServerConnected: false });
          sendResponse({ success: false, error: err.message });
        });
    };
    if (connectUrl) {
      doConnect(connectUrl);
    } else {
      getStoredServerUrl().then(doConnect);
    }
    return true; // async
  }

  // disconnect_server is sent by the popup UI
  if (message.action === "disconnect_server" || message.action === "disconnect_ws") {
    if (isMonitoring) {
      stopMonitoring().then(() => {
        wsManager.disconnect();
        updateStoredState({ isServerConnected: false });
        sendResponse({ success: true });
      });
    } else {
      wsManager.disconnect();
      updateStoredState({ isServerConnected: false });
      sendResponse({ success: true });
    }
    return true; // async
  }

  if (message.action === "start_monitoring") {
    startMonitoring()
      .then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // async
  }

  if (message.action === "stop_monitoring") {
    stopMonitoring()
      .then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // async
  }

  if (message.action === "get_logs") {
    sendResponse({ logs: logger.getLogs() });
  }
});

// Initialize on startup
logger.info("SCIE Extension Background worker initialized.");
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (tabs[0]) {
    checkGoogleMeetTab(tabs[0]);
  }
});
