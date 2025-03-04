import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce la pressione del bottone inline e mantiene il contesto del messaggio originale."""
    query = update.callback_query

    # Rispondiamo alla callback query (richiesto per le API Telegram)
    await query.answer()

    # Estrazione del testo del messaggio originale
    original_message_text = query.message.text

    # Utilizzo del testo originale nella risposta
    await query.edit_message_text(
        text=f"Hai premuto il bottone! Il messaggio originale era: '{original_message_text}'"
    )
