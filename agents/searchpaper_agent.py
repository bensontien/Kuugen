import os
import asyncio
import requests
import arxiv
import datetime
import re
from typing import List, Dict, Any
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, Event, step
from core.state import AgentState, PaperData

# OpenAlex Settings
OPENALEX_API_URL = "https://api.openalex.org/works"
TARGET_ISSNS = [
    "0001-0782", # Communications of the ACM (CACM)
    "0360-0300", # ACM Computing Surveys (CSUR)
    "0018-9340", # IEEE Transactions on Computers (TC)
    "0162-8828", # IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI)
    "2162-237X", # IEEE Transactions on Neural Networks and Learning Systems (TNNLS)
    "1532-4435", # Journal of Machine Learning Research (JMLR)
    "0004-3702", # Artificial Intelligence (Elsevier)
    "2522-5839", # Nature Machine Intelligence
    "1946-6226", # ACM Transactions on Computing Education (TOCE)
    "1939-1382", # IEEE Transactions on Learning Technologies (TLT)
    "0360-1315", # Computers & Education (Elsevier)
    "0747-5632", # Computers in Human Behavior (Elsevier)
    "0007-1013", # British Journal of Educational Technology (BJET)
    "1049-4820", # Interactive Learning Environments
    "0018-9359", # IEEE Transactions on Education (ToE)
    "1544-3566", # ACM Transactions on Architecture and Code Optimization (TACO)
    "0734-2071", # ACM Transactions on Computer Systems (TOCS)
    "0164-0925", # ACM Transactions on Programming Languages and Systems (TOPLAS)
    "0278-0070", # IEEE Transactions on Computer-Aided Design of Integrated Circuits and Systems (TCAD)
    "0272-1732", # IEEE Micro
    "0098-5589", # IEEE Transactions on Software Engineering (TSE)
    "1041-4347", # IEEE Transactions on Knowledge and Data Engineering (TKDE)
    "1045-9219"  # IEEE Transactions on Parallel and Distributed Systems (TPDS)
]
MAILTO = "banson56561ncu@g.ncu.edu.tw"

def reconstruct_openalex_abstract(inverted_index: Dict[str, List[int]]) -> str:
    """Reconstructs abstract from inverted index."""
    if not inverted_index:
        return "No Abstract Available."
    word_index_list = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_index_list.append((pos, word))
    return " ".join([word for _, word in sorted(word_index_list, key=lambda x: x[0])])

async def _score_single_paper(paper: Dict, user_topic: str, llm) -> Dict:
    """Scores paper relevance using LLM."""
    prompt = f"""Score paper abstract based on relevance (0-10 per dimension).
    Topic: "{user_topic}"
    Title: {paper['title']}
    Abstract: {paper['summary']}
    Dimensions: Relevance, Innovation, Technical Depth, Practical Value, Impact, Rigor.
    Output:
    Total Score: [Total Score]
    """
    try:
        if len(paper['summary']) < 50:
            paper['score'] = 0
            paper['detailed_score'] = "Abstract too short"
            return paper

        response = await llm.acomplete(prompt)
        res_text = str(response)
        scores = re.findall(r"Total Score:\s*(\d+)", res_text)
        paper['score'] = int(scores[0]) if scores else 0
        paper['detailed_score'] = res_text
    except Exception as e:
        paper['score'] = 0
        paper['detailed_score'] = f"Scoring failed: {e}"
    return paper

# --- Workflow Events ---
class FetchEvent(Event):
    state: AgentState
    papers: List[Dict]

class ScoreEvent(Event):
    state: AgentState
    scored_papers: List[Dict]

class SnowballEvent(Event):
    state: AgentState
    scored_papers: List[Dict]

class SummaryEvent(Event):
    state: AgentState
    scored_papers: List[Dict]
    final_report: str

