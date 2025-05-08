import os
import requests
import json

from dotenv import load_dotenv
load_dotenv()

def firecrawl_search(query: str, limit: int = 5, scrape_options: dict = None) -> dict:
    """
    Perform a search using the Firecrawler API.

    Args:
        query (str): The search query.
        limit (int): The maximum number of results to return.
        scrape_options (dict): Optional scraping options.
                               Example: {"formats": ["markdown", "links"]}

    Returns:
        dict: The search results as a dictionary, or an error dictionary if the request fails.
    """
    
    FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL")
    FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
    url = f"{FIRECRAWL_API_URL}/v1/search"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}"
    }

    payload = {
        "query": query,
        "limit": limit
    }

    if scrape_options:
        payload["scrapeOptions"] = scrape_options

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        return {"error": "HTTP error occurred", "details": str(http_err), "status_code": response.status_code, "response_text": response.text}
    except requests.exceptions.ConnectionError as conn_err:
        return {"error": "Connection error occurred", "details": str(conn_err)}
    except requests.exceptions.Timeout as timeout_err:
        return {"error": "Timeout error occurred", "details": str(timeout_err)}
    except requests.exceptions.RequestException as req_err:
        return {"error": "An unexpected error occurred", "details": str(req_err)}
    except json.JSONDecodeError:
        return {"error": "Failed to decode JSON response", "response_text": response.text}

def firecrawl_scrape(url_to_scrape: str, scrape_options: dict = None) -> dict:
    """
    Perform a scrape of a single URL using the Firecrawler API.

    Args:
        url_to_scrape (str): The URL to scrape.
        api_url (str): The base URL of the Firecrawler API (e.g., "http://localhost:3002").
        scrape_options (dict): Optional dictionary containing parameters for the scrape.
                               These options are passed directly to the Firecrawler /v1/scrape endpoint.
                               Example: {"extractorOptions": {"mode": "markdown"}, "pageOptions": {"onlyMainContent": True}}

    Returns:
        dict: The scrape results as a dictionary, or an error dictionary if the request fails.
    """

    FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL")
    FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
    scrape_api_endpoint = f"{FIRECRAWL_API_URL}/v1/scrape"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}"
    }

    payload = {
        "url": url_to_scrape
    }

    if scrape_options:
        payload.update(scrape_options)

    try:
        response = requests.post(scrape_api_endpoint, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        return {"error": "HTTP error occurred", "details": str(http_err), "status_code": response.status_code, "response_text": response.text}
    except requests.exceptions.ConnectionError as conn_err:
        return {"error": "Connection error occurred", "details": str(conn_err)}
    except requests.exceptions.Timeout as timeout_err:
        return {"error": "Timeout error occurred", "details": str(timeout_err)}
    except requests.exceptions.RequestException as req_err:
        return {"error": "An unexpected error occurred", "details": str(req_err)}
    except json.JSONDecodeError:
        response_text_content = ""
        if 'response' in locals() and hasattr(response, 'text'):
            response_text_content = response.text
        return {"error": "Failed to decode JSON response", "response_text": response_text_content}