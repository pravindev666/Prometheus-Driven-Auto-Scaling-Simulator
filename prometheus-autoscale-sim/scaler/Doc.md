# Scaler Service Documentation

## Overview

The scaler service is the core component of the auto-scaling system. It monitors Prometheus metrics and automatically adjusts the number of application replicas based on performance thresholds.

---

## File Structure

```
scaler/
├── scaler.py          # Main Python application
├── requirements.txt   # Python dependencies
└── Dockerfile        # Container image definition
```

---

## requirements.txt - Python Dependencies

### Core Dependencies

#### 1. **requests==2.31.0**
- **Purpose**: HTTP client for Prometheus API communication
- **Usage**: Queries Prometheus for metrics via REST API
- **Why this version**: Stable release with security patches

#### 2. **ansible==9.0.1**
- **Purpose**: Infrastructure automation framework
- **Usage**: Executes playbooks to scale Docker containers
- **Why this version**: Latest stable release with modern features

#### 3. **ansible-core==2.16.0**
- **Purpose**: Core Ansible functionality
- **Usage**: Required by ansible package for execution engine
- **Why this version**: Compatible with ansible 9.0.1

### Ansible Dependencies

#### 4. **jinja2==3.1.2**
- **Purpose**: Template engine for Ansible
- **Usage**: Processes variable substitution in playbooks
- **Required by**: Ansible for template rendering

#### 5. **PyYAML==6.0.1**
- **Purpose**: YAML parser and emitter
- **Usage**: Parses Ansible playbooks and configuration files
- **Required by**: Ansible for reading YAML files

#### 6. **cryptography==41.0.7**
- **Purpose**: Cryptographic operations
- **Usage**: SSH key handling, secure connections
- **Required by**: Ansible for secure communications

#### 7. **paramiko==3.4.0**
- **Purpose**: SSH protocol implementation
- **Usage**: Remote execution via SSH (if needed)
- **Required by**: Ansible for SSH connections

### Optional Dependencies

#### 8. **docker==7.0.0**
- **Purpose**: Docker SDK for Python
- **Usage**: Alternative to Docker CLI for container management
- **Note**: Currently using CLI, but SDK available for future enhancement

#### 9. **python-dateutil==2.8.2**
- **Purpose**: Date/time utilities
- **Usage**: Timestamp parsing and manipulation
- **Use case**: Logging and history tracking

#### 10. **pytz==2023.3**
- **Purpose**: Timezone handling
- **Usage**: Timestamp conversion for logs
- **Use case**: Consistent time representation

---

## Dockerfile - Container Image Definition

### Base Image

```dockerfile
FROM python:3.11-slim
```

**Why Python 3.11-slim:**
- Latest stable Python version
- Slim variant reduces image size (vs full image)
- Official Python image ensures security updates
- Size: ~120MB vs ~900MB for full image

### Environment Variables

```dockerfile
ENV PYTHONUNBUFFERED=1
```
- Ensures Python output is sent straight to terminal
- Critical for real-time logging in containers

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1
```
- Prevents Python from writing .pyc files
- Reduces disk usage and speeds up container startup

```dockerfile
ENV PIP_NO_CACHE_DIR=1
```
- Disables pip cache to reduce image size
- Saves ~50-100MB in final image

### System Dependencies

#### Network Tools
```dockerfile
curl, wget, netcat-openbsd
```
- **Purpose**: Debugging and health checks
- **Usage**: curl for Prometheus API testing, nc for port checking

#### Docker CLI
```dockerfile
docker.io
```
- **Purpose**: Container management from within container
- **Usage**: Execute `docker ps`, `docker-compose` commands
- **Size**: ~20MB

#### SSH Tools
```dockerfile
openssh-client, sshpass
```
- **Purpose**: Remote execution capabilities for Ansible
- **Usage**: SSH connections if needed for remote scaling
- **Note**: Not used in local setup but available for production

#### Build Tools
```dockerfile
gcc, python3-dev, libffi-dev, libssl-dev
```
- **Purpose**: Compile Python C extensions
- **Required by**: cryptography, paramiko packages
- **Note**: Can be removed after pip install in multi-stage build

#### Utilities
```dockerfile
git, procps, jq
```
- **git**: Clone Ansible Galaxy collections
- **procps**: Process monitoring (ps, top commands)
- **jq**: JSON parsing for Docker API responses

### Docker Compose Installation

```dockerfile
RUN curl -L "https://github.com/docker/compose/releases/download/v2.23.0/..."
```

**Why install Docker Compose:**
- Scaler uses `docker-compose` commands to scale services
- Binary installation (not Python package) for better compatibility
- Version 2.23.0 is stable and feature-complete

### Python Dependencies Installation

```dockerfile
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt
```

**Build optimization:**
- Upgrades pip/setuptools for faster installs
- `--no-cache-dir` reduces final image size
- Single RUN command reduces Docker layers

### Directory Structure

```dockerfile
RUN mkdir -p /ansible \
    && mkdir -p /root/.ansible \
    && mkdir -p /tmp/ansible
