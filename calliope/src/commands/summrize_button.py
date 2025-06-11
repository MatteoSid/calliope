import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, CallbackQuery
from telegram.ext import ContextTypes

from calliope.src.models.summarization_model import SummarizationModel
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.utils.utils import redis_connection

# Initialize the summarization model
summarization_model = SummarizationModel()

# Constants for view types
VIEW_SUMMARY = "summary"
VIEW_FULL = "full"

async def get_transcription_data(uuid: str) -> Tuple[dict, str]:
    """Get transcription data from Redis."""
    try:
        # Try to get the data from Redis with the new structured key
        redis_key = f"transcript:{uuid}"
        data = redis_connection.get(redis_key)
        
        if not data:
            # Fallback to old format for backward compatibility
            logger.debug(f"No data found with key {redis_key}, trying old format")
            data = redis_connection.get(uuid)
            if not data:
                return None, "❌ *Errore*: La trascrizione non è più disponibile."
            
            # If we got here, we have old format data
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            
            # Convert to new format
            transcription_data = {
                'full_text': data,
                'summary': None,
                'message_id': None,
                'chat_id': None
            }
        else:
            # We have data in the new format
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            transcription_data = json.loads(data)
        
        return transcription_data, ""
    except Exception as e:
        logger.error(f"Error getting transcription data: {e}", exc_info=True)
        return None, "❌ *Errore*: Impossibile accedere al database. Riprova più tardi."

def create_navigation_buttons(uuid: str, current_view: str) -> InlineKeyboardMarkup:
    """Create navigation buttons based on current view.
    
    Uses a more compact format for callback_data to avoid hitting size limits.
    """
    buttons = []
    
    if current_view == VIEW_SUMMARY:
        buttons.append(InlineKeyboardButton(
            "⬅️ Testo Completo",
            callback_data=f"nav:{VIEW_FULL}:{uuid}"
        ))
    else:  # VIEW_FULL
        buttons.append(InlineKeyboardButton(
            "Riassunto ➡️",
            callback_data=f"nav:{VIEW_SUMMARY}:{uuid}"
        ))
    
    return InlineKeyboardMarkup([buttons])

