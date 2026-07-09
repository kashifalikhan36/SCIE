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
const observer = new MutationObserver((mutations) => {
  // Throttle scanning to max once per second on DOM mutations
  const now = Date.now();
  if (now - lastScanTime > 1000) {
    scanMeetDOM();
  } else {
    if (scanTimeoutId) clearTimeout(scanTimeoutId);
    scanTimeoutId = setTimeout(scanMeetDOM, 1000 - (now - lastScanTime));
  }
});

// Run once DOM is ready
if (document.readyState === "complete" || document.readyState === "interactive") {
  initObserver();
} else {
  window.addEventListener("DOMContentLoaded", initObserver);
}

function initObserver() {
  console.log("[SCIE Content Script] Injected and initializing DOM observer.");
  
  // Watch the entire document body for mutations
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "style", "aria-label", "data-is-muted", "src"],
  });

  // Also scan periodically every 3 seconds to guarantee updates
  setInterval(scanMeetDOM, 3000);
  scanMeetDOM();
}

function scanMeetDOM() {
  lastScanTime = Date.now();
  if (scanTimeoutId) {
    clearTimeout(scanTimeoutId);
    scanTimeoutId = null;
  }

  const currentParticipants = new Map<string, ParticipantState>();
  const selfNameEl = document.querySelector("[data-self-name]");
  const selfName = selfNameEl?.textContent?.trim() || "You";

  // Heuristic 1: Scan grid tiles
  // In Google Meet, each participant tile has a container. We can search for video elements
  // and traverse up to find their tile card, name element, mic icons, etc.
  const videoElements = document.querySelectorAll("video");
  
  videoElements.forEach((video) => {
    // Find closest container that resembles a tile
    let container = video.parentElement;
    let name = "Unknown Participant";
    let isMuted = true;
    let isCameraOn = video.readyState === 4 && !video.paused; // playing video
    let isSpeaking = false;
    let isScreenSharing = false;

    // Traverse up to find a container with a name label or attributes
    let depth = 0;
    while (container && depth < 8) {
      // Look for name text (Google Meet name labels usually have a specific layout)
      // Check for elements with name tags or attributes
      const nameEl = container.querySelector("[data-self-name], [data-name], .ytU30d, .zWDL5");
      if (nameEl && nameEl.textContent) {
        name = nameEl.textContent.trim();
      }

      // Check if this container is screen sharing
      // Usually Google Meet adds a screen icon or label "presentation" or "screen share"
      const screenEl = container.querySelector("[data-is-presentation='true'], [data-screen-share='true']");
      if (screenEl || name.toLowerCase().includes("presentation") || name.toLowerCase().includes("screen share")) {
        isScreenSharing = true;
      }

      // Check if speaking (elements with wave animation or specific border colors)
      const speakingEl = container.querySelector(".I9AFdf, .VfPpkd-Bz112c-LgbsSe, [data-is-speaking='true']");
      if (speakingEl || container.classList.contains("speaking")) {
        isSpeaking = true;
      }

      // Check if muted
      const micEl = container.querySelector("[data-is-muted], .GvcuGe, .Qv2eCc");
      if (micEl) {
        const isMutedAttr = micEl.getAttribute("data-is-muted");
        if (isMutedAttr !== null) {
          isMuted = isMutedAttr === "true";
        } else {
          // Fallback check: look at mic icon paths or titles
          const label = micEl.getAttribute("aria-label") || micEl.getAttribute("title") || "";
          isMuted = label.toLowerCase().includes("muted") || label.toLowerCase().includes("off");
        }
      }

      container = container.parentElement;
      depth++;
    }

    if (name && name !== "Unknown Participant") {
      // Use clean string as ID or name as fallback ID
      let id = name.replace(/\s+/g, "_").toLowerCase();
      if (id === "you" || name === selfName) {
        id = "you";
      }
      
      currentParticipants.set(id, {
        id,
        name: id === "you" ? selfName : name,
        isMuted,
        isCameraOn,
        isSpeaking,
        isScreenSharing,
      });
    }
  });

  // Heuristic 2: Scan active participant panel if open
  // Google Meet renders a sidebar of participants when panel is toggled.
  const panelParticipants = document.querySelectorAll("[data-participant-id], .KV5Zae, .XW3o0e");
  panelParticipants.forEach((el) => {
    // Only process visible elements (avoid hidden panel rows from closed sidebar)
    if ((el as HTMLElement).offsetParent === null) {
      return;
    }

    let name = "";
    const nameEl = el.querySelector(".focus-target, .Z32Bgc, .cS4QAe") || el.querySelector("span");
    if (nameEl && nameEl.textContent) {
      name = nameEl.textContent.trim();
    }

    if (
      name && 
      name.length > 0 && 
      !name.includes("Add people") && 
      !name.includes("Mute all") &&
      name.length < 50
    ) {
      let id = name.replace(/\s+/g, "_").toLowerCase();
      if (id === "you" || name === selfName) {
        id = "you";
      }
      
      if (!currentParticipants.has(id)) {
        // If not found in video grid, add from list
        let isMuted = true;
        const micEl = el.querySelector("[data-is-muted]");
        if (micEl) {
          isMuted = micEl.getAttribute("data-is-muted") === "true";
        }

        currentParticipants.set(id, {
          id,
          name: id === "you" ? selfName : name,
          isMuted,
          isCameraOn: false, // Assume off if not in grid with active video
          isSpeaking: false,
          isScreenSharing: false,
        });
      }
    }
  });

  // Heuristic 3: Always add "You" (the local user)
  // Google Meet always has a self-video preview or self label
  const selfVideo = document.querySelector("video[mirror='true']");
  const selfId = "you";
  
  if (!currentParticipants.has(selfId)) {
    const isMuted = document.querySelector("[data-is-muted='true']") !== null;
    const isCameraOn = selfVideo !== null;
    
    currentParticipants.set(selfId, {
      id: selfId,
      name: selfName,
      isMuted,
      isCameraOn,
      isSpeaking: false,
      isScreenSharing: false,
    });
  }

  // Compare previous states with current states to emit delta events
  generateEvents(lastParticipants, currentParticipants);

  // Store current state
  lastParticipants = currentParticipants;

  // Send full participant list to background (for tracking participantCount and sync)
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

  // 1. Detect Joins and changes
  curr.forEach((currP, id) => {
    const prevP = prev.get(id);

    if (!prevP) {
      // Participant Join
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
      // Camera changed
      if (currP.isCameraOn !== prevP.isCameraOn) {
        emitMeetEvent({
          type: currP.isCameraOn ? "camera_on" : "camera_off",
          timestamp,
          participant_id: currP.id,
          display_name: currP.name,
        });
      }
      // Mic changed
      if (currP.isMuted !== prevP.isMuted) {
        emitMeetEvent({
          type: currP.isMuted ? "mic_off" : "mic_on",
          timestamp,
          participant_id: currP.id,
          display_name: currP.name,
        });
      }
      // Screen share changed
      if (currP.isScreenSharing !== prevP.isScreenSharing) {
        emitMeetEvent({
          type: "screen_share",
          timestamp,
          participant_id: currP.id,
          display_name: currP.name,
          state: currP.isScreenSharing ? "on" : "off",
        });
      }
      // Speaking changed
      if (currP.isSpeaking !== prevP.isSpeaking && currP.isSpeaking) {
        emitMeetEvent({
          type: "speaker_active",
          timestamp,
          participant_id: currP.id,
          display_name: currP.name,
        });
      }
    }
  });

  // 2. Detect Leaves
  prev.forEach((prevP, id) => {
    if (!curr.has(id)) {
      emitMeetEvent({
        type: "participant_leave",
        timestamp,
        participant_id: prevP.id,
        display_name: prevP.name,
      });
    }
  });
}

function emitMeetEvent(payload: any) {
  chrome.runtime.sendMessage({
    type: "MEET_DOM_EVENT",
    payload,
  }).catch(() => {});
}
