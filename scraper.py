import feedparser
import json
import os
import time
import urllib.parse
import difflib
from datetime import datetime, timedelta
import google.generativeai as genai

def setup_genai():
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
    return genai.GenerativeModel('gemini-pro')

def get_summary(model, title, link, fallback_text=""):
    try:
        prompt = (
            f"Write a concise 2-sentence summary focused on SAP S/4HANA Business Process transformation. "
            f"Mention specific modules (MM, PP, SCM, etc.) if relevant to the article.\n\n"
            f"Headline: {title}\n"
            f"Link: {link}\n"
            f"Context: {fallback_text[:500]}"
        )
        response = model.generate_content(prompt)
        ai_summary = response.text.replace('\n', ' ').strip()
        return ai_summary if ai_summary else f"SAP Functional Update: {title}"
    except Exception as e:
        print(f"Gemini Error: {e}")
    
    return f"SAP Strategic Insight: Functional update regarding {title}."

def determine_category(title, summary):
    text = (title + " " + summary).lower()
    
    # Category 1: SAP AI & Innovation
    if any(k in text for k in ['joule', 'agentic', 'copilot', 'generative ai', 'ai assistant']): 
        return 'SAP AI (Joule)'
    
    # Category 2: Digital Supply Chain & PTD
    if any(k in text for k in ['scm', 'ptd', 'plan to deliver', 'ibp', 'ewm', 'tm', 'supply chain']): 
        return 'Digital Supply Chain'
    
    # Category 3: Manufacturing & Production (PP)
    if any(k in text for k in [' pp ', 'production planning', 'manufacturing', 'shop floor', 'mrp']): 
        return 'Manufacturing (PP)'
    
    # Category 4: Sourcing & Procurement (MM)
    if any(k in text for k in [' mm ', 'materials management', 'procurement', 'inventory', 'sourcing', 'ariba']): 
        return 'Sourcing & Procurement (MM)'
    
    # Category 5: Infrastructure & Core
    if any(k in text for k in ['clean core', 'btp', 's/4hana cloud', 'rise', 'grow']): 
        return 'Platform & Core'
    
    return 'General SAP News'

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
    
    time_threshold = datetime.now() - timedelta(days=365)
    items = []
    
    for rss_url in rss_urls:
        if len(items) >= max_items: break
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                if len(items) >= max_items: break
                
                link = entry.get('link')
                title = entry.title if hasattr(entry, 'title') else ''
                title_lower = title.lower().strip()
                
                # Validation against your requested keywords
                valid_keywords = ['sap', 's/4hana', 's4hana', 'joule', 'scm', 'ptd', 'ibp']
                if not any(k in title_lower for k in valid_keywords): continue
                if link in existing_links or is_near_duplicate(title_lower, existing_titles): continue
                
                published_time = datetime.fromtimestamp(time.mktime(entry.published_parsed)) if hasattr(entry, 'published_parsed') else None
                
                if published_time and published_time >= time_threshold:
                    safe_seed = urllib.parse.quote(title[:20])
                    items.append({
                        "raw_date": published_time,
                        "image": f"https://picsum.photos/seed/{safe_seed}/800/450",
                        "title": title,
                        "date": published_time.strftime("%d.%m.%Y"),
                        "description": entry.get('description', ''),
                        "link": link
                    })
                    existing_links.add(link)
                    existing_titles.add(title_lower)
        except Exception:
            continue
    return items

def main():
    model = setup_genai()
    
    # 1. Functional Queries (MM, PP, SCM, PTD)
    functional_query = 'SAP ("MM" OR "PP" OR "SCM" OR "PTD" OR "Plan to Deliver" OR "Materials Management" OR "Production Planning")'
    
    # 2. Tech Queries (Joule, AI, BTP)
    tech_query = 'SAP ("Joule" OR "Agentic AI" OR "Clean Core" OR "BTP")'
    
    # 3. Industry/Module Specific (IBP, EWM, TM)
    supply_chain_query = 'SAP ("IBP" OR "EWM" OR "Digital Supply Chain" OR "Integrated Business Planning")'

    queries = [functional_query, tech_query, supply_chain_query]
    
    existing_links, existing_titles, all_items = set(), set(), []
    
    for q in queries:
        found = fetch_feed(q, existing_links, existing_titles, max_items=25)
        all_items.extend(found)

    # Sort by date (newest first)
    all_items.sort(key=lambda x: x['raw_date'], reverse=True)

    final_items = []
    for i, item in enumerate(all_items[:60]):
        print(f"Summarizing {i+1}: {item['title'][:50]}...")
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
        time.sleep(2) # Avoid AI rate limits
        
    with open("sap_expert_data.json", "w", encoding="utf-8") as f:
        json.dump(final_items, f, indent=2, ensure_ascii=False)
        
    print(f"Done! {len(final_items)} articles exported.")

if __name__ == "__main__":
    main()
