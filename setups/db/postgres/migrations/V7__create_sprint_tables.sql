DROP TABLE IF EXISTS sprints CASCADE;
DROP TABLE IF EXISTS stories CASCADE;
DROP TABLE IF EXISTS sprint_stories CASCADE;
DROP TABLE IF EXISTS story_tasks CASCADE;
CREATE TABLE sprints (
    id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL
);

CREATE TABLE stories (
    id VARCHAR(255) PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE sprint_stories (
    sprint_id VARCHAR(255) NOT NULL,
    story_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (sprint_id, story_id),
    FOREIGN KEY (sprint_id) REFERENCES sprints(id),
    FOREIGN KEY (story_id) REFERENCES stories(id)
);

CREATE TABLE story_tasks (
    story_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (story_id, task_id),
    FOREIGN KEY (story_id) REFERENCES stories(id)
);
