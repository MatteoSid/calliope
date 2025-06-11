import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from calliope.src.models.summarization_model import SummarizationModel
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.utils.utils import redis_connection

# Initialize the summarization model
summarization_model = SummarizationModel()

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the summarize button press and generate a summary of the transcription."""
    query = update.callback_query
    await query.answer()

    async def update_status(text: str) -> None:
        """Helper function to update the status message."""
        try:
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not update status: {e}")

    try:
        # Get the original message and callback data
        try:
            callback_data = json.loads(query.data)
            # Support both old and new callback data formats
            uuid = callback_data.get('u') or callback_data.get('uuid')
            action = callback_data.get('a') or callback_data.get('action')
            
            # Log the received callback data for debugging
            logger.debug(f"Received callback data: {callback_data}")
            
            # Validate callback data
            if action not in ['summ', 'summarize'] or not uuid:
                logger.warning(f"Invalid callback data: {callback_data}")
                await update_status("❌ *Errore*: Dati non validi.")
                return
                
        except json.JSONDecodeError as je:
            logger.error(f"JSON decode error in callback data: {query.data}")
            await update_status("❌ *Errore*: Formato dati non valido.")
            return
        except Exception as e:
            logger.error(f"Error parsing callback data: {e}", exc_info=True)
            await update_status("❌ *Errore*: Impossibile elaborare la richiesta.")
            return

        # Show initial status
        await update_status("🔄 *Sto generando il riassunto...*\n\n_Questa operazione potrebbe richiedere qualche istante._")

        # Get the full transcription from Redis
        try:
            # Try to get the data from Redis
            full_transcription = redis_connection.get(uuid)
            
            # If not found, try decoding as bytes if needed
            if full_transcription and isinstance(full_transcription, bytes):
                try:
                    full_transcription = full_transcription.decode('utf-8')
                except UnicodeDecodeError:
                    logger.error("Failed to decode transcription from bytes")
                    full_transcription = None
            
            if not full_transcription:
                logger.warning(f"No transcription found for UUID: {uuid}")
                await update_status("❌ *Errore*: La trascrizione non è più disponibile.")
                return
                
            logger.debug(f"Retrieved transcription for UUID: {uuid}, length: {len(full_transcription)}")
            
        except Exception as redis_error:
            logger.error(f"Redis error: {redis_error}", exc_info=True)
            await update_status("❌ *Errore*: Impossibile accedere al database. Riprova più tardi.")
            return

        try:
            # Update status to show we're working on it
            await update_status("🔍 *Analizzo la trascrizione...*\n\n_Sto elaborando il contenuto..._")
            
            # Generate summary
            summary = await summarization_model.summarize(full_transcription)
            
            if not summary:
                await update_status("ℹ️ *Attenzione*: Il messaggio è troppo breve per essere riassunto in modo significativo.")
                return

            # Update the message with the summary
            response = (
                "📝 *Riassunto*\n\n"
                f"{summary}\n\n"
                "_Il riassunto è stato generato automaticamente._"
            )
            
            await update_status(response)

            # Log the successful summary generation
            try:
                db = calliope_db_init()
                # Update user statistics
                await db.users.update_one(
                    {"user_id": update.effective_user.id},
                    {
                        "$setOnInsert": {
                            "username": update.effective_user.username,
                            "first_seen": datetime.utcnow()
                        },
                        "$set": {"last_activity": datetime.utcnow()},
                        "$inc": {"stats.summaries_generated": 1}
                    },
                    upsert=True
                )
                logger.info(f"Generated summary for user {update.effective_user.username}")
            except Exception as db_error:
                logger.error(f"Database update error: {db_error}")

        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"Error in summarization: {e}", exc_info=True)
            
            if "timeout" in error_msg or "timed out" in error_msg:
                await update_status(
                    "⏱ *Timeout*: Il riassunto sta impiegando troppo tempo. "
                    "Prova con un messaggio più breve o riprova più tardi."
                )
            elif "connection" in error_msg or "unreachable" in error_msg:
                await update_status(
                    "🔌 *Errore di connessione*: Impossibile raggiungere il servizio di riassunto. "
                    "Riprova più tardi."
                )
            else:
                await update_status(
                    "❌ *Errore*: Si è verificato un problema durante la generazione del riassunto. "
                    "Riprova più tardi."
                )

    except json.JSONDecodeError:
        await update_status("❌ *Errore*: Formato dati non valido.")
    except Exception as e:
        logger.error(f"Unexpected error in button_callback: {e}", exc_info=True)
        await update_status("❌ *Errore*: Si è verificato un errore imprevisto. Riprova più tardi.")
