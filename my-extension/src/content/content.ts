interface ParticipantState {
  id: string;
  name: string;
  isMuted: boolean;
  isCameraOn: boolean;
  isSpeaking: boolean;
  isScreenSharing: boolean;
}

let lastParticipants: Map<string, ParticipantState> = new Map();
let scanTimeoutId: any = null;
let lastScanTime = 0;

// Setup MutationObserver to watch Google Meet DOM changes
const observer = new MutationObserver(() => {
  const now = Date.now();
  if (now - lastScanTime > 1000) {
    scanMeetDOM();
  } else {
    if (scanTimeoutId) clearTimeout(scanTimeoutId);
    scanTimeoutId = setTimeout(scanMeetDOM, 1000 - (now - lastScanTime));
  }
});

if (document.readyState === "complete" || document.readyState === "interactive") {
  initObserver();
  initMicCapture();
} else {
  window.addEventListener("DOMContentLoaded", () => {
    initObserver();
    initMicCapture();
  });
}

function initObserver() {
  console.log("[SCIE Content Script] Injected and initializing DOM observer.");
  
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "style", "aria-label", "data-is-muted", "src"],
  });

  // Periodic fallback scan every 5 seconds
  setInterval(scanMeetDOM, 5000);
  scanMeetDOM();
}

// ── Microphone Capture ──────────────────────────────────────────────────
// The content script runs inside the Google Meet tab and CAN access
// getUserMedia for the microphone. The offscreen document cannot.
// We capture 500ms WebM/Opus chunks and forward them to the background
// script, which sends them to the backend WebSocket as MIC_AUDIO_CHUNK.
let micRecorder: MediaRecorder | null = null;
let micInitSegment: Uint8Array | null = null;

function makeMicStandaloneChunk(raw: Uint8Array): Uint8Array {
  if (!micInitSegment) {
    micInitSegment = raw;
    return raw;
  }
  const combined = new Uint8Array(micInitSegment.length + raw.length);
  combined.set(micInitSegment, 0);
  combined.set(raw, micInitSegment.length);
  return combined;
}

async function initMicCapture() {
  try {
    const micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    console.log("[SCIE Content Script] Microphone access granted.");

    let mime = "audio/webm;codecs=opus";
    if (!MediaRecorder.isTypeSupported(mime)) {
      mime = "audio/webm";
    }

    micRecorder = new MediaRecorder(micStream, { mimeType: mime });

    micRecorder.ondataavailable = async (event) => {
      if (event.data && event.data.size > 0) {
        try {
          const buffer = await event.data.arrayBuffer();
          const raw = new Uint8Array(buffer);
          const standalone = makeMicStandaloneChunk(raw);
          const byteArray = Array.from(standalone);
          chrome.runtime.sendMessage({
            type: "MIC_AUDIO_CHUNK",
            timestamp: Date.now(),
            data: byteArray,
          }).catch(() => {});
        } catch (err: any) {
          console.error("[SCIE Content Script] Mic chunk error:", err);
        }
      }
    };

    micRecorder.start(500); // 500ms chunks, same as tab audio
    console.log("[SCIE Content Script] Microphone recording started (500ms chunks).");
  } catch (err: any) {
    console.warn("[SCIE Content Script] Microphone access denied or unavailable:", err.message);
  }
}

/**
 * Primary DOM scraping strategy: Google Meet renders each participant in 
 * a container element. The most reliable signal is the participant's name
 * label rendered below or inside each video tile.
 *
 * We use multiple layered strategies and deduplicate by participant ID.
 */
