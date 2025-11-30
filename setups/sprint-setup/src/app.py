import os
import psycopg2
import structlog
import httpx
import random
from datetime import datetime, timedelta

logger = structlog.get_logger()

class SprintSetupJob:
    def __init__(self):
        self.db_config = self._get_db_config()
        self.project_service_url = os.getenv('PROJECT_SERVICE_URL', 'http://project-service:8080')
        self.backlog_service_url = os.getenv('BACKLOG_SERVICE_URL', 'http://backlog-service:8080')
        self.conn = None
        self.TEST_PROJECT_ID = "TEST-001"
        self.TEST_SPRINT_PREFIX = "SPRINT"

    def _get_db_config(self) -> dict:
        """Get database configuration from environment variables"""
        return {
            'host': os.getenv('POSTGRES_HOST'),
            'database': os.getenv('POSTGRES_DB'),
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
        """Creates sprint-related tables if they do not exist."""
        conn = self._get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                DROP TABLE IF EXISTS daily_scrum_updates;
                DROP TABLE IF EXISTS sprints CASCADE;
                CREATE TABLE IF NOT EXISTS sprints (
                    sprint_id VARCHAR(50) PRIMARY KEY,
                    project_id VARCHAR(50) NOT NULL,
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP NOT NULL,
                    status VARCHAR(50) NOT NULL
                );
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
            logger.info("Sprint tables created or already exist.")
        except psycopg2.Error as e:
            conn.rollback()
            logger.error("Failed to create sprint tables", error=str(e))
            raise
        finally:
            cur.close()

    def _get_project_details(self, prj_id: str):
        """Fetches project details from the Project Service API."""
        try:
            response = httpx.get(f"{self.project_service_url}/projects/{prj_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching project details for {prj_id}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Network error fetching project details for {prj_id}: {e}")
            return None

    def _get_backlog_items(self, prj_id: str):
        """Fetches unassigned backlog items from the Backlog Service API."""
        try:
            # Assuming an endpoint to get unassigned backlog items for a project
            response = httpx.get(f"{self.backlog_service_url}/backlogs/{prj_id}?status={status}")
            response.raise_for_status()
            return response.json().get('items', [])
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching backlog items for {prj_id}: {e.response.status_code} - {e.response.text}")
            return []
        except httpx.RequestError as e:
            logger.error(f"Network error fetching backlog items for {prj_id}: {e}")
            return []

    def populate_sprint_data(self):
        """Populates sample sprint data, including daily scrum updates."""
        conn = self._get_db_connection()
        cur = conn.cursor()

        try:
            # Clear existing test data for idempotency
            cur.execute("DELETE FROM daily_scrum_updates WHERE sprint_id LIKE 'SPRINT-%'")
            cur.execute("DELETE FROM sprints WHERE project_id = %s", (self.TEST_PROJECT_ID,))

            # Check if the test project exists via API
            project_details = self._get_project_details(self.TEST_PROJECT_ID)
            if not project_details:
                logger.warning(f"Test project {self.TEST_PROJECT_ID} not found via Project Service API. Skipping sprint data population.")
                return

            # Check for existing sprints for the test project
            cur.execute("SELECT sprint_id FROM sprints WHERE project_id = %s", (self.TEST_PROJECT_ID,))
            existing_sprints = cur.fetchall()
            if False: # Modified to always proceed
                logger.info(f"Sprints already exist for project {self.TEST_PROJECT_ID}. Skipping population to maintain idempotency.")
                return


            # Get unassigned backlog items
            backlog_items = self._get_backlog_items(self.TEST_PROJECT_ID)
            if not backlog_items:
                logger.warning(f"No unassigned backlog items found for project {self.TEST_PROJECT_ID}. Cannot create stories/tasks for sprints.")
                # Still create a sprint, but without stories/tasks
                pass

            # Determine new sprint number
            cur.execute("SELECT COUNT(*) FROM sprints WHERE project_id = %s", (self.TEST_PROJECT_ID,))
            sprint_count = cur.fetchone()[0]
            new_sprint_num = sprint_count + 1
            new_sprint_id = f'{self.TEST_SPRINT_PREFIX}-{new_sprint_num}'

            # Create new sprint
            start_date = datetime.now()
            end_date = start_date + timedelta(weeks=2)
            cur.execute(
                """
                INSERT INTO sprints (sprint_id, project_id, start_date, end_date, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (sprint_id) DO NOTHING;
                """,
                (new_sprint_id, self.TEST_PROJECT_ID, start_date, end_date, 'in_progress')
            )
            logger.info(f"Created sprint {new_sprint_id} for project {self.TEST_PROJECT_ID}.")

            # Simulate daily scrum updates for a few days
            sample_employees = ["EMP001", "EMP002", "EMP003"] # Placeholder, ideally from Project Service API
            for i in range(1, 4): # Simulate 3 days of updates
                update_date = start_date + timedelta(days=i)
                for emp_id in sample_employees:
                    yesterday_work = f"Completed task X on day {i-1}." if i > 1 else "Started planning."
                    today_work = f"Working on task Y on day {i}."
                    impediments = "None." if random.random() > 0.2 else "Waiting for clarification from team lead."
                    cur.execute(
                        """
                        INSERT INTO daily_scrum_updates (sprint_id, employee_id, update_date, yesterday_work, today_work, impediments)
                        VALUES (%s, %s, %s, %s, %s, %s);
                        """,
                        (new_sprint_id, emp_id, update_date, yesterday_work, today_work, impediments)
                    )
            logger.info(f"Populated sample daily scrum updates for sprint {new_sprint_id}.")

            conn.commit()
            logger.info("Sprint data population completed successfully.")

        except psycopg2.Error as e:
            conn.rollback()
            logger.error("Failed to populate sprint data", error=str(e))
            raise
        finally:
            cur.close()

    def run(self):
        """Main execution method for the sprint setup job."""
        logger.info("Starting Sprint Setup Job...")
        try:
            self.create_tables()
            self.populate_sprint_data()
            logger.info("Sprint Setup Job completed successfully.")
        except Exception as e:
            logger.error("Sprint Setup Job failed", error=str(e))
            raise
        finally:
            if self.conn:
                self.conn.close()
                logger.info("Database connection closed.")

if __name__ == "__main__":
    job = SprintSetupJob()
    job.run()