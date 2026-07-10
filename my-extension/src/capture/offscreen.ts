let audioRecorder: MediaRecorder | null = null;
let videoRecorder: MediaRecorder | null = null;
let activeStream: MediaStream | null = null;

// Cache the EBML init segment (first chunk from MediaRecorder)
// so we can prepend it to every subsequent chunk, making each
// chunk a self-contained valid WebM file that ffmpeg can decode.
let audioInitSegment: Uint8Array | null = null;
let videoInitSegment: Uint8Array | null = null;

// Send logs from offscreen document to background
function log(msg: string, level: "INFO" | "WARN" | "ERROR" = "INFO") {
  chrome.runtime.sendMessage({
    type: "OFFSCREEN_LOG",
    level,
    message: `[Offscreen] ${msg}`,
  }).catch(() => {});
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "start_capture") {
    const { streamId } = message;
    log(`Initializing capture with streamId: ${streamId}`);
    startCapture(streamId)
      .then(() => sendResponse({ success: true }))
      .catch((err) => {
        log(`Capture initialization failed: ${err.message}`, "ERROR");
        sendResponse({ success: false, error: err.message });
      });
    return true; // async response
  } else if (message.action === "stop_capture") {
    log("Stopping capture.");
    stopCapture();
    sendResponse({ success: true });
  }
});

/**
 * Prepend the cached EBML init segment to a raw chunk so that
 * the result is a fully self-contained WebM file.
 * If the init segment is not yet cached (this IS the init segment),
 * return it as-is and cache it.
 */
function makeStandaloneChunk(
  rawBytes: Uint8Array,
  initRef: { current: Uint8Array | null }
): Uint8Array {
  if (!initRef.current) {
    // First chunk — this IS the init segment, cache and return as-is
    initRef.current = rawBytes;
    return rawBytes;
  }
  // Subsequent chunks — prepend init segment
  const combined = new Uint8Array(initRef.current.length + rawBytes.length);
  combined.set(initRef.current, 0);
  combined.set(rawBytes, initRef.current.length);
  return combined;
}

async function startCapture(streamId: string) {
  stopCapture();

  // Reset init segment caches for the new session
  audioInitSegment = null;
  videoInitSegment = null;

  try {
    // Acquire the media stream for the tab
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      } as any,
      video: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      } as any,
    });

    activeStream = stream;
    log(`Successfully acquired tab MediaStream. Audio tracks: ${stream.getAudioTracks().length}, Video tracks: ${stream.getVideoTracks().length}`);

    const audioTracks = stream.getAudioTracks();
    const videoTracks = stream.getVideoTracks();

    // ── Audio Recorder ────────────────────────────────────────────────────
    if (audioTracks.length > 0) {
      const audioStream = new MediaStream(audioTracks);
      let audioMime = "audio/webm;codecs=opus";
      if (!MediaRecorder.isTypeSupported(audioMime)) {
        audioMime = "audio/webm";
      }

      log(`Starting audio recorder using MIME: ${audioMime}`);
      audioRecorder = new MediaRecorder(audioStream, { mimeType: audioMime });

      const audioInitRef = { current: null as Uint8Array | null };

      audioRecorder.ondataavailable = async (event) => {
        if (event.data && event.data.size > 0) {
          try {
            const buffer = await event.data.arrayBuffer();
            const raw = new Uint8Array(buffer);
            // Prepend EBML header so every chunk is a valid WebM file
            const standalone = makeStandaloneChunk(raw, audioInitRef);
            audioInitSegment = audioInitRef.current;
            const byteArray = Array.from(standalone);
            chrome.runtime.sendMessage({
              type: "AUDIO_CHUNK",
              timestamp: Date.now(),
              data: byteArray,
            }).catch(() => {});
          } catch (err: any) {
            log(`Failed to process audio chunk: ${err.message}`, "ERROR");
          }
        }
      };

      audioRecorder.onerror = (errEvent: any) => {
        log(`Audio recorder error: ${errEvent.error?.message || errEvent.message}`, "ERROR");
      };

      audioRecorder.start(500); // 500ms chunks — gives more data per chunk
    } else {
      log("No audio tracks found in stream.", "WARN");
    }

    // ── Video Recorder ────────────────────────────────────────────────────
    if (videoTracks.length > 0) {
      const videoStream = new MediaStream(videoTracks);
      let videoMime = "video/webm;codecs=vp8";
      if (!MediaRecorder.isTypeSupported(videoMime)) {
        videoMime = "video/webm";
      }

      log(`Starting video recorder using MIME: ${videoMime}`);
      videoRecorder = new MediaRecorder(videoStream, { mimeType: videoMime });

      const videoInitRef = { current: null as Uint8Array | null };

      videoRecorder.ondataavailable = async (event) => {
        if (event.data && event.data.size > 0) {
          try {
            const buffer = await event.data.arrayBuffer();
            const raw = new Uint8Array(buffer);
            // Prepend EBML header so every chunk is a valid WebM file
            const standalone = makeStandaloneChunk(raw, videoInitRef);
            videoInitSegment = videoInitRef.current;
            const byteArray = Array.from(standalone);
            chrome.runtime.sendMessage({
              type: "VIDEO_CHUNK",
              timestamp: Date.now(),
              data: byteArray,
            }).catch(() => {});
          } catch (err: any) {
            log(`Failed to process video chunk: ${err.message}`, "ERROR");
          }
        }
      };

      videoRecorder.onerror = (errEvent: any) => {
        log(`Video recorder error: ${errEvent.error?.message || errEvent.message}`, "ERROR");
      };

      videoRecorder.start(1000); // 1s video chunks
    } else {
      log("No video tracks found in stream.", "WARN");
    }

    // Monitor stream end (e.g. user stops sharing or closes the tab)
    stream.getVideoTracks()[0]?.addEventListener("ended", () => {
      log("Tab capture stream ended (video track ended).");
      chrome.runtime.sendMessage({ type: "CAPTURE_ENDED_EVENT" }).catch(() => {});
    });

  } catch (err: any) {
    log(`getUserMedia failed: ${err.message}`, "ERROR");
    throw err;
  }
}

function stopCapture() {
  if (audioRecorder && audioRecorder.state !== "inactive") {
    try { audioRecorder.stop(); } catch (e) {}
    audioRecorder = null;
  }
  if (videoRecorder && videoRecorder.state !== "inactive") {
    try { videoRecorder.stop(); } catch (e) {}
    videoRecorder = null;
  }
  if (activeStream) {
    activeStream.getTracks().forEach((track) => track.stop());
    activeStream = null;
  }
  // Reset init segments so next session starts fresh
  audioInitSegment = null;
  videoInitSegment = null;
  log("Tab capture stopped and tracks cleaned up.");
}
