
#!/bin/bash
# Start script for Prometheus Auto-Scaling Simulator

set -e

echo "=============================================="
echo "Prometheus Auto-Scaling Simulator"
echo "Starting all services..."
echo "=============================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed. Please install it and try again."
    exit 1
fi

# Create necessary directories if they don't exist
echo -e "${YELLOW}Creating necessary directories...${NC}"
mkdir -p grafana/provisioning/datasources
mkdir -p grafana/provisioning/dashboards
mkdir -p prometheus_rules

# Build and start services
echo -e "${YELLOW}Building Docker images...${NC}"
docker-compose build

echo -e "${YELLOW}Starting services...${NC}"
docker-compose up -d

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Check service health
echo -e "${YELLOW}Checking service health...${NC}"

# Check Prometheus
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Prometheus is healthy${NC}"
else
    echo "Warning: Prometheus may not be ready yet"
fi

# Check Grafana
if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Grafana is healthy${NC}"
else
    echo "Warning: Grafana may not be ready yet"
fi

# Check webapp
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Web application is healthy${NC}"
else
    echo "Warning: Web application may not be ready yet"
fi

echo ""
echo "=============================================="
echo "Services are starting!"
echo "=============================================="
echo ""
echo "Access URLs:"
echo "  • Prometheus:      http://localhost:9090"
echo "  • Grafana:         http://localhost:3000 (admin/admin)"
echo "  • Web Application: http://localhost:8000"
echo ""
echo "Useful commands:"
echo "  • View logs:       docker-compose logs -f"
echo "  • View scaler:     docker-compose logs -f scaler"
echo "  • Check status:    docker-compose ps"
echo "  • Stop services:   ./scripts/stop.sh"
echo ""
echo "To generate load and trigger scaling:"
echo "  ./scripts/load-test.sh"
echo ""
echo "=============================================="
