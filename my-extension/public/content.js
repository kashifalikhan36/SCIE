"use strict";
(() => {
  // src/content/content.ts
  var lastParticipants = /* @__PURE__ */ new Map();
  var scanTimeoutId = null;
  var lastScanTime = 0;
  var observer = new MutationObserver(() => {
    const now = Date.now();
    if (now - lastScanTime > 1e3) {
      scanMeetDOM();
    } else {
      if (scanTimeoutId) clearTimeout(scanTimeoutId);
      scanTimeoutId = setTimeout(scanMeetDOM, 1e3 - (now - lastScanTime));
    }
  });
  if (document.readyState === "complete" || document.readyState === "interactive") {
    initObserver();
  } else {
    window.addEventListener("DOMContentLoaded", initObserver);
  }
  function initObserver() {
    console.log("[SCIE Content Script] Injected and initializing DOM observer.");
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style", "aria-label", "data-is-muted", "src"]
    });
    setInterval(scanMeetDOM, 5e3);
    scanMeetDOM();
  }
  function scanMeetDOM() {
    lastScanTime = Date.now();
    if (scanTimeoutId) {
      clearTimeout(scanTimeoutId);
      scanTimeoutId = null;
    }
    const currentParticipants = /* @__PURE__ */ new Map();
    const selfNameEl = document.querySelector("[data-self-name]");
    const selfName = selfNameEl?.textContent?.trim() || "";
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
      "[jsname='r4nke']"
    ];
    const participantContainers = [];
    const participantEls = document.querySelectorAll("[data-participant-id]");
    participantEls.forEach((el) => {
      if (el.offsetParent !== null || el.closest("[aria-hidden='false']")) {
        participantContainers.push(el);
      }
    });
    participantContainers.forEach((container) => {
      const participantId = container.getAttribute("data-participant-id") || "";
      let name = "";
      const nameEl = container.querySelector("[data-self-name]") || container.querySelector(".NsNELd") || container.querySelector(".XEazBc") || container.querySelector(".cS4QAe") || container.querySelector(".zWGUib") || container.querySelector("[jsname='XpIydf']");
      if (nameEl?.textContent) {
        name = nameEl.textContent.trim();
      }
      if (!name) {
        const ariaLabel = container.getAttribute("aria-label") || "";
        if (ariaLabel && ariaLabel.length < 60) {
          name = ariaLabel.split("'")[0].split(",")[0].trim();
        }
      }
      if (!name || name.length === 0 || name.length > 60) return;
      const isMuted = !!(container.querySelector("[data-is-muted='true']") || container.querySelector("[aria-label*='muted']") || container.querySelector("[aria-label*='Muted']"));
      const videoEl = container.querySelector("video");
      const isCameraOn = !!(videoEl && videoEl.readyState >= 2 && !videoEl.paused);
      const isSpeaking = !!(container.querySelector("[data-is-speaking='true']") || container.querySelector(".speaking"));
      const isScreenSharing = !!(container.querySelector("[data-is-presentation='true']") || container.querySelector("[aria-label*='presentation']") || container.querySelector("[aria-label*='screen']"));
      let id = participantId || name.replace(/\s+/g, "_").toLowerCase();
      if (name === selfName || selfName && name.startsWith(selfName)) {
        id = "you";
        name = selfName || name;
      }
      currentParticipants.set(id, { id, name, isMuted, isCameraOn, isSpeaking, isScreenSharing });
    });
    const panelNameEls = document.querySelectorAll("[data-participant-id] span[jsname], .rua5Nb");
    panelNameEls.forEach((el) => {
      if (el.offsetParent === null) return;
      const name = el.textContent?.trim() || "";
      if (!name || name.length === 0 || name.length > 60) return;
      let id = name.replace(/\s+/g, "_").toLowerCase();
      if (name === selfName || selfName && name.startsWith(selfName)) {
        id = "you";
      }
      if (!currentParticipants.has(id)) {
        currentParticipants.set(id, {
          id,
          name: id === "you" ? selfName || name : name,
          isMuted: true,
          isCameraOn: false,
          isSpeaking: false,
          isScreenSharing: false
        });
      }
    });
    if (currentParticipants.size === 0) {
      const videos = document.querySelectorAll("video");
      let videoCount = 0;
      videos.forEach((v) => {
        if (v.readyState >= 2 || v.videoWidth > 0) {
          videoCount++;
        }
      });
      if (videoCount > 0) {
        for (let i = 0; i < videoCount; i++) {
          const placeholderId = i === 0 ? "you" : `participant_${i}`;
          const placeholderName = i === 0 ? selfName || "You" : `Participant ${i + 1}`;
          currentParticipants.set(placeholderId, {
            id: placeholderId,
            name: placeholderName,
            isMuted: true,
            isCameraOn: true,
            isSpeaking: false,
            isScreenSharing: false
          });
        }
      }
    }
    generateEvents(lastParticipants, currentParticipants);
    lastParticipants = currentParticipants;
    const listEvent = {
      type: "participants_list",
      timestamp: Date.now(),
      count: currentParticipants.size,
      participants: Array.from(currentParticipants.values()).map((p) => ({
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
      payload: listEvent
    }).catch(() => {
    });
  }
  function generateEvents(prev, curr) {
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
          screen_share: currP.isScreenSharing ? "on" : "off"
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
  function emitMeetEvent(payload) {
    chrome.runtime.sendMessage({
      type: "MEET_DOM_EVENT",
      payload
    }).catch(() => {
    });
  }
})();
