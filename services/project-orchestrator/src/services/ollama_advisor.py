"""
AI Agent Decision Advisor using local Ollama LLM infrastructure.

This service provides natural language explanations and recommendations
for orchestration decisions, making them accessible to non-technical stakeholders.
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
import httpx
import structlog
from datetime import datetime

logger = structlog.get_logger()


class AdvisoryResponse:
    """Structured response from the AI advisor."""
    
    def __init__(self, enabled: bool = False, error: Optional[str] = None):
        self.enabled = enabled
        self.model = None
        self.summary = None
        self.recommendations = []
        self.risk_assessment = None
        self.generation_time_ms = 0
        self.error = error
        self.fallback = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "enabled": self.enabled,
            "generation_time_ms": self.generation_time_ms
        }
        
        if self.error:
            result["error"] = self.error
            if self.fallback:
                result["fallback"] = self.fallback
        else:
            result.update({
                "model": self.model,
                "summary": self.summary,
                "recommendations": self.recommendations,
                "risk_assessment": self.risk_assessment
            })
        
        return result


class OllamaAdvisor:
    """AI Agent Decision Advisor using Ollama LLM."""
    
    def __init__(self, service_url: str, model: str = "llama3.2:latest", timeout: float = 5.0):
        """Initialize the Ollama advisor.
        
        Args:
            service_url: Ollama service URL (e.g., "http://ollama-server.dsm.svc.cluster.local:11434")
            model: LLM model to use (default: "llama3.2:latest")
            timeout: Request timeout in seconds (default: 5.0)
        """
        self.service_url = service_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        
        logger.info("OllamaAdvisor initialized", 
                   service_url=service_url, model=model, timeout=timeout)

    async def review_decision(self, 
                            project_id: str, 
                            decision: Dict[str, Any], 
                            analysis: Dict[str, Any]) -> AdvisoryResponse:
        """Review an orchestration decision and provide AI-powered advisory.
        
        Args:
            project_id: Project identifier
            decision: Final orchestration decision
            analysis: Project analysis context
            
        Returns:
            AdvisoryResponse with natural language summary, recommendations, and risk assessment
        """
        start_time = datetime.now()
        response = AdvisoryResponse(enabled=True)
        response.model = self.model
        
        try:
            # Build focused prompt for the LLM
            prompt = self._build_prompt(project_id, decision, analysis)
            
            # Call Ollama API
            llm_response = await self._call_ollama(prompt)
            
            # Parse structured response
            advisory_data = self._parse_response(llm_response)
            
            # Populate response
            response.summary = advisory_data.get("summary", "Decision analysis completed.")
            response.recommendations = advisory_data.get("recommendations", [])
            response.risk_assessment = advisory_data.get("risk_assessment", "Low")
            
            # Calculate generation time
            response.generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            logger.info("AI advisory generated successfully",
                       project_id=project_id,
                       generation_time_ms=response.generation_time_ms,
                       risk_assessment=response.risk_assessment,
                       num_recommendations=len(response.recommendations))
            
            return response
            
        except asyncio.TimeoutError:
            response.enabled = False
            response.error = "Advisory timeout - proceeding with standard decision"
            response.fallback = "AI advisor unavailable - using standard decision process"
            response.generation_time_ms = int(self.timeout * 1000)
            
            logger.warning("AI advisory timeout",
                          project_id=project_id,
                          timeout_seconds=self.timeout)
            
            return response
            
        except Exception as e:
            response.enabled = False
            response.error = f"Advisory generation failed: {str(e)[:100]}"
            response.fallback = "AI advisor unavailable - using standard decision process"
            response.generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            logger.error("AI advisory generation failed",
                        project_id=project_id,
                        error=str(e),
                        generation_time_ms=response.generation_time_ms,
                        exc_info=True)
            
            return response

    def _build_prompt(self, project_id: str, decision: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """Build a focused prompt for the LLM based on orchestration context."""
        
        # Extract key decision elements
        create_sprint = decision.get("create_new_sprint", False)
        tasks_assigned = decision.get("tasks_to_assign", 0)
        sprint_duration = decision.get("sprint_duration_weeks", 2)
        decision_source = decision.get("decision_source", "rule_based_only")
        reasoning = decision.get("reasoning", "No reasoning provided")
        
        # Extract analysis context
        team_size = analysis.get("team_members_count", 0)
        unassigned_tasks = analysis.get("unassigned_tasks", 0)
        confidence_scores = decision.get("confidence_scores", {})
        intelligence_adjustments = decision.get("intelligence_adjustments", {})
        
        prompt = f"""You are an AI assistant helping explain project management decisions to stakeholders.

CONTEXT:
- Project ID: {project_id}
- Team Size: {team_size}
- Available Tasks: {unassigned_tasks}

