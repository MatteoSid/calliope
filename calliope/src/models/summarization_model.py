from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from llama_index.llms.ollama import Ollama
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.prompts import PromptTemplate
from loguru import logger


class SummarizationModel:
    def __init__(self, model_name: str = "hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M", base_url: str = "http://192.168.50.50:11434"):
        """
        Initialize the summarization model using Ollama.
        
        Args:
            model_name: Name of the Ollama model to use (default: "qwen2.5-3b-instruct-gguf:Q4_K_M")
            base_url: Base URL of the Ollama server (default: "http://localhost:11434")
        """
        self.llm = Ollama(
            model=model_name,
            base_url=base_url,
            request_timeout=300.0,  # Increased timeout for longer transcriptions
            temperature=0.3,  # Lower temperature for more focused and deterministic outputs
            top_p=0.9,
        )
        self.prompt_template = self._load_prompt_template()
        
    def _load_prompt_template(self) -> PromptTemplate:
        """Load the Jinja2 prompt template for summarization."""
        try:
            # Get the directory containing the prompts
            prompts_dir = Path(__file__).parent.parent / "prompts"
            env = Environment(loader=FileSystemLoader(searchpath=str(prompts_dir)))
            template = env.get_template("summarization_prompt.j2")
            # Get the template as a string
            template_str = template.render()
            # Create a PromptTemplate with the template string
            return PromptTemplate(template_str)
        except Exception as e:
            logger.error(f"Error loading prompt template: {e}")
            raise
    
    async def summarize(self, text: str, language: str = "italian") -> str:
        """
        Generate a summary of the given text if it's longer than 1 minute (approximately 150 words).
        
        Args:
            text: The text to summarize
            language: The language of the text (default: "italian")
            
        Returns:
            str: The generated summary or empty string if text is too short
            
        Raises:
            Exception: If there's an error during summarization
        """
        try:
            # Validate input
            if not text or not isinstance(text, str):
                logger.warning("Invalid input text for summarization")
                return ""
                
            # Check if text is long enough to summarize (approximately 1 minute of speech)
            word_count = len(text.split())
            if word_count < 140:  # Assuming ~150 words per minute
                logger.info(f"Text too short for summarization: {word_count} words")
                return ""
                
            logger.info(f"Generating summary for text of length: {len(text)} characters")
            
            # Clean and prepare the text
            text = text.strip()
            if not text:
                return ""
            
            # Format the prompt with the provided text and language
            try:
                prompt = self.prompt_template.format(
                    text=text,
                    language=language.capitalize()
                )
            except Exception as e:
                logger.error(f"Error formatting prompt: {e}")
                raise ValueError("Error preparing the summarization request.")
            
            # Prepare messages for the LLM
            messages = [
                ChatMessage(
                    role="system",
                    content=(
                        "Sei un assistente che riassume le trascrizioni audio in modo chiaro e conciso. "
                        "Il riassunto deve essere in italiano, ben strutturato e facile da leggere."
                    )
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"Riassumi il seguente testo in {language} mantenendo i punti principali. "
                        f"Il riassunto deve essere conciso ma completo:\n\n{text}"
                    )
                )
            ]
            
            logger.info("Starting summarization with Ollama...")
            
            # Try different methods to get a response
            summary = ""
            methods_tried = 0
            max_retries = 2
            
            while not summary and methods_tried < max_retries:
                try:
                    if methods_tried == 0:
                        # First try: streaming chat
                        logger.info("Trying streaming chat...")
                        response = await self.llm.astream_chat(messages)
                        summary_parts = []
                        async for chunk in response.async_response_gen():
                            if hasattr(chunk, 'content') and chunk.content:
                                summary_parts.append(chunk.content)
                        summary = ''.join(summary_parts).strip()
                    else:
                        # Second try: regular chat
                        logger.info("Trying regular chat...")
                        response = await self.llm.achat(messages)
                        summary = response.message.content.strip()
                    
                    # Clean up the summary
                    if summary:
                        # Remove any remaining template markers or special tokens
                        summary = (
                            summary.replace("{{ ", "")
                            .replace(" }}", "")
                            .replace("<|im_start|>", "")
                            .replace("<|im_end|>", "")
                            .strip()
                        )
                        
                        # Remove the assistant's name/prefix if present
                        for prefix in ["assistente:", "assistant:", "riassunto:", "summary:"]:
                            if summary.lower().startswith(prefix):
                                summary = summary[len(prefix):].strip()
                        
                        # Remove any leading/trailing quotes
                        summary = summary.strip('"\'')
                        
                        # Ensure the summary is not too short or too long
                        if len(summary.split()) < 10:  # If summary is too short, it's probably not good
                            logger.warning(f"Summary too short, trying again. Length: {len(summary)} chars")
                            summary = ""
                            methods_tried += 1
                            continue
                            
                        logger.info(f"Summary generated successfully. Length: {len(summary)} characters")
                        return summary
                    
                except Exception as e:
                    logger.warning(f"Attempt {methods_tried + 1} failed: {str(e)}")
                    methods_tried += 1
            
            # If we get here, all methods failed
            if not summary:
                logger.error("All summarization attempts failed")
                raise Exception("Impossibile generare un riassunto. Riprova più tardi.")
                
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}", exc_info=True)
            # Re-raise with a more user-friendly message
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                raise Exception("Il servizio di riassunto ha impiegato troppo tempo a rispondere.")
            elif "connection" in str(e).lower() or "unreachable" in str(e).lower():
                raise Exception("Impossibile connettersi al servizio di riassunto.")
            else:
                raise Exception("Si è verificato un errore durante la generazione del riassunto.")
