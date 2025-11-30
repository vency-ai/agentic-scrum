"""
Unit tests for OllamaAdvisor service.

Tests cover prompt construction, response parsing, error handling, and health checks.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from httpx import AsyncClient, HTTPStatusError, TimeoutException, Response
import httpx

from services.ollama_advisor import OllamaAdvisor, AdvisoryResponse


class TestOllamaAdvisor:
    """Test suite for OllamaAdvisor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service_url = "http://test-ollama:11434"
        self.model = "llama3.2:latest"
        self.timeout = 5.0
        self.advisor = OllamaAdvisor(
            service_url=self.service_url,
            model=self.model,
            timeout=self.timeout
        )
        
    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self.advisor, 'client'):
            asyncio.run(self.advisor.client.aclose())

    def test_initialization(self):
        """Test OllamaAdvisor initialization."""
        advisor = OllamaAdvisor(
            service_url="http://test:11434/",  # Test URL cleanup
            model="test-model",
            timeout=10.0
        )
        
        assert advisor.service_url == "http://test:11434"
        assert advisor.model == "test-model"
        assert advisor.timeout == 10.0
        assert isinstance(advisor.client, AsyncClient)

    def test_build_prompt(self):
        """Test prompt construction for different decision scenarios."""
        project_id = "TEST-001"
        
        # Test with intelligence-enhanced decision
        decision = {
            "create_new_sprint": True,
            "tasks_to_assign": 6,
            "sprint_duration_weeks": 2,
            "decision_source": "intelligence_enhanced",
            "reasoning": "Intelligence override: Historical analysis shows 6-task sprints achieve 92% completion",
            "confidence_scores": {"overall_decision_confidence": 0.82},
            "intelligence_adjustments": {
                "task_count_modification": {
                    "original_recommendation": 8,
                    "intelligence_recommendation": 6
                }
            }
        }
        
        analysis = {
            "team_members_count": 5,
            "unassigned_tasks": 8
        }
        
        prompt = self.advisor._build_prompt(project_id, decision, analysis)
        
        assert "TEST-001" in prompt
        assert "Team Size: 5" in prompt
        assert "Tasks to Assign: 6" in prompt
        assert "intelligence_enhanced" in prompt
        assert "Confidence Scores" in prompt
        assert "Intelligence Adjustments" in prompt
        assert "valid JSON" in prompt
        assert '"summary"' in prompt
        assert '"recommendations"' in prompt
        assert '"risk_assessment"' in prompt
        
    def test_build_prompt_rule_based(self):
        """Test prompt construction for rule-based decisions."""
        decision = {
            "create_new_sprint": True,
            "tasks_to_assign": 10,
            "sprint_duration_weeks": 2,
            "decision_source": "rule_based_only",
            "reasoning": "Standard rule-based decision making",
            "confidence_scores": {},
            "intelligence_adjustments": {}
        }
        
        analysis = {"team_members_count": 4, "unassigned_tasks": 10}
        
        prompt = self.advisor._build_prompt("PROJ-002", decision, analysis)
        
        assert "rule_based_only" in prompt
        assert "None" in prompt  # Empty intelligence data
        
    def test_parse_response_valid_json(self):
        """Test parsing valid LLM JSON response."""
        llm_response = '''
        Some preamble text
        {
          "summary": "This decision appears well-justified based on historical data.",
          "recommendations": [
            "Monitor velocity during first 3 days",
            "Consider adding tasks if team exceeds expectations"
          ],
          "risk_assessment": "Low"
        }
        Some trailing text
        '''
        
        result = self.advisor._parse_response(llm_response)
        
        assert result["summary"] == "This decision appears well-justified based on historical data."
        assert len(result["recommendations"]) == 2
        assert "Monitor velocity" in result["recommendations"][0]
        assert result["risk_assessment"] == "Low"
        
    def test_parse_response_invalid_risk_assessment(self):
        """Test parsing response with invalid risk assessment."""
        llm_response = '''{"summary": "Test", "recommendations": [], "risk_assessment": "Invalid"}'''
        
        result = self.advisor._parse_response(llm_response)
        
        assert result["risk_assessment"] == "Low"  # Should default to Low
        
    def test_parse_response_malformed_json(self):
        """Test parsing malformed JSON response."""
        llm_response = '''{"summary": "Test", "recommendations": [,] "risk_assessment": "Low"}'''
        
        result = self.advisor._parse_response(llm_response)
        
        # Should return fallback response
        assert "successfully" in result["summary"]
        assert isinstance(result["recommendations"], list)
        assert result["risk_assessment"] == "Low"
        
    def test_parse_response_no_json(self):
        """Test parsing response with no JSON."""
        llm_response = "This is just plain text with no JSON structure."
        
        result = self.advisor._parse_response(llm_response)
        
        # Should return fallback response
        assert "successfully" in result["summary"]
        assert isinstance(result["recommendations"], list)
        assert result["risk_assessment"] == "Low"

    def test_parse_response_limits_content(self):
        """Test that response parsing limits content length."""
        long_summary = "A" * 1000
        many_recommendations = ["Recommendation"] * 10
        
        llm_response = json.dumps({
            "summary": long_summary,
            "recommendations": many_recommendations,
            "risk_assessment": "Medium"
        })
        
        result = self.advisor._parse_response(llm_response)
        
        assert len(result["summary"]) <= 500
        assert len(result["recommendations"]) <= 3
        assert result["risk_assessment"] == "Medium"

    @patch('services.ollama_advisor.httpx.AsyncClient.post')
    async def test_call_ollama_success(self, mock_post):
        """Test successful Ollama API call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Test LLM response"}
        mock_post.return_value = mock_response
        
        result = await self.advisor._call_ollama("Test prompt")
        
        assert result == "Test LLM response"
        mock_post.assert_called_once()
        
        # Check API call parameters
        call_args = mock_post.call_args
        assert call_args[1]["json"]["model"] == self.model
        assert call_args[1]["json"]["prompt"] == "Test prompt"
        assert call_args[1]["json"]["stream"] is False
        
    @patch('services.ollama_advisor.httpx.AsyncClient.post')
    async def test_call_ollama_timeout(self, mock_post):
        """Test Ollama API timeout handling."""
        mock_post.side_effect = TimeoutException("Request timeout")
        
        with pytest.raises(asyncio.TimeoutError, match="Ollama API timeout"):
            await self.advisor._call_ollama("Test prompt")
            
    @patch('services.ollama_advisor.httpx.AsyncClient.post')
    async def test_call_ollama_http_error(self, mock_post):
        """Test Ollama API HTTP error handling."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        
        mock_post.side_effect = HTTPStatusError(
            "500 Server Error",
            request=Mock(),
            response=mock_response
        )
        
        with pytest.raises(Exception, match="Ollama API error: 500"):
            await self.advisor._call_ollama("Test prompt")

    @patch('services.ollama_advisor.httpx.AsyncClient.get')
    async def test_health_check_success(self, mock_get):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "other-model:latest"}
            ]
        }
        mock_get.return_value = mock_response
        
        result = await self.advisor.health_check()
        
        assert result["status"] == "ok"
        assert result["service_url"] == self.service_url
        assert result["model"] == self.model
        assert "llama3.2:latest" in result["available_models"]
        assert result["model_available"] is True
        
    @patch('services.ollama_advisor.httpx.AsyncClient.get')
    async def test_health_check_model_not_available(self, mock_get):
        """Test health check when model is not available."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "other-model:latest"}]
        }
        mock_get.return_value = mock_response
        
        result = await self.advisor.health_check()
        
        assert result["status"] == "ok"
        assert result["model_available"] is False
        
    @patch('services.ollama_advisor.httpx.AsyncClient.get')
    async def test_health_check_error(self, mock_get):
        """Test health check error handling."""
        mock_get.side_effect = Exception("Connection failed")
        
        result = await self.advisor.health_check()
        
        assert result["status"] == "error"
        assert "Connection failed" in result["error"]

    @patch.object(OllamaAdvisor, '_call_ollama')
    async def test_review_decision_success(self, mock_call_ollama):
        """Test successful decision review."""
        mock_call_ollama.return_value = json.dumps({
            "summary": "Well-justified decision",
            "recommendations": ["Monitor progress"],
            "risk_assessment": "Low"
        })
        
        project_id = "TEST-001"
        decision = {"create_new_sprint": True, "tasks_to_assign": 6}
        analysis = {"team_members_count": 5}
        
        result = await self.advisor.review_decision(project_id, decision, analysis)
        
        assert isinstance(result, AdvisoryResponse)
        assert result.enabled is True
        assert result.summary == "Well-justified decision"
        assert len(result.recommendations) == 1
        assert result.risk_assessment == "Low"
        assert result.generation_time_ms > 0
        assert result.model == self.model
        
    @patch.object(OllamaAdvisor, '_call_ollama')
    async def test_review_decision_timeout(self, mock_call_ollama):
        """Test decision review timeout handling."""
        mock_call_ollama.side_effect = asyncio.TimeoutError("Timeout")
        
        result = await self.advisor.review_decision("TEST-001", {}, {})
        
        assert isinstance(result, AdvisoryResponse)
        assert result.enabled is False
        assert "timeout" in result.error.lower()
        assert "AI advisor unavailable" in result.fallback
        assert result.generation_time_ms == int(self.timeout * 1000)
        
    @patch.object(OllamaAdvisor, '_call_ollama')
    async def test_review_decision_general_error(self, mock_call_ollama):
        """Test decision review general error handling."""
        mock_call_ollama.side_effect = Exception("Network error")
        
        result = await self.advisor.review_decision("TEST-001", {}, {})
        
        assert isinstance(result, AdvisoryResponse)
        assert result.enabled is False
        assert "Network error" in result.error
        assert "AI advisor unavailable" in result.fallback

    def test_advisory_response_to_dict(self):
        """Test AdvisoryResponse dictionary conversion."""
        # Test successful response
        response = AdvisoryResponse(enabled=True)
        response.model = "llama3.2:latest"
        response.summary = "Test summary"
        response.recommendations = ["Test recommendation"]
        response.risk_assessment = "Medium"
        response.generation_time_ms = 1500
        
        result = response.to_dict()
        
        assert result["enabled"] is True
        assert result["model"] == "llama3.2:latest"
        assert result["summary"] == "Test summary"
        assert result["recommendations"] == ["Test recommendation"]
        assert result["risk_assessment"] == "Medium"
        assert result["generation_time_ms"] == 1500
        assert "error" not in result
        
    def test_advisory_response_to_dict_error(self):
        """Test AdvisoryResponse dictionary conversion with error."""
        response = AdvisoryResponse(enabled=False, error="Test error")
        response.fallback = "Using fallback"
        response.generation_time_ms = 5000
        
        result = response.to_dict()
        
        assert result["enabled"] is False
        assert result["error"] == "Test error"
        assert result["fallback"] == "Using fallback"
        assert result["generation_time_ms"] == 5000
        assert "summary" not in result
        assert "recommendations" not in result

    async def test_close(self):
        """Test advisor cleanup."""
        with patch.object(self.advisor.client, 'aclose', new_callable=AsyncMock) as mock_aclose:
            await self.advisor.close()
            mock_aclose.assert_called_once()


class TestAdvisoryResponse:
    """Test suite for AdvisoryResponse class."""
    
    def test_initialization_success(self):
        """Test successful response initialization."""
        response = AdvisoryResponse(enabled=True)
        
        assert response.enabled is True
        assert response.model is None
        assert response.summary is None
        assert response.recommendations == []
        assert response.risk_assessment is None
        assert response.generation_time_ms == 0
        assert response.error is None
        assert response.fallback is None
        
    def test_initialization_error(self):
        """Test error response initialization."""
        response = AdvisoryResponse(enabled=False, error="Test error")
        
        assert response.enabled is False
        assert response.error == "Test error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])