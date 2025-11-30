ALTER TABLE sprint_retrospectives
ADD COLUMN sprint_name TEXT,
ADD COLUMN start_date DATE,
ADD COLUMN end_date DATE,
ADD COLUMN duration_weeks INTEGER,
ADD COLUMN tasks_summary JSONB;