import trafilatura
import requests

url = "https://news.google.com/rss/articles/CBMisAFBVV95cUxQbEZ3RzR4UDk4VFV3WnlzQ3lmcGF5cTdoZklCajFhS1BrRzFwR2ZwbkFwdmxweV9rb2w0SjFmRzhOYnNnVl9kRmVrSmE0c1Fwb0tlZ0NVdENnbmZPajdTS0dvR2FtQzF4TWVwQWc5bDFXSURKVWxlS2F5U0t0TzV4RzZMcHNzTEx3Rll5V0hQM0Jmd1RvRzJ4eXZkWWg3U0VkUjlnQ2xLd2tZVE1B?oc=5"

print(f"Original URL: {url}")

# Try 1: Trafilatura direct
print("\n--- Method 1: Trafilatura fetch_url ---")
downloaded = trafilatura.fetch_url(url)
if downloaded:
    print(f"Downloaded length: {len(downloaded)}")
    print(f"Snippet: {downloaded[:200]}")
    text = trafilatura.extract(downloaded)
    print(f"Extracted Text: {text}")
else:
    print("Trafilatura failed to download.")

# Try 2: Requests resolution
print("\n--- Method 2: Requests resolution ---")
try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    r = requests.get(url, allow_redirects=True, headers=headers)
    print(f"Final URL: {r.url}")
    print(f"Status Code: {r.status_code}")
    print(f"Content Length: {len(r.text)}")
    
    # Try parsing the resolved URL
    if r.status_code == 200:
        text = trafilatura.extract(r.text)
        print(f"Extracted Text from Requests content: {text}")
except Exception as e:
    print(f"Requests failed: {e}")
