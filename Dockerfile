FROM docker.io/library/python:3.12-slim

# Set the working directory
RUN mkdir /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY requirements.txt requirements.txt
COPY otel.py otel.py
COPY main.py main.py

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

ENV SETUP=docker

# Run main.py when the container launches
ENTRYPOINT ["python", "main.py"]
