import asyncio
import argparse
import json
import os
import sys
from typing import Dict, Any, List

# Adjust path to import modules from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient, DataQualityReport
from config_loader import get_config

async def run_data_quality_analysis(project_id: str) -> DataQualityReport:
    config = get_config()
    chronicle_service_url = config["external_services"]["chronicle_service_url"]
    client = ChronicleAnalyticsClient(chronicle_service_url=chronicle_service_url)
    report = await client.validate_data_availability(project_id)
    await client.client.aclose() # Close httpx client session
    return report

def generate_human_readable_report(project_id: str, report: DataQualityReport) -> str:
    report_str = f"### Data Quality Report for Project: {project_id}\n\n"
    report_str += f"- **Data Available**: {report.data_available}\n"
    report_str += f"- **Historical Sprints**: {report.historical_sprints if report.historical_sprints is not None else 'N/A'}\n"
    report_str += f"- **Average Completion Rate**: {report.avg_completion_rate if report.avg_completion_rate is not None else 'N/A'}\n"
    report_str += f"- **Common Team Velocity**: {report.common_team_velocity if report.common_team_velocity is not None else 'N/A'}\n"
    report_str += f"- **Data Quality Score**: {report.data_quality_score if report.data_quality_score is not None else 'N/A'}\n"
    report_str += f"- **Observation Note**: {report.observation_note}\n"
    
    if report.recommendations:
        report_str += "\n- **Recommendations**:\n"
        for rec in report.recommendations:
            report_str += f"  - {rec}\n"
    else:
        report_str += "\n- **Recommendations**: None\n"

    return report_str

async def main():
    parser = argparse.ArgumentParser(description="Run data quality analysis for a project.")
    parser.add_argument("--project-id", required=True, help="The ID of the project to analyze.")
    parser.add_argument("--output-report", action="store_true", help="Output a human-readable report to stdout.")
    args = parser.parse_args()

    print(f"Running data quality analysis for project: {args.project_id}")
    report = await run_data_quality_analysis(args.project_id)
    print(f"Analysis complete. Data available: {report.data_available}")

    if args.output_report:
        human_report = generate_human_readable_report(args.project_id, report)
        print("\n" + human_report)
    else:
        print("\nRaw Data Quality Report (JSON):")
        print(json.dumps(report.dict(), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
