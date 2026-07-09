const DEFAULT_SERVER_URL = "ws://localhost:8000/ws/meeting";

export interface ExtensionState {
  serverUrl: string;
  isServerConnected: boolean;
  isMeetConnected: boolean;
  isMonitoring: boolean;
  activeMeetingId: string | null;
  activeMeetingUrl: string | null;
  participantCount: number;
}

export const getStoredServerUrl = async (): Promise<string> => {
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

export const setStoredServerUrl = async (url: string): Promise<void> => {
  return new Promise((resolve) => {
    if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.local) {
      resolve();
      return;
    }
    chrome.storage.local.set({ serverUrl: url }, () => {
      resolve();
    });
  });
};

export const getStoredState = async (): Promise<Partial<ExtensionState>> => {
  return new Promise((resolve) => {
    if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.local) {
      resolve({});
      return;
    }
    chrome.storage.local.get([
      "isServerConnected",
      "isMeetConnected",
      "isMonitoring",
      "activeMeetingId",
      "activeMeetingUrl",
      "participantCount"
    ], (result) => {
      resolve(result);
    });
  });
};

export const updateStoredState = async (state: Partial<ExtensionState>): Promise<void> => {
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
