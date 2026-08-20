#!/usr/bin/env python3
"""
Test Redis security configuration in docker-compose files.

Validates:
1. Redis ports are bound to 127.0.0.1 (not exposed to external network)
2. Redis command includes --requirepass with REDIS_PASSWORD env var
3. REDIS_URL includes password authentication

Usage:
    python test_redis_security.py
"""
import re
from pathlib import Path


def test_docker_compose_yml():
    """Test production docker-compose.yml Redis security."""
    path = Path(__file__).parent / "docker-compose.yml"
    content = path.read_text()
    
    # Check Redis ports bind to 127.0.0.1
    redis_section = extract_redis_section(content)
    assert '127.0.0.1:6379:6379' in redis_section, \
        "Redis ports must bind to 127.0.0.1:6379:6379"
    
    # Check Redis command includes requirepass
    assert '--requirepass' in redis_section, \
        "Redis command must include --requirepass"
    assert '${REDIS_PASSWORD:?REDIS_PASSWORD must be set}' in redis_section, \
        "Redis command must use REDIS_PASSWORD env var with fail-closed check"
    
    # Check REDIS_URL includes password for api and worker
    api_section = extract_service_section(content, 'api')
    assert 'redis://:${REDIS_PASSWORD}@redis:6379' in api_section, \
        "API REDIS_URL must include password authentication"
    
    worker_section = extract_service_section(content, 'worker')
    assert 'redis://:${REDIS_PASSWORD}@redis:6379' in worker_section, \
        "Worker REDIS_URL must include password authentication"
    
    # Check healthcheck includes auth
    assert 'redis-cli' in redis_section and '-a' in redis_section, \
        "Redis healthcheck must authenticate with -a flag"
    
    print("✓ docker-compose.yml Redis security checks passed")


def test_docker_compose_staging_yml():
    """Test staging docker-compose.staging.yml Redis security."""
    path = Path(__file__).parent / "docker-compose.staging.yml"
    content = path.read_text()
    
    # Check Redis ports bind to 127.0.0.1:6380 (staging uses different host port)
    redis_section = extract_redis_section(content)
    assert '127.0.0.1:6380:6379' in redis_section, \
        "Staging Redis ports must bind to 127.0.0.1:6380:6379"
    
    # Check Redis command includes requirepass
    assert '--requirepass' in redis_section, \
        "Staging Redis command must include --requirepass"
    assert '${REDIS_PASSWORD:?REDIS_PASSWORD must be set}' in redis_section, \
        "Staging Redis command must use REDIS_PASSWORD env var with fail-closed check"
    
    # Check REDIS_URL includes password for api and worker (staging uses different hostname)
    api_section = extract_service_section(content, 'api')
    assert 'redis://:${REDIS_PASSWORD}@staging-arquivo-redis:6379' in api_section, \
        "Staging API REDIS_URL must include password authentication"
    
    worker_section = extract_service_section(content, 'worker')
    assert 'redis://:${REDIS_PASSWORD}@staging-arquivo-redis:6379' in worker_section, \
        "Staging Worker REDIS_URL must include password authentication"
    
    # Check healthcheck includes auth
    assert 'redis-cli' in redis_section and '-a' in redis_section, \
        "Staging Redis healthcheck must authenticate with -a flag"
    
    print("✓ docker-compose.staging.yml Redis security checks passed")


def test_env_example():
    """Test env.example documents REDIS_PASSWORD."""
    path = Path(__file__).parent / "env.example"
    content = path.read_text()
    
    # Check REDIS_PASSWORD is documented
    assert 'REDIS_PASSWORD' in content, \
        "env.example must document REDIS_PASSWORD"
    
    # Check it includes openssl hint
    assert 'openssl' in content.lower(), \
        "env.example must include openssl generation hint for REDIS_PASSWORD"
    
    # Ensure no actual password is committed
    redis_pass_lines = [line for line in content.split('\n') 
                        if 'REDIS_PASSWORD=' in line and not line.strip().startswith('#')]
    for line in redis_pass_lines:
        value = line.split('=', 1)[1].strip()
        assert not value or len(value) < 10, \
            f"env.example must not contain real password (found: {line})"
    
    print("✓ env.example REDIS_PASSWORD documentation check passed")


def extract_redis_section(content: str) -> str:
    """Extract Redis service section from docker-compose YAML."""
    lines = content.split('\n')
    redis_lines = []
    in_redis = False
    indent_level = None
    
    for line in lines:
        if re.match(r'^\s+redis:', line):
            in_redis = True
            indent_level = len(line) - len(line.lstrip())
            redis_lines.append(line)
        elif in_redis:
            current_indent = len(line) - len(line.lstrip())
            # Stop when we hit another top-level service or end of section
            if line.strip() and current_indent <= indent_level and not line.strip().startswith('-'):
                break
            redis_lines.append(line)
    
    return '\n'.join(redis_lines)


def extract_service_section(content: str, service: str) -> str:
    """Extract a service section from docker-compose YAML."""
    lines = content.split('\n')
    service_lines = []
    in_service = False
    indent_level = None
    
    for line in lines:
        if re.match(rf'^\s+{service}:', line):
            in_service = True
            indent_level = len(line) - len(line.lstrip())
            service_lines.append(line)
        elif in_service:
            current_indent = len(line) - len(line.lstrip())
            # Stop when we hit another top-level service
            if line.strip() and current_indent <= indent_level and not line.strip().startswith('-'):
                break
            service_lines.append(line)
    
    return '\n'.join(service_lines)


if __name__ == '__main__':
    test_docker_compose_yml()
    test_docker_compose_staging_yml()
    test_env_example()
    print("\n✅ All Redis security tests passed!")
