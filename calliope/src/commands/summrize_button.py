import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, CallbackQuery
from telegram.ext import ContextTypes

from calliope.src.models.summarization_model import SummarizationModel
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.utils.utils import redis_connection, split_message

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

def create_navigation_buttons(uuid: str, current_view: str, current_page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Create navigation buttons based on current view and page.
    
    Args:
        uuid: The unique identifier for the transcription
        current_view: Either 'summary' or 'full'
        current_page: Current page number (0-based)
        total_pages: Total number of pages
    """
    keyboard = []
    
    # Add navigation buttons for full view
    if current_view == VIEW_FULL and total_pages > 1:
        nav_buttons = []
        # Previous button (disabled on first page)
        nav_buttons.append(
            InlineKeyboardButton(
                "⬅️ Indietro",
                callback_data=f"nav:full:{uuid}:prev:{current_page}" if current_page > 0 else "noop"
            )
        )
        # Page indicator
        nav_buttons.append(
            InlineKeyboardButton(
                f"{current_page + 1}/{total_pages}",
                callback_data="noop"
            )
        )
        # Next button (disabled on last page)
        nav_buttons.append(
            InlineKeyboardButton(
                "Avanti ➡️",
                callback_data=f"nav:full:{uuid}:next:{current_page}" if current_page < total_pages - 1 else "noop"
            )
        )
        keyboard.append(nav_buttons)
    
    # Add view toggle button
    view_buttons = []
    if current_view == VIEW_SUMMARY:
        view_buttons.append(InlineKeyboardButton(
            "⬅️ Testo Completo",
            callback_data=f"nav:full:{uuid}:{min(current_page, total_pages-1)}:{total_pages}"
        ))
    else:  # VIEW_FULL
        view_buttons.append(InlineKeyboardButton(
            "📝 Riassunto",
            callback_data=f"summ:summary:{uuid}"
        ))
    keyboard.append(view_buttons)
    
    return InlineKeyboardMarkup(keyboard)

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
            # 1. Navigation with pagination: "nav:view:uuid:action:page:total_pages"
            # 2. Navigation simple: "nav:view:uuid"
            # 3. Summarize: "summ:view:uuid"
            parts = query.data.split(':')
            
            if len(parts) >= 3 and parts[0] == 'nav':
                # Format: "nav:view:uuid[:action:current_page:total_pages]"
                action = 'nav'
                view = parts[1]
                uuid = parts[2]
                
                # Handle pagination parameters if present
                nav_action = parts[3] if len(parts) > 3 else None
                current_page = int(parts[4]) if len(parts) > 4 else 0
                total_pages = int(parts[5]) if len(parts) > 5 else None
                
            elif len(parts) == 3 and parts[0] == 'summ':
                # Format: "summ:view:uuid"
                action = 'summ'
                view = parts[1]
                uuid = parts[2]
                nav_action = None
                current_page = 0
                total_pages = None
                
            else:
                # Try to parse as JSON for backward compatibility
                try:
                    callback_data = json.loads(query.data)
                    action = callback_data.get('a') or callback_data.get('action')
                    uuid = callback_data.get('u') or callback_data.get('uuid')
                    view = callback_data.get('v', VIEW_SUMMARY)
                    nav_action = None
                    current_page = 0
                    total_pages = None
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
        logger.debug(f"Handling action: {action}, view: {view}, nav_action: {nav_action}")
        
        if action in ['summ', 'summarize']:
            logger.debug("Dispatching to handle_summarize_action")
            await handle_summarize_action(
                context, query, transcription_data, uuid
            )
        elif action == 'nav':
            # For navigation, we might have pagination actions
            if nav_action in ['prev', 'next']:
                await handle_navigation_action(
                    context=context, 
                    query=query, 
                    transcription_data=transcription_data, 
                    target_view=view,
                    action=nav_action, 
                    current_page=current_page
                )
            else:
                # Simple view toggle
                await handle_navigation_action(
                    context=context,
                    query=query,
                    transcription_data=transcription_data,
                    target_view=view,
                    current_page=current_page, 
                    total_pages=total_pages
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
    target_view: str,
    action: str = None,
    current_page: int = 0,
    total_pages: int = None,
    **kwargs  # Accept additional keyword arguments for future compatibility
) -> None:
    """Handle navigation between summary and full text views and pagination.
    
    Callback data format:
    - nav:full:uuid:prev:current_page
    - nav:full:uuid:next:current_page
    - nav:full:uuid:page:total_pages
    """
    try:
        full_text = transcription_data.get('full_text', '')
        summary = transcription_data.get('summary')
        uuid = transcription_data.get('uuid', '')  # Aggiunto per ottenere l'UUID dai dati della trascrizione
        
        # Handle page navigation if action is specified
        if action in ['prev', 'next'] and target_view == VIEW_FULL:
            current_page = int(current_page)
            total_pages = transcription_data.get('total_pages', 1)
            
            # Calculate new page
            if action == 'prev' and current_page > 0:
                new_page = current_page - 1
            elif action == 'next' and current_page < total_pages - 1:
                new_page = current_page + 1
            else:
                new_page = current_page
                
            # Update current page in Redis
            transcription_data['current_page'] = new_page
            redis_connection.setex(
                f"transcript:{uuid}",
                86400,  # 24 hours
                json.dumps(transcription_data)
            )
            
            # Split the text into pages
            message_parts, _ = split_message(full_text, 4090)
            text = message_parts[new_page]
            
            # Create navigation buttons
            reply_markup = create_navigation_buttons(
                uuid, 
                VIEW_FULL,
                current_page=new_page,
                total_pages=total_pages
            )
            
        # Toggle between summary and full views
        elif target_view == VIEW_SUMMARY:
            if not summary:
                await handle_summarize_action(context, query, transcription_data, uuid)
                return
                
            text = f"📝 *Riassunto*\n\n{summary}"
            reply_markup = create_navigation_buttons(
                uuid, 
                VIEW_SUMMARY,
                current_page=current_page,
                total_pages=total_pages or 1
            )
            
        else:  # VIEW_FULL
            # If coming from summary view, show first page
            message_parts, total_pages = split_message(full_text, 4090)
            current_page = min(int(current_page or 0), total_pages - 1)
            text = message_parts[current_page]
            
            # Update total_pages in Redis if needed
            if 'total_pages' not in transcription_data:
                transcription_data['total_pages'] = total_pages
                redis_connection.setex(
                    f"transcript:{uuid}",
                    86400,  # 24 hours
                    json.dumps(transcription_data)
                )
                
            reply_markup = create_navigation_buttons(
                uuid, 
                VIEW_FULL,
                current_page=current_page,
                total_pages=total_pages
            )
        
        # Update the message
        await update_message(
            context,
            query.message.chat_id,
            query.message.message_id,
            text,
            reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_navigation_action: {e}", exc_info=True)
        await update_message(
            context,
            query.message.chat_id,
            query.message.message_id,
            "❌ *Errore*: Impossibile cambiare visualizzazione o pagina."
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
