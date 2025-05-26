import abc
import os
import httpx
import openai # type: ignore

# Custom Exception
class SummarizationError(Exception):
    """Custom exception for errors during summarization."""
    pass

# Abstract Base Class for Summarizers
class Summarizer(abc.ABC):
    """Abstract base class for summarizers."""

    @abc.abstractmethod
    def summarize(self, text: str) -> str:
        """
        Summarizes the given text.

        Args:
            text: The text to summarize.

        Returns:
            The summarized text.

        Raises:
            SummarizationError: If an error occurs during summarization.
        """
        pass

# Concrete Implementations

class OpenAISummarizer(Summarizer):
    """Summarizer using the OpenAI API."""
    def __init__(self, api_key: str):
        """
        Initializes the OpenAISummarizer.

        Args:
            api_key: The OpenAI API key.
        """
        if not api_key:
            raise ValueError("OpenAI API key is required.")
        self.api_key = api_key
        self.client = openai.OpenAI(api_key=self.api_key)

    def summarize(self, text: str) -> str:
        """
        Summarizes the given text using the OpenAI API.

        Args:
            text: The text to summarize.

        Returns:
            The summarized text.

        Raises:
            SummarizationError: If an error occurs during summarization.
        """
        prompt = f"Summarize the following text:\n\n{text}"
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes text."},
                    {"role": "user", "content": prompt}
                ]
            )
            summary = response.choices[0].message.content
            if not summary:
                raise SummarizationError("OpenAI returned an empty summary.")
            return summary.strip()
        except openai.APIError as e:
            raise SummarizationError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise SummarizationError(f"An unexpected error occurred with OpenAI: {e}") from e


