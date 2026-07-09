"use strict";
(() => {
  // src/content/content.ts
  var lastParticipants = /* @__PURE__ */ new Map();
  var scanTimeoutId = null;
  var lastScanTime = 0;
  var observer = new MutationObserver((mutations) => {
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
    console.log("[Sherlock AI Content Script] Injected and initializing DOM observer.");
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style", "aria-label", "data-is-muted", "src"]
    });
    setInterval(scanMeetDOM, 3e3);
    scanMeetDOM();
  }
  function scanMeetDOM() {
    lastScanTime = Date.now();
    if (scanTimeoutId) {
      clearTimeout(scanTimeoutId);
      scanTimeoutId = null;
    }
    const currentParticipants = /* @__PURE__ */ new Map();
    const videoElements = document.querySelectorAll("video");
    videoElements.forEach((video) => {
      let container = video.parentElement;
      let name = "Unknown Participant";
      let isMuted = true;
      let isCameraOn = video.readyState === 4 && !video.paused;
      let isSpeaking = false;
      let isScreenSharing = false;
      let depth = 0;
      while (container && depth < 8) {
        const nameEl = container.querySelector("[data-self-name], [data-name], .ytU30d, .zWDL5");
        if (nameEl && nameEl.textContent) {
          name = nameEl.textContent.trim();
        }
        const screenEl = container.querySelector("[data-is-presentation='true'], [data-screen-share='true']");
        if (screenEl || name.toLowerCase().includes("presentation") || name.toLowerCase().includes("screen share")) {
          isScreenSharing = true;
        }
        const speakingEl = container.querySelector(".I9AFdf, .VfPpkd-Bz112c-LgbsSe, [data-is-speaking='true']");
        if (speakingEl || container.classList.contains("speaking")) {
          isSpeaking = true;
        }
        const micEl = container.querySelector("[data-is-muted], .GvcuGe, .Qv2eCc");
        if (micEl) {
          const isMutedAttr = micEl.getAttribute("data-is-muted");
          if (isMutedAttr !== null) {
            isMuted = isMutedAttr === "true";
          } else {
            const label = micEl.getAttribute("aria-label") || micEl.getAttribute("title") || "";
            isMuted = label.toLowerCase().includes("muted") || label.toLowerCase().includes("off");
          }
        }
        container = container.parentElement;
        depth++;
      }
      if (name && name !== "Unknown Participant") {
        const id = name.replace(/\s+/g, "_").toLowerCase();
        currentParticipants.set(id, {
          id,
          name,
          isMuted,
          isCameraOn,
          isSpeaking,
          isScreenSharing
        });
      }
    });
    const panelParticipants = document.querySelectorAll("[data-participant-id], .KV5Zae, .XW3o0e");
    panelParticipants.forEach((el) => {
      let name = "";
      const nameEl = el.querySelector(".focus-target, .Z32Bgc, .cS4QAe");
      if (nameEl && nameEl.textContent) {
        name = nameEl.textContent.trim();
      } else if (el.textContent) {
        name = el.textContent.trim();
      }
      if (name && name.length > 0 && !name.includes("Add people") && !name.includes("Mute all")) {
        const id = name.replace(/\s+/g, "_").toLowerCase();
        if (!currentParticipants.has(id)) {
          let isMuted = true;
          const micEl = el.querySelector("[data-is-muted]");
          if (micEl) {
            isMuted = micEl.getAttribute("data-is-muted") === "true";
          }
          currentParticipants.set(id, {
            id,
            name,
            isMuted,
            isCameraOn: false,
            // Assume off if not in grid with active video
            isSpeaking: false,
            isScreenSharing: false
          });
        }
      }
    });
    const selfVideo = document.querySelector("video[mirror='true']");
    const selfNameEl = document.querySelector("[data-self-name]");
    let selfName = selfNameEl?.textContent?.trim() || "You";
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
        isScreenSharing: false
      });
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
          emitMeetEvent({
            type: currP.isCameraOn ? "camera_on" : "camera_off",
            timestamp,
            participant_id: currP.id,
            display_name: currP.name
          });
        }
        if (currP.isMuted !== prevP.isMuted) {
          emitMeetEvent({
            type: currP.isMuted ? "mic_off" : "mic_on",
            timestamp,
            participant_id: currP.id,
            display_name: currP.name
          });
        }
        if (currP.isScreenSharing !== prevP.isScreenSharing) {
          emitMeetEvent({
            type: "screen_share",
            timestamp,
            participant_id: currP.id,
            display_name: currP.name,
            state: currP.isScreenSharing ? "on" : "off"
          });
        }
        if (currP.isSpeaking !== prevP.isSpeaking && currP.isSpeaking) {
          emitMeetEvent({
            type: "speaker_active",
            timestamp,
            participant_id: currP.id,
            display_name: currP.name
          });
        }
      }
    });
    prev.forEach((prevP, id) => {
      if (!curr.has(id)) {
        emitMeetEvent({
          type: "participant_leave",
          timestamp,
          participant_id: prevP.id,
          display_name: prevP.name
        });
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
