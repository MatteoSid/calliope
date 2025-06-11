import json
import os
import tempfile
import time
from datetime import timedelta
from uuid import uuid4
from loguru import logger

import librosa
from loguru import logger
from moviepy.editor import VideoFileClip
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram._files.videonote import VideoNote
import json
from uuid import UUID
from typing import cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Voice, VideoNote
from telegram.error import RetryAfter, BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, CallbackContext

from calliope.src.utils.utils import (
    extract_audio,
    message_type,
    redis_connection,
    split_message,
)
from calliope.src.models.inference_model import WhisperInferenceModel
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.commands import change_language, help_command, start, stt, timestamp

redis_timeout = timedelta(minutes=60)

calliope_db = calliope_db_init()

whisper = WhisperInferenceModel()


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    calliope_db.update(update)

    audio, duration = await extract_audio(update, context)

    try:
        start_time = time.time()
        segments = whisper.transcribe(audio)

        # avviso l'utente che la trascrizione è in corso
        current_message = await update.message.reply_text(
            text="[...]",
            disable_notification=True,
        )

        # unisco le trascrizioni
        full_transcription = ""
        for segment in segments:
            full_transcription += segment.text

        

        # Dividi il messaggio in pagine
        message_parts, total_pages = split_message(full_transcription, 4090)  # 4090 per lasciare spazio ai pulsanti
        
        # Store the full transcription in Redis with a structured key
        uuid = uuid4().hex
        try:
            # Ensure we're storing a string
            if not isinstance(full_transcription, str):
                full_transcription = str(full_transcription)
            
            # Create a structured data object
            transcription_data = {
                'full_text': full_transcription,
                'summary': None,  # Will be filled when summary is generated
                'message_id': current_message.message_id,
                'chat_id': current_message.chat_id,
                'current_page': 0,  # Aggiungiamo il numero di pagina corrente
                'total_pages': total_pages,  # Aggiungiamo il numero totale di pagine
                'uuid': uuid  # Aggiungiamo l'UUID ai dati della trascrizione
            }
            
            # Store in Redis with a longer timeout (24 hours)
            redis_connection.setex(
                f"transcript:{uuid}", 
                86400,  # 24 hours
                json.dumps(transcription_data)
            )
            logger.debug(f"Stored transcription in Redis with UUID: {uuid}, length: {len(full_transcription)}")
        except Exception as e:
            logger.error(f"Error storing transcription in Redis: {e}")
            # Continue anyway, the button will just not work if Redis is down

        # Crea la tastiera di navigazione
        keyboard = []
        
        # Aggiungi i pulsanti di navigazione solo se ci sono più pagine
        if total_pages > 1:
            nav_buttons = []
            # Pulsante indietro (disabilitato nella prima pagina)
            nav_buttons.append(
                InlineKeyboardButton(
                    "⬅️ Indietro",
                    callback_data=f"nav:full:{uuid}:prev:0"  # 0 è la pagina corrente
                )
            )
            # Indicatore di pagina
            nav_buttons.append(
                InlineKeyboardButton(
                    f"1/{total_pages}",
                    callback_data="noop"
                )
            )
            # Pulsante avanti (disabilitato nell'ultima pagina)
            nav_buttons.append(
                InlineKeyboardButton(
                    "Avanti ➡️",
                    callback_data=f"nav:full:{uuid}:next:0"  # 0 è la pagina corrente
                )
            )
            keyboard.append(nav_buttons)
        
        # Aggiungi il pulsante di riassunto solo per messaggi lunghi (> 1 minuto di parlato)
        word_count = len(full_transcription.split())
        if word_count >= 140:  # ~150 parole = ~1 minuto di parlato
            keyboard.append([
                InlineKeyboardButton(
                    "📝 Riassunto",
                    callback_data=f"summ:summary:{uuid}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Invia solo la prima pagina
        try:
            await current_message.edit_text(
                text=message_parts[0],
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error in stt handler: {e}", exc_info=True)
        try:
            await update.message.reply_text("❌ Si è verificato un errore durante l'elaborazione del messaggio.")
        except:
            pass


async def handle_navigation(update: Update, context: CallbackContext) -> None:
    """Gestisce la navigazione tra le pagine del messaggio."""
    query = update.callback_query
    await query.answer()
    
    # Estrai i dati dalla callback (formato: "nav:full:uuid:action:current_page")
    parts = query.data.split(':')
    if len(parts) >= 5:
        # Nuovo formato: "nav:full:uuid:action:current_page"
        uuid = parts[2]
        action = parts[3]
        current_page = int(parts[4])
    else:
        # Vecchio formato per retrocompatibilità
        _, uuid, action, current_page = query.data.split(':', 3)
        current_page = int(current_page)
    
    # Recupera i dati della trascrizione da Redis
    redis_key = f"transcript:{uuid}"
    try:
        data = redis_connection.get(redis_key)
        if not data:
            await query.edit_message_text("❌ La trascrizione non è più disponibile.")
            return
            
        transcription_data = json.loads(data)
        full_text = transcription_data['full_text']
        total_pages = transcription_data['total_pages']
        
        # Calcola la nuova pagina
        if action == 'next':
            new_page = min(current_page + 1, total_pages - 1)
        elif action == 'prev':
            new_page = max(0, current_page - 1)
        else:
            new_page = current_page
        
        # Aggiorna la pagina corrente nei dati
        transcription_data['current_page'] = new_page
        # Assicurati che l'UUID sia sempre presente nei dati
        if 'uuid' not in transcription_data:
            transcription_data['uuid'] = uuid
        redis_connection.setex(redis_key, 86400, json.dumps(transcription_data))
        
        # Dividi il testo in pagine
        message_parts, _ = split_message(full_text, 4090)
        
        # Crea la tastiera di navigazione
        keyboard = []
        
        # Aggiungi i pulsanti di navigazione
        if total_pages > 1:
            nav_buttons = []
            # Pulsante indietro (disabilitato nella prima pagina)
            nav_buttons.append(
                InlineKeyboardButton(
                    "⬅️ Indietro",
                    callback_data=f"nav:full:{uuid}:prev:{new_page}" if new_page > 0 else "noop"
                )
            )
            # Indicatore di pagina
            nav_buttons.append(
                InlineKeyboardButton(
                    f"{new_page + 1}/{total_pages}",
                    callback_data="noop"
                )
            )
            # Pulsante avanti (disabilitato nell'ultima pagina)
            nav_buttons.append(
                InlineKeyboardButton(
                    "Avanti ➡️",
                    callback_data=f"nav:full:{uuid}:next:{new_page}" if new_page < total_pages - 1 else "noop"
                )
            )
            keyboard.append(nav_buttons)
        
        # Aggiungi il pulsante di riassunto se presente
        if 'summary' in transcription_data or len(full_text.split()) >= 140:
            keyboard.append([
                InlineKeyboardButton(
                    "📝 Riassunto",
                    callback_data=f"summ:summary:{uuid}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Aggiorna il messaggio con la nuova pagina
        await query.edit_message_text(
            text=message_parts[new_page],
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error handling navigation: {e}", exc_info=True)
        try:
            await query.edit_message_text("❌ Si è verificato un errore durante la navigazione.")
        except:
            pass


async def handle_summary(update: Update, context: CallbackContext) -> None:
    """Gestisce la generazione del riassunto."""
    query = update.callback_query
    await query.answer()
    
    # Estrai l'UUID dalla callback (formato: "summ:summary:uuid")
    parts = query.data.split(':')
    if len(parts) >= 3:
        uuid = parts[2]  # Prendi l'UUID dalla terza posizione
    else:
        # Formato vecchio per retrocompatibilità
        uuid = parts[1] if len(parts) > 1 else ""
    
    # Recupera i dati della trascrizione da Redis
    redis_key = f"transcript:{uuid}"
    try:
        data = redis_connection.get(redis_key)
        if not data:
            await query.edit_message_text("❌ La trascrizione non è più disponibile.")
            return
            
        transcription_data = json.loads(data)
        
        # Qui dovresti implementare la logica per generare il riassunto
        # Per ora mostriamo un messaggio di esempio
        summary = "Questo è un riassunto di esempio. Implementa qui la tua logica di riassunto."
        
        # Aggiorna il riassunto nei dati
        transcription_data['summary'] = summary
        redis_connection.setex(redis_key, 86400, json.dumps(transcription_data))
        
        # Aggiorna il messaggio con il riassunto
        await query.edit_message_text(
            text=f"📝 **Riassunto**\n\n{summary}",
            reply_markup=query.message.reply_markup  # Mantieni la stessa tastiera
        )
        
    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))
