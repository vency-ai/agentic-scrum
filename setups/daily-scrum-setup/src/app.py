import os
import psycopg2
import structlog
import httpx
import random
from datetime import datetime, timedelta

logger = structlog.get_logger()

class DailyScrumSetupJob:
    def __init__(self):
        self.db_config = self._get_db_config()
        self.project_service_url = os.getenv('PROJECT_SERVICE_URL', 'http://project-service:80')
        self.sprint_service_url = os.getenv('SPRINT_SERVICE_URL', 'http://sprint-service:8080') # Assuming sprint service runs on 8080
        self.backlog_service_url = os.getenv('BACKLOG_SERVICE_URL', 'http://backlog-service:8080') # Assuming backlog service runs on 8080
        self.conn = None
        self.TEST_PROJECT_ID = "TEST-001"

    def _get_db_config(self) -> dict:
        """Get database configuration from environment variables"""
        return {
            'host': os.getenv('POSTGRES_HOST'),
            'dbname': os.getenv('POSTGRES_DB'),
            'user': os.getenv('POSTGRES_USER'),
            'password': os.getenv('POSTGRES_PASSWORD')
        }

    def _get_db_connection(self):
        """Establishes and returns a new database connection."""
        if self.conn and not self.conn.closed:
            return self.conn
        try:
            self.conn = psycopg2.connect(**self.db_config)
            logger.info("Database connection established.")
            return self.conn
        except psycopg2.Error as e:
            logger.error("Failed to connect to database", error=str(e))
            raise

    def create_tables(self):
        """Ensures daily_scrum_updates table exists. (It should be created by sprint-setup-job, but for robustness)"""
        conn = self._get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_scrum_updates (
                    id SERIAL PRIMARY KEY,
                    sprint_id VARCHAR(50) NOT NULL,
                    employee_id VARCHAR(50) NOT NULL,
                    update_date TIMESTAMP NOT NULL,
                    yesterday_work TEXT,
                    today_work TEXT,
                    impediments TEXT,
                    FOREIGN KEY (sprint_id) REFERENCES sprints(id)
                );
            """)
            conn.commit()
            logger.info("Daily scrum updates table created or already exists.")
        except psycopg2.Error as e:
            conn.rollback()
            logger.error("Failed to create daily scrum updates table", error=str(e))
            raise
        finally:
            cur.close()

    def _get_project_team_members(self, prj_id: str):
        """Fetches team members for a project from the Project Service API."""
        try:
            response = httpx.get(f"{self.project_service_url}/projects/{prj_id}/team-members")
            response.raise_for_status()
            return response.json().get('team_members', [])
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching team members for {prj_id}: {e.response.status_code} - {e.response.text}")
            return []
        except httpx.RequestError as e:
            logger.error(f"Network error fetching team members for {prj_id}: {e}")
            return []

    def _get_active_sprint(self, prj_id: str):
        """Fetches the active sprint for a project from the Sprint Service API."""
        try:
            response = httpx.get(f"{self.sprint_service_url}/sprints/by-project/{prj_id}")
            response.raise_for_status()
            sprints_data = response.json()
            for sprint in sprints_data:
                if sprint.get('status') == 'in_progress':
                    return sprint.get('sprint_id')
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching active sprint for {prj_id}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Network error fetching active sprint for {prj_id}: {e}")
            return None

    def populate_daily_scrum_data(self):
        """Populates sample daily scrum updates."""
        conn = self._get_db_connection()
        cur = conn.cursor()

        try:
            # Get team members for the test project
            team_members = self._get_project_team_members(self.TEST_PROJECT_ID)
            if not team_members:
                logger.warning(f"No team members found for project {self.TEST_PROJECT_ID}. Skipping daily scrum data population.")
                return
            employee_ids = [member['id'] for member in team_members]

            # Get active sprint for the test project
            active_sprint_id = self._get_active_sprint(self.TEST_PROJECT_ID)
            if not active_sprint_id:
                logger.warning(f"No active sprint found for project {self.TEST_PROJECT_ID}. Skipping daily scrum data population.")
                return

            # Simulate daily scrum updates for a few days for each employee
            for emp_id in employee_ids:
                for i in range(1, 4): # Simulate 3 days of updates
                    update_date = datetime.now() - timedelta(days=3-i) # Simulate past days
                    
                    # Check if update already exists for idempotency
                    cur.execute(
                        "SELECT COUNT(*) FROM daily_scrum_updates WHERE sprint_id = %s AND employee_id = %s AND update_date::date = %s::date",
                        (active_sprint_id, emp_id, update_date.date())
                    )
                    if cur.fetchone()[0] > 0:
                        logger.info(f"Daily scrum update for {emp_id} on {update_date.date()} already exists. Skipping.")
                        continue

                    yesterday_work = f"Completed tasks for day {i-1}." if i > 1 else "Planned tasks."
                    today_work = f"Working on tasks for day {i}."
                    impediments = "None." if random.random() > 0.2 else "Blocked by external team."
                    
                    cur.execute(
                        """
                        INSERT INTO daily_scrum_updates (sprint_id, employee_id, update_date, yesterday_work, today_work, impediments)
                        VALUES (%s, %s, %s, %s, %s, %s);
                        """,
                        (active_sprint_id, emp_id, update_date, yesterday_work, today_work, impediments)
                    )
                    logger.info(f"Populated daily scrum update for {emp_id} in sprint {active_sprint_id} on {update_date.date()}.")

            conn.commit()
            logger.info("Daily scrum data population completed successfully.")

        except psycopg2.Error as e:
            conn.rollback()
            logger.error("Failed to populate daily scrum data", error=str(e))
            raise
        finally:
            cur.close()

    def run(self):
        """Main execution method for the daily scrum setup job."""
        logger.info("Starting Daily Scrum Setup Job...")
        try:
            self.create_tables()
            self.populate_daily_scrum_data()
            logger.info("Daily Scrum Setup Job completed successfully.")
        except Exception as e:
            logger.error("Daily Scrum Setup Job failed", error=str(e))
            raise
        finally:
            if self.conn:
                self.conn.close()
                logger.info("Database connection closed.")

if __name__ == "__main__":
    job = DailyScrumSetupJob()
    job.run()
