#!/usr/bin/env python3
"""
Flask Web Application with Prometheus Metrics
Simulates a production web service with variable performance characteristics.
Exposes metrics at /metrics endpoint for Prometheus scraping.
"""

import os
import random
import time
import logging
from flask import Flask, Response, jsonify, request
from prometheus_client import (
    Gauge, 
    Counter, 
    Histogram,
    generate_latest, 
    CollectorRegistry,
    CONTENT_TYPE_LATEST
)
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)

# Get application configuration from environment
APP_NAME = os.environ.get('APP_NAME', 'webapp')
FLASK_ENV = os.environ.get('FLASK_ENV', 'production')

# Create Prometheus metrics registry
registry = CollectorRegistry()

# Define Prometheus metrics

# Gauge: Current response time (simulated)
response_time_gauge = Gauge(
    'webapp_response_time_seconds',
    'Simulated response time in seconds',
    registry=registry
)

# Gauge: Current request count (simulated load indicator)
request_count_gauge = Gauge(
    'webapp_request_count',
    'Simulated request count',
    registry=registry
)

# Counter: Total requests processed
total_requests = Counter(
    'webapp_total_requests',
    'Total number of requests processed',
    ['method', 'endpoint', 'status'],
    registry=registry
)

# Histogram: Request duration distribution
request_duration = Histogram(
    'webapp_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint'],
    registry=registry,
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

# Gauge: Application info
app_info = Gauge(
    'webapp_info',
    'Application information',
    ['app_name', 'version', 'environment'],
    registry=registry
)

# Set application info
app_info.labels(
    app_name=APP_NAME,
    version='1.0.0',
    environment=FLASK_ENV
).set(1)

# Gauge: Health status
health_status = Gauge(
    'webapp_health_status',
    'Application health status (1=healthy, 0=unhealthy)',
    registry=registry
)
health_status.set(1)


class LoadSimulator:
    """
    Simulates variable load patterns for realistic testing.
    """
    def __init__(self):
        self.base_response_time = 0.1
        self.load_factor = 1.0
        self.spike_probability = 0.05
        
    def get_simulated_response_time(self):
        """
        Generate simulated response time with realistic patterns.
        Includes:
        - Base latency with random variation
        - Occasional spikes to simulate high load
        - Gradual trend changes
        """
        # Random variation around base time
        random_factor = random.uniform(0.8, 1.2)
        
        # Occasional spikes (5% probability)
        if random.random() < self.spike_probability:
            spike_factor = random.uniform(2.0, 5.0)
            logger.info(f"Simulating load spike: {spike_factor}x normal")
        else:
            spike_factor = 1.0
        
        # Calculate simulated response time
        response_time = (
            self.base_response_time * 
            random_factor * 
            self.load_factor * 
            spike_factor
        )
        
        # Add some jitter
        jitter = random.uniform(-0.02, 0.02)
        response_time = max(0.01, response_time + jitter)
        
        return response_time
    
    def get_simulated_request_count(self):
        """
        Generate simulated request count.
        """
        base_count = 50
        variation = random.uniform(0.5, 1.5)
        return int(base_count * variation * self.load_factor)
    
    def update_load_factor(self):
        """
        Gradually change load factor to simulate changing traffic patterns.
        """
        # Small random walk
        change = random.uniform(-0.05, 0.05)
        self.load_factor = max(0.5, min(2.0, self.load_factor + change))


# Initialize load simulator
load_simulator = LoadSimulator()


@app.before_request
def before_request():
    """
    Record request start time for duration tracking.
    """
    request.start_time = time.time()


@app.after_request
def after_request(response):
    """
    Record metrics after request completes.
    """
    # Calculate request duration
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        
        # Record histogram
        request_duration.labels(
            method=request.method,
            endpoint=request.endpoint or 'unknown'
        ).observe(duration)
    
    # Increment request counter
    total_requests.labels(
        method=request.method,
        endpoint=request.endpoint or 'unknown',
        status=response.status_code
    ).inc()
    
    return response


@app.route('/')
def index():
    """
    Main application endpoint.
    Simulates variable response time and updates metrics.
    """
    # Simulate processing time
    simulated_rt = load_simulator.get_simulated_response_time()
    time.sleep(simulated_rt)
    
    # Update metrics
    response_time_gauge.set(simulated_rt)
    request_count_gauge.set(load_simulator.get_simulated_request_count())
    
    # Update load factor occasionally
    if random.random() < 0.1:
        load_simulator.update_load_factor()
    
    return jsonify({
        'status': 'ok',
        'app': APP_NAME,
        'response_time': round(simulated_rt, 3),
        'load_factor': round(load_simulator.load_factor, 2)
    })


@app.route('/health')
def health():
    """
    Health check endpoint.
    Returns 200 if application is healthy.
    """
    return jsonify({
        'status': 'healthy',
        'app': APP_NAME
    }), 200


@app.route('/ready')
def ready():
    """
    Readiness check endpoint.
    Returns 200 if application is ready to serve traffic.
    """
    return jsonify({
        'status': 'ready',
        'app': APP_NAME
    }), 200


@app.route('/metrics')
def metrics():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus text format.
    """
    return Response(
        generate_latest(registry),
        mimetype=CONTENT_TYPE_LATEST
    )


@app.route('/load/<action>')
def control_load(action):
    """
    Control load simulator for testing.
    Actions: increase, decrease, reset, spike
    """
    if action == 'increase':
        load_simulator.load_factor = min(3.0, load_simulator.load_factor + 0.5)
        message = f"Load increased to {load_simulator.load_factor:.2f}"
    elif action == 'decrease':
        load_simulator.load_factor = max(0.5, load_simulator.load_factor - 0.5)
        message = f"Load decreased to {load_simulator.load_factor:.2f}"
    elif action == 'reset':
        load_simulator.load_factor = 1.0
        message = "Load reset to 1.0"
    elif action == 'spike':
        load_simulator.spike_probability = 0.5
        message = "Spike probability increased to 50%"
    else:
        return jsonify({'error': 'Invalid action'}), 400
    
    logger.info(message)
    return jsonify({
        'status': 'ok',
        'message': message,
        'current_load_factor': load_simulator.load_factor
    })


@app.errorhandler(404)
def not_found(error):
    """
    Handle 404 errors.
    """
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """
    Handle 500 errors.
    """
    logger.error(f"Internal error: {error}")
    health_status.set(0)
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    logger.info(f"Starting {APP_NAME} application")
    logger.info(f"Environment: {FLASK_ENV}")
    logger.info(f"Metrics endpoint: /metrics")
    
    # Run Flask application
    app.run(
        host='0.0.0.0',
        port=8000,
        debug=(FLASK_ENV == 'development')
    )
