import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import structlog
import logging
from typing import Optional, List, Dict, Any

from psycopg2.extras import RealDictCursor

from database import db_pool

logger = structlog.get_logger(__name__)

class AnalyticsEngine:
    def __init__(self):
        self.project_service_url = os.getenv("PROJECT_SERVICE_URL", "http://project-service.dsm.svc.cluster.local")
        self.cache = {} # Simple in-memory cache

    async def _execute_query(self, query: str, params: tuple = None, fetch_one: bool = False):
        conn = None
        try:
            conn = db_pool.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch_one:
                    result = cursor.fetchone()
                else:
                    result = cursor.fetchall()

                # Explicitly parse JSONB fields if they are strings
                if result:
                    if isinstance(result, list):
                        for row in result:
                            for key, value in row.items():
                                if isinstance(value, str) and (key == 'additional_data' or key == 'tasks_summary'):
                                    try:
                                        row[key] = json.loads(value)
                                    except json.JSONDecodeError:
                                        logger.warning(f"Failed to decode JSON for {key}: {value}")
                                        row[key] = {} # Default to empty dict on decode error
                    elif isinstance(result, dict):
                        for key, value in result.items():
                            if isinstance(value, str) and (key == 'additional_data' or key == 'tasks_summary'):
                                try:
                                    result[key] = json.loads(value)
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to decode JSON for {key}: {value}")
                                    result[key] = {} # Default to empty dict on decode error
                return result
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise
        finally:
            if conn:
                db_pool.put_connection(conn)

    async def get_decision_impact_report(self, project_id: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> Dict[str, Any]:
        logger.info(f"Generating decision impact report for project {project_id}")

        _end_date = end_date if end_date else datetime.utcnow()
        _start_date = start_date if start_date else (_end_date - timedelta(days=30))

        # 1. Fetch orchestration decision audit events
        decision_audits_query = """
        SELECT id, project_id, sprint_id, created_at, additional_data
        FROM chronicle_notes
        WHERE project_id = %s
          AND event_type = 'daily_scrum_report' -- Orchestrator logs decisions as daily_scrum_report
          AND additional_data -> 'orchestration_decision_details' IS NOT NULL
          AND created_at BETWEEN %s AND %s
        ORDER BY created_at ASC;
        """
        decision_audits_raw = await self._execute_query(decision_audits_query, (project_id, _start_date, _end_date))
        
        # Parse decision audits to extract relevant info
        orchestration_decisions = {} # Key: sprint_id, Value: decision_details
        for audit in decision_audits_raw:
            additional_data = audit.get('additional_data', {})
            orchestration_decision_details = additional_data.get('orchestration_decision_details', {})
            
            # Ensure additional_data is parsed if it's a string
            if isinstance(additional_data, str):
                try:
                    additional_data = json.loads(additional_data)
                    orchestration_decision_details = additional_data.get('orchestration_decision_details', {})
                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode additional_data for audit {audit.get('id')}")
                    continue

            # Extract sprint_id from the decision details or the main audit record
            sprint_id = audit.get('sprint_id')
            if not sprint_id and orchestration_decision_details.get('sprint_id'):
                sprint_id = orchestration_decision_details['sprint_id']
            elif not sprint_id and additional_data.get('sprint_id'):
                sprint_id = additional_data['sprint_id']

            if sprint_id:
                orchestration_decisions[sprint_id] = {
                    "audit_id": str(audit['id']),
                    "project_id": audit['project_id'],
                    "sprint_id": sprint_id,
                    "decision_source": orchestration_decision_details.get('decision_type', 'unknown'), # Map to decision_source
                    "timestamp": audit['created_at'].isoformat(),
                    "intelligence_adjustments": additional_data.get('intelligence_adjustments', {})
                }
        logger.debug(f"Parsed orchestration decisions: {orchestration_decisions}")

        # 2. Fetch sprint retrospective outcomes
        retrospectives_query = """
        SELECT sprint_id, project_id, tasks_summary, start_date, end_date
        FROM sprint_retrospectives
        WHERE project_id = %s
          AND start_date BETWEEN %s AND %s
        ORDER BY start_date ASC;
        """
        retrospectives_raw = await self._execute_query(retrospectives_query, (project_id, _start_date, _end_date))
        
        sprint_outcomes = {} # Key: sprint_id, Value: outcome_details
        for retro in retrospectives_raw:
            sprint_id = retro['sprint_id']
            tasks_summary = retro.get('tasks_summary', [])
            
            # Ensure tasks_summary is parsed if it's a string
            if isinstance(tasks_summary, str):
                try:
                    tasks_summary = json.loads(tasks_summary)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode tasks_summary for retrospective {retro.get('id')}")
                    tasks_summary = []

            total_tasks = 0
            completed_tasks = 0
            for task in tasks_summary:
                total_tasks += 1
                if task.get('status') == 'close' or task.get('progress_percentage', 0) >= 100:
                    completed_tasks += 1
            
            completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0
            success = completion_rate >= 0.8 # Heuristic for success

            sprint_outcomes[sprint_id] = {
                "completion_rate": round(completion_rate, 2),
                "success": success,
                "actual_duration_weeks": (retro['end_date'] - retro['start_date']).days / 7 if retro['start_date'] and retro['end_date'] else None,
                "actual_task_count": total_tasks
            }
        logger.debug(f"Parsed sprint outcomes: {sprint_outcomes}")

        # 3. Correlate decisions with outcomes and aggregate
        all_decisions_details = []
        intelligence_enhanced_decisions = []
        rule_based_decisions = []

        for sprint_id, decision_data in orchestration_decisions.items():
            outcome_data = sprint_outcomes.get(sprint_id)
            
            if outcome_data:
                combined_record = {**decision_data, **outcome_data}
                all_decisions_details.append(combined_record)

                if "intelligence_enhanced" in decision_data["decision_source"].lower():
                    intelligence_enhanced_decisions.append(combined_record)
                else:
                    rule_based_decisions.append(combined_record)
            else:
                # Include decisions without a direct outcome for completeness, but mark missing outcome
                all_decisions_details.append({**decision_data, "completion_rate": None, "success": None, "notes": "Outcome data not yet available."})
        
        total_decisions_analyzed = len(all_decisions_details)
        intelligence_enhanced_count = len(intelligence_enhanced_decisions)
        rule_based_count = len(rule_based_decisions)

        intel_completion_rates = [d["completion_rate"] for d in intelligence_enhanced_decisions if d["completion_rate"] is not None]
        rule_completion_rates = [d["completion_rate"] for d in rule_based_decisions if d["completion_rate"] is not None]

        intelligence_completion_rate_avg = sum(intel_completion_rates) / len(intel_completion_rates) if intel_completion_rates else 0.0
        rule_based_completion_rate_avg = sum(rule_completion_rates) / len(rule_completion_rates) if rule_completion_rates else 0.0

        completion_rate_improvement_percent = 0.0
        if rule_based_completion_rate_avg > 0:
            completion_rate_improvement_percent = ((intelligence_completion_rate_avg - rule_based_completion_rate_avg) / rule_based_completion_rate_avg) * 100

        # Placeholders for other metrics
        task_efficiency_improvement_percent = 0.0
        resource_utilization_improvement_percent = 0.0

        report = {
            "time_period": {
                "start_date": _start_date.isoformat(),
                "end_date": _end_date.isoformat()
            },
            "total_decisions_analyzed": total_decisions_analyzed,
            "intelligence_enhanced_decisions": intelligence_enhanced_count,
            "rule_based_decisions": rule_based_count,
            "intelligence_completion_rate_avg": round(intelligence_completion_rate_avg, 3),
            "rule_based_completion_rate_avg": round(rule_based_completion_rate_avg, 3),
            "completion_rate_improvement_percent": round(completion_rate_improvement_percent, 2),
            "task_efficiency_improvement_percent": task_efficiency_improvement_percent,
            "resource_utilization_improvement_percent": resource_utilization_improvement_percent,
            "details": all_decisions_details
        }
        logger.info(f"[INFO] Returning decision impact report for project {project_id}: {report}")
        return report

    async def get_system_summary_metrics(self):
        conn = None
        try:
            conn = db_pool.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if fetch_one:
                    result = cursor.fetchone()
                else:
                    result = cursor.fetchall()

                # Explicitly parse JSONB fields if they are strings
                if result:
                    if isinstance(result, list):
                        for row in result:
                            for key, value in row.items():
                                if isinstance(value, str) and (key == 'additional_data' or key == 'tasks_summary'):
                                    try:
                                        row[key] = json.loads(value)
                                    except json.JSONDecodeError:
                                        logger.warning(f"Failed to decode JSON for {key}: {value}")
                                        row[key] = {} # Default to empty dict on decode error
                    elif isinstance(result, dict):
                        for key, value in result.items():
                            if isinstance(value, str) and (key == 'additional_data' or key == 'tasks_summary'):
                                try:
                                    result[key] = json.loads(value)
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to decode JSON for {key}: {value}")
                                    result[key] = {} # Default to empty dict on decode error
                return result
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise
        finally:
            if conn:
                db_pool.put_connection(conn)

    async def get_system_summary_metrics(self):
        query = """
        SELECT
            (SELECT COUNT(DISTINCT project_id) FROM chronicle_notes) AS total_projects,
            (SELECT COUNT(DISTINCT sprint_id) FROM sprint_retrospectives) AS total_sprints,
            (SELECT COUNT(*) FROM chronicle_notes WHERE event_type = 'daily_scrum_report') AS total_daily_scrum_reports,
            (SELECT COUNT(*) FROM sprint_retrospectives) AS total_retrospectives,
            (SELECT COUNT(*) FROM retrospective_action_items WHERE status = 'open') AS total_action_items_open,
            (SELECT COUNT(*) FROM retrospective_action_items WHERE status = 'closed') AS total_action_items_closed;
        """
        result = await self._execute_query(query, fetch_one=True)
        if result:
            total_action_items = result['total_action_items_open'] + result['total_action_items_closed']
            overall_health = "Good" if result['total_action_items_open'] < total_action_items * 0.2 else "Needs Attention"
            return {
                "total_projects": result['total_projects'],
                "total_sprints": result['total_sprints'],
                "total_daily_scrum_reports": result['total_daily_scrum_reports'],
                "total_retrospectives": result['total_retrospectives'],
                "total_action_items": total_action_items,
                "overall_system_health": overall_health,
                "summary_analysis": "Aggregated metrics across all DSM projects, providing a high-level overview of activity and historical data."
            }
        return {}

    async def get_project_patterns(self, project_id: str):
        logger.info(f"Getting project patterns for {project_id}")
        cache_key = f"project_patterns_{project_id}"
        if cache_key in self.cache:
            logger.info(f"Returning cached project patterns for {project_id}")
            return self.cache[cache_key]

        daily_scrums_query = """
        SELECT additional_data, report_date
        FROM chronicle_notes
        WHERE project_id = %s AND event_type = 'daily_scrum_report'
        ORDER BY report_date DESC;
        """
        daily_scrums = await self._execute_query(daily_scrums_query, (project_id,))

        retrospectives_query = """
        SELECT id, sprint_id, what_went_well, what_could_be_improved, tasks_summary
        FROM sprint_retrospectives
        WHERE project_id = %s
        ORDER BY start_date DESC;
        """
        retrospectives = await self._execute_query(retrospectives_query, (project_id,))

        total_tasks_completed_in_daily_scrums = 0
        common_impediments = defaultdict(int)
        common_retrospective_action_items = defaultdict(int)

        for scrum in daily_scrums:
            if scrum['additional_data'] and isinstance(scrum['additional_data'], dict):
                for date_key, reports in scrum['additional_data'].items():
                    if reports is None:
                        continue
                    if isinstance(reports, bool):
                        logger.warning(f"Skipping boolean report for date {date_key}: {reports}")
                        continue
                    if isinstance(reports, str):
                        try:
                            reports = json.loads(reports)
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode reports string for date {date_key}: {reports}")
                            continue
                    if not isinstance(reports, list):
                        reports = [reports]
                    
                    for report_item in reports:
                        report = {}
                        try:
                            if isinstance(report_item, str):
                                report = json.loads(report_item)
                            elif isinstance(report_item, dict):
                                report = report_item
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode report item: {report_item}")
                            continue

                        for task in report.get('tasks', []):
                            if 'impediments' in task and task['impediments'] and task['impediments'].lower() != 'none.':
                                common_impediments[task['impediments']] += 1
                            if 'new_total_progress' in task and task['new_total_progress'] >= 100:
                                total_tasks_completed_in_daily_scrums += 1
                            elif 'status' in task and task['status'].lower() == 'completed':
                                total_tasks_completed_in_daily_scrums += 1

        for retro in retrospectives:
            action_items_query = """
            SELECT description FROM retrospective_action_items WHERE retrospective_id = %s;
            """
            action_items = await self._execute_query(action_items_query, (retro['id'],))
            for item in action_items:
                common_retrospective_action_items[item['description']] += 1

        patterns_analysis_summary = f"Detailed analysis of project patterns for {project_id} based on {len(daily_scrums)} daily scrums and {len(retrospectives)} retrospectives."

        result = {
            "project_id": project_id,
            "metrics": {
                "daily_scrum_count": len(daily_scrums),
                "retrospective_count": len(retrospectives),
                "total_tasks_completed_in_daily_scrums": total_tasks_completed_in_daily_scrums,
            },
            "common_impediments_reported": dict(common_impediments),
            "common_retrospective_action_items": dict(common_retrospective_action_items),
            "patterns_analysis_summary": patterns_analysis_summary
        }
        logger.info(f"Project patterns for {project_id}: {result}")
        self.cache[cache_key] = result
        return result

    async def get_project_velocity(self, project_id: str):
        cache_key = f"project_velocity_{project_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        sprints_query = """
        SELECT sprint_id, start_date, end_date, tasks_summary
        FROM sprint_retrospectives
        WHERE project_id = %s
        ORDER BY start_date;
        """
        sprints = await self._execute_query(sprints_query, (project_id,))

        velocity_trend_data = []
        total_completed_tasks = 0
        for sprint in sprints:
            completed_tasks_in_sprint = 0
            if sprint['tasks_summary'] and isinstance(sprint['tasks_summary'], list):
                for task_item in sprint['tasks_summary']:
                    task = {}
                    try:
                        if isinstance(task_item, str):
                            task = json.loads(task_item)
                        elif isinstance(task_item, dict):
                            task = task_item
                    except json.JSONDecodeError:
                        logger.warning(f"Could not decode task item: {task_item}")
                        continue
                    
                    if task.get('status') == 'close' or task.get('progress_percentage') == 100:
                        completed_tasks_in_sprint += 1
            velocity_trend_data.append({
                "sprint_id": sprint['sprint_id'],
                "start_date": sprint['start_date'].strftime('%Y-%m-%d') if sprint['start_date'] else None,
                "end_date": sprint['end_date'].strftime('%Y-%m-%d') if sprint['end_date'] else None,
                "completed_tasks": completed_tasks_in_sprint
            })
            total_completed_tasks += completed_tasks_in_sprint

        average_velocity = total_completed_tasks / len(sprints) if sprints else 0

        result = {
            "project_id": project_id,
            "velocity_trend_data": velocity_trend_data,
            "average_velocity": round(average_velocity, 2),
            "velocity_analysis": "Analysis of tasks completed per sprint over time."
        }
        self.cache[cache_key] = result
        return result

    async def get_project_impediments(self, project_id: str):
        cache_key = f"project_impediments_{project_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        impediment_frequency = defaultdict(int)
        impediment_status_counts = defaultdict(lambda: defaultdict(int))

        daily_scrums_query = """
        SELECT additional_data
        FROM chronicle_notes
        WHERE project_id = %s AND event_type = 'daily_scrum_report';
        """
        daily_scrums = await self._execute_query(daily_scrums_query, (project_id,))

        for scrum in daily_scrums:
            if scrum['additional_data'] and isinstance(scrum['additional_data'], dict):
                for date_key, reports in scrum['additional_data'].items():
                    if reports is None:
                        continue
                    if isinstance(reports, bool):
                        logger.warning(f"Skipping boolean report for date {date_key}: {reports}")
                        continue
                    if isinstance(reports, str):
                        try:
                            reports = json.loads(reports)
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode reports string for date {date_key}: {reports}")
                            continue
                    if not isinstance(reports, list):
                        reports = [reports]
                        
                    for report_item in reports:
                        report = {}
                        try:
                            if isinstance(report_item, str):
                                report = json.loads(report_item)
                            elif isinstance(report_item, dict):
                                report = report_item
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode report item: {report_item}")
                            continue

                        for task in report.get('tasks', []):
                            impediment = task.get('impediments')
                            if impediment and impediment.lower() != 'none.':
                                impediment_frequency[impediment] += 1
                                impediment_status_counts[impediment]['open'] += 1

        retrospective_action_items_query = """
        SELECT description, status
        FROM retrospective_action_items rai
        JOIN sprint_retrospectives sr ON rai.retrospective_id = sr.id
        WHERE sr.project_id = %s;
        """
        action_items = await self._execute_query(retrospective_action_items_query, (project_id,))

        for item in action_items:
            impediment_frequency[item['description']] += 1
            impediment_status_counts[item['description']][item['status']] += 1

        result = {
            "project_id": project_id,
            "impediment_frequency": dict(impediment_frequency),
            "impediment_status_counts": {k: dict(v) for k, v in impediment_status_counts.items()},
            "impediment_analysis_summary": "Analysis of common impediments and their resolution status."
        }
        self.cache[cache_key] = result
        return result

    async def get_similar_projects(self, reference_project_id: str, similarity_threshold: float = 0.7):
        logger.info(f"Getting similar projects for {reference_project_id}")
        cache_key = f"similar_projects_{reference_project_id}_{similarity_threshold}"
        if cache_key in self.cache:
            logger.info(f"Returning cached similar projects for {reference_project_id}")
            return self.cache[cache_key]

        reference_patterns = await self.get_project_patterns(reference_project_id)
        if not reference_patterns:
            return []

        all_projects_query = """
        SELECT DISTINCT project_id FROM chronicle_notes;
        """
        all_projects_data = await self._execute_query(all_projects_query)
        all_project_ids = [p['project_id'] for p in all_projects_data if p['project_id'] != reference_project_id]

        similar_projects = []
        for project_id in all_project_ids:
            current_project_patterns = await self.get_project_patterns(project_id)
            if not current_project_patterns:
                continue

            score = self._calculate_similarity_score(reference_patterns, current_project_patterns)
            if score >= similarity_threshold:
                # Fetch full details for the similar project to enrich the response
                project_details = await self.get_project_summary_for_similarity(project_id)
                project_details['similarity_score'] = round(score, 2)
                similar_projects.append(project_details)
        
        similar_projects.sort(key=lambda x: x['similarity_score'], reverse=True)

        result = similar_projects
        self.cache[cache_key] = result  # Re-enable caching
        return result

    async def get_project_summary_for_similarity(self, project_id: str) -> dict:
        logger.debug(f"[DEBUG] Entering get_project_summary_for_similarity for project: {project_id}")
        """
        Fetches a consolidated summary for a project, intended for the 'similar_projects' response.
        This method calculates completion_rate, avg_sprint_duration, and optimal_task_count.
        """
        retrospectives_query = """
        SELECT id, sprint_id, what_went_well, what_could_be_improved, tasks_summary, start_date, end_date
        FROM sprint_retrospectives
        WHERE project_id = %s;
        """
        retrospectives = await self._execute_query(retrospectives_query, (project_id,))
        logger.debug(f"[DEBUG] get_project_summary_for_similarity: Retrospectives for {project_id}: {retrospectives}")

        total_tasks = 0
        completed_tasks = 0
        total_duration_days = 0
        sprint_task_counts = defaultdict(int)
        sprint_completion_rates = defaultdict(list)  # Changed to store list of completion rates

        for retro in retrospectives:
            logger.debug(f"[DEBUG] Processing retrospective: {retro.get('sprint_id')}")
            sprint_total = 0
            sprint_completed = 0
            if retro['tasks_summary'] and isinstance(retro['tasks_summary'], list):
                for task_item in retro['tasks_summary']:
                    # Ensure task_item is a dictionary, even if it was a string that failed to parse earlier
                    task = {}
                    if isinstance(task_item, dict):
                        task = task_item
                    elif isinstance(task_item, str):
                        try:
                            task = json.loads(task_item)
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode task item in tasks_summary: {task_item}")
                            continue # Skip malformed task

                    sprint_total += 1
                    total_tasks += 1
                    if task.get('status') == 'close' or task.get('progress_percentage', 0) >= 100:
                        sprint_completed += 1
                        completed_tasks += 1
            
            logger.debug(f"[DEBUG] Sprint {retro.get('sprint_id')}: sprint_total={sprint_total}, sprint_completed={sprint_completed}")

            if sprint_total > 0:
                sprint_task_counts[sprint_total] += 1
                # Store individual completion rates for proper averaging
                current_completion_rate = sprint_completed / sprint_total
                sprint_completion_rates[sprint_total].append(current_completion_rate)
            
            logger.debug(f"[DEBUG] After processing retro {retro.get('sprint_id')}: sprint_task_counts={sprint_task_counts}, sprint_completion_rates={sprint_completion_rates}")

            if retro['start_date'] and retro['end_date']:
                total_duration_days += (retro['end_date'] - retro['start_date']).days

        # Calculate average completion rates for each task count
        avg_completion_rates = {}
        for task_count, rates_list in sprint_completion_rates.items():
            if rates_list:
                avg_completion_rates[task_count] = sum(rates_list) / len(rates_list)
        
        logger.debug(f"[DEBUG] Calculated avg_completion_rates for {project_id}: {avg_completion_rates}")

        completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0
        avg_sprint_duration = (total_duration_days / len(retrospectives)) if retrospectives else 0
        
        optimal_task_count = 0
        if avg_completion_rates:
            # Find the task count with the highest average completion rate
            optimal_task_count = max(avg_completion_rates, key=avg_completion_rates.get)
        
        logger.debug(f"[DEBUG] Final optimal_task_count for {project_id}: {optimal_task_count}, avg_completion_rates: {avg_completion_rates}")

        return {
            "project_id": project_id,
            "team_size": 0, # Placeholder, would need to get from Project Service
            "avg_task_complexity": 0.0, # Placeholder
            "domain_category": "unknown", # Placeholder
            "project_duration": 0.0, # Placeholder
            "completion_rate": round(completion_rate, 2),
            "avg_sprint_duration": round(avg_sprint_duration, 2),
            "optimal_task_count": optimal_task_count,
            "key_success_factors": ["derived_from_retrospectives"]
        }

    def _calculate_similarity_score(self, patterns1: dict, patterns2: dict) -> float:
        logger.info(f"Calculating similarity score between {patterns1.get('project_id')} and {patterns2.get('project_id')}")
        logger.debug(f"Patterns 1: {patterns1}")
        logger.debug(f"Patterns 2: {patterns2}")
        score = 0.0
        
        impediments1 = set(patterns1.get('common_impediments_reported', {}).keys())
        impediments2 = set(patterns2.get('common_impediments_reported', {}).keys())
        common_impediments = len(impediments1.intersection(impediments2))
        total_impediments = len(impediments1.union(impediments2))
        if total_impediments > 0:
            score += (common_impediments / total_impediments) * 0.4

        action_items1 = set(patterns1.get('common_retrospective_action_items', {}).keys())
        action_items2 = set(patterns2.get('common_retrospective_action_items', {}).keys())
        common_action_items = len(action_items1.intersection(action_items2))
        total_action_items = len(action_items1.union(action_items2))
        if total_action_items > 0:
            score += (common_action_items / total_action_items) * 0.6
        
        logger.info(f"Similarity score: {score}")
        return score