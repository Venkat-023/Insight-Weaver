import json
import logging
import re
import time
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import get_settings

logger = logging.getLogger("scientific_discovery.gemma")


class GemmaEngine:
    def __init__(self, model_name: str | None = None, timeout_seconds: int | None = None) -> None:
        import ollama

        self.settings = get_settings()
        # Prefer explicitly passed model_name; fall back to settings (which warmup may have patched)
        self.model_name = model_name or self.settings.gemma_reasoning_model
        self.temperature = 0.25
        self.max_retries = 3
        self.ollama = ollama
        self.client = ollama.Client(
            host=self.settings.ollama_host,
            timeout=timeout_seconds or self.settings.gemma_timeout_seconds,
        )

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        num_predict: int | None = None,
        num_ctx: int | None = None,
    ) -> str:
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((ConnectionError, TimeoutError, self.ollama.ResponseError)),
            reraise=True,
        )
        def _call() -> str:
            started = time.perf_counter()
            options: dict[str, Any] = {"temperature": self.temperature if temperature is None else temperature}
            if num_predict is not None:
                options["num_predict"] = num_predict
            if num_ctx is not None:
                options["num_ctx"] = num_ctx
            if self.settings.gemma_num_thread:
                options["num_thread"] = self.settings.gemma_num_thread
            response = self.client.generate(
                model=self.model_name,
                prompt=prompt,
                options=options,
                keep_alive=self.settings.gemma_keep_alive,
            )
            latency = time.perf_counter() - started
            text = response.get("response", "")
            logger.info(
                "gemma_call latency=%.3fs model=%s prompt_words=%d response_words=%d",
                latency,
                self.model_name,
                len(prompt.split()),
                len(text.split()),
            )
            return text

        return _call()

    def generate_structured(self, prompt: str, schema_hint: str = "") -> dict[str, Any]:
        full_prompt = (
            f"{prompt}\n\n{schema_hint}\n\n"
            "Respond ONLY with valid JSON. No markdown, no backticks, no preamble."
        )
        first_response = self.generate(full_prompt)
        parsed = self._parse_json(first_response)
        if parsed is not None:
            return parsed
        # Second attempt with explicit reminder
        second_response = self.generate(full_prompt + "\n\nRemember: output ONLY raw JSON, nothing else.")
        parsed = self._parse_json(second_response)
        if parsed is not None:
            return parsed
        raise ValueError(f"Gemma returned invalid JSON after 2 attempts. Last response: {first_response[:200]}")

    @staticmethod
    def _parse_json(response: str) -> dict[str, Any] | None:
        if not response:
            return None
        # Direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        # Strip markdown fences
        cleaned = re.sub(r"```(?:json)?", "", response).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Find first JSON object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def extract_entities(self, text: str) -> dict[str, Any]:
        prompt = f"""You are a scientific entity extraction specialist. Analyze this scientific text and extract named entities and relationships.

TEXT:
{text}

Return a JSON object with keys:
- entities: list of {{name, type, description}}
- relationships: list of {{source, target, relationship_type, confidence}}

Types: DISEASE, DRUG, GENE, PROTEIN, METHOD, DATASET, METRIC, CONCEPT
"""
        try:
            return self.generate_structured(prompt)
        except Exception:
            return {"entities": [], "relationships": []}

    def generate_hypothesis(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = f"""You are an AI co-scientist specialising in identifying breakthrough research opportunities.
Your outputs will be reviewed by domain experts. Be scientifically rigorous.

RESEARCH QUERY: {context.get("query", "")}

RETRIEVED EVIDENCE FROM PAPERS:
{context.get("chunks_text", context.get("retrieved_chunks", ""))}

KNOWLEDGE GRAPH CONTEXT:
Entities involved: {json.dumps(context.get("entities", []))}
Known relationships: {json.dumps(context.get("relationships", []))}

IDENTIFIED KNOWLEDGE GAPS:
{json.dumps(context.get("knowledge_gaps", []))}

CROSS-DOMAIN CONNECTIONS FOUND:
{json.dumps(context.get("cross_domain_connections", []))}

YOUR TASK:
Generate exactly {context.get("num_hypotheses", 3)} scientifically novel research hypotheses that:
1. Address at least one identified knowledge gap
2. Are grounded entirely in the provided evidence (no unsupported claims)
3. Are testable with methods that currently exist
4. Have potential for meaningful scientific impact
5. Are NOT already explicitly stated in any of the retrieved papers

STRICT OUTPUT — valid JSON only, no markdown, no backticks, no preamble:
{{
  "hypotheses": [
    {{
      "id": 1,
      "hypothesis": "Clear, single-sentence testable hypothesis statement",
      "reasoning": "3-5 sentence mechanistic explanation of why this is plausible",
      "supporting_evidence": [{{"paper_title": "title", "section": "section name", "excerpt": "quote", "relevance": "why"}}],
      "confidence": 0.0,
      "novelty_score": 0.0,
      "testability": "high",
      "suggested_experiments": ["specific experiment"],
      "falsifiable_conditions": "what result would disprove this hypothesis",
      "research_gaps_addressed": ["gap"],
      "cross_domain_insight": "insight"
    }}
  ],
  "meta_insights": {{"dominant_themes": [], "most_promising_direction": "", "critical_missing_experiments": []}}
}}
"""
        output = self.generate_structured(prompt)
        if "hypotheses" not in output or "meta_insights" not in output:
            raise ValueError("Hypothesis response missing required keys: hypotheses, meta_insights")
        return output

    def detect_contradiction(self, text_a: str, text_b: str, topic: str) -> dict[str, Any]:
        prompt = f"""Analyse these two research excerpts on the topic: "{topic}"

PAPER A:
{text_a[:2000]}

PAPER B:
{text_b[:2000]}

Determine if these papers contradict each other. Look for opposite conclusions, conflicting quantitative results, different causal claims, or methodological incompatibilities.

STRICT OUTPUT — valid JSON only:
{{
  "has_contradiction": false,
  "severity": "LOW",
  "contradiction_type": "results",
  "paper_a_claim": "",
  "paper_b_claim": "",
  "explanation": "",
  "resolution_suggestion": ""
}}
"""
        try:
            return self.generate_structured(prompt)
        except Exception:
            return {
                "has_contradiction": False,
                "severity": "LOW",
                "contradiction_type": "model_error",
                "paper_a_claim": "",
                "paper_b_claim": "",
                "explanation": "Model could not analyse these papers.",
                "resolution_suggestion": "Retry with a smaller excerpt or faster model.",
            }

    def run_agent_turn(self, agent_role: str, agent_context: str, debate_history: list[dict]) -> str:
        prompt = f"""You are acting as: {agent_role}

Context:
{agent_context}

Debate history so far:
{json.dumps(debate_history, indent=2)}

Respond with rigorous, concise scientific reasoning from your role.
"""
        return self.generate(prompt)