```

**Directories created:**
- `/ansible` - Mount point for Ansible playbooks
- `/root/.ansible` - Ansible configuration directory
- `/tmp/ansible` - Temporary files for Ansible execution

### Ansible Configuration

```dockerfile
RUN echo "[defaults]" > /root/.ansible.cfg && \
    echo "host_key_checking = False" >> /root/.ansible.cfg
```

**Configuration settings:**
- `host_key_checking = False` - Skip SSH host key verification (local execution)
- `stdout_callback = yaml` - Better output formatting
- `gathering = explicit` - Disable fact gathering for speed

### Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python3.*scaler.py" > /dev/null || exit 1
```

**Health check parameters:**
- `--interval=30s` - Check every 30 seconds
- `--timeout=10s` - Health check timeout
- `--start-period=40s` - Grace period on startup
- `--retries=3` - Mark unhealthy after 3 failures

**Check logic:**
- Uses `pgrep` to verify scaler.py process is running
- Returns 0 (healthy) if process found, 1 (unhealthy) otherwise

### Default Environment Variables

```dockerfile
ENV PROMETHEUS_URL=http://prometheus:9090 \
    SERVICE_NAME=webapp \
    SCALE_UP_THRESHOLD=0.6
```

**Purpose:**
- Provides sensible defaults for all configuration
- Can be overridden in docker-compose.yml
- Documents available configuration options

### Security Considerations

#### Current Setup (Development)
```dockerfile
# Running as root for Docker socket access
```

**Why root:**
- Requires access to `/var/run/docker.sock`
- Docker socket is owned by root:docker
- Simpler for local development

#### Production Setup (Commented)
```dockerfile
# RUN useradd -m -u 1000 scaler
# USER scaler
```

**For production:**
- Create non-root user
- Add user to docker group
- Use Docker API with TLS instead of socket mount
- Implement RBAC for Docker access

### Volume Mounts

```dockerfile
VOLUME ["/ansible"]
```

**Expected volumes:**
1. `/ansible` - Ansible playbooks (read-only)
2. `/var/run/docker.sock` - Docker socket (read-write)
3. `/docker-compose.yml` - Compose file (read-only)

**Mount configuration in docker-compose.yml:**
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
  - ./ansible:/ansible:ro
  - ./docker-compose.yml:/docker-compose.yml:ro
```

### Command Execution

```dockerfile
CMD ["python3", "-u", "scaler.py"]
```

**Flags explained:**
- `python3` - Python interpreter
- `-u` - Unbuffered output (immediate logging)
- `scaler.py` - Main application script

**Alternative commands for debugging:**
```dockerfile
# Debug mode with verbose logging
CMD ["python3", "-u", "scaler.py", "--debug"]

# Keep container running for troubleshooting
CMD ["tail", "-f", "/dev/null"]

# Interactive shell
CMD ["/bin/bash"]
```

---

## Build and Run Instructions

### Building the Image

```bash
# Build from scaler directory
cd scaler
docker build -t prometheus-scaler:latest .

# Build with custom tag
docker build -t prometheus-scaler:1.0.0 .

# Build with build args (if needed)
docker build --build-arg PYTHON_VERSION=3.11 -t prometheus-scaler .
```

### Running Standalone

```bash
# Run with environment variables
docker run -d \
  --name scaler \
  -e PROMETHEUS_URL=http://prometheus:9090 \
  -e SERVICE_NAME=webapp \
  -e SCALE_UP_THRESHOLD=0.6 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/../ansible:/ansible:ro \
  prometheus-scaler:latest

# View logs
docker logs -f scaler

# Execute commands inside container
docker exec -it scaler bash

# Stop and remove
docker stop scaler && docker rm scaler
```

### Running with Docker Compose

```bash
# Start via compose (recommended)
docker-compose up -d scaler

# View logs
docker-compose logs -f scaler

# Restart after code changes
docker-compose restart scaler

# Rebuild and restart
docker-compose up -d --build scaler
```

---

## Image Size Optimization

### Current Image Layers

1. **Base image**: python:3.11-slim (~120MB)
2. **System packages**: +80MB
3. **Python packages**: +150MB
4. **Application code**: +0.5MB
5. **Total**: ~350MB

### Optimization Techniques

#### 1. Multi-Stage Build (Future Enhancement)

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim as builder
RUN apt-get update && apt-get install -y gcc python3-dev
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
COPY --from=builder /wheels /wheels
RUN pip install --no-cache /wheels/*
```

**Benefit**: Removes build tools from final image (~50MB savings)

#### 2. Alpine Linux Base (Alternative)

```dockerfile
FROM python:3.11-alpine
```

**Trade-offs:**
- Smaller base (~50MB vs 120MB)
- Requires compilation of all C extensions
- Longer build times
- Potential compatibility issues

#### 3. Cleanup Commands

