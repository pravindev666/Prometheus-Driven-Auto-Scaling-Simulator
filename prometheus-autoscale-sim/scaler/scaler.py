#!/usr/bin/env python3
"""
Prometheus-Driven Auto-Scaler Service

This service polls Prometheus for metrics, analyzes performance data,
and triggers scaling actions via Ansible playbooks to adjust the number
of application replicas based on configurable thresholds.

Architecture:
1. Query Prometheus API for average response time
2. Determine current replica count via Docker API
3. Apply scaling logic based on thresholds
4. Execute Ansible playbook to scale service
5. Wait for next check interval

Author: Auto-Scaling Simulator
Version: 1.0.0
"""

import os
import sys
import time
import logging
import json
import subprocess
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List

# Configure logging with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration from environment variables
# ============================================================================

PROMETHEUS_URL = os.environ.get('PROMETHEUS_URL', 'http://localhost:9090')
SERVICE_NAME = os.environ.get('SERVICE_NAME', 'webapp')
SCALE_UP_THRESHOLD = float(os.environ.get('SCALE_UP_THRESHOLD', '0.6'))
SCALE_DOWN_THRESHOLD = float(os.environ.get('SCALE_DOWN_THRESHOLD', '0.2'))
MAX_REPLICAS = int(os.environ.get('MAX_REPLICAS', '6'))
MIN_REPLICAS = int(os.environ.get('MIN_REPLICAS', '1'))
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '10'))
ANSIBLE_PLAYBOOK = os.environ.get('ANSIBLE_PLAYBOOK', '/ansible/playbook-scale.yml')
COMPOSE_PROJECT_NAME = os.environ.get('COMPOSE_PROJECT_NAME', 'prometheus-autoscale-sim')

# Scaling cooldown to prevent thrashing (seconds)
SCALE_UP_COOLDOWN = int(os.environ.get('SCALE_UP_COOLDOWN', '30'))
SCALE_DOWN_COOLDOWN = int(os.environ.get('SCALE_DOWN_COOLDOWN', '60'))

# Consecutive threshold breaches required before scaling
SCALE_UP_BREACHES_REQUIRED = int(os.environ.get('SCALE_UP_BREACHES_REQUIRED', '2'))
SCALE_DOWN_BREACHES_REQUIRED = int(os.environ.get('SCALE_DOWN_BREACHES_REQUIRED', '3'))

# ============================================================================
# Global state tracking
# ============================================================================

last_scale_time = 0
last_scale_action = None
consecutive_threshold_breaches = 0
scaling_history = []


# ============================================================================
# Prometheus Client
# ============================================================================

