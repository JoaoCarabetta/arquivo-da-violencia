from loguru import logger

from gnews import GNews

google_news = GNews(max_results=5)
# Search for Rio de Janeiro
json_resp = google_news.get_news('Rio de Janeiro')

logger.info(f"Found {len(json_resp)} articles.")

if json_resp:
    article = json_resp[0]
    logger.info(f"First article: {article}")
    
    # GNews can also get the full article
    logger.info("Fetching full article...")
    full_article = google_news.get_full_article(article['url'])
    
    if full_article:
        logger.info(f"Title: {full_article.title}")
        logger.info(f"Text Length: {len(full_article.text)}")
        logger.info(f"Text Snippet: {full_article.text[:100]}")
    else:
        logger.info("Failed to fetch full article via GNews.")
