let audioRecorder: MediaRecorder | null = null;
let videoRecorder: MediaRecorder | null = null;
let activeStream: MediaStream | null = null;

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

async function startCapture(streamId: string) {
  stopCapture();

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

    // Separate audio and video tracks
    const audioTracks = stream.getAudioTracks();
    const videoTracks = stream.getVideoTracks();

    // Setup Audio Recorder if audio tracks exist
    if (audioTracks.length > 0) {
      const audioStream = new MediaStream(audioTracks);
      let audioMime = "audio/webm;codecs=opus";
      if (!MediaRecorder.isTypeSupported(audioMime)) {
        audioMime = "audio/webm";
      }
      
      log(`Starting audio recorder using MIME: ${audioMime}`);
      audioRecorder = new MediaRecorder(audioStream, { mimeType: audioMime });
      
      audioRecorder.ondataavailable = async (event) => {
        if (event.data && event.data.size > 0) {
          try {
            const buffer = await event.data.arrayBuffer();
            // IMPORTANT: Chrome's runtime.sendMessage cannot serialize raw ArrayBuffer.
            // Convert to regular Array of numbers for safe cross-context messaging.
            const byteArray = Array.from(new Uint8Array(buffer));
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

      audioRecorder.start(250); // 250ms chunks
    } else {
      log("No audio tracks found in stream.", "WARN");
    }

    // Setup Video Recorder if video tracks exist
    if (videoTracks.length > 0) {
      const videoStream = new MediaStream(videoTracks);
      let videoMime = "video/webm;codecs=vp8";
      if (!MediaRecorder.isTypeSupported(videoMime)) {
        videoMime = "video/webm";
      }
      
      log(`Starting video recorder using MIME: ${videoMime}`);
      videoRecorder = new MediaRecorder(videoStream, { mimeType: videoMime });
      
      videoRecorder.ondataavailable = async (event) => {
        if (event.data && event.data.size > 0) {
          try {
            const buffer = await event.data.arrayBuffer();
            // IMPORTANT: Convert to regular Array of numbers for safe cross-context messaging.
            const byteArray = Array.from(new Uint8Array(buffer));
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

      videoRecorder.start(250); // 250ms chunks
    } else {
      log("No video tracks found in stream.", "WARN");
    }

    // Monitor stream end (e.g. if the user stops sharing, tab is closed, etc.)
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
    try {
      audioRecorder.stop();
    } catch (e) {}
    audioRecorder = null;
  }
  if (videoRecorder && videoRecorder.state !== "inactive") {
    try {
      videoRecorder.stop();
    } catch (e) {}
    videoRecorder = null;
  }
  if (activeStream) {
    activeStream.getTracks().forEach((track) => {
      track.stop();
    });
    activeStream = null;
  }
  log("Tab capture stopped and tracks cleaned up.");
}
