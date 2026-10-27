---
name: news_search
description: Real-time bilingual web news search, content scraping via ToolManager, and trend analysis summarization.
---

# Skill: News Search (`news_search`)

This skill executes bilingual web searches for current topics, scrapes webpage contents using `ToolManager`, and uses LLM to synthesize trends into a markdown report.

## Execution Pipeline
1. **Bilingual Search**:
   - Searches DuckDuckGo for both English and Chinese queries for the specified topic.
   - De-duplicates result URLs and retains up to 10 sources.
2. **Scrape Webpages**:
   - Concurrently invokes `ToolManager` to execute the `fetch_page_content` tool for each webpage URL.
   - Truncates and formats extracted text into structured context blocks.
3. **Trend Synthesis**:
   - Formats news context into prompt using dynamic template.
   - Analyzes trends and writes report to `state.news_report`.
