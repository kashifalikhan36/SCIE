from models import InterviewData
from evidence.name_match import NameMatchModule
from evidence.email_match import EmailMatchModule
from evidence.join_events import JoinTimingModule
from evidence.webcam import WebcamModule
from evidence.screen_share import ScreenShareModule
from evidence.speaking import SpeakingModule
from evidence.interviewer_detection import InterviewerDetectionModule
from evidence.transcript import TranscriptModule
from evidence.embedding_match import EmbeddingMatchModule
from evidence.metadata import MetadataModule

class Detector:
    def __init__(self):
        self.modules = [
            NameMatchModule(),
            EmailMatchModule(),
            JoinTimingModule(),
            WebcamModule(),
            ScreenShareModule(),
            SpeakingModule(),
            InterviewerDetectionModule(),
            TranscriptModule(),
            EmbeddingMatchModule(),
            MetadataModule()
        ]

    def process(self, data: InterviewData) -> list:
        all_evidence = []
        for module in self.modules:
            try:
                evidence = module.run(data)
                
                # Fix module names to match the weights map in config if needed
                name_map = {
                    "NameMatchModule": "Name Match",
                    "EmailMatchModule": "Email Match",
                    "JoinTimingModule": "Join Timing",
                    "WebcamModule": "Webcam",
                    "ScreenShareModule": "Screen Share",
                    "SpeakingModule": "Speaking",
                    "InterviewerDetectionModule": "Interviewer Detection", # No weight explicitly given, acts as penalty
                    "TranscriptModule": "Transcript",
                    "EmbeddingMatchModule": "Embedding Similarity",
                    "MetadataModule": "Metadata"
                }
                
                for ev in evidence:
                    ev.module = name_map.get(ev.module, ev.module)
                    
                all_evidence.extend(evidence)
            except Exception as e:
                # If any information is missing, skip module and continue running
                # print(f"Warning: {module.name} failed with error: {e}")
                pass
                
        return all_evidence