function scanMeetDOM() {
  lastScanTime = Date.now();
  if (scanTimeoutId) {
    clearTimeout(scanTimeoutId);
    scanTimeoutId = null;
  }

  const currentParticipants = new Map<string, ParticipantState>();
  
  // Determine local user name from Google Meet's self-name attribute
  const selfNameEl = document.querySelector("[data-self-name]");
  const selfName = selfNameEl?.textContent?.trim() || "";

  // ─────────────────────────────────────────────────────────────────
  // Strategy 1: Read name labels rendered directly in participant tiles.
  // Google Meet renders a text label element with the participant name
  // inside the video grid tile. We look for all visible text spans that
  // contain a participant's display name (those inside tiles but NOT
  // inside the top toolbar, chat panel, or reactions).
  // ─────────────────────────────────────────────────────────────────
  
  // Try multiple known selector patterns for participant name labels.
  // These can change across Google Meet updates, so we try several.
  const nameLabelSelectors = [
    // Data attributes (most reliable)
    "[data-participant-id] [data-self-name]",
    "[data-participant-id]",
    // Class-based patterns observed in various GM versions
    ".NsNELd",
    ".XEazBc",
    ".cS4QAe",
    ".zWGUib",
    // ARIA patterns
    "[jsname='XpIydf']",
    "[jsname='r4nke']",
  ];

  // Collect all participant-containing tiles
  const participantContainers: Element[] = [];
  
  // Try [data-participant-id] first — most reliable
  const participantEls = document.querySelectorAll("[data-participant-id]");
  participantEls.forEach(el => {
    // Ignore hidden elements (closed sidebar/panel)
    if ((el as HTMLElement).offsetParent !== null || el.closest("[aria-hidden='false']")) {
      participantContainers.push(el);
    }
  });

  participantContainers.forEach((container) => {
    const participantId = container.getAttribute("data-participant-id") || "";
    
    // Extract name from name element inside this tile
    let name = "";
    // Try multiple name extraction points
    const nameEl = 
      container.querySelector("[data-self-name]") ||
      container.querySelector(".NsNELd") ||
      container.querySelector(".XEazBc") ||
      container.querySelector(".cS4QAe") ||
      container.querySelector(".zWGUib") ||
      container.querySelector("[jsname='XpIydf']");
    
    if (nameEl?.textContent) {
      name = nameEl.textContent.trim();
    }
    
    // If still not found, try aria-label on the container
    if (!name) {
      const ariaLabel = container.getAttribute("aria-label") || "";
      if (ariaLabel && ariaLabel.length < 60) {
        // aria-label often contains "Name's camera is off" etc. Extract just the name.
        name = ariaLabel.split("'")[0].split(",")[0].trim();
      }
    }

    if (!name || name.length === 0 || name.length > 60) return;

    // Determine mic/camera state
    const isMuted = !!(
      container.querySelector("[data-is-muted='true']") ||
      container.querySelector("[aria-label*='muted']") ||
      container.querySelector("[aria-label*='Muted']")
    );

    const videoEl = container.querySelector("video");
    const isCameraOn = !!(videoEl && videoEl.readyState >= 2 && !videoEl.paused);

    const isSpeaking = !!(
      container.querySelector("[data-is-speaking='true']") ||
      container.querySelector(".speaking")
    );

    const isScreenSharing = !!(
      container.querySelector("[data-is-presentation='true']") ||
      container.querySelector("[aria-label*='presentation']") ||
      container.querySelector("[aria-label*='screen']")
    );

    // Normalize ID — self-participant gets unified ID "you"
    let id = participantId || name.replace(/\s+/g, "_").toLowerCase();
    if (name === selfName || selfName && name.startsWith(selfName)) {
      id = "you";
      name = selfName || name;
    }

    currentParticipants.set(id, { id, name, isMuted, isCameraOn, isSpeaking, isScreenSharing });
  });

  // ─────────────────────────────────────────────────────────────────
  // Strategy 2: Participant panel sidebar (when opened)
  // ─────────────────────────────────────────────────────────────────
  const panelNameEls = document.querySelectorAll("[data-participant-id] span[jsname], .rua5Nb");
  panelNameEls.forEach((el) => {
    if ((el as HTMLElement).offsetParent === null) return;
    const name = el.textContent?.trim() || "";
    if (!name || name.length === 0 || name.length > 60) return;

    let id = name.replace(/\s+/g, "_").toLowerCase();
    if (name === selfName || (selfName && name.startsWith(selfName))) {
      id = "you";
    }

    if (!currentParticipants.has(id)) {
      currentParticipants.set(id, {
        id,
        name: id === "you" ? (selfName || name) : name,
        isMuted: true,
        isCameraOn: false,
        isSpeaking: false,
        isScreenSharing: false,
      });
    }
  });

  // ─────────────────────────────────────────────────────────────────
  // Strategy 3: Fallback — count video elements as minimum participant proxy
  // This ensures at least a non-zero count even if DOM selectors change.
  // Each active video element = 1 participant.
  // ─────────────────────────────────────────────────────────────────
  if (currentParticipants.size === 0) {
    const videos = document.querySelectorAll("video");
    let videoCount = 0;
    videos.forEach((v) => {
      if (v.readyState >= 2 || v.videoWidth > 0) {
        videoCount++;
      }
    });
    
    if (videoCount > 0) {
      // Minimum fallback: create placeholder participants based on video count
      for (let i = 0; i < videoCount; i++) {
        const placeholderId = i === 0 ? "you" : `participant_${i}`;
        const placeholderName = i === 0 ? (selfName || "You") : `Participant ${i + 1}`;
        currentParticipants.set(placeholderId, {
          id: placeholderId,
          name: placeholderName,
          isMuted: true,
          isCameraOn: true,
          isSpeaking: false,
          isScreenSharing: false,
        });
      }
    }
  }

  // Compare and emit delta events
  generateEvents(lastParticipants, currentParticipants);
  lastParticipants = currentParticipants;

  // Send full participant list to background (for participant count display)
  const listEvent = {
    type: "participants_list",
    timestamp: Date.now(),
    count: currentParticipants.size,
    participants: Array.from(currentParticipants.values()).map(p => ({
      id: p.id,
      display_name: p.name,
      camera: p.isCameraOn ? "on" : "off",
      mic: p.isMuted ? "off" : "on",
      screen_share: p.isScreenSharing ? "on" : "off",
      is_speaking: p.isSpeaking
    }))
  };

  chrome.runtime.sendMessage({
    type: "MEET_DOM_EVENT",
    payload: listEvent,
  }).catch(() => {});
}

