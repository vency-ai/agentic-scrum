import logging
import json
from typing import List, Dict, Any, Optional
from .embedding_client import EmbeddingClient
from .models import Episode

logger = logging.getLogger(__name__)

class EpisodeEmbedder:
    """Converts Episode objects into text representations and embeddings"""
    
    def __init__(self, embedding_client: EmbeddingClient):
        self.embedding_client = embedding_client
    
    def episode_to_text(self, episode: Episode) -> str:
        """Convert Episode to text representation for embedding generation"""
        
        # Extract key information from perception
        perception_text = self._extract_perception_text(episode.perception)
        
        # Extract key information from reasoning
        reasoning_text = self._extract_reasoning_text(episode.reasoning)
        
        # Extract key information from action
        action_text = self._extract_action_text(episode.action)
        
        # Combine into coherent text
        text_parts = []
        
        # Add project context
        text_parts.append(f"Project: {episode.project_id}")
        
        # Add perception context
        if perception_text:
            text_parts.append(f"Context: {perception_text}")
        
        # Add reasoning process
        if reasoning_text:
            text_parts.append(f"Analysis: {reasoning_text}")
        
        # Add action taken
        if action_text:
            text_parts.append(f"Decision: {action_text}")
        
        # Add outcome if available
        if episode.outcome:
            outcome_text = self._extract_outcome_text(episode.outcome)
            if outcome_text:
                text_parts.append(f"Result: {outcome_text}")
        
        # Add quality rating if available
        if episode.outcome_quality is not None:
            text_parts.append(f"Quality: {episode.outcome_quality:.2f}")
        
        # Join all parts
        full_text = " | ".join(text_parts)
        
        logger.debug(f"Episode {episode.episode_id} converted to text ({len(full_text)} chars)")
        return full_text
    
    def _extract_perception_text(self, perception: Dict[str, Any]) -> str:
        """Extract meaningful text from perception data"""
        text_parts = []
        
        # Handle common perception fields
        if 'backlog_tasks' in perception:
            text_parts.append(f"backlog has {perception['backlog_tasks']} tasks")
        
        if 'team_size' in perception:
            text_parts.append(f"team of {perception['team_size']} members")
        
        if 'current_sprint' in perception:
            text_parts.append(f"current sprint: {perception['current_sprint']}")
        
        if 'workload' in perception:
            text_parts.append(f"workload: {perception['workload']}")
        
        if 'blockers' in perception:
            blockers = perception['blockers']
            if isinstance(blockers, list) and blockers:
                text_parts.append(f"blockers: {', '.join(str(b) for b in blockers)}")
            elif blockers:
                text_parts.append(f"blockers present: {blockers}")
        
        if 'available_capacity' in perception:
            text_parts.append(f"capacity: {perception['available_capacity']}")
        
        # Handle generic fields
        for key, value in perception.items():
            if key not in ['backlog_tasks', 'team_size', 'current_sprint', 'workload', 'blockers', 'available_capacity']:
                if isinstance(value, (str, int, float, bool)):
                    text_parts.append(f"{key}: {value}")
                elif isinstance(value, (list, dict)) and len(str(value)) < 100:
                    text_parts.append(f"{key}: {value}")
        
        return ", ".join(text_parts)
    
    def _extract_reasoning_text(self, reasoning: Dict[str, Any]) -> str:
        """Extract meaningful text from reasoning data"""
        text_parts = []
        
        # Handle common reasoning fields
        if 'decision' in reasoning:
            text_parts.append(f"decided to {reasoning['decision']}")
        
        if 'rationale' in reasoning:
            text_parts.append(f"reasoning: {reasoning['rationale']}")
        
        if 'confidence' in reasoning:
            text_parts.append(f"confidence: {reasoning['confidence']}")
        
        if 'alternatives_considered' in reasoning:
            alternatives = reasoning['alternatives_considered']
            if isinstance(alternatives, list) and alternatives:
                text_parts.append(f"considered: {', '.join(str(a) for a in alternatives)}")
        
        if 'risk_assessment' in reasoning:
            text_parts.append(f"risk: {reasoning['risk_assessment']}")
        
        if 'final_recommendation' in reasoning:
            rec = reasoning['final_recommendation']
            if isinstance(rec, dict):
                if 'reasoning' in rec:
                    text_parts.append(f"recommendation: {rec['reasoning']}")
                if 'action' in rec:
                    text_parts.append(f"recommended action: {rec['action']}")
            else:
                text_parts.append(f"recommendation: {rec}")
        
        # Handle generic fields
        for key, value in reasoning.items():
            if key not in ['decision', 'rationale', 'confidence', 'alternatives_considered', 'risk_assessment', 'final_recommendation']:
                if isinstance(value, (str, int, float, bool)):
                    text_parts.append(f"{key}: {value}")
                elif isinstance(value, (list, dict)) and len(str(value)) < 100:
                    text_parts.append(f"{key}: {value}")
        
        return ", ".join(text_parts)
    
    def _extract_action_text(self, action: Dict[str, Any]) -> str:
        """Extract meaningful text from action data"""
        text_parts = []
        
        # Handle common action fields
        if 'sprint_created' in action:
            if action['sprint_created']:
                text_parts.append("created new sprint")
        
        if 'tasks_assigned' in action:
            tasks = action['tasks_assigned']
            if isinstance(tasks, int):
                text_parts.append(f"assigned {tasks} tasks")
            elif isinstance(tasks, list):
                text_parts.append(f"assigned tasks: {', '.join(str(t) for t in tasks)}")
        
        if 'workflow_update' in action:
            text_parts.append(f"workflow: {action['workflow_update']}")
        
        if 'notifications_sent' in action:
            notifications = action['notifications_sent']
            if isinstance(notifications, int):
                text_parts.append(f"sent {notifications} notifications")
            elif isinstance(notifications, list):
                text_parts.append(f"notified: {', '.join(str(n) for n in notifications)}")
        
        if 'status_change' in action:
            text_parts.append(f"status changed to: {action['status_change']}")
        
        if 'type' in action:
            text_parts.append(f"action type: {action['type']}")
        
        # Handle generic fields
        for key, value in action.items():
            if key not in ['sprint_created', 'tasks_assigned', 'workflow_update', 'notifications_sent', 'status_change', 'type']:
                if isinstance(value, (str, int, float, bool)):
                    text_parts.append(f"{key}: {value}")
                elif isinstance(value, (list, dict)) and len(str(value)) < 100:
                    text_parts.append(f"{key}: {value}")
        
        return ", ".join(text_parts)
    
    def _extract_outcome_text(self, outcome: Dict[str, Any]) -> str:
        """Extract meaningful text from outcome data"""
        text_parts = []
        
        # Handle common outcome fields
        if 'result' in outcome:
            text_parts.append(f"result: {outcome['result']}")
        
        if 'success' in outcome:
            text_parts.append(f"success: {outcome['success']}")
        
        if 'metrics' in outcome:
            metrics = outcome['metrics']
            if isinstance(metrics, dict):
                for metric_key, metric_value in metrics.items():
                    text_parts.append(f"{metric_key}: {metric_value}")
        
        if 'feedback' in outcome:
            text_parts.append(f"feedback: {outcome['feedback']}")
        
        if 'duration' in outcome:
            text_parts.append(f"duration: {outcome['duration']}")
        
        # Handle generic fields
        for key, value in outcome.items():
            if key not in ['result', 'success', 'metrics', 'feedback', 'duration']:
                if isinstance(value, (str, int, float, bool)):
                    text_parts.append(f"{key}: {value}")
                elif isinstance(value, (list, dict)) and len(str(value)) < 100:
                    text_parts.append(f"{key}: {value}")
        
        return ", ".join(text_parts)
    
    async def embed_episode(self, episode: Episode) -> List[float]:
        """Generate embedding for an episode"""
        try:
            # Convert episode to text
            episode_text = self.episode_to_text(episode)
            
            # Generate embedding
            embedding = await self.embedding_client.generate_embedding(episode_text)
            
            logger.info(f"Generated embedding for episode {episode.episode_id} from {len(episode_text)} chars")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to embed episode {episode.episode_id}: {e}")
            raise
    
    async def embed_episodes_batch(self, episodes: List[Episode]) -> List[List[float]]:
        """Generate embeddings for multiple episodes"""
        try:
            # Convert episodes to text
            episode_texts = [self.episode_to_text(episode) for episode in episodes]
            
            # Generate batch embeddings
            embeddings = await self.embedding_client.generate_batch_embeddings(episode_texts)
            
            logger.info(f"Generated {len(embeddings)} embeddings for episode batch")
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to embed episode batch: {e}")
            raise
    
    async def embed_query(self, query_text: str) -> List[float]:
        """Generate embedding for a query text (for similarity search)"""
        try:
            embedding = await self.embedding_client.generate_embedding(query_text)
            logger.debug(f"Generated query embedding from {len(query_text)} chars")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            raise
    
    def create_query_from_context(self, context: Dict[str, Any]) -> str:
        """Create query text from context for similarity search"""
        
        # Use similar logic to episode_to_text but for context
        text_parts = []
        
        # Handle common context fields
        if 'backlog_tasks' in context:
            text_parts.append(f"backlog has {context['backlog_tasks']} tasks")
        
        if 'team_size' in context:
            text_parts.append(f"team of {context['team_size']} members")
        
        if 'current_sprint' in context:
            text_parts.append(f"current sprint: {context['current_sprint']}")
        
        if 'workload' in context:
            text_parts.append(f"workload: {context['workload']}")
        
        if 'decision_needed' in context:
            text_parts.append(f"decision needed: {context['decision_needed']}")
        
        if 'goal' in context:
            text_parts.append(f"goal: {context['goal']}")
        
        # Handle generic fields
        for key, value in context.items():
            if key not in ['backlog_tasks', 'team_size', 'current_sprint', 'workload', 'decision_needed', 'goal']:
                if isinstance(value, (str, int, float, bool)):
                    text_parts.append(f"{key}: {value}")
                elif isinstance(value, (list, dict)) and len(str(value)) < 100:
                    text_parts.append(f"{key}: {value}")
        
        query_text = "Context: " + ", ".join(text_parts)
        logger.debug(f"Created query from context: {len(query_text)} chars")
        return query_text
    
    async def close(self):
        """Close embedding client"""
        await self.embedding_client.close()