import os
import json
import logging
from typing import Dict, Any, Optional
from openai import AsyncAzureOpenAI
from database.mongodb import get_mongo_db
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("SCIE.reasoning_engine.pipeline")


class ReasoningSettings(BaseSettings):
    """Reads Azure OpenAI credentials from .env — no prefix so var names match exactly."""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    REASONING_DEPLOYMENT: str = "gpt-5.5"   # set in .env to override

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


_settings = ReasoningSettings()


class ReasoningPipeline:
    """Synthesizes meeting evidence into a structured JSON explainability report via Azure OpenAI."""

    def __init__(self):
        api_key  = _settings.AZURE_OPENAI_API_KEY
        endpoint = _settings.AZURE_OPENAI_ENDPOINT
        version  = _settings.AZURE_OPENAI_API_VERSION
        self.deployment = _settings.REASONING_DEPLOYMENT

        if api_key and endpoint:
            self.client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=version,
            )
            logger.info(
                f"ReasoningPipeline: Azure OpenAI ready — "
                f"deployment='{self.deployment}', endpoint='{endpoint}'"
            )
        else:
            self.client = None
            logger.warning(
                "ReasoningPipeline: Azure OpenAI credentials missing "
                "(set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT in .env)."
            )

    async def generate_reasoning(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Extracts meeting evidence and generates a structured verification report."""
        try:
            db = get_mongo_db()

            # ── Gather all evidence ──────────────────────────────────────────
            rankings = await db.fusion_ranking_snapshots.find(
                {"meeting_id": meeting_id}
            ).sort("timestamp", -1).limit(1).to_list(1)
            ranking_doc = rankings[0] if rankings else {}

            matches = await db.identity_matches.find({"meeting_id": meeting_id}).to_list(10)

            transcripts = await db.transcript_segments.find(
                {"meeting_id": meeting_id}
            ).sort("timestamp", 1).limit(10).to_list(10)

            meeting = await db.meetings.find_one({"meeting_id": meeting_id})
            extra = (meeting or {}).get("extra_data", {})
            candidate = extra.get("candidate") or "Unknown Candidate"
            candidate_email = extra.get("candidate_email", "")
            interviewers = extra.get("interviewers", [])
            identity_result = (meeting or {}).get("identity_result", {})

            num_participants = len((meeting or {}).get("participants_data", []))
            num_transcripts = len(transcripts)

            # ── AI path: use Azure OpenAI gpt-5.5 reasoning model ───────────
            if self.client:
                # Serialize all evidence — strip MongoDB _id fields
                def _clean(obj):
                    if isinstance(obj, dict):
                        return {k: _clean(v) for k, v in obj.items() if k != "_id"}
                    if isinstance(obj, list):
                        return [_clean(i) for i in obj]
                    return obj

                prompt = f"""You are the SCIE Sherlock Reasoning Engine.
Analyse the following interview evidence and produce a JSON verification report.

Meeting ID: {meeting_id}
Candidate (expected): {candidate}
Candidate Email: {candidate_email}
Interviewers: {', '.join(interviewers) if interviewers else 'Not specified'}

Sherlock Identity Engine Result: {json.dumps(_clean(identity_result))}
Identity Database Matches: {json.dumps(_clean(matches))}
Audio Fusion Ranking: {json.dumps(_clean(ranking_doc))}
Transcript Sample ({num_transcripts} segments): {json.dumps(_clean(transcripts))}

Return ONLY valid JSON matching this exact schema:
{{
    "meeting_id": "{meeting_id}",
    "candidate": "{candidate}",
    "identified_participant_id": "<participant ID Sherlock matched, or null>",
    "is_verified": true or false,
    "confidence_score": <float 0.0-1.0>,
    "summary": "<2-3 sentences explaining the verification result>",
    "evidence_reasons": ["<reason 1>", "<reason 2>"],
    "flags": ["<anomaly if any, empty list if none>"]
}}"""

                # gpt-5.5 is an o-series reasoning model:
                # - Does NOT support: temperature, top_p, max_tokens, presence_penalty
                # - Uses: max_completion_tokens, reasoning_effort
                response = await self.client.chat.completions.create(
                    model=self.deployment,
                    messages=[
                        {"role": "system", "content": "You are a precise JSON-outputting analytical engine. Return only valid JSON, no markdown."},
                        {"role": "user", "content": prompt},
                    ],
                    max_completion_tokens=2000,
                    response_format={"type": "json_object"},
                )
                raw_content = response.choices[0].message.content
                # Strip markdown code fences if model wrapped output
                raw_content = raw_content.strip()
                if raw_content.startswith("```"):
                    raw_content = raw_content.split("```")[1]
                    if raw_content.startswith("json"):
                        raw_content = raw_content[4:]
                    raw_content = raw_content.strip()
                structured_data = json.loads(raw_content)
                logger.info(f"ReasoningPipeline: gpt-5.5 report generated for {meeting_id} — verified={structured_data.get('is_verified')}")


            else:
                # ── Fallback: structured report from available data ───────────
                logger.warning("Azure OpenAI not configured — generating data-driven fallback report.")

                # Use Sherlock identity result if available
                id_pid = identity_result.get("identified_participant_id")
                id_name = identity_result.get("identified_display_name", "Unknown")
                id_score = identity_result.get("score", 0.0)
                id_conf = identity_result.get("confidence", 0.0)
                is_verified = id_score >= 0.70 and id_conf >= 0.65

                reasons = []
                if identity_result:
                    reasons.append(
                        f"Sherlock identity engine matched '{id_name}' to candidate '{candidate}' "
                        f"with score={id_score:.2f}, confidence={id_conf:.2f}."
                    )
                if num_transcripts > 0:
                    reasons.append(f"Audio pipeline produced {num_transcripts} transcript segment(s).")
                if matches:
                    reasons.append(f"{len(matches)} identity match(es) recorded in the identity database.")
                if not reasons:
                    reasons.append("Insufficient evidence collected — audio processing may still be running.")

                flags = []
                if not self.client:
                    flags.append("Azure OpenAI not configured — AI-powered reasoning unavailable.")
                if not identity_result:
                    flags.append("Sherlock identity pipeline produced no result (candidate name may be missing).")
                if num_transcripts == 0:
                    flags.append("No transcript segments captured — check Azure Speech / Groq credentials.")

                structured_data = {
                    "meeting_id": meeting_id,
                    "candidate": candidate,
                    "identified_participant_id": id_pid,
                    "is_verified": is_verified,
                    "confidence_score": round(id_score, 4),
                    "summary": (
                        f"Interview session for candidate '{candidate}' processed. "
                        f"Sherlock identity engine {'verified' if is_verified else 'could not verify'} the candidate "
                        f"(score={id_score:.2f}). "
                        f"{num_transcripts} transcript segment(s) captured."
                    ),
                    "evidence_reasons": reasons,
                    "flags": flags,
                }

            # ── Persist to MongoDB ───────────────────────────────────────────
            await db.reasoning_reports.update_one(
                {"meeting_id": meeting_id},
                {"$set": structured_data},
                upsert=True,
            )

            logger.info(f"ReasoningPipeline: Report persisted for {meeting_id} — verified={structured_data.get('is_verified')}")
            return structured_data

        except Exception as e:
            import traceback
            logger.error(f"ReasoningPipeline failed for {meeting_id}: {e}\n{traceback.format_exc()}")
            return None


reasoning_pipeline = ReasoningPipeline()
