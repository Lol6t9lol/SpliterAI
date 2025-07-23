import os
import subprocess
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # 🔒 Secure from Render ENV

ASK_START, ASK_END, ASK_DURATION, ASK_NAME = range(4)
video_path = "input.mp4"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me an MP4 video to begin.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("❌ Please upload a valid MP4 video.")
        return
    await update.message.reply_text("📥 Downloading video...")
    file = await video.get_file()
    await file.download_to_drive(video_path)
    await update.message.reply_text("✅ Video downloaded.\nNow send **START time** (HH:MM:SS):")
    return ASK_START

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['start_time'] = update.message.text.strip()
    await update.message.reply_text("Now send **END time** (HH:MM:SS):")
    return ASK_END

async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['end_time'] = update.message.text.strip()
    await update.message.reply_text("Send split duration in **minutes** (e.g. 1):")
    return ASK_DURATION

async def ask_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        minutes = float(update.message.text.strip())
        context.user_data['duration'] = int(minutes * 60)
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ASK_DURATION
    await update.message.reply_text("Now send the base name (e.g. `Squid Game`):")
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['base_name'] = update.message.text.strip()
    await update.message.reply_text("🎬 Processing your video...")

    start = context.user_data['start_time']
    end = context.user_data['end_time']
    duration = context.user_data['duration']
    base_name = context.user_data['base_name']

    os.makedirs("clips", exist_ok=True)
    trimmed = "trimmed.mp4"

    try:
        subprocess.run([
            "ffmpeg", "-ss", start, "-to", end,
            "-i", video_path, "-c", "copy", trimmed, "-y"
        ], check=True)

        subprocess.run([
            "ffmpeg", "-i", trimmed,
            "-c:v", "libx264", "-preset", "fast",
            "-f", "segment", "-segment_time", str(duration),
            "-reset_timestamps", "1",
            "clips/output%03d.mp4", "-y"
        ], check=True)

        files = sorted(os.listdir("clips"))
        for i, file in enumerate(files, 1):
            new_name = f"{base_name} {i}.mp4"
            os.rename(f"clips/{file}", f"clips/{new_name}")
            await update.message.reply_video(InputFile(f"clips/{new_name}"), caption=new_name)

        await update.message.reply_text("✅ Done! All clips sent.")
    except subprocess.CalledProcessError as e:
        await update.message.reply_text("❌ Error processing video.")
        print("FFmpeg error:", e)
    finally:
        try:
            os.remove(video_path)
            os.remove(trimmed)
            for f in os.listdir("clips"):
                os.remove(f"clips/{f}")
        except Exception as e:
            print("Cleanup error:", e)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

app = ApplicationBuilder().token(BOT_TOKEN).build()

conv = ConversationHandler(
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
app.add_handler(conv)
app.run_polling()
