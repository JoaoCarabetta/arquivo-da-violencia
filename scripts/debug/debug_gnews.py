from gnews import GNews

google_news = GNews(max_results=5)
# Search for Rio de Janeiro
json_resp = google_news.get_news('Rio de Janeiro')

print(f"Found {len(json_resp)} articles.")

if json_resp:
    article = json_resp[0]
    print(f"First article: {article}")
    
    # GNews can also get the full article
    print("Fetching full article...")
    full_article = google_news.get_full_article(article['url'])
    
    if full_article:
        print(f"Title: {full_article.title}")
        print(f"Text Length: {len(full_article.text)}")
        print(f"Text Snippet: {full_article.text[:100]}")
    else:
        print("Failed to fetch full article via GNews.")
