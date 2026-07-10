"use strict";
(() => {
  // src/capture/offscreen.ts
  var audioRecorder = null;
  var videoRecorder = null;
  var activeStream = null;
  var audioInitSegment = null;
  var videoInitSegment = null;
  function log(msg, level = "INFO") {
    chrome.runtime.sendMessage({
      type: "OFFSCREEN_LOG",
      level,
      message: `[Offscreen] ${msg}`
    }).catch(() => {
    });
  }
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "start_capture") {
      const { streamId } = message;
      log(`Initializing capture with streamId: ${streamId}`);
      startCapture(streamId).then(() => sendResponse({ success: true })).catch((err) => {
        log(`Capture initialization failed: ${err.message}`, "ERROR");
        sendResponse({ success: false, error: err.message });
      });
      return true;
    } else if (message.action === "stop_capture") {
      log("Stopping capture.");
      stopCapture();
      sendResponse({ success: true });
    }
  });
  function makeStandaloneChunk(rawBytes, initRef) {
    if (!initRef.current) {
      initRef.current = rawBytes;
      return rawBytes;
    }
    const combined = new Uint8Array(initRef.current.length + rawBytes.length);
    combined.set(initRef.current, 0);
    combined.set(rawBytes, initRef.current.length);
    return combined;
  }
  async function startCapture(streamId) {
    stopCapture();
    audioInitSegment = null;
    videoInitSegment = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: "tab",
            chromeMediaSourceId: streamId
          }
        },
        video: {
          mandatory: {
            chromeMediaSource: "tab",
            chromeMediaSourceId: streamId
          }
        }
      });
      activeStream = stream;
      log(`Successfully acquired tab MediaStream. Audio tracks: ${stream.getAudioTracks().length}, Video tracks: ${stream.getVideoTracks().length}`);
      const audioTracks = stream.getAudioTracks();
      const videoTracks = stream.getVideoTracks();
      if (audioTracks.length > 0) {
        const audioStream = new MediaStream(audioTracks);
        let audioMime = "audio/webm;codecs=opus";
        if (!MediaRecorder.isTypeSupported(audioMime)) {
          audioMime = "audio/webm";
        }
        log(`Starting audio recorder using MIME: ${audioMime}`);
        audioRecorder = new MediaRecorder(audioStream, { mimeType: audioMime });
        const audioInitRef = { current: null };
        audioRecorder.ondataavailable = async (event) => {
          if (event.data && event.data.size > 0) {
            try {
              const buffer = await event.data.arrayBuffer();
              const raw = new Uint8Array(buffer);
              const standalone = makeStandaloneChunk(raw, audioInitRef);
              audioInitSegment = audioInitRef.current;
              const byteArray = Array.from(standalone);
              chrome.runtime.sendMessage({
                type: "AUDIO_CHUNK",
                timestamp: Date.now(),
                data: byteArray
              }).catch(() => {
              });
            } catch (err) {
              log(`Failed to process audio chunk: ${err.message}`, "ERROR");
            }
          }
        };
        audioRecorder.onerror = (errEvent) => {
          log(`Audio recorder error: ${errEvent.error?.message || errEvent.message}`, "ERROR");
        };
        audioRecorder.start(500);
      } else {
        log("No audio tracks found in stream.", "WARN");
      }
      if (videoTracks.length > 0) {
        const videoStream = new MediaStream(videoTracks);
        let videoMime = "video/webm;codecs=vp8";
        if (!MediaRecorder.isTypeSupported(videoMime)) {
          videoMime = "video/webm";
        }
        log(`Starting video recorder using MIME: ${videoMime}`);
        videoRecorder = new MediaRecorder(videoStream, { mimeType: videoMime });
        const videoInitRef = { current: null };
        videoRecorder.ondataavailable = async (event) => {
          if (event.data && event.data.size > 0) {
            try {
              const buffer = await event.data.arrayBuffer();
              const raw = new Uint8Array(buffer);
              const standalone = makeStandaloneChunk(raw, videoInitRef);
              videoInitSegment = videoInitRef.current;
              const byteArray = Array.from(standalone);
              chrome.runtime.sendMessage({
                type: "VIDEO_CHUNK",
                timestamp: Date.now(),
                data: byteArray
              }).catch(() => {
              });
            } catch (err) {
              log(`Failed to process video chunk: ${err.message}`, "ERROR");
            }
          }
        };
        videoRecorder.onerror = (errEvent) => {
          log(`Video recorder error: ${errEvent.error?.message || errEvent.message}`, "ERROR");
        };
        videoRecorder.start(1e3);
      } else {
        log("No video tracks found in stream.", "WARN");
      }
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        log("Tab capture stream ended (video track ended).");
        chrome.runtime.sendMessage({ type: "CAPTURE_ENDED_EVENT" }).catch(() => {
        });
      });
    } catch (err) {
      log(`getUserMedia failed: ${err.message}`, "ERROR");
      throw err;
    }
  }
  function stopCapture() {
    if (audioRecorder && audioRecorder.state !== "inactive") {
      try {
        audioRecorder.stop();
      } catch (e) {
      }
      audioRecorder = null;
    }
    if (videoRecorder && videoRecorder.state !== "inactive") {
      try {
        videoRecorder.stop();
      } catch (e) {
      }
      videoRecorder = null;
    }
    if (activeStream) {
      activeStream.getTracks().forEach((track) => track.stop());
      activeStream = null;
    }
    audioInitSegment = null;
    videoInitSegment = null;
    log("Tab capture stopped and tracks cleaned up.");
  }
})();
