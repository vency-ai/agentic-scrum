with open("/home/sysadmin/sysadmin/k8s/prj-sdlc/postgres-chronicle-17-vector/performance/insert_perf_data_individual.sql", "w") as f:
    for i in range(1, 1001):
        f.write(f"INSERT INTO agent_episodes (project_id, perception, reasoning, action, embedding, agent_version, decision_source) VALUES ('PERF-TEST-{i}', '{{\"test\": true}}', '{{\"test\": true}}', '{{\"test\": true}}', ARRAY(SELECT random() FROM generate_series(1, 1536))::vector, '1.0.0', 'rule_based_only');\n")
