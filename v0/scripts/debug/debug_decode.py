from loguru import logger

import base64
import re

url = "https://news.google.com/rss/articles/CBMisAFBVV95cUxQbEZ3RzR4UDk4VFV3WnlzQ3lmcGF5cTdoZklCajFhS1BrRzFwR2ZwbkFwdmxweV9rb2w0SjFmRzhOYnNnVl9kRmVrSmE0c1Fwb0tlZ0NVdENnbmZPajdTS0dvR2FtQzF4TWVwQWc5bDFXSURKVWxlS2F5U0t0TzV4RzZMcHNzTEx3Rll5V0hQM0Jmd1RvRzJ4eXZkWWg3U0VkUjlnQ2xLd2tZVE1B?oc=5"

# Extract the ID part
match = re.search(r'articles/([^?]+)', url)
if match:
    encoded = match.group(1)
    logger.info(f"Encoded part: {encoded}")
    
    # Needs padding correction
    padding = len(encoded) % 4
    if padding:
        encoded += '=' * (4 - padding)
        
    try:
        decoded = base64.urlsafe_b64decode(encoded)
        logger.info(f"Decoded (raw): {decoded}")
        
        # Often it's a binary blob (protobuf), but might contain the URL as a string.
        # Let's search for http strings.
        import string
        printable = set(string.printable.encode('ascii'))
        strings = re.findall(rb'(https?://[^\s\x00]+)', decoded)
        logger.info(f"Found URLs in decoded: {strings}")
    except Exception as e:
        logger.info(f"Decoding error: {e}")
