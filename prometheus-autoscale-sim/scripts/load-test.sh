#!/bin/bash
# Load testing script to trigger auto-scaling

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TARGET_URL="http://localhost:8000"
DURATION=${1:-60}  # Duration in seconds (default: 60)
REQUESTS_PER_SECOND=${2:-50}  # Requests per second (default: 50)
DELAY=$(echo "scale=4; 1 / $REQUESTS_PER_SECOND" | bc)

echo "=============================================="
echo "Load Test for Auto-Scaling Simulator"
echo "=============================================="
echo "Target URL: $TARGET_URL"
echo "Duration: ${DURATION}s"
echo "Target Rate: ${REQUESTS_PER_SECOND} req/s"
echo "Delay between requests: ${DELAY}s"
echo "=============================================="
echo ""

# Check if bc is installed (required for calculations)
if ! command -v bc &> /dev/null; then
    echo -e "${RED}Error: 'bc' command not found. Please install it:${NC}"
    echo "  Ubuntu/Debian: sudo apt-get install bc"
    echo "  macOS: brew install bc"
    exit 1
fi

# Check if target is reachable
echo -e "${BLUE}Checking target availability...${NC}"
if ! curl -s "$TARGET_URL/health" > /dev/null 2>&1; then
    echo -e "${RED}Error: Target application is not reachable at $TARGET_URL${NC}"
    echo "Make sure the application is running with: ./scripts/start.sh"
    exit 1
fi

echo -e "${GREEN}✓ Target application is reachable${NC}"
echo ""

# Calculate total requests
TOTAL_REQUESTS=$((DURATION * REQUESTS_PER_SECOND))

echo -e "${YELLOW}Starting load test...${NC}"
echo "Sending approximately $TOTAL_REQUESTS requests over ${DURATION} seconds"
echo ""
echo -e "${BLUE}Monitoring tips:${NC}"
echo "  • Watch scaler logs:     docker-compose logs -f scaler"
echo "  • Check Prometheus:      http://localhost:9090"
echo "  • View Grafana:          http://localhost:3000"
echo "  • Monitor containers:    watch docker-compose ps webapp"
echo ""

# Track statistics
SUCCESS_COUNT=0
FAIL_COUNT=0
TOTAL_RESPONSE_TIME=0
START_TIME=$(date +%s)

# Function to display progress bar
display_progress() {
    local current=$1
    local total=$2
    local percent=$((current * 100 / total))
    local filled=$((percent / 2))
    local empty=$((50 - filled))
    
    printf "\rProgress: ["
    printf "%${filled}s" | tr ' ' '='
    printf "%${empty}s" | tr ' ' '-'
    printf "] %3d%% (%d/%d)" $percent $current $total
}

echo -e "${YELLOW}Sending requests...${NC}"
echo ""

# Send requests
for ((i=1; i<=TOTAL_REQUESTS; i++)); do
    # Send request and capture response code and time
    START_REQ=$(date +%s%3N)
    RESPONSE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TARGET_URL" 2>/dev/null || echo "000")
    END_REQ=$(date +%s%3N)
    REQ_TIME=$((END_REQ - START_REQ))
    
    if [ "$RESPONSE_CODE" = "200" ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        TOTAL_RESPONSE_TIME=$((TOTAL_RESPONSE_TIME + REQ_TIME))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    
    # Display progress bar
    display_progress $i $TOTAL_REQUESTS
    
    # Display detailed progress every 100 requests
    if [ $((i % 100)) -eq 0 ]; then
        ELAPSED=$(($(date +%s) - START_TIME))
        if [ $ELAPSED -gt 0 ]; then
            RATE=$(echo "scale=2; $i / $ELAPSED" | bc)
            AVG_RESP_TIME=$(echo "scale=0; $TOTAL_RESPONSE_TIME / $SUCCESS_COUNT" | bc)
            echo ""
            echo "  Elapsed: ${ELAPSED}s | Success: $SUCCESS_COUNT | Failed: $FAIL_COUNT | Rate: ${RATE} req/s | Avg: ${AVG_RESP_TIME}ms"
        fi
    fi
    
    # Sleep to maintain target rate
    sleep "$DELAY"
done

echo ""
echo ""

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
ACTUAL_RATE=$(echo "scale=2; $TOTAL_REQUESTS / $TOTAL_TIME" | bc)

# Calculate average response time
if [ $SUCCESS_COUNT -gt 0 ]; then
    AVG_RESPONSE_TIME=$(echo "scale=2; $TOTAL_RESPONSE_TIME / $SUCCESS_COUNT" | bc)
else
    AVG_RESPONSE_TIME=0
fi

# Calculate success rate
SUCCESS_RATE=$(echo "scale=2; $SUCCESS_COUNT * 100 / $TOTAL_REQUESTS" | bc)

echo "=============================================="
echo -e "${GREEN}Load Test Completed${NC}"
echo "=============================================="
echo "Total Requests:      $TOTAL_REQUESTS"
echo "Successful:          $SUCCESS_COUNT"
echo "Failed:              $FAIL_COUNT"
echo "Success Rate:        ${SUCCESS_RATE}%"
echo "Duration:            ${TOTAL_TIME}s"
echo "Actual Rate:         ${ACTUAL_RATE} req/s"
echo "Avg Response Time:   ${AVG_RESPONSE_TIME}ms"
echo "=============================================="
echo ""

# Check if scaling occurred
echo -e "${BLUE}Checking if auto-scaling occurred...${NC}"
REPLICA_COUNT=$(docker-compose ps webapp | grep -c "Up" || echo "0")
echo "Current replica count: $REPLICA_COUNT"
echo ""

if [ $REPLICA_COUNT -gt 1 ]; then
    echo -e "${GREEN}✓ Auto-scaling triggered! Running $REPLICA_COUNT replicas${NC}"
else
    echo -e "${YELLOW}⚠ No scaling detected. Still running $REPLICA_COUNT replica${NC}"
    echo "  Possible reasons:"
    echo "  • Load wasn't high enough to trigger scaling threshold"
    echo "  • Scaler is in cooldown period"
    echo "  • Scaler service may not be running"
fi

echo ""
echo "=============================================="
echo -e "${BLUE}Additional Commands:${NC}"
echo "=============================================="
echo "View current containers:"
echo "  docker-compose ps webapp"
echo ""
echo "View scaler decisions:"
echo "  docker-compose logs scaler | grep -i scaling"
echo ""
echo "Check Prometheus metrics:"
echo "  curl 'http://localhost:9090/api/v1/query?query=avg_over_time(webapp_response_time_seconds[30s])'"
echo ""
echo "View Grafana dashboard:"
echo "  open http://localhost:3000"
echo ""
echo "Generate more load:"
echo "  ./scripts/load-test.sh 120 100  # 120 seconds at 100 req/s"
echo ""
echo "=============================================="
