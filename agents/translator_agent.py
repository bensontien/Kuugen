import os
import asyncio
import fitz
from typing import List, Tuple
from core.base_agent import BaseAgent
from core.state import AgentState

class PDFTranslatorAgent(BaseAgent):
    def __init__(self, llm, **kwargs):
        super().__init__(llm=llm, **kwargs)

    async def load_and_chunk(self, state: AgentState) -> Tuple[AgentState, List[str], str]:
        if not state.top_paper or not state.top_paper.pdf_path:
            print("[Translator] Error: PDF path not found in State.")
            state.is_aborted = True
            return state, [], ""
            
        pdf_path = state.top_paper.pdf_path
        print(f"[Translator] Reading PDF: {pdf_path}")
        
        if not os.path.exists(pdf_path):
            print(f"[Translator] Error: File not found {pdf_path}")
            state.is_aborted = True
            return state, [], ""

        try:
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text()
        except Exception as e:
            print(f"[Translator] Failed to read PDF: {e}")
            state.is_aborted = True
            return state, [], ""
        
        chunk_size = 2000
        chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
        
        file_name = os.path.basename(pdf_path).replace(".pdf", "")
        print(f"Segmented into {len(chunks)} chunks, preparing for translation...")
        
        return state, chunks, file_name

    async def translate_chunks(self, state: AgentState, chunks: List[str], file_name: str) -> AgentState:
        print(f"[Translator] Starting parallel translation (Total {len(chunks)} chunks)...")
        
        os.makedirs("Papers", exist_ok=True)
        output_path = f"Papers/Translated_{file_name}.md"
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {file_name} (Full Traditional Chinese Translation)\n\n")

        async def translate_single_chunk(i: int, chunk: str):
            print(f"   Translating chunk {i+1}/{len(chunks)}...")
            prompt = f"""You are a professional computer science academic translator.
            Please translate the following paper excerpt into Traditional Chinese (Taiwan academic terminology).
            
            Requirements:
            1. Preserve mathematical formulas in LaTeX format (e.g., $E=mc^2$).
            2. Keep proper nouns (e.g., LLM, Transformer, zero-shot) in English or provide them in parentheses.
            3. Maintain a rigorous and fluent academic tone.

            Original excerpt:
            {chunk}

            Please output ONLY the translated result without any additional explanations.
            """
            try:
                response = await self.llm.acomplete(prompt)
                return i, str(response)
            except Exception as e:
                print(f"Translation failed for chunk {i+1}: {e}")
                return i, f"\n\n[Error: Translation failed for chunk {i+1}]\n\n"

        tasks = [translate_single_chunk(i, chunk) for i, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks)
        
        results.sort(key=lambda x: x[0])

        with open(output_path, "a", encoding="utf-8") as f:
            for i, translated_text in results:
                f.write(f"\n\n## Section {i+1}\n\n")
                f.write(translated_text)

        print(f"Translation complete! File saved at: {output_path}")
        
        state.final_translated_file = output_path
        return state

    async def run(self, state: AgentState) -> AgentState:
        state, chunks, file_name = await self.load_and_chunk(state)
        if state.is_aborted or not chunks:
            return state
        return await self.translate_chunks(state, chunks, file_name)
