from models import InterviewData
from evidence.identity_correlation import IdentityCorrelationModule
from evidence.name_match import NameMatchModule
from evidence.join_events import JoinTimingModule
from evidence.webcam import WebcamModule
from evidence.screen_share import ScreenShareModule
from evidence.speaking import SpeakingModule
from evidence.interviewer_detection import InterviewerDetectionModule
from evidence.conversation_role import ConversationRoleModule
from evidence.transcript_mentions import TranscriptMentionsModule
from evidence.timeline import TimelineModule
from evidence.metadata import MetadataModule

class Detector:
    def __init__(self):
        self.modules = [
            IdentityCorrelationModule(),
            NameMatchModule(),
            JoinTimingModule(),
            WebcamModule(),
            ScreenShareModule(),
            SpeakingModule(),
            InterviewerDetectionModule(),
            ConversationRoleModule(),
            TranscriptMentionsModule(),
            TimelineModule(),
            MetadataModule()
        ]

    def process(self, data: InterviewData) -> list:
        all_evidence = []
        for module in self.modules:
            try:
                evidence = module.run(data)
                
                name_map = {
                    "IdentityCorrelationModule": "Identity Correlation",
                    "NameMatchModule": "Name Match",
                    "JoinTimingModule": "Join Timeline",
                    "WebcamModule": "Webcam Behaviour",
                    "ScreenShareModule": "Screen Share",
                    "SpeakingModule": "Speaking Behaviour",
                    "InterviewerDetectionModule": "Interviewer Detection",
                    "ConversationRoleModule": "Conversation Role",
                    "TranscriptMentionsModule": "Transcript Mentions",
                    "TimelineModule": "Event Timeline",
                    "MetadataModule": "Metadata Consistency"
                }
                
                for ev in evidence:
                    ev.module = name_map.get(ev.module, ev.module)
                    
                all_evidence.extend(evidence)
            except Exception as e:
                # Never crash, simply skip
                pass
                
        return all_evidence
