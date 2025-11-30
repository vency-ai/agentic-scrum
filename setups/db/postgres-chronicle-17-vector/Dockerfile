# Use the official PostgreSQL 16 image as the base
FROM postgres:17

# Install the pgvector extension using the PostgreSQL APT repository
RUN apt-get update && \
    apt-get install -y postgresql-17-pgvector && \
    rm -rf /var/lib/apt/lists/*

# Add a file to the Docker entrypoint to automatically enable the extension.
#COPY enable-extension.sql /docker-entrypoint-initdb.d/
# Expose default Postgres port
EXPOSE 5432

# Add a file to the Docker entrypoint to automatically enable the extension.
#COPY enable-extension.sql /docker-entrypoint-initdb.d/

# (Optional) Enable the extension by default for the “postgres” database on init
COPY docker-entrypoint-initdb.d/enable_pgvector.sql /docker-entrypoint-initdb.d/enable_pgvector.sql
# Ensure the file is readable by the postgres user
RUN chmod 644 /docker-entrypoint-initdb.d/enable_pgvector.sql

#CMD ["docker-entrypoint.sh", "postgres"]
