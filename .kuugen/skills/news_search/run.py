import asyncio
import urllib.parse
import xml.etree.ElementTree as ET
import httpx
from core.state import AgentState

async def fetch_news_data(topic: str, tool_manager=None) -> str:
    search_topic = topic.strip() if topic and topic.strip() else "科技"
    print(f"[News Skill] Executing Google News RSS search for topic '{search_topic}'...")
    
    query = urllib.parse.quote(search_topic)
    urls = [
        f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    news_items = []
    seen_links = set()
    
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
            responses = await asyncio.gather(*[client.get(u) for u in urls], return_exceptions=True)
            for resp in responses:
                if isinstance(resp, Exception) or resp.status_code != 200:
                    continue
                try:
                    root = ET.fromstring(resp.text)
                    for item in root.findall("./channel/item")[:5]:
                        title = item.findtext("title", "").strip()
                        link = item.findtext("link", "").strip()
                        pub_date = item.findtext("pubDate", "").strip()
                        desc = item.findtext("description", "").strip()
                        if link and link not in seen_links:
                            seen_links.add(link)
                            news_items.append({
                                "title": title,
                                "link": link,
                                "pub_date": pub_date,
                                "description": desc
                            })
                except Exception as parse_err:
                    print(f"[News Skill] XML parse warning: {parse_err}")
    except Exception as e:
        print(f"[News Skill] RSS request error: {e}")

    if not news_items:
        return "Unable to obtain the latest web news."

    # If tool_manager is available, optionally fetch detailed contents for top articles
    scraped_contents = {}
    if tool_manager:
        tasks = []
        target_items = news_items[:5]
        for it in target_items:
            task = tool_manager.execute("fetch_page_content", url=it["link"], max_chars=1000)
            tasks.append((it["link"], task))
        
        if tasks:
            print(f"[News Skill] Concurrently calling ToolManager for {len(tasks)} webpages...")
            gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
            for (url, _), res in zip(tasks, gathered):
                if not isinstance(res, Exception):
                    scraped_contents[url] = str(res)

    context_blocks = []
    for it in news_items[:10]:
        content = scraped_contents.get(it["link"], it["description"] or "No detailed content available.")
        block = f"Title: {it['title']}\nPublished Date: {it['pub_date']}\nLink: {it['link']}\nContent: \n{content}"
        context_blocks.append(block)

    return "\n\n---\n\n".join(context_blocks)

async def execute(state: AgentState, llm=None, tool_manager=None, **kwargs) -> AgentState:
    """Standard entrypoint for news_search skill."""
    topic = state.user_topic
    context_text = await fetch_news_data(topic, tool_manager)

    print("[News Skill] Content scraping complete! Analyzing trends...")
    
    prompt = f"""You are a professional tech news journalist and trend analyst.
Based on the following [Latest Scraped Web Content], please summarize the current technological development trends, important news, or industry dynamics regarding this topic.

Topic: "{topic}"

[Latest Scraped Web Content]:
{context_text}

Requirements:
1. Please synthesize this information and output a summary using a bulleted list.
2. Keep it concise and professional.
3. The content must be strictly based on the provided content above.
4. [IMPORTANT]: Add a "References" section using Markdown link format: [News Title](Original Link).
5. Please output in Traditional Chinese using Markdown.
"""
    
    try:
        response = await llm.acomplete(prompt)
        news_text = str(response).strip()
    except Exception as e:
        news_text = "Unable to fetch the latest news summary."

    state.news_report = news_text
    return state
