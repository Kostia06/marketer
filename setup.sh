#!/bin/bash
set -e

echo "=== Marketer Setup ==="

# Check for .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
  echo "Edit .env with your API keys before continuing."
  exit 1
fi

# Check for Docker
if ! command -v docker &> /dev/null; then
  echo "Docker is required. Install it from https://docs.docker.com/get-docker/"
  exit 1
fi

# Start n8n
echo "Starting n8n..."
docker compose up -d

echo ""
echo "Waiting for n8n to start..."
sleep 5

# Check if n8n is running
if curl -s http://localhost:5678/healthz > /dev/null 2>&1; then
  echo "n8n is running at http://localhost:5678"
else
  echo "n8n is starting... check http://localhost:5678 in a few seconds"
fi

echo ""
echo "=== Next Steps ==="
echo "1. Open http://localhost:5678"
echo "2. Create your account"
echo "3. Import workflows from workflows/*.json"
echo "4. Set up credentials (LinkedIn Auth, Twitter OAuth)"
echo "5. Activate workflows: Review Handler first, then Content Generator, then Publisher"
echo ""
echo "For server deployment, update .env:"
echo "  N8N_HOST=your-domain.com"
echo "  N8N_PROTOCOL=https"
echo "  WEBHOOK_URL=https://your-domain.com"
echo "  MARKETER_REVIEW_WEBHOOK=https://your-domain.com/webhook/marketer-review"