```dockerfile
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/* && \
    rm -rf /root/.cache
```

**Already implemented** - Reduces image by ~30MB

---

## Troubleshooting

### Common Issues

#### 1. Permission Denied on Docker Socket

**Error:**
```
PermissionError: [Errno 13] Permission denied: '/var/run/docker.sock'
```

**Solution:**
```bash
# Option 1: Fix socket permissions (temporary)
sudo chmod 666 /var/run/docker.sock

# Option 2: Add user to docker group (permanent)
sudo usermod -aG docker $USER
newgrp docker

# Option 3: Run with sudo (not recommended)
sudo docker-compose up
```

#### 2. Ansible Command Not Found

**Error:**
```
ansible-playbook: command not found
```

**Solution:**
```bash
# Rebuild image to ensure Ansible is installed
docker-compose build --no-cache scaler

# Verify installation
docker-compose run scaler ansible --version
```

#### 3. Connection to Prometheus Failed

**Error:**
```
Failed to connect to Prometheus at http://prometheus:9090
```

**Solution:**
```bash
# Check if Prometheus is running
docker-compose ps prometheus

# Check network connectivity
docker-compose exec scaler curl http://prometheus:9090/-/healthy

# Verify DNS resolution
docker-compose exec scaler nslookup prometheus
```

#### 4. Scaler Not Detecting Containers

**Error:**
```
Found 0 running replicas
```

**Solution:**
```bash
# Check filter pattern
docker ps --filter "name=prometheus-autoscale-sim_webapp"

# Verify COMPOSE_PROJECT_NAME matches
echo $COMPOSE_PROJECT_NAME

# Check Docker socket mount
docker-compose exec scaler ls -la /var/run/docker.sock
```

---

## Performance Considerations

### Resource Limits

```yaml
# In docker-compose.yml
scaler:
  deploy:
    resources:
      limits:
        cpus: '0.5'
        memory: 512M
      reservations:
        cpus: '0.25'
        memory: 256M
```

**Recommended limits:**
- CPU: 0.25-0.5 cores (scaler is not CPU intensive)
- Memory: 256-512MB (Ansible + Python runtime)

### Scaling Performance

**Typical operation times:**
- Prometheus query: 50-200ms
- Docker replica count check: 100-300ms
- Ansible playbook execution: 3-10s
- Total iteration time: 4-12s

---

## Security Best Practices

### 1. Docker Socket Security

**Current (Development):**
```yaml
- /var/run/docker.sock:/var/run/docker.sock
```

**Production:**
```yaml
# Use Docker API over TLS
environment:
  - DOCKER_HOST=tcp://docker-api:2376
  - DOCKER_TLS_VERIFY=1
  - DOCKER_CERT_PATH=/certs
volumes:
  - ./certs:/certs:ro
```

### 2. Secrets Management

**Current:**
```yaml
environment:
  - PROMETHEUS_URL=http://prometheus:9090
```

**Production:**
```yaml
secrets:
  - prometheus_url
environment:
  - PROMETHEUS_URL_FILE=/run/secrets/prometheus_url
```

### 3. Read-Only Filesystem

```yaml
scaler:
  read_only: true
  tmpfs:
    - /tmp
    - /root/.ansible/tmp
```

### 4. Capability Dropping

```yaml
scaler:
  cap_drop:
    - ALL
  cap_add:
    - NET_BIND_SERVICE  # Only if needed
```

---

## Monitoring the Scaler

### Log Levels

```bash
# Set log level via environment
docker-compose run -e LOG_LEVEL=DEBUG scaler

# Or in scaler.py:
logging.basicConfig(level=logging.DEBUG)
```

### Key Log Messages

```
✓ Prometheus is ready                    # Startup successful
⚠️  ABOVE scale-up threshold            # Scaling trigger
✅ Successfully scaled to N replicas     # Scaling success
❌ Scaling action failed                 # Scaling failure
⏸️  Scaling action postponed            # Cooldown active
```

### Metrics to Monitor

1. **Scaler iterations per minute**: Should be ~6 (every 10s)
2. **Scaling actions per hour**: Depends on load pattern
3. **Failed scaling attempts**: Should be 0
4. **Average iteration time**: Should be < 1s

---

## Summary

The scaler service is containerized Python application that:

1. **Monitors** Prometheus for application metrics
2. **Decides** when scaling is needed based on thresholds
3. **Executes** Ansible playbooks to scale containers
4. **Tracks** scaling history and statistics
5. **Logs** all actions for debugging and audit

**Key Files:**
- `requirements.txt` - 10 Python packages totaling ~150MB
- `Dockerfile` - Multi-layered image of ~350MB
- `scaler.py` - 600+ lines of Python code

**Image includes:**
- Python 3.11 runtime
- Ansible automation framework
- Docker CLI and Compose
- Debugging and monitoring tools

This setup provides a production-ready auto-scaling solution that can be deployed locally or adapted for cloud environments.
