FROM python:3.11-slim

LABEL maintainer="auto-scaler-team"
LABEL description="Prometheus-driven auto-scaling service"
LABEL version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /scaler

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    netcat-openbsd \
    docker.io \
    openssh-client \
    sshpass \
    gcc \
    python3-dev \
    libffi-dev \
    libssl-dev \
    git \
    procps \
    jq \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose \
    && chmod +x /usr/local/bin/docker-compose \
    && docker-compose --version

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

RUN ansible --version && \
    ansible-playbook --version

COPY scaler.py .

RUN chmod +x scaler.py

RUN mkdir -p /ansible \
    && mkdir -p /root/.ansible \
    && mkdir -p /tmp/ansible

RUN echo "[defaults]" > /root/.ansible.cfg && \
    echo "host_key_checking = False" >> /root/.ansible.cfg && \
    echo "stdout_callback = yaml" >> /root/.ansible.cfg && \
    echo "display_skipped_hosts = False" >> /root/.ansible.cfg && \
    echo "gathering = explicit" >> /root/.ansible.cfg && \
    echo "" >> /root/.ansible.cfg && \
    echo "[privilege_escalation]" >> /root/.ansible.cfg && \
    echo "become = False" >> /root/.ansible.cfg

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python3.*scaler.py" > /dev/null || exit 1

ENV PROMETHEUS_URL=http://prometheus:9090 \
    SERVICE_NAME=webapp \
    SCALE_UP_THRESHOLD=0.6 \
    SCALE_DOWN_THRESHOLD=0.2 \
    MAX_REPLICAS=6 \
    MIN_REPLICAS=1 \
    CHECK_INTERVAL=10 \
    ANSIBLE_PLAYBOOK=/ansible/playbook-scale.yml \
    COMPOSE_PROJECT_NAME=prometheus-autoscale-sim \
    SCALE_UP_COOLDOWN=30 \
    SCALE_DOWN_COOLDOWN=60 \
    PYTHONUNBUFFERED=1

VOLUME ["/ansible"]

WORKDIR /scaler

CMD ["python3", "-u", "scaler.py"]
