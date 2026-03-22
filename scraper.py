import feedparser
import json
import os
import time
import urllib.parse
import difflib
from datetime import datetime, timedelta
import google.generativeai as genai
from dotenv import load_dotenv

import nltk
from newspaper import Article

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

def setup_genai():
    load_dotenv()
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        print("Error: AI_API_KEY environment variable is not set.")
        exit(1)
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

def get_summary(model, title, link, fallback_text=""):
    # 1. Newspaper3k Native NLP Logic
    try:
        article = Article(link)
        article.download()
        article.parse()
        article.nlp()
        
        if article.summary and len(article.summary) > 40:
            return article.summary.replace('\n', ' ').strip()
    except Exception as e:
        pass
        
    # 2. AI-Powered Fallback
    try:
        prompt = f"Write a concise 2-sentence summary focused strictly on Digital Supply Chain implications of the following article.\n\nHeadline: {title}\nLink: {link}\nSnippet: {fallback_text}"
        response = model.generate_content(prompt)
        ai_summary = response.text.replace('\n', ' ').strip()
        if ai_summary:
            return ai_summary
    except Exception as e:
        pass
        
    # 3. Paywall / Hard Error Bypass
    return f"Strategic Insight: This article covers {title} - visit source for full technical details."

def determine_category(title, summary):
    text = (title + " " + summary).lower()
    
    if any(k in text for k in ['agentic ai', 'data fabric']):
        return 'Future-Tech'
        
    if any(k in text for k in ['wms', 'tms', 'transportation', 'warehouse', 'logistics', 'fleet', 'delivery', 'routing', 'autonomous logistics', 'agv', 'forklift', 'autonomous e-trucks']):
        return 'Logistics'
    elif any(k in text for k in ['smart manufacturing', 'iot', 'factory', 'automation', 'robot', 'digital twin', 'zero-waste', 'lineview', 'oee', 'line optimization', 'predictive maintenance', 'asset reliability', 'computer vision', 'maintenance', 'digital safety']):
        return 'Smart Manufacturing'
    elif any(k in text for k in ['procurement', 'sourcing', 'supplier', 'purchasing', 'vendor', 'ecommerce', 'e-commerce connectivity', 'gep', 'smart procurement', 'coupa']):
        return 'Procurement'
    elif any(k in text for k in ['planning', 'blue yonder', 'blueyonder', 'forecast', 'demand', 'production orchestration', 'agentic ai in planning', 'sap ibp', 'ibp', 'o9', 'llamasoft', 'control tower', 'carbon-aware planning']):
        return 'Planning'
    elif any(k in text for k in ['data', 'analytics', 'ai ', 'artificial intelligence', 'agentic', 'lake', 'ml ', 'machine learning', 'end-to-end digital thread', 'prescriptive analytics', 'generative ai', 'causal ai', 'edge computing', 'unified namespace', 'uns', 'digital product passport']):
        return 'Data Analytics'
    return 'Logistics'

def is_near_duplicate(new_title, existing_titles, threshold=0.85):
    for et in existing_titles:
        if difflib.SequenceMatcher(None, new_title, et).ratio() >= threshold:
            return True
    return False

def fetch_feed(query, existing_links, existing_titles, max_items):
    print(f"Fetching Multi-Source RSS feeds for: {query[:80]}...")
    encoded_query = urllib.parse.quote(query)
    
    rss_urls = [
        f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en",
        f"https://www.bing.com/news/search?q={encoded_query}&format=rss",
        f"https://news.search.yahoo.com/news/rss?p={encoded_query}"
    ]
    
    time_threshold = datetime(2025, 3, 22) # 1-year archive boundary enforced
    items = []
    
    for rss_url in rss_urls:
        if len(items) >= max_items:
            break
            
        print(f" -> Querying {rss_url.split('/')[2]}...")
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries:
            if len(items) >= max_items:
                break
                
            link = entry.get('link')
            title = entry.title if hasattr(entry, 'title') else ''
            title_lower = title.lower().strip()
            
            # The strict 'Supply Chain' Title Mandate
            if 'supply chain' not in title_lower:
                continue
            
            if not link or link in existing_links or not title:
                continue
                
            # Smart 85-90% Headline Similarity Filter
            if is_near_duplicate(title_lower, existing_titles, 0.85):
                continue
                
            # Strict Exclusions Corporate Filter (Python level secondary blocker)
            noise_words = ['stock market', 'stock price', 'share price', 'dividend', 'nyse', 'nasdaq', 'investor relations', 'ceo', 'chief', 'appointment', 'promotion', 'hiring', 'earnings', 'board of directors', 'marketing', 'flavor', 'branding']
            if any(w in title_lower for w in noise_words):
                continue
                
            published_time = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_time = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published_time = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                
            if published_time and published_time >= time_threshold:
                date_str = published_time.strftime("%d.%m.%Y")
                
                image_url = ""
                if hasattr(entry, 'media_content') and entry.media_content:
                    image_url = entry.media_content[0].get('url', '')
                
                if not image_url and hasattr(entry, 'description') and entry.description:
                    import re
                    match = re.search(r'<img[^>]+src="([^">]+)"', entry.description)
                    if match:
                        image_url = match.group(1)
                
                if not image_url:
                    safe_seed = urllib.parse.quote(entry.title[:30].replace(' ', ''))
                    image_url = f"https://picsum.photos/seed/{safe_seed}/800/450"
                
                item = {
                    "raw_date": published_time,
                    "image": image_url,
                    "title": title,
                    "date": date_str,
                    "description": entry.get('description', ''),
                    "link": link
                }
                items.append(item)
                existing_links.add(link)
                existing_titles.add(title_lower)
    
    return items