function generateEvents(prev: Map<string, ParticipantState>, curr: Map<string, ParticipantState>) {
  const timestamp = Date.now();

  curr.forEach((currP, id) => {
    const prevP = prev.get(id);

    if (!prevP) {
      emitMeetEvent({
        type: "participant_join",
        timestamp,
        participant_id: currP.id,
        display_name: currP.name,
        camera: currP.isCameraOn ? "on" : "off",
        mic: currP.isMuted ? "off" : "on",
        screen_share: currP.isScreenSharing ? "on" : "off",
      });
    } else {
      if (currP.isCameraOn !== prevP.isCameraOn) {
        emitMeetEvent({ type: currP.isCameraOn ? "camera_on" : "camera_off", timestamp, participant_id: currP.id, display_name: currP.name });
      }
      if (currP.isMuted !== prevP.isMuted) {
        emitMeetEvent({ type: currP.isMuted ? "mic_off" : "mic_on", timestamp, participant_id: currP.id, display_name: currP.name });
      }
      if (currP.isScreenSharing !== prevP.isScreenSharing) {
        emitMeetEvent({ type: "screen_share", timestamp, participant_id: currP.id, display_name: currP.name, state: currP.isScreenSharing ? "on" : "off" });
      }
      if (currP.isSpeaking && !prevP.isSpeaking) {
        emitMeetEvent({ type: "speaker_active", timestamp, participant_id: currP.id, display_name: currP.name });
      }
    }
  });

  prev.forEach((prevP, id) => {
    if (!curr.has(id)) {
      emitMeetEvent({ type: "participant_leave", timestamp, participant_id: prevP.id, display_name: prevP.name });
    }
  });
}

function emitMeetEvent(payload: any) {
  chrome.runtime.sendMessage({
    type: "MEET_DOM_EVENT",
    payload,
  }).catch(() => {});
}
