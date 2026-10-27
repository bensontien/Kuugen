import asyncio
from core.state import AgentState
try:
    from duckduckgo_search import DDGS
except ImportError:
    from ddgs import DDGS

async def fetch_news_data(topic: str, tool_manager):
    print(f"[News Skill] Executing bilingual web search for topic '{topic}'...")
    
    search_results_meta = []
    try:
        with DDGS() as ddgs:
            en_results = list(ddgs.text(f"{topic}", max_results=5))
            zh_results = list(ddgs.text(f"{topic}", max_results=5))
            
            seen_urls = set()
            for r in en_results + zh_results:
                href = r.get('href')
                if href and href not in seen_urls:
                    seen_urls.add(href)
                    search_results_meta.append(r)
    except Exception as e:
        print(f"[News Skill] Web search failed: {e}")

    search_results_meta = search_results_meta[:10]

    if not search_results_meta:
        return "Unable to obtain the latest web information."

    tasks = []
    for meta in search_results_meta:
        if tool_manager:
            task = tool_manager.execute(
                "fetch_page_content", 
                url=meta.get('href'), 
                max_chars=1000
            )
            tasks.append(task)
    
    if not tasks:
        return "Unable to obtain the latest web information."

    print(f"[News Skill] Concurrently calling ToolManager for {len(tasks)} webpages...")
    page_contents = await asyncio.gather(*tasks, return_exceptions=True)

    context_blocks = []
    for meta, content in zip(search_results_meta, page_contents):
        if isinstance(content, Exception):
            content = f"(Tool Error: {str(content)})"
            
        block = f"Title: {meta.get('title')}\nLink: {meta.get('href')}\nScraped Content: \n{content}"
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
