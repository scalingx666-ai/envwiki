FROM python:3.12-slim

# Material the task depends on, copied from the source material.
COPY commands-and-groups.md /app/commands-and-groups.md
COPY options.md /app/options.md

RUN pip install --no-cache-dir click==8.1.8

WORKDIR /app

CMD ["sleep", "infinity"]
