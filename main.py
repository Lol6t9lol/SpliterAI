import os
import subprocess
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

# Your Bot Token
BOT_TOKEN = "8118607834:AAHucoXtSK6qbkenGxmjR8igzFJc-4fV7nI"

# Conversation states
ASK_START, ASK_END, ASK_DURATION, ASK_NAME = range(4)

video_path = "input.mp4"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Please upload your video (MP4 format).")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("❌ This is not a valid video.")
        return

    await update.message.reply_text("📥 Downloading video...")
    file = await video.get_file()
    await file.download_to_drive(video_path)
    await update.message.reply_text("✅ Downloaded!\n\nNow send the START time (e.g., 00:10:00):")
    return ASK_START

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['start_time'] = update.message.text.strip()
    await update.message.reply_text("Send the END time (e.g., 00:40:00):")
    return ASK_END

async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['end_time'] = update.message.text.strip()
    await update.message.reply_text("Send clip duration in seconds (e.g., 60):")
    return ASK_DURATION

async def ask_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['duration'] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ASK_DURATION
    await update.message.reply_text("Send the base name for the clips (e.g., Squid Game):")
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['base_name'] = update.message.text.strip()

    await update.message.reply_text("🎬 Processing video... Please wait.")

    start = context.user_data['start_time']
    end = context.user_data['end_time']
    duration = context.user_data['duration']
    base_name = context.user_data['base_name']

    os.makedirs("clips", exist_ok=True)
    trimmed_video = "trimmed.mp4"

    # Step 1: Trim the video
    trim_cmd = f'ffmpeg -ss {start} -to {end} -i "{video_path}" -c copy "{trimmed_video}" -y'
    subprocess.call(trim_cmd, shell=True)

    # Step 2: Split + HDR-style filter + watermark
    split_cmd = (
        f'ffmpeg -i "{trimmed_video}" -i logo.png '
        f'-filter_complex "[0:v]scale=1080:1920,eq=contrast=1.4:saturation=1.5:brightness=0.05,unsharp=5:5:0.8[vid];'
        f'[vid][1:v]overlay=W-w-10:H-h-10" '
        f'-c:a copy -f segment -segment_time {duration} clips/output%03d.mp4 -y'
    )
    subprocess.call(split_cmd, shell=True)

    # Step 3: Rename + Send each clip
    files = sorted(os.listdir("clips"))
    for idx, filename in enumerate(files, start=1):
        new_name = f"{base_name} {idx}.mp4"
        os.rename(f"clips/{filename}", f"clips/{new_name}")
        await update.message.reply_video(video=InputFile(f"clips/{new_name}"), caption=new_name)

    await update.message.reply_text("✅ Done! All clips sent.")

    # Cleanup
    try:
        os.remove(video_path)
        os.remove(trimmed_video)
        for f in os.listdir("clips"):
            os.remove(f"clips/{f}")
    except Exception as e:
        print("Cleanup error:", e)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Process cancelled.")
    return ConversationHandler.END

# App builder
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video)],
    states={
        ASK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start)],
        ASK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end)],
        ASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_duration)],
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

app.add_handler(CommandHandler("start", start))
app.add_handler(conv_handler)

app.run_polling()