class PrometheusClient:
    """
    Client for querying Prometheus HTTP API.
    
    Provides methods to query metrics, check health, and retrieve
    time-series data from Prometheus.
    """
    
    def __init__(self, base_url: str):
        """
        Initialize Prometheus client.
        
        Args:
            base_url: Prometheus server URL (e.g., http://prometheus:9090)
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'prometheus-autoscaler/1.0'
        })
        logger.info(f"Initialized Prometheus client: {self.base_url}")
    
    def query(self, query: str, timeout: int = 5) -> Optional[float]:
        """
        Execute instant PromQL query and return the result value.
        
        Args:
            query: PromQL query string
            timeout: Request timeout in seconds
            
        Returns:
            Float value if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/api/v1/query"
            params = {'query': query}
            
            logger.debug(f"Querying Prometheus: {query}")
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if query was successful
            if data.get('status') != 'success':
                error_msg = data.get('error', 'Unknown error')
                error_type = data.get('errorType', 'unknown')
                logger.error(f"Prometheus query failed: [{error_type}] {error_msg}")
                return None
            
            result = data.get('data', {}).get('result', [])
            
            if not result:
                logger.warning(f"No data returned for query: {query}")
                return None
            
            # Extract value from first result
            # Result format: [{'metric': {...}, 'value': [timestamp, 'value']}]
            value = float(result[0]['value'][1])
            logger.debug(f"Query result: {value}")
            
            return value
            
        except requests.exceptions.Timeout:
            logger.error(f"Prometheus query timed out after {timeout}s")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to Prometheus at {self.base_url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query Prometheus: {e}")
            return None
        except (KeyError, IndexError, ValueError) as e:
            logger.error(f"Failed to parse Prometheus response: {e}")
            return None
    
    def query_range(self, query: str, start: int, end: int, step: str = '15s') -> Optional[List[Dict]]:
        """
        Execute range PromQL query and return time-series data.
        
        Args:
            query: PromQL query string
            start: Start timestamp (Unix time)
            end: End timestamp (Unix time)
            step: Query resolution step width
            
        Returns:
            List of data points if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/api/v1/query_range"
            params = {
                'query': query,
                'start': start,
                'end': end,
                'step': step
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'success':
                logger.error(f"Prometheus range query failed: {data.get('error')}")
                return None
            
            return data.get('data', {}).get('result', [])
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to execute range query: {e}")
            return None
    
    def health_check(self) -> bool:
        """
        Check if Prometheus is reachable and healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            url = f"{self.base_url}/-/healthy"
            response = self.session.get(url, timeout=5)
            is_healthy = response.status_code == 200
            
            if is_healthy:
                logger.debug("Prometheus health check: OK")
            else:
                logger.warning(f"Prometheus health check failed: {response.status_code}")
            
            return is_healthy
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Prometheus health check failed: {e}")
            return False
    
    def get_targets(self) -> Optional[List[Dict]]:
        """
        Get list of scrape targets from Prometheus.
        
        Returns:
            List of targets if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/api/v1/targets"
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == 'success':
                return data.get('data', {}).get('activeTargets', [])
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get targets: {e}")
            return None


# ============================================================================
# Docker Manager
# ============================================================================

class DockerManager:
    """
    Manager for interacting with Docker containers.
    
    Provides methods to get current replica count and container information.
    """
    
    def __init__(self, service_name: str, project_name: str):
        """
        Initialize Docker manager.
        
        Args:
            service_name: Name of the service to manage
            project_name: Docker Compose project name
        """
        self.service_name = service_name
        self.project_name = project_name
        logger.info(f"Initialized Docker manager for service: {service_name}")
    
    def get_current_replicas(self) -> int:
        """
        Get current number of running replicas for the service.
        
        Returns:
            Number of running replicas
        """
        try:
            # Use docker ps to count containers for this service
            cmd = [
                'docker', 'ps',
                '--filter', f'name={self.project_name}_{self.service_name}',
                '--filter', 'status=running',
                '--format', '{{.Names}}'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            
            # Count lines (each line is one container)
            container_names = [line for line in result.stdout.strip().split('\n') if line]
            count = len(container_names)
            
            logger.debug(f"Found {count} running replicas: {container_names}")
            return count
            
        except subprocess.TimeoutExpired:
            logger.error("Docker command timed out")
            return MIN_REPLICAS
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get replica count: {e}")
            logger.error(f"Stderr: {e.stderr}")
            return MIN_REPLICAS
        except Exception as e:
            logger.error(f"Unexpected error getting replica count: {e}")
            return MIN_REPLICAS
    
    def get_container_stats(self) -> List[Dict[str, Any]]:
        """
        Get statistics for all running containers of the service.
        
        Returns:
            List of container statistics
        """
        try:
            cmd = [
                'docker', 'stats',
                '--no-stream',
                '--format', '{{json .}}',
                f'{self.project_name}_{self.service_name}'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            
            stats = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        stats.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get container stats: {e}")
            return []


# ============================================================================
# Scaling Decision Engine
# ============================================================================

class ScalingDecisionEngine:
    """
    Engine for making scaling decisions based on metrics and thresholds.
    
    Implements logic to determine when and how to scale services based on
    observed metrics, thresholds, and historical patterns.
    """
    
    def __init__(self):
        """Initialize decision engine."""
        self.history = []
        logger.info("Initialized scaling decision engine")
    
    def decide_scale(
        self,
        current_metric: Optional[float],
        current_replicas: int,
        threshold_up: float,
        threshold_down: float,
        min_replicas: int,
        max_replicas: int
    ) -> Optional[int]:
        """
        Decide if scaling is needed and return target replica count.
        
        Args:
            current_metric: Current metric value (e.g., response time)
            current_replicas: Current number of replicas
            threshold_up: Threshold for scaling up
            threshold_down: Threshold for scaling down
            min_replicas: Minimum allowed replicas
            max_replicas: Maximum allowed replicas
            
        Returns:
            Target replica count if scaling needed, None otherwise
        """
        global consecutive_threshold_breaches
        
        if current_metric is None:
            logger.warning("No metric data available, cannot make scaling decision")
            consecutive_threshold_breaches = 0
            return None
        
        # Store in history for trend analysis
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'metric': current_metric,
            'replicas': current_replicas,
            'threshold_up': threshold_up,
            'threshold_down': threshold_down
        })
        
        # Keep only last 100 entries (about 16 minutes at 10s intervals)
        if len(self.history) > 100:
            self.history.pop(0)
        
        # Calculate metric statistics for better decision making
        recent_metrics = [h['metric'] for h in self.history[-5:]]
        avg_recent = sum(recent_metrics) / len(recent_metrics) if recent_metrics else current_metric
        
        logger.debug(f"Metric analysis - Current: {current_metric:.3f}, Recent avg: {avg_recent:.3f}")
        
        # ====================================================================
        # Scale Up Logic
        # ====================================================================
        if current_metric > threshold_up:
            consecutive_threshold_breaches += 1
            logger.info(
                f"Metric {current_metric:.3f}s exceeds scale-up threshold {threshold_up}s "
                f"(breach #{consecutive_threshold_breaches}/{SCALE_UP_BREACHES_REQUIRED})"
            )
            
            # Require multiple consecutive breaches to avoid false positives
            if consecutive_threshold_breaches >= SCALE_UP_BREACHES_REQUIRED:
                if current_replicas < max_replicas:
                    # Calculate how many replicas to add based on severity
                    overshoot_ratio = current_metric / threshold_up
                    
                    if overshoot_ratio > 2.0:
                        # Severe overload: add 2 replicas
                        increment = min(2, max_replicas - current_replicas)
                    else:
                        # Moderate overload: add 1 replica
                        increment = 1
                    
                    target = min(max_replicas, current_replicas + increment)
                    logger.info(
                        f"Scaling decision: UP from {current_replicas} to {target} "
                        f"(+{increment} replicas, overshoot: {overshoot_ratio:.2f}x)"
                    )
                    consecutive_threshold_breaches = 0
                    return target
                else:
                    logger.warning(
                        f"Already at maximum replicas ({max_replicas}), cannot scale up further"
                    )
                    consecutive_threshold_breaches = 0
                    return None
        
        # ====================================================================
        # Scale Down Logic
        # ====================================================================
        elif current_metric < threshold_down:
            consecutive_threshold_breaches += 1
            logger.info(
                f"Metric {current_metric:.3f}s below scale-down threshold {threshold_down}s "
                f"(breach #{consecutive_threshold_breaches}/{SCALE_DOWN_BREACHES_REQUIRED})"
            )
            
            # Require more consecutive breaches for scale-down (more conservative)
            if consecutive_threshold_breaches >= SCALE_DOWN_BREACHES_REQUIRED:
                if current_replicas > min_replicas:
                    # Always scale down by 1 replica for safety
                    target = max(min_replicas, current_replicas - 1)
                    logger.info(
                        f"Scaling decision: DOWN from {current_replicas} to {target} "
                        f"(-1 replica)"
                    )
                    consecutive_threshold_breaches = 0
                    return target
                else:
                    logger.info(
                        f"Already at minimum replicas ({min_replicas}), cannot scale down"
                    )
                    consecutive_threshold_breaches = 0
                    return None
        
        # ====================================================================
        # Within Acceptable Range
        # ====================================================================
        else:
            if consecutive_threshold_breaches > 0:
                logger.debug(
                    f"Metric back within acceptable range "
                    f"({threshold_down}s - {threshold_up}s), resetting breach counter"
                )
            consecutive_threshold_breaches = 0
            return None
        
        return None
    
    def get_scaling_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about scaling history and patterns.
        
        Returns:
            Dictionary containing scaling statistics
        """
        if not self.history:
            return {}
        
        metrics = [h['metric'] for h in self.history]
        replicas = [h['replicas'] for h in self.history]
        
        return {
            'total_samples': len(self.history),
            'avg_metric': sum(metrics) / len(metrics),
            'min_metric': min(metrics),
            'max_metric': max(metrics),
            'avg_replicas': sum(replicas) / len(replicas),
            'min_replicas': min(replicas),
            'max_replicas': max(replicas)
        }


# ============================================================================
# Ansible Executor
# ============================================================================

class AnsibleExecutor:
    """
    Executor for running Ansible playbooks.
    
    Provides interface to trigger infrastructure changes via Ansible.
    """
    
    def __init__(self, playbook_path: str):
        """
        Initialize Ansible executor.
        
        Args:
            playbook_path: Path to Ansible playbook file
        """
        self.playbook_path = playbook_path
        logger.info(f"Initialized Ansible executor: {playbook_path}")
        
        # Verify playbook exists
        if not os.path.exists(playbook_path):
            logger.error(f"Playbook not found: {playbook_path}")
    
    def scale_service(self, target_replicas: int) -> bool:
        """
        Execute Ansible playbook to scale service.
        
        Args:
            target_replicas: Desired number of replicas
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = [
                'ansible-playbook',
                self.playbook_path,
                '-e', f'target_replicas={target_replicas}',
                '-v'  # Verbose output
            ]
            
            logger.info(f"Executing: {' '.join(cmd)}")
            start_time = time.time()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=120  # 2 minute timeout
            )
            
            duration = time.time() - start_time
            logger.info(f"Ansible playbook executed successfully in {duration:.2f}s")
            logger.debug(f"Output: {result.stdout}")
            
            # Record successful scaling action
            self._record_scaling_action(target_replicas, True, duration)
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Ansible playbook execution timed out")
            self._record_scaling_action(target_replicas, False, 120)
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Ansible playbook failed with exit code {e.returncode}")
            logger.error(f"Stdout: {e.stdout}")
            logger.error(f"Stderr: {e.stderr}")
            self._record_scaling_action(target_replicas, False, 0)
            return False
        except Exception as e:
            logger.error(f"Unexpected error executing Ansible: {e}")
            self._record_scaling_action(target_replicas, False, 0)
            return False
    
    def _record_scaling_action(self, target: int, success: bool, duration: float):
        """
        Record scaling action in history.
        
        Args:
            target: Target replica count
            success: Whether the action was successful
            duration: Execution duration in seconds
        """
        global scaling_history
        
        scaling_history.append({
            'timestamp': datetime.now().isoformat(),
            'target_replicas': target,
            'success': success,
            'duration': duration
        })
        
        # Keep only last 50 scaling actions
        if len(scaling_history) > 50:
            scaling_history.pop(0)


# ============================================================================
# Cooldown Management
# ============================================================================

def check_cooldown(action: str) -> bool:
    """
    Check if enough time has passed since last scaling action.
    
    Prevents rapid scaling changes (thrashing) by enforcing cooldown periods.
    
    Args:
        action: 'up' or 'down'
        
    Returns:
        True if cooldown period has passed, False otherwise
    """
    global last_scale_time, last_scale_action
    
    current_time = time.time()
    time_since_last_scale = current_time - last_scale_time
    
    # No previous scaling action
    if last_scale_action is None:
        return True
    
    # Determine required cooldown based on action type
    if action == 'up':
        required_cooldown = SCALE_UP_COOLDOWN
    else:
        required_cooldown = SCALE_DOWN_COOLDOWN
    
    # Check if cooldown period has passed
    if time_since_last_scale < required_cooldown:
        remaining = int(required_cooldown - time_since_last_scale)
        logger.info(
            f"Cooldown active: {remaining}s remaining for {action} action "
            f"(last action: {last_scale_action}, {int(time_since_last_scale)}s ago)"
        )
        return False
    
    logger.debug(f"Cooldown check passed for {action} action")
    return True


def update_scale_state(action: str):
    """
    Update scaling state after successful action.
    
    Args:
        action: 'up' or 'down'
    """
    global last_scale_time, last_scale_action
    last_scale_time = time.time()
    last_scale_action = action
    logger.debug(f"Updated scale state: action={action}, time={last_scale_time}")


# ============================================================================
# Main Application
# ============================================================================

def print_startup_banner():
    """Print startup banner with configuration details."""
    banner = """
    ╔════════════════════════════════════════════════════════════╗
    ║     PROMETHEUS-DRIVEN AUTO-SCALER SERVICE                  ║
    ║     Version 1.0.0                                          ║
    ╚════════════════════════════════════════════════════════════╝
    """
    logger.info(banner)
    logger.info("=" * 60)
    logger.info("Configuration:")
    logger.info("=" * 60)
    logger.info(f"  Prometheus URL:        {PROMETHEUS_URL}")
    logger.info(f"  Service Name:          {SERVICE_NAME}")
    logger.info(f"  Scale Up Threshold:    {SCALE_UP_THRESHOLD}s")
    logger.info(f"  Scale Down Threshold:  {SCALE_DOWN_THRESHOLD}s")
    logger.info(f"  Replica Range:         {MIN_REPLICAS} - {MAX_REPLICAS}")
    logger.info(f"  Check Interval:        {CHECK_INTERVAL}s")
    logger.info(f"  Scale Up Cooldown:     {SCALE_UP_COOLDOWN}s")
    logger.info(f"  Scale Down Cooldown:   {SCALE_DOWN_COOLDOWN}s")
    logger.info(f"  Playbook Path:         {ANSIBLE_PLAYBOOK}")
    logger.info("=" * 60)


def wait_for_prometheus(prom_client: PrometheusClient, max_retries: int = 30):
    """
    Wait for Prometheus to be ready before starting main loop.
    
    Args:
        prom_client: Prometheus client instance
        max_retries: Maximum number of retry attempts
    """
    logger.info("Waiting for Prometheus to be ready...")
    
    for attempt in range(1, max_retries + 1):
        if prom_client.health_check():
            logger.info("✓ Prometheus is ready")
            return
        
        logger.warning(f"Prometheus not ready (attempt {attempt}/{max_retries}), retrying in 5s...")
        time.sleep(5)
    
    logger.error(f"Prometheus did not become ready after {max_retries} attempts")
    sys.exit(1)


def main():
    """
    Main scaler loop.
    
    Continuously monitors Prometheus metrics and triggers scaling actions
    based on configured thresholds and logic.
    """
    # Print startup information
    print_startup_banner()
    
    # Initialize components
    prom_client = PrometheusClient(PROMETHEUS_URL)
    docker_manager = DockerManager(SERVICE_NAME, COMPOSE_PROJECT_NAME)
    decision_engine = ScalingDecisionEngine()
    ansible_executor = AnsibleExecutor(ANSIBLE_PLAYBOOK)
    
    # Wait for Prometheus to be ready
    wait_for_prometheus(prom_client)
    
    # Main monitoring loop
    iteration = 0
    
    try:
        while True:
            iteration += 1
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Iteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info('=' * 60)
            
            try:
                # ============================================================
                # Step 1: Query Prometheus for metrics
                # ============================================================
                query = 'avg_over_time(webapp_response_time_seconds[30s])'
                avg_response_time = prom_client.query(query)
                
                # ============================================================
                # Step 2: Get current replica count
                # ============================================================
                current_replicas = docker_manager.get_current_replicas()
                
                # Log current state
                logger.info(f"Current State:")
                if avg_response_time is not None:
                    logger.info(f"  • Average Response Time (30s): {avg_response_time:.3f}s")
                    
                    # Visual indicator for thresholds
                    if avg_response_time > SCALE_UP_THRESHOLD:
                        logger.info(f"    ⚠️  ABOVE scale-up threshold ({SCALE_UP_THRESHOLD}s)")
                    elif avg_response_time < SCALE_DOWN_THRESHOLD:
                        logger.info(f"    ⬇️  BELOW scale-down threshold ({SCALE_DOWN_THRESHOLD}s)")
                    else:
                        logger.info(f"    ✓ Within acceptable range")
                else:
                    logger.info(f"  • Average Response Time: N/A (no data)")
                
                logger.info(f"  • Current Replicas: {current_replicas}")
                
                # ============================================================
                # Step 3: Make scaling decision
                # ============================================================
                target_replicas = decision_engine.decide_scale(
                    current_metric=avg_response_time,
                    current_replicas=current_replicas,
                    threshold_up=SCALE_UP_THRESHOLD,
                    threshold_down=SCALE_DOWN_THRESHOLD,
                    min_replicas=MIN_REPLICAS,
                    max_replicas=MAX_REPLICAS
                )
                
                # ============================================================
                # Step 4: Execute scaling if needed
                # ============================================================
                if target_replicas is not None and target_replicas != current_replicas:
                    action = 'up' if target_replicas > current_replicas else 'down'
                    
                    logger.info(f"\n{'─' * 60}")
                    logger.info(f"🔧 SCALING ACTION REQUIRED")
                    logger.info(f"{'─' * 60}")
                    logger.info(f"  Direction: {action.upper()}")
                    logger.info(f"  Current:   {current_replicas} replicas")
                    logger.info(f"  Target:    {target_replicas} replicas")
                    logger.info(f"  Change:    {target_replicas - current_replicas:+d} replicas")
                    
                    # Check cooldown before executing
                    if not check_cooldown(action):
                        logger.info("⏸️  Scaling action postponed due to cooldown period")
                    else:
                        logger.info(f"▶️  Executing scaling action...")
                        
                        if ansible_executor.scale_service(target_replicas):
                            logger.info(f"✅ Successfully scaled to {target_replicas} replicas")
                            update_scale_state(action)
                        else:
                            logger.error(f"❌ Scaling action failed")
                    
                    logger.info(f"{'─' * 60}\n")
                else:
                    logger.info("✓ No scaling action required")
                
                # ============================================================
                # Step 5: Print statistics periodically
                # ============================================================
                if iteration % 10 == 0:
                    stats = decision_engine.get_scaling_statistics()
                    if stats:
                        logger.info(f"\n{'─' * 60}")
                        logger.info(f"📊 STATISTICS (last {stats['total_samples']} samples)")
                        logger.info(f"{'─' * 60}")
                        logger.info(f"  Avg Response Time: {stats['avg_metric']:.3f}s")
                        logger.info(f"  Min Response Time: {stats['min_metric']:.3f}s")
                        logger.info(f"  Max Response Time: {stats['max_metric']:.3f}s")
                        logger.info(f"  Avg Replicas:      {stats['avg_replicas']:.1f}")
                        logger.info(f"  Replica Range:     {stats['min_replicas']} - {stats['max_replicas']}")
                        logger.info(f"{'─' * 60}\n")
            
            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}", exc_info=True)
            
            # ============================================================
            # Step 6: Sleep until next check
            # ============================================================
            logger.info(f"💤 Sleeping for {CHECK_INTERVAL}s until next check...")
            time.sleep(CHECK_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 60)
        logger.info("🛑 Shutdown requested by user")
        logger.info("=" * 60)
        
        # Print final statistics
        stats = decision_engine.get_scaling_statistics()
        if stats:
            logger.info("\nFinal Statistics:")
            logger.info(f"  Total iterations: {iteration}")
            logger.info(f"  Total samples:    {stats['total_samples']}")
            logger.info(f"  Total scaling actions: {len(scaling_history)}")
            
            if scaling_history:
                successful = sum(1 for s in scaling_history if s['success'])
                logger.info(f"  Successful scalings:   {successful}/{len(scaling_history)}")
        
        logger.info("\n✓ Scaler service stopped gracefully")
        sys.exit(0)
    
    except Exception as e:
        logger.critical(f"Fatal error in main loop: {e}", exc_info=True)
        sys.exit(1)


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
