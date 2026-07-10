import { logger } from "../utils/logger";
import { updateStoredState } from "../storage/store";

export type MessageType = "event" | "metadata" | "audio" | "mic_audio" | "video" | "heartbeat";

export interface TextMessage {
  type: MessageType;
  timestamp: number;
  meeting_id: string;
  payload: any;
}

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string = "";
  private isConnecting = false;
  private reconnectTimeoutId: any = null;
  private reconnectDelay = 1000; // start with 1s
  private readonly maxReconnectDelay = 30000; // max 30s
  private heartbeatIntervalId: any = null;
  private heartbeatTimeoutId: any = null;
  private lastHeartbeatAck = Date.now();
  private messageQueue: (TextMessage | ArrayBuffer)[] = [];
  private onStatusChangeCallback: ((connected: boolean) => void) | null = null;
  private activeMeetingId: string | null = null;

  constructor() {}

  setMeetingId(meetingId: string | null) {
    this.activeMeetingId = meetingId;
  }

  onStatusChange(callback: (connected: boolean) => void) {
    this.onStatusChangeCallback = callback;
  }

  async connect(url: string): Promise<void> {
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

    return new Promise<void>((resolve, reject) => {
      try {
        this.ws = new WebSocket(url);
        this.ws.binaryType = "arraybuffer";

        this.ws.onopen = () => {
          this.isConnecting = false;
          this.reconnectDelay = 1000; // reset backoff
          logger.info("WebSocket connection established successfully.");
          updateStoredState({ isServerConnected: true });
          if (this.onStatusChangeCallback) {
            this.onStatusChangeCallback(true);
          }
          this.startHeartbeat();
          this.flushQueue();
          resolve(); // ✅ resolve AFTER connection is confirmed open
        };

        this.ws.onclose = (event) => {
          if (this.isConnecting) {
            // Still in connecting phase — reject the promise
            this.isConnecting = false;
            reject(new Error(`WebSocket closed before connecting: Code ${event.code}`));
          } else {
            logger.warn(`WebSocket closed: Code ${event.code}, Reason: ${event.reason}`);
          }
          this.handleDisconnect();
        };

        this.ws.onerror = (error) => {
          this.isConnecting = false;
          logger.error(`WebSocket error occurred.`);
          reject(new Error("WebSocket connection failed. Check that the backend is running."));
          // Note: Close event will follow error event, handling reconnect there
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

      } catch (e: any) {
        this.isConnecting = false;
        logger.error(`Failed to create WebSocket instance: ${e.message}`);
        this.handleDisconnect();
        reject(e);
      }
    });
  }

  disconnect() {
    logger.info("Manually disconnecting WebSocket.");
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
    this.stopHeartbeat();
    if (this.ws) {
      // Clear handlers to avoid trigger reconnection on manual disconnect
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

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  sendText(type: MessageType, payload: any) {
    if (!this.activeMeetingId) {
      logger.warn(`Attempted to send text message of type ${type} but no active meeting ID is set.`);
      return;
    }

    const message: TextMessage = {
      type,
      timestamp: Date.now(),
      meeting_id: this.activeMeetingId,
      payload,
    };

    if (this.isConnected()) {
      this.ws!.send(JSON.stringify(message));
    } else {
      logger.info(`Socket disconnected. Queueing message of type ${type}.`);
      this.messageQueue.push(message);
    }
  }

  sendBinary(type: "audio" | "mic_audio" | "video", timestamp: number, chunkPayload: ArrayBuffer) {
    if (!this.activeMeetingId) {
      logger.warn(`Attempted to send binary of type ${type} but no active meeting ID is set.`);
      return;
    }

    const packet = this.buildBinaryPacket(type, timestamp, this.activeMeetingId, chunkPayload);

    if (this.isConnected()) {
      this.ws!.send(packet);
    } else {
      // Discard binary data if disconnected to avoid blowing up memory queues
      // Audio and video streams are high-throughput and should be real-time
      logger.warn(`Socket disconnected. Discarding ${type} binary chunk of size ${chunkPayload.byteLength} bytes.`);
    }
  }

  private buildBinaryPacket(type: "audio" | "mic_audio" | "video", timestamp: number, meetingId: string, payload: ArrayBuffer): ArrayBuffer {
    const headerJson = JSON.stringify({ type, timestamp, meeting_id: meetingId });
    const headerBytes = new TextEncoder().encode(headerJson);
    const headerLen = headerBytes.byteLength;

    const totalBuffer = new ArrayBuffer(4 + headerLen + payload.byteLength);
    const view = new DataView(totalBuffer);

    // Write header length in big-endian (4 bytes)
    view.setUint32(0, headerLen, false);

    // Write header string
    const uint8View = new Uint8Array(totalBuffer);
    uint8View.set(headerBytes, 4);

    // Write raw binary payload
    uint8View.set(new Uint8Array(payload), 4 + headerLen);

    return totalBuffer;
  }

  private handleDisconnect() {
    updateStoredState({ isServerConnected: false });
    if (this.onStatusChangeCallback) {
      this.onStatusChangeCallback(false);
    }
    this.stopHeartbeat();

    if (this.reconnectTimeoutId) return;

    logger.info(`Scheduling reconnection in ${this.reconnectDelay}ms...`);
    this.reconnectTimeoutId = setTimeout(() => {
      this.reconnectTimeoutId = null;
      // Exponential backoff
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      this.connect(this.url);
    }, this.reconnectDelay);
  }

  private startHeartbeat() {
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
          this.ws!.send(heartbeatMsg);
          
          // Set safety timeout for heartbeat response
          this.heartbeatTimeoutId = setTimeout(() => {
            logger.error("Heartbeat timed out (no response in 3s). Reconnecting.");
            this.ws!.close(); // forces close event and reconnection
          }, 3000);
        } catch (e) {
          logger.error("Failed to send heartbeat message.");
        }
      }
    }, 5000); // every 5s
  }

  private stopHeartbeat() {
    if (this.heartbeatIntervalId) {
      clearInterval(this.heartbeatIntervalId);
      this.heartbeatIntervalId = null;
    }
    if (this.heartbeatTimeoutId) {
      clearTimeout(this.heartbeatTimeoutId);
      this.heartbeatTimeoutId = null;
    }
  }

  private flushQueue() {
    if (this.messageQueue.length === 0) return;
    logger.info(`Flushing ${this.messageQueue.length} queued messages...`);
    while (this.messageQueue.length > 0 && this.isConnected()) {
      const msg = this.messageQueue.shift();
      if (msg) {
        if (msg instanceof ArrayBuffer) {
          this.ws!.send(msg);
        } else {
          // Re-inject current active meeting ID just in case
          if (this.activeMeetingId) {
            msg.meeting_id = this.activeMeetingId;
          }
          this.ws!.send(JSON.stringify(msg));
        }
      }
    }
  }
}
