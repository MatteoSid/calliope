import logging
import json

from telegram import Update
from telegram.ext import ContextTypes

from calliope.src.configs_manager import settings
from calliope.src.models.summarization_llm import get_summarizer, SummarizationError
from calliope.src.utils.utils import redis_connection # Ensure this import is correct

# Ensure logger is configured (it should be by the main application, but good practice)
logger = logging.getLogger(__name__)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the inline button press for summarization.
    Retrieves the full text from Redis using a UUID from callback_data,
    calls the summarization service, and updates the message with the summary or an error.
    """
    query = update.callback_query
    if not query:
        logger.warning("Callback query is None, cannot proceed.")
        return

    # Answer the callback query (required by Telegram API)
    await query.answer()

    if not query.message:
        logger.warning("Callback query does not have an associated message.")
        # If query.edit_message_text is used, it needs a message_id.
        # If query.message is None, we can't edit. Consider sending a new message if applicable,
        # but for now, we'll just log and return if there's no message context.
        return

    # Initial message update
    await query.edit_message_text(text="Processing summarization request...")

    # Parse callback_data to get UUID
    text_uuid = None
    try:
        if query.callback_data:
            callback_data_dict = json.loads(query.callback_data)
            text_uuid = callback_data_dict.get("uuid")
        else:
            logger.error("callback_data is missing.")
            await query.edit_message_text("Error: Button data is missing.")
            return

    except json.JSONDecodeError:
        logger.error(f"Failed to parse callback_data: {query.callback_data}", exc_info=True)
        await query.edit_message_text("Error: Invalid button data format.")
        return
    
    if not text_uuid:
        logger.error(f"UUID not found in callback_data: {query.callback_data}")
        await query.edit_message_text("Error: Missing identifier for summarization text.")
        return

    # Fetch text from Redis
    original_message_text = None
    try:
        await query.edit_message_text(text="Fetching text for summarization...")
        original_message_text_bytes = redis_connection.get(text_uuid)
        if not original_message_text_bytes:
            logger.warning(f"No text found in Redis for UUID: {text_uuid}. It might have expired or was not set.")
            await query.edit_message_text(
                "Error: The text to summarize is no longer available (it may have expired). Please try transcribing again."
            )
            return
        original_message_text = original_message_text_bytes.decode('utf-8')
    except ConnectionRefusedError as e: # Specific error for Redis connection refused
        logger.error(f"Redis connection refused while fetching text for UUID {text_uuid}: {e}", exc_info=True)
        await query.edit_message_text("Error: Could not connect to the text storage. Please try again later.")
        return
    except Exception as e: # Catch other potential Redis connection errors or decode errors
        logger.error(f"Error fetching text from Redis for UUID {text_uuid}: {e}", exc_info=True)
        await query.edit_message_text("Error: Could not retrieve the text for summarization.")
        return

    if not original_message_text or not original_message_text.strip():
        logger.info(f"Text fetched from Redis for UUID {text_uuid} is empty or whitespace.")
        await query.edit_message_text("The text to summarize is empty.")
        return

    # Initialize the summarizer
    summarizer = None
    try:
        summarizer = get_summarizer(settings)
    except ValueError as e:
        logger.error(f"Failed to initialize summarizer: {e}")
        await query.edit_message_text(
            text="Sorry, the summarization service is not configured correctly. Please contact an administrator."
        )
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred during summarizer initialization: {e}", exc_info=True)
        await query.edit_message_text(
            text="An unexpected error occurred while setting up summarization. Please try again later."
        )
        return

    if summarizer:
        try:
            # Inform the user that summarization is in progress, showing a snippet
            snippet = original_message_text[:200] + "..." if len(original_message_text) > 200 else original_message_text
            await query.edit_message_text(
                text=f"Summarizing the following text (snippet):\n\n\"{snippet}\"\n\nPlease wait..."
            )

            # Run the synchronous summarization method in a separate thread
            summary = await context.application.run_in_thread(
                summarizer.summarize,
                original_message_text # Use the full text from Redis
            )

            if summary:
                # For the final message, we might want to show a snippet of the original
                # if it's too long to repeat in the message.
                final_text_display = f"Original text (snippet):\n\"{snippet}\"\n\nSummary:\n{summary}"
                if len(original_message_text) <= 300: # Arbitrary length to decide if to show full or snippet
                    final_text_display = f"Original text:\n\"{original_message_text}\"\n\nSummary:\n{summary}"
                
                await query.edit_message_text(text=final_text_display)
            else:
                logger.warning(f"Summarization resulted in an empty summary for UUID: {text_uuid}.")
                await query.edit_message_text(
                    text=f"Original text (snippet):\n\"{snippet}\"\n\nSorry, I couldn't generate a summary for this text."
                )

        except SummarizationError as e:
            logger.error(f"Summarization failed for UUID {text_uuid}: {e}")
            await query.edit_message_text(
                text=f"Sorry, I couldn't summarize the text (snippet: \"{snippet}\"). An error occurred during the process."
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred during summarization for UUID {text_uuid}: {e}", exc_info=True)
            await query.edit_message_text(
                text="An unexpected error occurred while trying to summarize. Please try again later."
            )
    else:
        logger.error("Summarizer was None after initialization attempt without raising an exception.")
        await query.edit_message_text(
            text="Could not initialize the summarization service. Please contact an administrator."
        )
