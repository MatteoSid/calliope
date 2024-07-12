from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes


# TODO: convert in mongodb
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /stats is issued."""
    logger.info(f"{update.message.from_user.username}: Stats command")
    file_path = "stast.json"

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await update.message.reply_text("Stats not found")
        logger.error("Stats not found")
        return

    # check if is a single user or a group
    if str(update.message.chat.type) == "private":
        # check if there is stats for the user
        if str(update.message.from_user.id) in data["single_users"]:
            total_speech_time = timedelta(
                seconds=data["single_users"][str(update.message.from_user.id)][
                    "total_speech_time"
                ]
            )
            await update.message.reply_text(
                f"Time speech converted:\n{format_timedelta(total_speech_time)}"
            )
            logger.success("Stats sent")
        else:
            await update.message.reply_text("Stats not found")
            logger.error("Stats not found")

    elif str(update.message.chat.type) in ["group", "supergroup"]:
        # check if there is stats for the group
        if str(update.message.chat.id) in data["groups"]:
            # load user stats in a dataframe
            members_stats = data["groups"][str(update.message.chat.id)]["members_stats"]
            data_tmp = pd.DataFrame.from_dict(
                members_stats, orient="index", columns=["total_speech_time"]
            )
            data_tmp.sort_values(by="total_speech_time", ascending=False, inplace=True)

            result = ""
            for index, row in data_tmp.iterrows():
                total_speech_time = timedelta(seconds=int(row["total_speech_time"]))
                result += f"@{index}: {format_timedelta(total_speech_time)}\n"

            await update.message.reply_text(result)
        else:
            await update.message.reply_text("Stats not found")
