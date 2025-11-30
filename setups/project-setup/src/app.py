import os
import psycopg2
import structlog
from typing import List, Dict, Any
import pandas as pd
from mimesis import Person
from mimesis.enums import Gender
import random
import json
from datetime import date, timedelta

logger = structlog.get_logger()

class ProjectSetupJob:
    def __init__(self):
        self.db_config = self._get_db_config()
        self.conn = None
        
    def _get_db_config(self) -> Dict[str, str]:
        """Get database configuration from environment variables"""
        return {
            'host': os.getenv('POSTGRES_HOST'),
            'dbname': os.getenv('POSTGRES_DB'),
            'user': os.getenv('POSTGRES_USER'),
            'password': os.getenv('POSTGRES_PASSWORD')
        }

    def __enter__(self):
        self.conn = psycopg2.connect(**self.db_config)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def create_tables(self):
        """Create all project-related tables"""
        logger.info("Creating tables...")
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    prjid VARCHAR(10) PRIMARY KEY,
                    projectname VARCHAR(255) NOT NULL,
                    codename VARCHAR(255) NOT NULL,
                    status VARCHAR(50) DEFAULT 'inactive'
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id VARCHAR(10) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    gender VARCHAR(10),
                    state VARCHAR(2),
                    age INTEGER,
                    project_assign BOOLEAN DEFAULT FALSE,
                    active BOOLEAN DEFAULT TRUE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS designations (
                    id VARCHAR(10) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    experience VARCHAR(50),
                    years INTEGER
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    id VARCHAR(10) PRIMARY KEY,
                    role VARCHAR(255) NOT NULL UNIQUE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_team_mapping (
                    project_id VARCHAR(10) NOT NULL,
                    employee_id VARCHAR(10) NOT NULL,
                    PRIMARY KEY (project_id, employee_id),
                    FOREIGN KEY (project_id) REFERENCES projects(prjid) ON DELETE CASCADE,
                    FOREIGN KEY (employee_id) REFERENCES teams(id) ON DELETE CASCADE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS team_designation_mapping (
                    id VARCHAR(10) PRIMARY KEY,
                    did VARCHAR(10) NOT NULL,
                    eid VARCHAR(10) NOT NULL,
                    FOREIGN KEY (did) REFERENCES designations(id) ON DELETE CASCADE,
                    FOREIGN KEY (eid) REFERENCES teams(id) ON DELETE CASCADE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS team_role_mapping (
                    id VARCHAR(10) PRIMARY KEY,
                    rid VARCHAR(10) NOT NULL,
                    eid VARCHAR(10) NOT NULL,
                    FOREIGN KEY (rid) REFERENCES roles(id) ON DELETE CASCADE,
                    FOREIGN KEY (eid) REFERENCES teams(id) ON DELETE CASCADE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS role_designation_mapping (
                    id VARCHAR(10) PRIMARY KEY,
                    roleid VARCHAR(10) NOT NULL,
                    did VARCHAR(10) NOT NULL,
                    FOREIGN KEY (roleid) REFERENCES roles(id) ON DELETE CASCADE,
                    FOREIGN KEY (did) REFERENCES designations(id) ON DELETE CASCADE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pto_calendar (
                    pto_id UUID PRIMARY KEY,
                    employee_id VARCHAR(255),
                    start_date DATE,
                    end_date DATE,
                    reason TEXT,
                    created_at TIMESTAMP
                );
            """)
        self.conn.commit()
        logger.info("Tables created successfully.")

    def populate_projects(self):
        """Populate projects table with sample data"""
        logger.info("Populating projects table...")
        SAMPLE_PROJECTS = [
            {"id": "TEST-001", "name": "Test Project for Sprint Setup", "codename": "TestSprint", "status": "inactive"},
            {"id": "PHE001", "name": "Healthcare Analytics", "codename": "Phoenix", "status": "inactive"},
            {"id": "ORI002", "name": "Retail Automation", "codename": "Orion", "status": "inactive"},
            {"id": "AEG003", "name": "Investment Portfolio Management", "codename": "Aegis", "status": "inactive"},
            {"id": "SEN004", "name": "Maritime Tracking System", "codename": "Sentinel", "status": "inactive"},
            {"id": "NEX005", "name": "IoT in Smart Homes", "codename": "Nexus", "status": "inactive"},
            {"id": "CHR006", "name": "AI Customer Support", "codename": "Chronos", "status": "inactive"},
            {"id": "TIT007", "name": "Blockchain for Finance", "codename": "Titan", "status": "inactive"},
            {"id": "VOY008", "name": "E-commerce Platform", "codename": "Voyager", "status": "inactive"},
            {"id": "APO009", "name": "Smart Inventory Management", "codename": "Apollo", "status": "inactive"},
            {"id": "ZEP010", "name": "Telemedicine Application", "codename": "Zephyr", "status": "inactive"}
        ]
        with self.conn.cursor() as cur:
            for project in SAMPLE_PROJECTS:
                cur.execute(
                    "INSERT INTO projects (prjid, projectname, codename, status) VALUES (%s, %s, %s, %s) ON CONFLICT (prjid) DO UPDATE SET projectname = EXCLUDED.projectname, codename = EXCLUDED.codename, status = EXCLUDED.status",
                    (project['id'], project['name'], project['codename'], project['status'])
                )
        self.conn.commit()
        logger.info("Projects table populated.")

    def populate_teams(self):
        """Populate teams table with sample data"""
        logger.info("Populating teams table...")
        person = Person('en')
        states = [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
        ]
        teams_data = []
        for i in range(1, 101):
            gender = Gender.FEMALE if i % 2 == 0 else Gender.MALE
            teams_data.append({
                'id': f'E{i:03}',
                'name': person.full_name(gender),
                'gender': 'Female' if gender == Gender.FEMALE else 'Male',
                'state': random.choice(states),
                'age': person.age(minimum=22, maximum=60),
                'project_assign': False,
                'active': True
            })
        
        with self.conn.cursor() as cur:
            for team_member in teams_data:
                cur.execute(
                    """
                    INSERT INTO teams (id, name, gender, state, age, project_assign, active) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        team_member['id'], team_member['name'], team_member['gender'],
                        team_member['state'], team_member['age'], team_member['project_assign'],
                        team_member['active']
                    )
                )
        self.conn.commit()
        logger.info("Teams table populated.")

    def populate_designations(self):
        """Populate designations table with sample data"""
        logger.info("Populating designations table...")
        DESIGNATIONS = [
            ('D01', 'Software Engineer', 'Entry-level', 0),
            ('D02', 'Senior Software Engineer', 'Mid-level', 3),
            ('D03', 'Lead Software Engineer', 'Senior-level', 5),
            ('D04', 'Principal Software Engineer', 'Expert-level', 8),
            ('D05', 'Software Architect', 'Architect-level', 10),
            ('D06', 'QA Engineer', 'Entry-level', 0),
            ('D07', 'Senior QA Engineer', 'Mid-level', 3),
            ('D08', 'QA Lead', 'Senior-level', 5),
            ('D09', 'Project Manager', 'Mid-level', 4),
            ('D10', 'Senior Project Manager', 'Senior-level', 7),
            ('D11', 'Product Manager', 'Mid-level', 4),
            ('D12', 'DevOps Engineer', 'Mid-level', 3),
            ('D13', 'Senior DevOps Engineer', 'Senior-level', 6),
            ('D14', 'UI/UX Designer', 'Mid-level', 3),
            ('D15', 'Senior UI/UX Designer', 'Senior-level', 6)
        ]
        with self.conn.cursor() as cur:
            for d in DESIGNATIONS:
                cur.execute(
                    "INSERT INTO designations (id, name, experience, years) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                    d
                )
        self.conn.commit()
        logger.info("Designations table populated.")

    def populate_roles(self):
        """Populate roles table with sample data"""
        logger.info("Populating roles table...")
        ROLES = [
            ('R01', 'Developer'),
            ('R02', 'Tester'),
            ('R03', 'Team Lead'),
            ('R04', 'Architect'),
            ('R05', 'Project Manager'),
            ('R06', 'Product Owner'),
            ('R07', 'Scrum Master'),
            ('R08', 'DevOps Specialist'),
            ('R09', 'UI/UX Specialist')
        ]
        with self.conn.cursor() as cur:
            for r in ROLES:
                cur.execute(
                    "INSERT INTO roles (id, role) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                    r
                )
        self.conn.commit()
        logger.info("Roles table populated.")

    def populate_holidays(self):
        """Populate us_holidays table from JSON file"""
        logger.info("Populating us_holidays table...")
        try:
            with open('/app/us-holiday.json', 'r') as f:
                holidays = json.load(f)
            logger.info(f"Loaded {len(holidays)} holidays from JSON file.")
        except FileNotFoundError:
            logger.error("us-holiday.json not found. Skipping holiday population.")
            return

        with self.conn.cursor() as cur:
            logger.info("Truncating us_holidays table.")
            cur.execute("TRUNCATE TABLE us_holidays")
            
            for holiday in holidays:
                holiday_date = date.fromisoformat(holiday['date'])
                original_date_str = holiday['date']
                
                # If holiday falls on a Saturday, move it to the previous Friday
                if holiday_date.weekday() == 5:
                    holiday_date -= timedelta(days=1)
                    logger.info(f"Adjusted Saturday holiday '{holiday['name']}' from {original_date_str} to {holiday_date.isoformat()}")
                # If holiday falls on a Sunday, move it to the next Monday
                elif holiday_date.weekday() == 6:
                    holiday_date += timedelta(days=1)
                    logger.info(f"Adjusted Sunday holiday '{holiday['name']}' from {original_date_str} to {holiday_date.isoformat()}")
                
                logger.info(f"Inserting holiday: {holiday['name']}, {holiday_date}, {holiday.get('type')}")
                cur.execute(
                    "INSERT INTO us_holidays (holiday_date, holiday_name, type) VALUES (%s, %s, %s) ON CONFLICT (holiday_date) DO NOTHING",
                    (holiday_date, holiday['name'], holiday.get('type'))
                )
        self.conn.commit()
        logger.info("us_holidays table populated.")

    def create_mappings(self):
        """Create all mapping relationships"""
        logger.info("Creating mappings...")
        with self.conn.cursor() as cur:
            # Simple mapping for demonstration
            # Assign first 10 employees to PHE001
            for i in range(1, 11):
                cur.execute(
                    "INSERT INTO project_team_mapping (project_id, employee_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    ('PHE001', f'E{i:03}')
                )
            # Assign first 3 employees to TEST-001
            for i in range(1, 4):
                cur.execute(
                    "INSERT INTO project_team_mapping (project_id, employee_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    ('TEST-001', f'E{i:03}')
                )
            
            # Sample team-designation mapping
            cur.execute("INSERT INTO team_designation_mapping (id, did, eid) VALUES ('TD01', 'D01', 'E001') ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO team_designation_mapping (id, did, eid) VALUES ('TD02', 'D02', 'E002') ON CONFLICT DO NOTHING")

            # Sample team-role mapping
            cur.execute("INSERT INTO team_role_mapping (id, rid, eid) VALUES ('TR01', 'R01', 'E001') ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO team_role_mapping (id, rid, eid) VALUES ('TR02', 'R01', 'E002') ON CONFLICT DO NOTHING")

            # Sample role-designation mapping
            cur.execute("INSERT INTO role_designation_mapping (id, roleid, did) VALUES ('RD01', 'R01', 'D01') ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO role_designation_mapping (id, roleid, did) VALUES ('RD02', 'R01', 'D02') ON CONFLICT DO NOTHING")

        self.conn.commit()
        logger.info("Mappings created.")

    def run(self):
        """Main execution method"""
        try:
            with self as job:
                job.create_tables()
                job.populate_projects()
                job.populate_teams()
                job.populate_designations()
                job.populate_roles()
                job.create_mappings()
                job.populate_holidays()
                logger.info("Project setup completed successfully")
        except Exception as e:
            logger.error("Project setup failed", error=str(e))
            raise

if __name__ == "__main__":
    job = ProjectSetupJob()
    job.run()