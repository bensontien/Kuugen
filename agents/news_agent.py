import asyncio
from core.base_agent import BaseAgent
from core.state import AgentState
from ddgs import DDGS 
from core.prompt_loader import PromptLoader

class NewsAgent(BaseAgent):
    def __init__(self, llm, tool_manager, **kwargs):
        super().__init__(llm=llm, tool_manager=tool_manager, **kwargs)

    async def run(self, state: AgentState) -> AgentState:
        topic = state.user_topic
        
        print(f"[NewsAgent] Executing bilingual web search for topic '{topic}'...")
        
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
            print(f"[NewsAgent] Web search failed: {e}")

        search_results_meta = search_results_meta[:10]

        if not search_results_meta:
            context_text = "Unable to obtain the latest web information."
        else:
            tasks = []
            for meta in search_results_meta:
                task = self.tool_manager.execute(
                    "fetch_page_content", 
                    url=meta.get('href'), 
                    max_chars=1000
                )
                tasks.append(task)
            
            print(f"[NewsAgent] Concurrently calling ToolManager for {len(tasks)} webpages...")
            page_contents = await asyncio.gather(*tasks, return_exceptions=True)

            context_blocks = []
            for meta, content in zip(search_results_meta, page_contents):
                if isinstance(content, Exception):
                    content = f"(Tool Error: {str(content)})"
                    
                block = f"Title: {meta.get('title')}\nLink: {meta.get('href')}\nScraped Content: \n{content}"
                context_blocks.append(block)
                
            context_text = "\n\n---\n\n".join(context_blocks)

        print("[NewsAgent] Content scraping complete! Analyzing trends...")
        
        prompt_template = PromptLoader.load_agent_prompt("news_agent")
        prompt = prompt_template.format(
            topic=topic,
            context_text=context_text
        )
        
        try:
            response = await self.llm.acomplete(prompt)
            news_text = str(response).strip()
        except Exception as e:
            news_text = "Unable to fetch the latest news summary."

        state.news_report = news_text
        return state
