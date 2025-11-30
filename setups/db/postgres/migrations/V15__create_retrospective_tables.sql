CREATE TABLE sprint_retrospectives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id VARCHAR(255) NOT NULL UNIQUE,
    project_id VARCHAR(255) NOT NULL,
    what_went_well TEXT,
    what_could_be_improved TEXT,
    facilitator_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE retrospective_action_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    retrospective_id UUID NOT NULL REFERENCES sprint_retrospectives(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'open' -- open, in-progress, done
);

CREATE TABLE retrospective_attendees (
    retrospective_id UUID NOT NULL REFERENCES sprint_retrospectives(id) ON DELETE CASCADE,
    employee_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (retrospective_id, employee_id)
);
