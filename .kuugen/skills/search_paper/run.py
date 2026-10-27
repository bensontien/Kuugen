import os
import asyncio
import requests
import arxiv
import datetime
import re
from typing import List, Dict, Tuple
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

async def fetch_papers(state: AgentState, llm) -> Tuple[AgentState, List[Dict]]:
    raw_prompt = state.user_topic
    print("Starting Deep SearchPaper Skill | Arxiv + OpenAlex")

    # Extract core topic
    print("Extracting core research topic...")
    extract_prompt = f"Extract core topic from: '{raw_prompt}'. English only, no quotes."
    try:
        core_topic_res = await llm.acomplete(extract_prompt)
        core_topic = str(core_topic_res).strip().replace('"', '').replace("'", "")
    except Exception:
        core_topic = raw_prompt
    state.search_keywords_used = [core_topic]

    # SLR keyword expansion
    print("Performing SLR expansion...")
    query_prompt = f"Convert to Boolean query string: '{core_topic}'"
    try:
        expanded = await llm.acomplete(query_prompt)
        search_query = str(expanded).strip().replace('"', '')
    except Exception:
        search_query = core_topic

    def fetch_arxiv(query):
        print(" [Arxiv] Fetching preprints...")
        papers = []
        try:
            search = arxiv.Search(query=query, max_results=30, sort_by=arxiv.SortCriterion.SubmittedDate)
            for r in search.results():
                papers.append({
                    "title": r.title.replace("\n", " "), "summary": r.summary.replace("\n", " "),
                    "url": r.pdf_url, "venue": "Arxiv Preprint", "date": r.published.strftime("%Y-%m-%d"), "id": r.entry_id
                })
        except Exception:
            pass
        return papers

    def fetch_openalex(query):
        print(" [OpenAlex] Fetching journal articles...")
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
        except Exception:
            pass
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
            seen.add(p['title'].lower())
            unique.append(p)
    return state, unique

async def score_papers(state: AgentState, papers: List[Dict], llm) -> Tuple[AgentState, List[Dict]]:
    if not papers:
        return state, []
    print(f"Scoring {len(papers)} papers...")
    scored = []
    for i in range(0, len(papers), 10):
        batch = papers[i:i+10]
        results = await asyncio.gather(*[_score_single_paper(p, state.user_topic, llm) for p in batch])
        scored.extend(results)
        await asyncio.sleep(1)
    top_20 = sorted(scored, key=lambda x: x['score'], reverse=True)[:20]
    return state, top_20

async def snowball_expansion(state: AgentState, scored_papers: List[Dict], llm) -> Tuple[AgentState, List[Dict]]:
    if not scored_papers:
        return state, []
    top = scored_papers[0]
    ref_ids = top.get("referenced_works", [])
    if not ref_ids:
        return state, scored_papers
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
            scored_sb = await asyncio.gather(*[_score_single_paper(p, state.user_topic, llm) for p in sb_papers])
            final = sorted(scored_papers + scored_sb, key=lambda x: x['score'], reverse=True)[:20]
            return state, final
    except Exception:
        pass
    return state, scored_papers

async def generate_summary(state: AgentState, scored_papers: List[Dict], llm) -> Tuple[AgentState, List[Dict], str]:
    if not scored_papers:
        return state, [], ""
    print(f"Generating summary for Top {len(scored_papers)} papers...")
    report = f"## Deep Literature Review\n**Topic**: {state.user_topic}\n\n---\n\n"
    
    async def summarize(p):
        prompt = f"Summarize in Traditional Chinese: {p['title']}\n{p['summary']}"
        try:
            return str(await llm.acomplete(prompt))
        except Exception:
            return "Summary failed"
            
    summaries = await asyncio.gather(*[summarize(p) for p in scored_papers])
    for i, (p, s) in enumerate(zip(scored_papers, summaries)):
        report += f"### {i+1}. {p['title']}\n- Rank: {i+1} | Score: {p['score']}/60\n- {p['venue']} | {p['date']}\n\n{s}\n\n[PDF]({p['url']})\n\n---\n\n"
    return state, scored_papers, report

async def save_report(state: AgentState, scored_papers: List[Dict], final_report: str) -> AgentState:
    if not scored_papers:
        state.chat_reply = "No papers found."
        return state
    filename = f"Papers/DeepReview_{datetime.date.today()}.md"
    os.makedirs("Papers", exist_ok=True)
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_report)
        state.search_report_file = filename
        state.top_paper = PaperData(title=scored_papers[0]['title'], url=scored_papers[0]['url'])
        state.search_report_content = final_report 
        state.chat_reply = "Search completed and report generated."
    except Exception:
        state.chat_reply = "Error saving report."
    return state

async def execute(state: AgentState, llm=None, tool_manager=None, **kwargs) -> AgentState:
    """Standard entrypoint for search_paper skill."""
    state, papers = await fetch_papers(state, llm)
    state, scored = await score_papers(state, papers, llm)
    state, final_scored = await snowball_expansion(state, scored, llm)
    state, final_scored, report = await generate_summary(state, final_scored, llm)
    state = await save_report(state, final_scored, report)
    return state
