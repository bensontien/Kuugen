---
name: search_paper
description: Deep literature review and search skill across ArXiv preprints and OpenAlex top-journal papers with 6-dimension scoring and backward snowballing.
---

# Skill: Search Paper (`search_paper`)

This skill performs a rigorous academic literature review on a given research topic using ArXiv and OpenAlex databases.

## Execution Pipeline
1. **Fetch Papers**:
   - Extracts core English research topic and boolean query string from user prompt using LLM.
   - Concurrently fetches up to 30 preprints from ArXiv and 30 journal articles from OpenAlex top journal whitelist.
   - De-duplicates by normalized paper titles.
2. **Score Papers**:
   - Evaluates each paper across 6 dimensions: Relevance, Innovation, Technical Depth, Practical Value, Impact, and Rigor (Total 60 points).
   - Ranks papers and selects Top 20 candidates.
3. **Backward Snowballing**:
   - Extracts referenced works from the top-ranked paper.
   - Fetches and scores related foundational papers, integrating them into the ranking pool.
4. **Generate Summary**:
   - Produces comprehensive academic summaries in Traditional Chinese (Taiwan terminology).
   - Formats ranking, publication venue, scores, and PDF URLs into Markdown.
5. **Save Report**:
   - Saves final report to `Papers/DeepReview_YYYY-MM-DD.md`.
   - Injects top paper data and summary report into `AgentState`.