DECISION MADE:
- Create New Sprint: {create_sprint}
- Tasks to Assign: {tasks_assigned}
- Sprint Duration: {sprint_duration} weeks
- Decision Source: {decision_source}
- Reasoning: {reasoning}

INTELLIGENCE DATA:
- Confidence Scores: {json.dumps(confidence_scores, indent=2) if confidence_scores else "None"}
- Intelligence Adjustments: {json.dumps(intelligence_adjustments, indent=2) if intelligence_adjustments else "None"}

TASK: Provide a brief, clear explanation that non-technical stakeholders (Product Managers, Scrum Masters) can understand.

Respond with ONLY valid JSON in this exact format:
{{
  "summary": "A 2-3 sentence summary explaining the decision and its rationale",
  "recommendations": ["Action item 1", "Action item 2"],
  "risk_assessment": "Low|Medium|High"
}}

Focus on practical insights and actionable recommendations. Keep language professional but accessible."""

        return prompt

    async def _call_ollama(self, prompt: str) -> str:
        """Make async HTTP call to Ollama API with timeout protection."""
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Lower temperature for more consistent responses
                "num_predict": 500,  # Limit response length
                "stop": ["\n\n"]    # Stop at double newlines
            }
        }
        
        url = f"{self.service_url}/api/generate"
        
        logger.debug("Calling Ollama API",
                    url=url,
                    model=self.model,
                    prompt_length=len(prompt))
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            llm_response = result.get("response", "")
            
            logger.debug("Ollama API response received",
                        response_length=len(llm_response),
                        status_code=response.status_code)
            
            return llm_response
            
        except httpx.TimeoutException:
            logger.warning("Ollama API timeout", url=url, timeout=self.timeout)
            raise asyncio.TimeoutError("Ollama API timeout")
            
        except httpx.HTTPStatusError as e:
            logger.error("Ollama API HTTP error",
                        url=url,
                        status_code=e.response.status_code,
                        response_text=e.response.text[:200])
            raise Exception(f"Ollama API error: {e.response.status_code}")
            
        except Exception as e:
            logger.error("Ollama API call failed", url=url, error=str(e))
            raise

    def _parse_response(self, llm_response: str) -> Dict[str, Any]:
        """Parse LLM response into structured advisory data."""
        
        # Clean up the response - remove any text before/after JSON
        response_text = llm_response.strip()
        
        # Find JSON boundaries
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        
        if start_idx == -1 or end_idx == 0:
            logger.warning("No JSON found in LLM response", response_text=response_text[:200])
            return {
                "summary": "Decision processed successfully with available data.",
                "recommendations": ["Monitor project progress closely"],
                "risk_assessment": "Low"
            }
        
        json_text = response_text[start_idx:end_idx]
        
        try:
            parsed = json.loads(json_text)
            
            # Validate required fields and provide defaults
            result = {
                "summary": parsed.get("summary", "Decision processed successfully."),
                "recommendations": parsed.get("recommendations", []),
                "risk_assessment": parsed.get("risk_assessment", "Low")
            }
            
            # Validate risk_assessment value
            if result["risk_assessment"] not in ["Low", "Medium", "High"]:
                result["risk_assessment"] = "Low"
                
            # Ensure recommendations is a list
            if not isinstance(result["recommendations"], list):
                result["recommendations"] = []
                
            # Limit recommendation count and length
            result["recommendations"] = result["recommendations"][:3]  # Max 3 recommendations
            result["recommendations"] = [rec[:200] for rec in result["recommendations"]]  # Max 200 chars each
            
            # Limit summary length
            result["summary"] = result["summary"][:500]  # Max 500 characters
            
            logger.debug("LLM response parsed successfully",
                        summary_length=len(result["summary"]),
                        num_recommendations=len(result["recommendations"]),
                        risk_assessment=result["risk_assessment"])
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM JSON response",
                          json_text=json_text[:200],
                          error=str(e))
            
            # Fallback response
            return {
                "summary": "Decision completed based on available project data and rules.",
                "recommendations": ["Continue monitoring project metrics"],
                "risk_assessment": "Low"
            }

    async def health_check(self) -> Dict[str, Any]:
        """Check if Ollama service is available and responsive."""
        try:
            url = f"{self.service_url}/api/tags"
            response = await self.client.get(url, timeout=3.0)
            response.raise_for_status()
            
            models_data = response.json()
            models = [model.get("name", "unknown") for model in models_data.get("models", [])]
            
            return {
                "status": "ok",
                "service_url": self.service_url,
                "model": self.model,
                "available_models": models,
                "model_available": self.model in models
            }
            
        except Exception as e:
            logger.error("Ollama health check failed",
                        service_url=self.service_url,
                        error=str(e))
            
            return {
                "status": "error",
                "service_url": self.service_url,
                "model": self.model,
                "error": str(e)[:100]
            }

    async def close(self):
        """Clean up resources."""
        await self.client.aclose()
        logger.info("OllamaAdvisor client closed")