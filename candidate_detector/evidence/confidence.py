from dataclasses import dataclass

@dataclass
class EvidenceScore:
    participant_id: str
    module: str
    score: float       # Raw score (0.0 to 1.0)
    confidence: float  # Confidence (0.0 to 100.0)
    reason: str

class BaseEvidenceModule:
    @property
    def name(self) -> str:
        return self.__class__.__name__

    def run(self, data: 'InterviewData') -> list[EvidenceScore]:
        raise NotImplementedError("Modules must implement the run method")
