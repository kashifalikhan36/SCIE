# Model Constants
VAD_MODEL_NAME = "pyannote/segmentation-3.0"
DIARIZATION_MODEL_NAME = "pyannote/speaker-diarization-3.1"
SPEAKER_RECOGNITION_MODEL_NAME = "speechbrain/spkrec-resnet-voxceleb"
LANGUAGE_DETECTION_MODEL_NAME = "speechbrain/lang-id-voxlingua107-ecapa"
STT_MODEL_NAME = "whisper-large-v3"

# Audio Settings
SAMPLE_RATE = 16000
CHANNELS = 1

# Database Collections
MONGO_MEETINGS_COL = "meetings"
MONGO_SEGMENTS_COL = "audio_segments"
MONGO_TRANSCRIPTS_COL = "transcripts"
MONGO_EMBEDDINGS_COL = "speaker_embeddings"
MONGO_EVIDENCE_COL = "voice_evidence"