# --- Integrated Workflow ---
class SearchPaperAgent(Workflow):
    def __init__(self, llm, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm

    @step
    async def fetch_papers(self, ev: StartEvent) -> FetchEvent:
        state: AgentState = ev.get("state")
        raw_prompt = state.user_topic
        print(f"Starting Deep SearchPaperAgent | Arxiv + OpenAlex")

        # Extract core topic
        print("Extracting core research topic...")
        extract_prompt = f"Extract core topic from: '{raw_prompt}'. English only, no quotes."
        try:
            core_topic_res = await self.llm.acomplete(extract_prompt)
            core_topic = str(core_topic_res).strip().replace('"', '').replace("'", "")
        except:
            core_topic = raw_prompt
        state.search_keywords_used = [core_topic]

        # SLR keyword expansion
        print("Performing SLR expansion...")
        query_prompt = f"Convert to Boolean query string: '{core_topic}'"
        try:
            expanded = await self.llm.acomplete(query_prompt)
            search_query = str(expanded).strip().replace('"', '')
        except:
            search_query = core_topic

        def fetch_arxiv(query):
            print(f" [Arxiv] Fetching preprints...")
            papers = []
            try:
                search = arxiv.Search(query=query, max_results=30, sort_by=arxiv.SortCriterion.SubmittedDate)
                for r in search.results():
                    papers.append({
                        "title": r.title.replace("\n", " "), "summary": r.summary.replace("\n", " "),
                        "url": r.pdf_url, "venue": "Arxiv Preprint", "date": r.published.strftime("%Y-%m-%d"), "id": r.entry_id
                    })
            except: pass
            return papers

        def fetch_openalex(query):
            print(f" [OpenAlex] Fetching journal articles...")
            papers = []
            params = {
                "filter": f"primary_location.source.issn:{'|'.join(TARGET_ISSNS)},default.search:{query},from_publication_date:2024-01-01",
                "sort": "publication_date:desc", "per_page": 30, "mailto": MAILTO
            }
            try:
                resp = requests.get(OPENALEX_API_URL, params=params)
                results = resp.json().get("results", [])
                for r in results:
                    papers.append({
                        "title": r.get("title", "No Title"),
                        "summary": reconstruct_openalex_abstract(r.get("abstract_inverted_index")),
                        "url": r.get("doi") or r.get("primary_location", {}).get("landing_page_url", "No URL"),
                        "venue": r.get("primary_location", {}).get("source", {}).get("display_name", "Unknown Journal"),
                        "date": r.get("publication_date"), "id": r.get("id"), "referenced_works": r.get("referenced_works", [])
                    })
            except: pass
            return papers

        loop = asyncio.get_event_loop()
        ar_res, oa_res = await asyncio.gather(
            loop.run_in_executor(None, fetch_arxiv, core_topic),
            loop.run_in_executor(None, fetch_openalex, search_query)
        )
        all_papers = ar_res + oa_res
        unique = []
        seen = set()
        for p in all_papers:
            if p['title'].lower() not in seen:
                seen.add(p['title'].lower()); unique.append(p)
        return FetchEvent(state=state, papers=unique)

    @step
    async def score_papers(self, ev: FetchEvent) -> ScoreEvent:
        if not ev.papers: return ScoreEvent(state=ev.state, scored_papers=[])
        print(f"Scoring {len(ev.papers)} papers...")
        scored = []
        for i in range(0, len(ev.papers), 10):
            batch = ev.papers[i:i+10]
            results = await asyncio.gather(*[_score_single_paper(p, ev.state.user_topic, self.llm) for p in batch])
            scored.extend(results)
            await asyncio.sleep(1)
        top_20 = sorted(scored, key=lambda x: x['score'], reverse=True)[:20]
        return ScoreEvent(state=ev.state, scored_papers=top_20)

    @step
    async def snowball_expansion(self, ev: ScoreEvent) -> SnowballEvent:
        if not ev.scored_papers: return SnowballEvent(state=ev.state, scored_papers=[])
        top = ev.scored_papers[0]
        ref_ids = top.get("referenced_works", [])
        if not ref_ids: return SnowballEvent(state=ev.state, scored_papers=ev.scored_papers)
        print(f"Backward Snowballing for: {top['title']}")
        params = {"filter": f"openalex_id:{'|'.join([u.split('/')[-1] for u in ref_ids[:10]])}", "per_page": 10, "mailto": MAILTO}
        try:
            resp = requests.get(OPENALEX_API_URL, params=params)
            results = resp.json().get("results", [])
            sb_papers = []
            for r in results:
                sb_papers.append({
                    "title": f"[Snowball] {r.get('title')}",
                    "summary": reconstruct_openalex_abstract(r.get("abstract_inverted_index")),
                    "url": r.get("doi") or (r.get("primary_location") or {}).get("landing_page_url"),
                    "venue": ((r.get("primary_location") or {}).get("source") or {}).get("display_name"),
                    "date": r.get("publication_date"), "id": r.get("id")
                })
            if sb_papers:
                scored_sb = await asyncio.gather(*[_score_single_paper(p, ev.state.user_topic, self.llm) for p in sb_papers])
                final = sorted(ev.scored_papers + scored_sb, key=lambda x: x['score'], reverse=True)[:20]
                return SnowballEvent(state=ev.state, scored_papers=final)
        except: pass
        return SnowballEvent(state=ev.state, scored_papers=ev.scored_papers)

    @step
    async def generate_summary(self, ev: SnowballEvent) -> SummaryEvent:
        if not ev.scored_papers: return SummaryEvent(state=ev.state, scored_papers=[], final_report="")
        print(f"Generating summary for Top {len(ev.scored_papers)} papers...")
        report = f"## Deep Literature Review\n**Topic**: {ev.state.user_topic}\n\n---\n\n"
        async def summarize(p):
            prompt = f"Summarize in Traditional Chinese: {p['title']}\n{p['summary']}"
            try: return str(await self.llm.acomplete(prompt))
            except: return "Summary failed"
        summaries = await asyncio.gather(*[summarize(p) for p in ev.scored_papers])
        for i, (p, s) in enumerate(zip(ev.scored_papers, summaries)):
            report += f"### {i+1}. {p['title']}\n- Rank: {i+1} | Score: {p['score']}/60\n- {p['venue']} | {p['date']}\n\n{s}\n\n[PDF]({p['url']})\n\n---\n\n"
        return SummaryEvent(state=ev.state, scored_papers=ev.scored_papers, final_report=report)

    @step
    async def save_report(self, ev: SummaryEvent) -> StopEvent:
        state = ev.state
        if not ev.scored_papers:
            state.chat_reply = "No papers found."; return StopEvent(result=state)
        filename = f"Papers/DeepReview_{datetime.date.today()}.md"
        os.makedirs("Papers", exist_ok=True)
        try:
            with open(filename, "w", encoding="utf-8") as f: f.write(ev.final_report)
            state.search_report_file = filename
            state.top_paper = PaperData(title=ev.scored_papers[0]['title'], url=ev.scored_papers[0]['url'])
            state.search_report_content = ev.final_report 
            state.chat_reply = "Search completed and report generated."
        except: state.chat_reply = "Error saving report."
        return StopEvent(result=state)