FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Expose port
EXPOSE 8000

# Start server
CMD ["sh", "-c", "cd server && uvicorn main:app --host 0.0.0.0 --port 8000"]
