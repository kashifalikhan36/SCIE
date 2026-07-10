from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from embeddings import generate_embedding, cosine_similarity

class EmbeddingMatchModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        candidate_name = data.external_metadata.candidate_name
        if not candidate_name:
            return []
            
        cand_emb = generate_embedding(candidate_name)
        if not cand_emb:
            return []
            
        for participant in data.participant_information:
            part_emb = generate_embedding(participant.display_name)
            if not part_emb:
                continue
                
            sim = cosine_similarity(cand_emb, part_emb)
            
            # Map similarity [-1, 1] to [0, 100] approximately.
            # Names usually have high similarity > 0.7 if they match
            conf = max(0.0, min(100.0, (sim - 0.5) * 200.0))
            
            scores.append(EvidenceScore(
                participant_id=participant.participant_id,
                module=self.name,
                score=conf / 100.0,
                confidence=conf,
                reason=f"Semantic similarity score: {sim:.2f}"
            ))
            
        return scores
