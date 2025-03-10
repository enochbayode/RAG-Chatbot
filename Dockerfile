# Use official Python slim image as a base
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install necessary system dependencies and Ollama
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements file and install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose ports that the app will run on
EXPOSE 8080
EXPOSE 11434

# Start ollama and the gunicorn
CMD ["sh", "-c", "ollama serve & sleep 5 && ollama run llama3.2:1b && gunicorn -b 0.0.0.0:8080 app:app"]

