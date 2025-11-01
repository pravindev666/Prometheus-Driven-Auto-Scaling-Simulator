#!/bin/bash
# Stop script for Prometheus Auto-Scaling Simulator

set -e

echo "=============================================="
echo "Stopping Prometheus Auto-Scaling Simulator"
echo "=============================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Error: docker-compose is not installed${NC}"
    exit 1
fi

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: docker-compose.yml not found${NC}"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Display current running services
echo -e "${BLUE}Current running services:${NC}"
docker-compose ps
echo ""

# Ask for confirmation
read -p "Do you want to stop all services? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Operation cancelled${NC}"
    exit 0
fi

# Stop all services
echo -e "${YELLOW}Stopping services...${NC}"
docker-compose stop

echo -e "${YELLOW}Removing containers...${NC}"
docker-compose down

echo -e "${GREEN}✓ All services stopped and containers removed${NC}"
echo ""

# Ask if user wants to remove volumes
read -p "Do you want to remove data volumes? (This will delete all Prometheus/Grafana data) (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Removing volumes...${NC}"
    docker-compose down -v
    echo -e "${GREEN}✓ Volumes removed${NC}"
else
    echo -e "${BLUE}ℹ Volumes preserved. Data will be available on next start${NC}"
fi

echo ""
echo "=============================================="
echo -e "${GREEN}Cleanup Complete${NC}"
echo "=============================================="
echo ""
echo "To start again:"
echo "  ./scripts/start.sh"
echo ""
echo "To remove dangling images:"
echo "  docker image prune -f"
echo ""
echo "To view remaining containers:"
echo "  docker ps -a"
echo ""
echo "=============================================="
