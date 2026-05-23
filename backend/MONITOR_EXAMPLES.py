#!/usr/bin/env python3
"""
Examples of creating and running monitors using the new monitor types.
Run these against a local Alfred backend instance.
"""

import requests
import json
from typing import Any

BASE_URL = "http://localhost:8000"


def create_monitor(monitor_data: dict) -> dict:
    """Create a new monitor."""
    response = requests.post(f"{BASE_URL}/monitors", json=monitor_data)
    response.raise_for_status()
    return response.json()


def run_monitor(monitor_id: int) -> dict:
    """Run a specific monitor."""
    response = requests.post(f"{BASE_URL}/monitors/{monitor_id}/run")
    response.raise_for_status()
    return response.json()


def get_monitor_logs(monitor_id: int, limit: int = 10) -> list:
    """Get recent logs for a monitor."""
    response = requests.get(f"{BASE_URL}/monitors/{monitor_id}/log?limit={limit}")
    response.raise_for_status()
    return response.json()


def print_result(title: str, data: Any):
    """Pretty print results."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2))


# ============================================================================
# EXAMPLE 1: HTML Static Monitor
# ============================================================================
def example_html_static():
    """Monitor static HTML content with CSS selectors."""
    monitor = {
        "name": "GitHub Status - Static",
        "description": "Check GitHub status page for operational status",
        "type": "html_static",
        "url": "https://www.githubstatus.com/",
        "selector": ".component-status",  # Status indicators
        "target": "Operational",
        "case_sensitive": False,
        "timeout": 15,
    }
    
    print("\n>>> Creating HTML Static Monitor...")
    created = create_monitor(monitor)
    print_result("Monitor Created", created)
    
    monitor_id = created["id"]
    
    print("\n>>> Running the monitor...")
    result = run_monitor(monitor_id)
    print_result("Monitor Result", result)
    
    print("\n>>> Getting recent logs...")
    logs = get_monitor_logs(monitor_id, limit=5)
    print_result("Recent Logs", logs)


# ============================================================================
# EXAMPLE 2: HTML with JavaScript Monitor
# ============================================================================
def example_html_javascript():
    """Monitor HTML content that requires JavaScript rendering."""
    monitor = {
        "name": "Dynamic Dashboard - JS Rendered",
        "description": "Monitor a dashboard that loads content via JavaScript",
        "type": "html_javascript",
        "url": "https://example.com/dashboard",  # Replace with actual URL
        "selector": "[data-metric]",  # Elements with data-metric attribute
        "target": "healthy",
        "case_sensitive": False,
        "wait_selector": ".dashboard-loaded",  # Wait for this element
        "timeout": 20,
    }
    
    print("\n>>> Creating HTML JavaScript Monitor...")
    created = create_monitor(monitor)
    print_result("Monitor Created", created)
    
    monitor_id = created["id"]
    
    print("\n>>> Running the monitor (this will take longer due to rendering)...")
    result = run_monitor(monitor_id)
    print_result("Monitor Result", result)


# ============================================================================
# EXAMPLE 3: API Monitor with Pagination
# ============================================================================
def example_api_monitor():
    """Monitor API endpoint with paginated JSON responses."""
    monitor = {
        "name": "KIVIK Product Monitor",
        "description": "Search IKEA Circular Hub for KIVIK availability",
        "type": "api",
        "url": "https://web-api.ikea.com/circular/circular-asis/offers/grouped/search?languageCode=pt&size=32&storeIds=499%2C009&categories=700640&query=KIVIK",
        "json_path": "content",  # The API returns a list of items in the 'content' key
        "target": "KIVIK",
        "case_sensitive": True,
        "page_size": 50,
        "max_pages": 5,  # Limit to 5 pages to avoid excessive requests
        "request_delay": 1000,  # 1 second between requests (polite crawling)
        "timeout": 15,
    }
    
    print("\n>>> Creating API Monitor...")
    created = create_monitor(monitor)
    print_result("Monitor Created", created)
    
    monitor_id = created["id"]
    
    print("\n>>> Running the monitor...")
    result = run_monitor(monitor_id)
    print_result("Monitor Result", result)
    
    print("\n>>> Getting logs...")
    logs = get_monitor_logs(monitor_id, limit=5)
    print_result("Logs", logs)


# ============================================================================
# EXAMPLE 4: API Monitor with Nested JSON Path
# ============================================================================
def example_api_nested_json():
    """Monitor API with nested JSON structure."""
    monitor = {
        "name": "Nested API Monitor",
        "description": "Search nested JSON response for inventory status",
        "type": "api",
        "url": "https://api.example.com/products",  # Replace with actual API
        "json_path": "data.items",  # Nested path: data -> items
        "target": "in_stock",
        "case_sensitive": True,
        "page_size": 25,
        "max_pages": 3,
        "request_delay": 500,  # 0.5 second between requests
        "timeout": 10,
    }
    
    print("\n>>> Creating Nested API Monitor...")
    created = create_monitor(monitor)
    print_result("Monitor Created", created)
    
    monitor_id = created["id"]
    
    print("\n>>> Running the monitor...")
    result = run_monitor(monitor_id)
    print_result("Monitor Result", result)


# ============================================================================
# EXAMPLE 5: Batch Running All Active Monitors
# ============================================================================
def run_all_monitors():
    """Run all active monitors at once."""
    print("\n>>> Running all active monitors...")
    response = requests.post(f"{BASE_URL}/monitors/run")
    response.raise_for_status()
    results = response.json()
    print_result("All Monitors Run Results", results)


# ============================================================================
# Main
# ============================================================================
if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║       Alfred Monitor Examples - Three Monitor Types        ║
╚════════════════════════════════════════════════════════════╝
    
This script demonstrates the three monitor types:

1. HTML Static      - CSS selectors on static HTML
2. HTML JavaScript  - CSS selectors on JS-rendered content  
3. API Monitor      - JSON search with pagination

Uncomment the examples you want to run below.
Make sure Alfred backend is running at http://localhost:8000
    """)
    
    try:
        # Uncomment examples to run them:
        
        # example_html_static()
        # example_html_javascript()
        # example_api_monitor()
        # example_api_nested_json()
        # run_all_monitors()
        
        print("\n✓ All examples completed successfully!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to backend at http://localhost:8000")
        print("Make sure the Alfred backend is running.")
    except Exception as e:
        print(f"❌ Error: {e}")
