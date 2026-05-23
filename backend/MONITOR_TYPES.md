# Monitor Types Guide

The monitoring system now supports three different monitor types: **HTML Static**, **HTML with JavaScript**, and **API Monitoring**.

## Monitor Types

### 1. HTML Static (`html_static`)
Monitors static HTML content without JavaScript rendering. Uses CSS selectors to find elements and checks if they contain the target text.

**Required fields:**
- `url`: The website URL to monitor
- `selector`: CSS selector to find elements (e.g., `.price`, `div.product-name`, `#status-message`)
- `target`: Text to search for
- `case_sensitive`: Whether the search is case-sensitive (default: true)
- `timeout`: Request timeout in seconds (default: 10)

**Example:**
```json
{
  "name": "Product Price Monitor",
  "type": "html_static",
  "url": "https://example.com/product",
  "selector": ".price",
  "target": "$99.99",
  "case_sensitive": false,
  "timeout": 15
}
```

### 2. HTML with JavaScript (`html_javascript`)
Monitors HTML content after JavaScript has been executed. Uses Selenium with headless Chrome to render the page dynamically before checking.

**Required fields:**
- `url`: The website URL to monitor
- `selector`: CSS selector to find elements
- `target`: Text to search for
- `wait_selector` (optional): CSS selector to wait for before checking (useful for async content loading)

**Optional fields:**
- `case_sensitive`: Whether the search is case-sensitive (default: true)
- `timeout`: How long to wait for the page to load in seconds (default: 10)

**Example:**
```json
{
  "name": "Dynamic Dashboard Monitor",
  "type": "html_javascript",
  "url": "https://dashboard.example.com",
  "selector": "[data-status]",
  "target": "online",
  "wait_selector": ".loading-complete",
  "case_sensitive": false,
  "timeout": 20
}
```

**Note:** Requires Selenium to be installed: `pip install selenium`

### 3. API Monitoring (`api`)
Monitors REST API endpoints by fetching paginated JSON data and searching through it. Uses dot-notation paths to navigate nested JSON structures.

**Required fields:**
- `url`: The API endpoint URL
- `json_path`: Dot-notation path to the **list/array** of items to search (e.g., `content`, `data.items`). 
  *Note: The system will automatically search all fields within every object in this list.*
- `target`: Text to search for in the values

**Optional fields:**
- `case_sensitive`: Whether the search is case-sensitive (default: true)
- `page_size`: Items per page (default: 32, should match API expectations)
- `max_pages`: Maximum number of pages to fetch (default: unlimited)
- `request_delay`: Delay between requests in milliseconds (default: 0, useful for polite crawling)
- `timeout`: Request timeout in seconds (default: 10)

**Example:**
```json
{
  "name": "KIVIK Product Monitor",
  "type": "api",
  "url": "https://web-api.ikea.com/circular/circular-asis/offers/grouped/search?languageCode=pt&size=32&storeIds=499%2C009&categories=700640&query=KIVIK",
  "json_path": "content",
  "target": "KIVIK",
  "case_sensitive": true,
  "page_size": 32,
  "request_delay": 500,
  "timeout": 15
}
```

Another example with nested JSON:
```json
{
  "name": "Nested API Monitor",
  "type": "api",
  "url": "https://api.example.com/products",
  "json_path": "data.items",
  "target": "in_stock",
  "max_pages": 10
}
```

## JSON Path Examples

For an API response like:
```json
{
  "content": [
    {"name": "Item 1", "price": 10},
    {"name": "Item 2", "price": 20}
  ]
}
```
Use `json_path: "content"`

For nested structure:
```json
{
  "data": {
    "items": [
      {"id": 1, "status": "active"},
      {"id": 2, "status": "inactive"}
    ]
  }
}
```
Use `json_path: "data.items"`

## Running Monitors

### Run all active monitors:
```bash
POST /monitors/run
```

### Run a specific monitor:
```bash
POST /monitors/{monitor_id}/run
```

### Get recent logs for a monitor:
```bash
GET /monitors/{monitor_id}/log?limit=10
```

## Common Use Cases

### Website Price Changes
- Type: `html_static`
- Selector: CSS class or ID of the price element
- Target: The new price you're watching for

### Dynamic Dashboard Status
- Type: `html_javascript`
- Selector: Element showing status
- Wait Selector: Loading indicator that disappears when ready

### Inventory Availability
- Type: `api` (if API is available)
- JSON Path: Path to inventory items
- Target: "in_stock" or "available"

### Multi-page Content Search
- Type: `api`
- JSON Path: "content" or path to items
- Request Delay: 1000ms (1 second) for polite crawling
- Max Pages: 20 to avoid excessive requests