class OllamaSummarizer(Summarizer):
    """Summarizer using a self-hosted Ollama instance."""
    def __init__(self, base_url: str, model_name: str = "llama2:latest"):
        """
        Initializes the OllamaSummarizer.

        Args:
            base_url: The base URL of the Ollama API.
            model_name: The name of the Ollama model to use.
        """
        if not base_url:
            raise ValueError("Ollama base URL is required.")
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout = 30 # Default timeout for requests

    def summarize(self, text: str) -> str:
        """
        Summarizes the given text using the Ollama API.

        Args:
            text: The text to summarize.

        Returns:
            The summarized text.

        Raises:
            SummarizationError: If an error occurs during summarization.
        """
        prompt = f"Summarize the following text:\n\n{text}"
        api_url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False  # Get the full response at once
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(api_url, json=payload)
                response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
                response_data = response.json()
                
                summary = response_data.get("response")
                if not summary:
                    raise SummarizationError("Ollama API response did not contain a summary.")
                return summary.strip()
        except httpx.HTTPStatusError as e:
            raise SummarizationError(f"Ollama API request failed with status {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise SummarizationError(f"Ollama API request failed: {e}") from e
        except Exception as e:
            raise SummarizationError(f"An unexpected error occurred with Ollama: {e}") from e


class VLLMSummarizer(Summarizer):
    """Summarizer using a self-hosted vLLM instance (OpenAI-compatible)."""
    def __init__(self, base_url: str, model_name: str = "mistralai/Mistral-7B-Instruct-v0.1"):
        """
        Initializes the VLLMSummarizer.

        Args:
            base_url: The base URL of the vLLM API.
            model_name: The name of the vLLM model to use.
        """
        if not base_url:
            raise ValueError("vLLM base URL is required.")
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout = 60 # Default timeout for requests

    def summarize(self, text: str) -> str:
        """
        Summarizes the given text using the vLLM API.

        Args:
            text: The text to summarize.

        Returns:
            The summarized text.

        Raises:
            SummarizationError: If an error occurs during summarization.
        """
        prompt = f"Summarize the following text:\n\n{text}"
        # Using the /v1/completions endpoint as vLLM is often OpenAI compatible
        api_url = f"{self.base_url}/v1/completions"
        
        # Payload for OpenAI-compatible completion endpoint
        # Note: vLLM might also support /v1/chat/completions, which would be more similar to OpenAI's structure
        # For simplicity, using /v1/completions. This might need adjustment based on specific vLLM setup.
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": 512,  # Max tokens for the summary
            "temperature": 0.7,
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(api_url, json=payload)
                response.raise_for_status()
                response_data = response.json()
                
                summary = response_data.get("choices")[0].get("text")
                if not summary:
                    raise SummarizationError("vLLM API response did not contain a summary.")
                return summary.strip()
        except httpx.HTTPStatusError as e:
            error_details = e.response.text
            try:
                error_json = e.response.json()
                error_details = error_json.get("detail", error_details)
            except Exception:
                pass # Keep original text if JSON parsing fails
            raise SummarizationError(f"vLLM API request failed with status {e.response.status_code}: {error_details}") from e
        except httpx.RequestError as e:
            raise SummarizationError(f"vLLM API request failed: {e}") from e
        except (KeyError, IndexError) as e:
            raise SummarizationError(f"Failed to parse vLLM API response: {e}") from e
        except Exception as e:
            raise SummarizationError(f"An unexpected error occurred with vLLM: {e}") from e


# Factory Function
def get_summarizer(config: dict) -> Summarizer:
    """
    Factory function to get a summarizer instance based on the configuration.

    Args:
        config: The application configuration dictionary. 
                Expected to have an 'llm' key with provider details.

    Returns:
        A Summarizer instance.

    Raises:
        ValueError: If the provider is unknown or required configuration is missing.
    """
    if not config or 'llm' not in config:
        raise ValueError("LLM configuration is missing.")

    llm_config = config['llm']
    provider = llm_config.get('provider')

    if not provider:
        raise ValueError("LLM provider is not specified in the configuration.")

    if provider == "openai":
        api_key = llm_config.get('openai_api_key')
        if not api_key:
            raise ValueError("OpenAI API key is missing in the configuration for 'openai' provider.")
        return OpenAISummarizer(api_key=api_key)
    elif provider == "ollama":
        base_url = llm_config.get('ollama_api_url')
        if not base_url:
            raise ValueError("Ollama base URL is missing in the configuration for 'ollama' provider.")
        # model_name could be added to config if needed, using default for now
        return OllamaSummarizer(base_url=base_url)
    elif provider == "vllm":
        base_url = llm_config.get('vllm_api_url')
        if not base_url:
            raise ValueError("vLLM base URL is missing in the configuration for 'vllm' provider.")
        # model_name could be added to config if needed, using default for now
        return VLLMSummarizer(base_url=base_url)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")

if __name__ == '__main__':
    # Example Usage (requires .env file or environment variables for API keys/URLs)
    # This part is for basic testing and might need adjustment based on your setup.
    
    print("Attempting to test summarizers. Ensure your .env file or environment variables are set.")

    # Mock config for local testing
    # In a real application, this config would be loaded from YAML and env vars
    mock_config_openai = {
        "llm": {
            "provider": "openai",
            "openai_api_key": os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE"), # Replace with your key or ensure .env is loaded
        }
    }
    mock_config_ollama = {
        "llm": {
            "provider": "ollama",
            "ollama_api_url": os.getenv("OLLAMA_API_URL", "http://localhost:11434"),
        }
    }
    mock_config_vllm = {
        "llm": {
            "provider": "vllm",
            "vllm_api_url": os.getenv("VLLM_API_URL", "http://localhost:8000"), # Adjust if your vLLM runs elsewhere or uses a different port
            # "vllm_model_name": "specific_model_if_needed" # Optional: specify model if not default
        }
    }
    
    sample_text = (
        "Artificial intelligence (AI) is intelligence demonstrated by machines, "
        "as opposed to the natural intelligence displayed by humans and animals. "
        "Leading AI textbooks define the field as the study of 'intelligent agents': "
        "any device that perceives its environment and takes actions that maximize "
        "its chance of successfully achieving its goals. Some popular accounts use "
        "the term 'artificial intelligence' to describe machines that mimic 'cognitive' "
        "functions that humans associate with the human mind, such as 'learning' and 'problem solving'."
    )

    print(f"\n--- Testing with Sample Text ---\n{sample_text}\n")

    # Test OpenAI
    if mock_config_openai["llm"]["openai_api_key"] and mock_config_openai["llm"]["openai_api_key"] != "YOUR_OPENAI_API_KEY_HERE":
        try:
            print("--- Testing OpenAI Summarizer ---")
            openai_summarizer = get_summarizer(mock_config_openai)
            summary = openai_summarizer.summarize(sample_text)
            print(f"OpenAI Summary: {summary}")
        except (SummarizationError, ValueError) as e:
            print(f"OpenAI Error: {e}")
        except Exception as e:
            print(f"Unexpected error during OpenAI test: {e}")
    else:
        print("--- Skipping OpenAI Summarizer Test (API key not found) ---")

    # Test Ollama
    # Ensure Ollama is running and accessible at the OLLAMA_API_URL
    # Example: docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
    # And then: docker exec -it ollama ollama pull llama2
    if mock_config_ollama["llm"]["ollama_api_url"]:
        try:
            print("\n--- Testing Ollama Summarizer ---")
            ollama_summarizer = get_summarizer(mock_config_ollama)
            summary = ollama_summarizer.summarize(sample_text)
            print(f"Ollama Summary: {summary}")
        except (SummarizationError, ValueError) as e:
            print(f"Ollama Error: {e}")
        except Exception as e:
            print(f"Unexpected error during Ollama test: {e}")
    else:
        print("--- Skipping Ollama Summarizer Test (OLLAMA_API_URL not found) ---")


    # Test vLLM
    # Ensure vLLM is running and accessible at the VLLM_API_URL
    # Example: python -m vllm.entrypoints.openai.api_server --model mistralai/Mistral-7B-Instruct-v0.1
    if mock_config_vllm["llm"]["vllm_api_url"]:
        try:
            print("\n--- Testing vLLM Summarizer ---")
            vllm_summarizer = get_summarizer(mock_config_vllm)
            summary = vllm_summarizer.summarize(sample_text)
            print(f"vLLM Summary: {summary}")
        except (SummarizationError, ValueError) as e:
            print(f"vLLM Error: {e}")
        except Exception as e:
            print(f"Unexpected error during vLLM test: {e}")
    else:
        print("--- Skipping vLLM Summarizer Test (VLLM_API_URL not found) ---")

    # Test unknown provider
    try:
        print("\n--- Testing Unknown Provider ---")
        get_summarizer({"llm": {"provider": "unknown"}})
    except ValueError as e:
        print(f"Caught expected error for unknown provider: {e}")
    
    # Test missing config
    try:
        print("\n--- Testing Missing LLM Config ---")
        get_summarizer({})
    except ValueError as e:
        print(f"Caught expected error for missing llm config: {e}")

    try:
        print("\n--- Testing Missing Provider ---")
        get_summarizer({"llm": {}})
    except ValueError as e:
        print(f"Caught expected error for missing provider: {e}")

    try:
        print("\n--- Testing Missing OpenAI API Key ---")
        get_summarizer({"llm": {"provider": "openai"}})
    except ValueError as e:
        print(f"Caught expected error for missing OpenAI API key: {e}")

    try:
        print("\n--- Testing Missing Ollama URL ---")
        get_summarizer({"llm": {"provider": "ollama"}})
    except ValueError as e:
        print(f"Caught expected error for missing Ollama URL: {e}")
    
    try:
        print("\n--- Testing Missing vLLM URL ---")
        get_summarizer({"llm": {"provider": "vllm"}})
    except ValueError as e:
        print(f"Caught expected error for missing vLLM URL: {e}")
