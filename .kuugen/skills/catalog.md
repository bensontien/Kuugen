# Available Skill Categories
When assigning tasks to `GenericAgent`, you can choose the category that best fits the required action:

* **`academic_research`**: 
  Use this skill to perform deep academic literature search and review across ArXiv preprints and OpenAlex top journals (using `search_paper`).
* **`academic_translation`**: 
  Use this skill to read, segment, and translate academic PDF papers into Traditional Chinese (using `pdf_translator`).
* **`web_scraping`**: 
  Use this skill to search real-time news (using `news_search`) or fetch and scrape webpage content from specific URLs (using `fetch_page_content`).
* **`system_ops`**: 
  Use this skill to interact with the host operating system (Windows PowerShell commands, files, directories, hardware/network status using `execute_windows_command`).
* **`general`**: 
  General conversation, reasoning, code synthesis, or direct answers without external tool execution.
