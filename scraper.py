import feedparser
import json
import os
import time
import urllib.parse
import difflib
import requests
from datetime import datetime
from newspaper import Article
import google.generativeai as genai

def setup_genai():
    # Hybrid loading: Works on Local PC (with dotenv) and GitHub (without)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        print("Error: AI_API_KEY environment variable is not set.")
        exit(1)
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

def get_summary(model, title, link, fallback_text=""):
    """Simplified summary logic using only Gemini (No NLTK required)"""
    try:
        # Prompt focused on Supply Chain implications
        prompt = (
            f"Write a concise 2-sentence summary focused strictly on the Digital Supply Chain "
            f"implications of this article.\n\n"
            f"Headline: {title}\n"
            f"Link: {link}\n"
            f"Context: {fallback_text[:500]}"
        )
        response = model.generate_content(prompt)
        ai_summary = response.text.replace('\n', ' ').strip()
        if ai_summary:
            return ai_summary
    except Exception as e:
        print(f"Gemini Error: {e}")
    
    # Simple backup if AI fails
    return f"Strategic Insight: This article covers {title}. Visit source for full technical details."

def determine_category(title, summary):
    text = (title + " " + summary).lower()
    if any(k in text for k in ['agentic ai', 'data fabric']): return 'Future-Tech'
    if any(k in text for k in ['wms', 'tms', 'transportation', 'warehouse', 'logistics', 'fleet', 'delivery']): return 'Logistics'
    if any(k in text for k in ['smart manufacturing', 'iot', 'factory', 'automation', 'digital twin', 'lineview', 'oee']): return 'Smart Manufacturing'
    if any(k in text for k in ['procurement', 'sourcing', 'supplier', 'purchasing', 'vendor', 'gep', 'coupa']): return 'Procurement'
    if any(k in text for k in ['planning', 'blue yonder', 'forecast', 'demand', 'sap ibp', 'ibp', 'o9']): return 'Planning'
    if any(k in text for k in ['data', 'analytics', 'ai ', 'artificial intelligence', 'machine learning', 'lake']): return 'Data Analytics'
    return 'Logistics'

def is_near_duplicate(new_title, existing_titles, threshold=0.85):
    for et in existing_titles:
        if difflib.SequenceMatcher(None, new_title, et).ratio() >= threshold:
            return True
    return False

def fetch_feed(query, existing_links, existing_titles, max_items):
    encoded_query = urllib.parse.quote(query)
    rss_urls = [
        f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en",
        f"https://www.bing.com/news/search?q={encoded_query}&format=rss"
    ]
    
    # 1-year archive boundary
    time_threshold = datetime(2025, 3, 22)
    items = []
    
    for rss_url in rss_urls:
        if len(items) >= max_items: break
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            if len(items) >= max_items: break
            
            link = entry.get('link')
            title = entry.title if hasattr(entry, 'title') else ''
            title_lower = title.lower().strip()
            
            # Filters
            if 'supply chain' not in title_lower or link in existing_links: continue
            if is_near_duplicate(title_lower, existing_titles, 0.85): continue
            
            # Corporate Noise Filter
            noise = ['stock market', 'dividend', 'hiring', 'earnings', 'marketing', 'flavor']
            if any(w in title_lower for w in noise): continue
                
            published_time = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_time = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                
            if published_time and published_time >= time_threshold:
                # Image Logic
                safe_seed = urllib.parse.quote(title[:30].replace(' ', ''))
                image_url = f"https://picsum.photos/seed/{safe_seed}/800/450"
                
                items.append({
                    "raw_date": published_time,
                    "image": image_url,
                    "title": title,
                    "date": published_time.strftime("%d.%m.%Y"),
                    "description": entry.get('description', ''),
                    "link": link
                })
                existing_links.add(link)
                existing_titles.add(title_lower)
    return items

def main():
    model = setup_genai()
    
    sites = "site:logisticsmgt.com OR site:blueyonder.com OR site:supplychaindive.com OR site:scmr.com OR site:gep.com OR site:lineview.com"
    base_query = 'intitle:"Supply Chain" (FMCG OR Beverage OR Food OR "Coca Cola")'
    exclusions = '-CEO -hiring -earnings -"stock price"'
    
    queries = [
        f'{base_query} (GEP OR Siemens OR Lineview OR BlueYonder) {exclusions} ({sites})',
        f'("Sedef Salingan Sahin" OR "Henrique Braun") ("Coca-Cola" OR Digital) {exclusions}'
    ]
    
    existing_links, existing_titles, all_items = set(), set(), []
    
    for q in queries:
        if len(all_items) >= 40: break
        found_items = fetch_feed(q, existing_links, existing_titles, max_items=40 - len(all_items))
        all_items.extend(found_items)
        
    if not all_items:
        print("No news found today.")
        return
        
    # Sort by priority (Executive names first) then date
    all_items.sort(key=lambda x: (
        1 if ('sahin' in x['title'].lower() or 'braun' in x['title'].lower()) else 0,
        x['raw_date']
    ), reverse=True)

    final_items = []
    for i, item in enumerate(all_items[:15]): # Limiting to 15 for API speed
        print(f"Processing ({i+1}/{len(all_items[:15])}): {item['title'][:40]}...")
        summary = get_summary(model, item['title'], item['link'], item['description'])
        category = determine_category(item['title'], summary)
        
        final_items.append({
            "id": i + 1,
            "image": item["image"],
            "category": category,
            "title": item["title"],
            "date": item["date"],
            "description": summary,
            "link": item["link"]
        })
        time.sleep(2) # Short delay for API limits
        
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_items, f, indent=2, ensure_ascii=False)
        
    print(f"Success! {len(final_items)} articles saved to data.json")

if __name__ == "__main__":
    main()
