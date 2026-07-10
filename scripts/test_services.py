"""
Quick diagnostic tests for Azure OpenAI and Groq Whisper.
Run with: python -X utf8 scripts/test_services.py
"""
import os, sys, json, wave, io, struct, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env manually
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Parse manually if dotenv not installed
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):  print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def info(msg): print(f"  {YELLOW}→{RESET} {msg}")
def head(t):   print(f"\n{CYAN}{'─'*50}\n {t}\n{'─'*50}{RESET}")


def make_440hz_wav(duration_sec=2, sample_rate=16000) -> bytes:
    """Generate a 440Hz sine wave WAV (audible speech-like tone) for testing."""
    num_samples = sample_rate * duration_sec
    samples = [int(32767 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(num_samples)]
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{num_samples}h", *samples))
    return buf.getvalue()


# ── TEST 1: Azure OpenAI ─────────────────────────────────────────────────────
def test_azure_openai():
    head("TEST 1: Azure OpenAI")
    api_key  = os.getenv("AZURE_OPENAI_API_KEY", "")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    version  = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    deployment = os.getenv("REASONING_DEPLOYMENT", "gpt-5.5")

    if not api_key or not endpoint:
        fail(f"AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT not set in .env")
        return False

    info(f"API key: {api_key[:8]}...")
    info(f"Endpoint: {endpoint}")
    info(f"Deployment: {deployment}")

    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=version)
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": "Reply with ONLY the word: WORKING"}],
            max_tokens=10,
            temperature=0,
        )
        text = resp.choices[0].message.content.strip()
        ok(f"Azure OpenAI response: '{text}'")
        return True
    except Exception as e:
        fail(f"Azure OpenAI call failed: {e}")
        return False


# ── TEST 2: Groq Whisper ─────────────────────────────────────────────────────
def test_groq_whisper():
    head("TEST 2: Groq Whisper Transcription")
    import requests

    api_key = os.getenv("GROQ_API_KEY", "")
    model   = os.getenv("GROQ_AUDIO_MODEL", "whisper-large-v3")
    video_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "tests", "video", "interview.mp4")

    if not api_key:
        fail("GROQ_API_KEY not set in .env")
        return False

    info(f"API key: {api_key[:8]}...")
    info(f"Model: {model}")

    # Test 1: Synthetic tone (checks API connectivity)
    info("Test A — Sending 440Hz tone (checks API connectivity)...")
    try:
        wav_bytes = make_440hz_wav(duration_sec=3)
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("test.wav", wav_bytes, "audio/wav")},
            data={"model": model, "response_format": "json"},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json().get("text", "").strip()
        ok(f"API reachable — tone transcript: '{text}' (blank is fine for a tone)")
    except requests.exceptions.HTTPError as e:
        fail(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        return False
    except Exception as e:
        fail(f"Groq API call failed: {e}")
        return False

    # Test 2: Real video first 30s (checks real transcription)
    if os.path.exists(video_path):
        info(f"Test B — Transcribing first 30s of {os.path.basename(video_path)}...")
        try:
            import subprocess
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            result = subprocess.run(
                [ffmpeg_exe, "-y", "-i", video_path, "-vn", "-t", "30",
                 "-f", "wav", "-ac", "1", "-ar", "16000", "pipe:1"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            wav_30s = result.stdout
            if wav_30s:
                resp2 = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("chunk.wav", wav_30s, "audio/wav")},
                    data={"model": model, "response_format": "json"},
                    timeout=60,
                )
                resp2.raise_for_status()
                real_text = resp2.json().get("text", "").strip()
                if real_text:
                    ok(f"Real transcript (first 80 chars): '{real_text[:80]}...' " if len(real_text) > 80 else f"Real transcript: '{real_text}'")
                else:
                    info("Groq returned empty text for this 30s chunk (may be silence/music)")
            else:
                info("FFmpeg returned no audio — check video file path")
        except Exception as e:
            fail(f"Real video test failed: {e}")
    else:
        info(f"Video not found at {video_path} — skipping real audio test")

    return True


if __name__ == "__main__":
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════╗")
    print(f"║   SCIE Service Diagnostics           ║")
    print(f"╚══════════════════════════════════════╝{RESET}")

    r1 = test_azure_openai()
    r2 = test_groq_whisper()

    head("SUMMARY")
    print(f"  Azure OpenAI : {'✓ PASS' if r1 else '✗ FAIL'}")
    print(f"  Groq Whisper : {'✓ PASS' if r2 else '✗ FAIL'}")
    print()
    sys.exit(0 if (r1 and r2) else 1)