def main():
    model = setup_genai()
    
    sites = "site:logisticsmgt.com OR site:blueyonder.com OR site:supplychaindive.com OR site:scmr.com OR site:fooddive.com OR site:supplychainbrain.com OR site:inboundlogistics.com OR site:dcvelocity.com OR site:mhlnews.com OR site:procurious.com OR site:forecastingblog.com OR site:blog.siemens.com OR site:intuit.com OR site:infor.com OR site:gep.com OR site:siemens.com OR site:lineview.com OR site:beveragedaily.com OR site:foodindustryexecutive.com OR site:maintenancetechnology.com"
    
    base_query = 'intitle:"Supply Chain" (FMCG OR Beverage OR Food OR "Coca Cola" OR Bottling OR Bottlers OR "Consumer industry" OR Asahi OR Pepsi)'
    exclusions = '-CEO -Chief -appointment -promotion -hiring -earnings -"stock price" -"share price" -"Board of Directors" -marketing -flavor -branding -"stock" -"share" -"dividend"'
    
    core_tech = '(GEP OR Siemens OR Lineview OR BlueYonder OR "SAP IBP" OR WMS OR TMS OR RPA OR "Data Lake" OR "computer vision" OR "Siemens MIS" OR SAP OR "S/4 Hana" OR O9 OR "Demand Forecasting" OR Planning OR IBP OR Coupa OR Llamasoft OR "Control tower")'
    next_gen_ai = '("Agentic AI" OR "Autonomous Agents" OR "Generative AI for SCM" OR "Causal AI")'
    smart_ops = '("Digital Twin" OR "Predictive Maintenance" OR "Computer Vision" OR IOT OR "Smart Manufacturing" OR OEE OR "Line Optimization" OR AGV OR Forklift OR Maintenance)'
    logistics_data = '("Autonomous e-Trucks" OR "5G Private Networks" OR "Edge Computing" OR "Data Fabric" OR "Unified Namespace" OR UNS)'
    sustainability = '("Digital Safety" OR "Asset Reliability" OR "Digital Product Passport" OR "Carbon-Aware Planning")'
    
    queries = [
        f'{base_query} {core_tech} {exclusions} ({sites}) after:2025-03-22',
        f'{base_query} {next_gen_ai} {exclusions} ({sites}) after:2025-03-22',
        f'{base_query} {smart_ops} {exclusions} ({sites}) after:2025-03-22',
        f'{base_query} {logistics_data} {exclusions} ({sites}) after:2025-03-22',
        f'{base_query} {sustainability} {exclusions} ({sites}) after:2025-03-22',
        f'("Sedef Salingan Sahin" OR "Henrique Braun") ("Coca-Cola" OR Digital OR "Supply Chain") {exclusions} after:2025-03-22'
    ]
    
    existing_links = set()
    existing_titles = set()
    all_items = []
    
    print("Running high-precision 1-Year multi-query searches...")
    for q in queries:
        if len(all_items) >= 40:
            break
        print(f"\\nExecuting Target Query Vector...")
        found_items = fetch_feed(q, existing_links, existing_titles, max_items=40 - len(all_items))
        all_items.extend(found_items)
        
    if not all_items:
        print("\nNo news found. data.json was not overwritten.")
        return
        
    print(f"\nFound {len(all_items)} articles total. Filtering duplicates, sorting by date and priority...")
    
    # Final strict deduplication pass to ensure 0 leakage before Gemini API overhead
    final_deduped_items = []
    seen_titles = []
    for item in all_items:
        if not is_near_duplicate(item['title'].lower(), seen_titles, 0.85):
            final_deduped_items.append(item)
            seen_titles.append(item['title'].lower())
    
    def sort_key(x):
        t_l = x["title"].lower()
        d_l = x["description"].lower()
        exec_priority = 2 if ('sedef salingan sahin' in t_l or 'henrique braun' in t_l or 'sedef salingan sahin' in d_l or 'henrique braun' in d_l) else 0
        standard_priority = 1 if ('coca-cola' in t_l or 'coca cola' in t_l or 'digital planning' in t_l or 'coca-cola' in d_l or 'coca cola' in d_l or 'digital planning' in d_l) else 0
        priority = max(exec_priority, standard_priority)
        return (priority, x["raw_date"])
        
    final_deduped_items.sort(key=sort_key, reverse=True)
    final_deduped_items = final_deduped_items[:40]
    
    final_items = []
    item_id = 1
    for item in final_deduped_items:
        print(f"Processing ({item_id}/{len(final_deduped_items)}): {item['title'][:30]}")
        summary = get_summary(model, item['title'], item['link'], item['description'])
        category = determine_category(item['title'], summary) # Inherently assigns only ONE single strict Category.
        
        t_l = item['title'].lower()
        s_l = summary.lower()
        if 'sedef salingan sahin' in t_l or 'henrique braun' in t_l or 'sedef salingan sahin' in s_l or 'henrique braun' in s_l:
            category = 'Planning'
            
        final_item = {
            "id": item_id,
            "image": item["image"],
            "category": category,
            "title": item["title"],
            "date": item["date"],
            "description": summary,
            "link": item["link"]
        }
        final_items.append(final_item)
        item_id += 1
        time.sleep(12.5) # Wait period to satisfy Gemini RPM limits!
        
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_items, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccess! Saved {len(final_items)} dynamically generated news cards to data.json")

if __name__ == "__main__":
    main()
