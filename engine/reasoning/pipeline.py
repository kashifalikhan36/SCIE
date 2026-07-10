import os
import json
import logging
from typing import Dict, Any, Optional
from openai import AsyncAzureOpenAI
from database.mongodb import get_mongo_db
from engine.identity.config import identity_config

logger = logging.getLogger("SCIE.reasoning_engine.pipeline")

class ReasoningPipeline:
    """Invokes GPT-5.5 to synthesize fusion evidence into a structured JSON explainability report."""
    
    def __init__(self):
        # We can reuse the Azure OpenAI credentials from identity_config,
        # but point to a reasoning deployment, e.g. gpt-5.5 (or fallback to gpt-4)
        api_key = identity_config.AZURE_OPENAI_API_KEY
        endpoint = identity_config.AZURE_OPENAI_ENDPOINT
        api_version = identity_config.AZURE_OPENAI_API_VERSION
        
        self.deployment = os.getenv("REASONING_DEPLOYMENT", "gpt-4")
        
        if api_key and endpoint:
            self.client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version
            )
        else:
            self.client = None
            logger.warning("ReasoningPipeline: Azure OpenAI credentials missing.")

    async def generate_reasoning(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Extracts meeting fusion data and generates structured JSON reasoning."""
        if not self.client:
            logger.error("Cannot generate reasoning: OpenAI client not initialized.")
            return None
            
        try:
            db = get_mongo_db()
            # Gather fusion results
            rankings = await db.fusion_ranking_snapshots.find({"meeting_id": meeting_id}).sort("timestamp", -1).limit(1).to_list(1)
            ranking_doc = rankings[0] if rankings else {}
            
            # Gather identity evidence matches
            matches = await db.identity_matches.find({"meeting_id": meeting_id}).to_list(10)
            
            # We construct a prompt for the reasoning engine
            prompt = f"""
You are the SCIE Sherlock Reasoning Engine (powered by GPT-5.5).
Your task is to analyze the evidence from the interview and determine if the candidate was definitively the person who attended, and explain your reasoning clearly based on visual, audio, and metadata evidence.

Meeting ID: {meeting_id}
Latest Fusion Ranking: {json.dumps(ranking_doc, default=str)}
Identity Matches: {json.dumps(matches, default=str)}

Provide a structured JSON output with the following schema exactly:
{{
    "meeting_id": "{meeting_id}",
    "identified_participant_id": "<ID of the most likely candidate, or null>",
    "is_verified": true/false,
    "confidence_score": <float 0.0-1.0>,
    "summary": "<A 2-3 sentence summary of the verification>",
    "evidence_reasons": [
        "<Reason 1>",
        "<Reason 2>"
    ],
    "flags": [
        "<Any suspicious anomalies like low visual similarity or stale tracks>"
    ]
}}

Return ONLY valid JSON.
"""

            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are a precise JSON-outputting analytical engine."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.2
            )
            
            output_text = response.choices[0].message.content
            structured_data = json.loads(output_text)
            
            # Persist reasoning report to MongoDB
            await db.reasoning_reports.update_one(
                {"meeting_id": meeting_id},
                {"$set": structured_data},
                upsert=True
            )
            
            logger.info(f"Generated reasoning report for meeting {meeting_id}")
            return structured_data
            
        except Exception as e:
            logger.error(f"ReasoningPipeline failed: {e}")
            return None

reasoning_pipeline = ReasoningPipeline()