async def update_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup = None
) -> None:
    """Helper function to update a message with error handling."""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.warning(f"Could not update message: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses for the transcription viewer."""
    query = update.callback_query
    await query.answer()
    
    logger.debug(f"Button pressed with data: {query.data}")
    
    try:
        # Parse callback data
        try:
            # Parse the callback data which can be in one of these formats:
            # 1. Compact format: "action:uuid" (for summarize)
            # 2. Navigation format: "nav:view:uuid" (for navigation)
            parts = query.data.split(':')
            
            if len(parts) == 2 and parts[0] == 'summ':
                # Format: "summ:uuid"
                action = 'summ'
                uuid = parts[1]
                view = VIEW_SUMMARY
            elif len(parts) == 3 and parts[0] == 'nav':
                # Format: "nav:view:uuid"
                action = 'nav'
                view = parts[1]
                uuid = parts[2]
            else:
                # Try to parse as JSON for backward compatibility
                try:
                    callback_data = json.loads(query.data)
                    action = callback_data.get('a') or callback_data.get('action')
                    uuid = callback_data.get('u') or callback_data.get('uuid')
                    view = callback_data.get('v', VIEW_SUMMARY)
                except json.JSONDecodeError:
                    raise ValueError("Invalid callback data format")
            
            logger.debug(f"Received callback data: action={action}, view={view}, uuid={uuid}")
            
            if not all([action, uuid]):
                raise ValueError("Missing required fields in callback data")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Invalid callback data: {query.data} - {e}")
            await update_message(
                context,
                query.message.chat_id,
                query.message.message_id,
                "❌ *Errore*: Dati non validi."
            )
            return
        
        # Get transcription data from Redis
        logger.debug(f"Getting transcription data for UUID: {uuid}")
        transcription_data, error_msg = await get_transcription_data(uuid)
        if not transcription_data:
            logger.error(f"Failed to get transcription data: {error_msg}")
            await update_message(
                context,
                query.message.chat_id,
                query.message.message_id,
                error_msg
            )
            return
        logger.debug("Successfully retrieved transcription data from Redis")
        
        # Handle different actions
        logger.debug(f"Handling action: {action}")
        if action in ['summ', 'summarize']:
            logger.debug("Dispatching to handle_summarize_action")
        if action in ['summ', 'summarize']:
            await handle_summarize_action(
                context, query, transcription_data, uuid
            )
        elif action == 'nav':
            await handle_navigation_action(
                context, query, transcription_data, uuid, view
            )
        else:
            logger.warning(f"Unknown action: {action}")
            await update_message(
                context,
                query.message.chat_id,
                query.message.message_id,
                "❌ *Errore*: Azione non riconosciuta."
            )
            
    except Exception as e:
        logger.error(f"Unexpected error in button_callback: {e}", exc_info=True)
        try:
            await update_message(
                context,
                query.message.chat_id,
                query.message.message_id,
                "❌ *Errore*: Si è verificato un errore imprevisto. Riprova più tardi."
            )
        except Exception as update_error:
            logger.error(f"Failed to send error message: {update_error}")

async def handle_summarize_action(
    context: ContextTypes.DEFAULT_TYPE,
    query: CallbackQuery,
    transcription_data: dict,
    uuid: str
) -> None:
    """Handle the summarize action."""
    # Show initial status
    await update_message(
        context,
        query.message.chat_id,
        query.message.message_id,
        "🔄 *Sto generando il riassunto...*\n\n_Questa operazione potrebbe richiedere qualche istante._"
    )
    
    full_text = transcription_data.get('full_text', '')
    
    try:
        # Update status to show we're working on it
        await update_message(
            context,
            query.message.chat_id,
            query.message.message_id,
            "🔍 *Analizzo la trascrizione...*\n\n_Sto elaborando il contenuto..._"
        )
        
        # Generate summary
        summary = await summarization_model.summarize(full_text)
        
        if not summary:
            await update_message(
                context,
                query.message.chat_id,
                query.message.message_id,
                "ℹ️ *Attenzione*: Il messaggio è troppo breve per essere riassunto in modo significativo."
            )
            return
        
        # Update the transcription data with the new summary
        transcription_data['summary'] = summary
        redis_key = f"transcript:{uuid}"
        redis_connection.setex(redis_key, 86400, json.dumps(transcription_data))
        
        # Create the response with navigation buttons
        response = (
            "📝 *Riassunto*\n\n"
            f"{summary}\n\n"
            "_Usa i pulsanti qui sotto per navigare tra il riassunto e il testo completo._"
        )
        
        # Create navigation buttons
        reply_markup = create_navigation_buttons(uuid, VIEW_SUMMARY)
        
        # Update the message with the summary and navigation
        await update_message(
            context,
            query.message.chat_id,
            query.message.message_id,
            response,
            reply_markup
        )
        
        # Log the successful summary generation
        await log_summary_generation(query, transcription_data)
        
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Error in summarization: {e}", exc_info=True)
        
        if "timeout" in error_msg or "timed out" in error_msg:
            msg = "⏱ *Timeout*: Il riassunto sta impiegando troppo tempo. Prova con un messaggio più breve o riprova più tardi."
        elif "connection" in error_msg or "unreachable" in error_msg:
            msg = "🔌 *Errore di connessione*: Impossibile raggiungere il servizio di riassunto. Riprova più tardi."
        else:
            msg = "❌ *Errore*: Si è verificato un problema durante la generazione del riassunto. Riprova più tardi."
        
        await update_message(
            context,
            query.message.chat_id,
            query.message.message_id,
            msg
        )

async def handle_navigation_action(
    context: ContextTypes.DEFAULT_TYPE,
    query: CallbackQuery,
    transcription_data: dict,
    uuid: str,
    target_view: str
) -> None:
    """Handle navigation between summary and full text views."""
    full_text = transcription_data.get('full_text', '')
    summary = transcription_data.get('summary', '')
    
    if target_view == VIEW_SUMMARY and not summary:
        # If trying to view summary but it doesn't exist yet, generate it
        await handle_summarize_action(context, query, transcription_data, uuid)
        return
    
    # Prepare the appropriate response based on the target view
    if target_view == VIEW_SUMMARY:
        response = (
            "📝 *Riassunto*\n\n"
            f"{summary}\n\n"
            "_Usa i pulsanti qui sotto per navigare tra il riassunto e il testo completo._"
        )
    else:  # VIEW_FULL
        response = (
            "📜 *Testo Completo*\n\n"
            f"{full_text}\n\n"
            "_Usa i pulsanti qui sotto per tornare al riassunto._"
        )
    
    # Create navigation buttons
    reply_markup = create_navigation_buttons(uuid, target_view)
    
    # Update the message
    await update_message(
        context,
        query.message.chat_id,
        query.message.message_id,
        response,
        reply_markup
    )

async def log_summary_generation(query: CallbackQuery, transcription_data: dict) -> None:
    """Log the successful summary generation to the database."""
    try:
        db = await calliope_db_init()
        if not hasattr(db, 'users'):
            # Create the users collection if it doesn't exist
            await db.create_collection('users')
        
        # Update user statistics
        await db.users.update_one(
            {"user_id": query.from_user.id},
            {
                "$setOnInsert": {
                    "username": query.from_user.username,
                    "first_seen": datetime.utcnow(),
                    "stats": {"summaries_generated": 0}  # Initialize stats if not exists
                },
                "$set": {"last_activity": datetime.utcnow()},
                "$inc": {"stats.summaries_generated": 1}
            },
            upsert=True
        )
        logger.info(f"Generated summary for user {query.from_user.username}")
    except Exception as db_error:
        logger.error(f"Database update error: {db_error}")
        # Don't raise the error to avoid breaking the user experience
