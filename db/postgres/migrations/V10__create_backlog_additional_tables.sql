DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS stories CASCADE;
DROP TABLE IF EXISTS story_tasks CASCADE;
CREATE TABLE tasks (
    task_id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50),
    assigned_to VARCHAR(255),
    sprint_id VARCHAR(255),
    progress_percentage INTEGER
);

CREATE TABLE stories (
    id VARCHAR(255) PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE story_tasks (
    story_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (story_id, task_id)
);