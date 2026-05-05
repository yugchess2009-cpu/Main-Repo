import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running')
    def log_message(self, format, *args):
        pass

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', 8080), Handler).serve_forever(), daemon=True).start()

import os
import base64
import random
import logging
import os
import base64
import random
import logging
from collections import defaultdict
from openai import AsyncOpenAI
from telegram import Update, Message, BotCommand, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Environment ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
OPENAI_API_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy")
BOT_USERNAME    = os.environ.get("BOT_USERNAME", "").lower()
MEME_PATH       = os.path.join(os.path.dirname(__file__), "assets", "padhai_meme.jpg")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a warm, sharp JEE tutor — like a caring elder sibling who wants you to succeed.

PERSONALITY:
- Always polite, never condescending or harsh.
- Concise but kind. Every reply feels human and caring.

STRICT RULES:
1. Maximum 5-8 lines per reply. Never exceed.
2. Formulas in plain text: "F = ma", "v^2 = u^2 + 2as". No LaTeX.
3. For doubts: concept (1 line) → formula → numbered steps (1 line each).
4. HINT mode: one key insight only, no solution.
5. FORMULA mode: "Name: formula" per line only.
6. Adapt to the student's level using conversation history.
7. No filler, no repetition.

SPECIAL CASES — handle these warmly, never with [OFF_TOPIC]:
- Compliments, appreciation, thank you, nice words about the bot → respond warmly and encourage them to keep studying.
- Questions about what the bot can do, how it works, who made it → answer kindly and briefly.
- Greetings (hello, hi, good morning) → greet back warmly and invite them to ask a doubt.
- Study-related chat (asking about study plans, feeling stuck, exam stress, motivation) → be warm and supportive, give practical advice.

ONLY use [OFF_TOPIC] for messages clearly unrelated to JEE, studying, or the bot itself — like gossip, movies, cricket scores, politics, relationships, etc.
When off-topic, reply with exactly:
[OFF_TOPIC]
Then one warm line gently nudging them back to studying. Do NOT be rude."""

# ── Savage off-topic replies ──────────────────────────────────────────────────
SAVAGE_REPLIES = [
    "Arey laala, ye mera syllabus nahi hai.\nPadhle padhle — kyu nahi horhi padhai? Aa, ek doubt pooch.",
    "Yaar, ye cheez JEE mein nahi aati, lekin Newton ke laws zaroor aate hain.\nChal ek doubt bhej, solve karte hain!",
    "Galat jagah aa gaya thoda, bhai.\nMera kaam Physics, Chemistry aur Maths hai — aa, kuch pooch.",
    "Haha, ye toh main nahi jaanta laala.\nLekin projectile motion zaroor jaanta hoon. Padh le thoda!",
    "Padhle padhle — kyu nahi horhi padhai?\nBook khol, ek question pooch, main hoon na.",
    "Yaar, JEE ke baad yeh sab poochna — tab main bhi baat karunga.\nAbhi ek doubt bhej de, chal shuru karte hain.",
    "Mujhe ye nahi aata, but integration aata hai.\nKuch aur nahi toh ek formula puch le, laala!",
    "Bhai, ye topic toh mera nahi hai — Physics, Chemistry, Maths mera kaam hai.\nAa, saath mein padhte hain.",
    "Sahi sawaal galat bot pe pooch liya.\nLekin sahi bot pe sahi sawaal bhi pooch — ek doubt try kar!",
    "Laala, ye mera field nahi — lekin tera IIT ka sapna mera field hai.\nPadhle, main hoon yahan.",
]

# ── Study & stress tips ───────────────────────────────────────────────────────
TIPS = [
    "Study tip: Use the Pomodoro technique — 25 minutes of focused study, then a 5-minute break. Repeat 4 times, then take a longer break.",
    "Stress tip: When overwhelmed, write down every pending task. A clear list is less scary than a foggy mind.",
    "Study tip: Teach what you just learned to an imaginary student. If you can explain it simply, you truly understand it.",
    "Stress tip: Take 5 deep breaths — inhale for 4 counts, hold for 4, exhale for 4. It resets your nervous system instantly.",
    "Study tip: Solve at least 10 problems on every new concept before moving on. Understanding without practice is incomplete.",
    "Stress tip: Step outside for 10 minutes. Sunlight and fresh air reset your focus better than staring at a wall.",
    "Study tip: Revise the previous day's topics for the first 15 minutes of each session. Spaced repetition builds long-term memory.",
    "Stress tip: Drink water. Most brain fog is just dehydration. Keep a bottle on your study table always.",
    "Study tip: Do the hardest subject first when your energy is at its peak, usually in the morning.",
    "Stress tip: Stop comparing your chapter count with others. Your journey is not their journey. Focus on your own progress.",
    "Study tip: Make a formula sheet as you study each chapter. Revising it before sleep takes 5 minutes and works wonders.",
    "Stress tip: Sleep 7-8 hours. Memory consolidation happens during sleep. Pulling all-nighters deletes more than it adds.",
    "Study tip: Attempt previous year JEE papers topic-wise, not just full papers. It shows you exactly what the exam expects.",
    "Stress tip: Do not read news or social media during study hours. Every distraction breaks your focus for 20+ minutes.",
    "Study tip: Mark your weak topics and schedule extra time for them instead of always revising what you already know.",
    "Stress tip: Talk to someone you trust when pressure feels heavy. Bottling up stress makes it worse, not better.",
    "Study tip: Write your own short notes while studying. The act of writing reinforces memory far better than re-reading.",
    "Stress tip: Exercise for even 20 minutes a day. Physical activity reduces cortisol and improves concentration significantly.",
    "Study tip: Group similar concepts together — for example, all electrochemistry in one block. Connections make recall faster.",
    "Stress tip: Set a fixed end time for studying each night. Knowing you will stop at 11 PM makes the study hours more focused.",
    "Study tip: Mistakes in practice are good. Analyze each wrong answer — do not just check the answer and move on.",
    "Stress tip: Your worth is not your rank. You are more than your JEE result. Do your best and trust the process.",
    "Study tip: Use diagrams and flowcharts for complex topics like organic reaction mechanisms or thermodynamic cycles.",
    "Stress tip: Before sleeping, write three things you did well today. Small wins compound into confidence.",
    "Study tip: Solve numericals without a calculator occasionally. Mental math speed matters in the exam hall.",
    "Stress tip: Eat proper meals. Skipping lunch to study more is a bad trade — a hungry brain retains nothing.",
    "Study tip: If a concept confuses you, come back to it after a day. Sometimes rest gives your brain the time to connect the dots.",
    "Stress tip: Your exam hall performance depends on 90 days of preparation, not the last 90 minutes before it. Prepare early.",
    "Study tip: Read the question fully before solving. Half the mistakes in JEE come from misreading, not miscalculating.",
    "Stress tip: Celebrate small milestones — finished a chapter, solved a tough problem, scored well in a mock. Reward yourself.",
]

# ── Motivational quotes ───────────────────────────────────────────────────────
QUOTES = [
    "The expert in anything was once a beginner. Keep going.",
    "You don't have to be great to start, but you have to start to be great.",
    "Consistency beats talent when talent doesn't show up every day.",
    "Hard work beats genius when genius doesn't work hard.",
    "Every problem you solve today is one fewer on exam day.",
    "The pain of discipline is far less than the pain of regret.",
    "Your future self is watching you right now. Make them proud.",
    "IIT is not a dream for those who chase it — it is a decision.",
    "Ordinary efforts produce ordinary results. You are built for more.",
    "One more revision. One more problem. One more step forward.",
    "Success doesn't come from what you do occasionally, it comes from what you do consistently.",
    "Champions train when no one is watching.",
    "Pressure makes diamonds. Embrace it.",
    "You have survived every hard day so far. Today is no different.",
    "Study not to pass, but to know. Passing will follow.",
    "The rank you want is earned in the hours no one sees.",
    "A year from now you will wish you had started harder today.",
    "Focus on progress, not perfection.",
    "Rest if you must, but never quit.",
    "The goal is not to be better than others — it is to be better than your yesterday.",
    "Every formula you memorize today is a second saved on exam day.",
    "The student who asks questions learns faster than the one who pretends to understand.",
    "Mistakes are proof that you are trying.",
    "Small daily improvements lead to stunning long-term results.",
    "You are closer than you think. Do not stop now.",
    "Physics, Chemistry, Math — three mountains. Climb them one step at a time.",
    "Clarity comes with effort. Keep working.",
    "Believe in the process. The result will take care of itself.",
    "Discipline is choosing what you want most over what you want now.",
    "Your mind is your most powerful tool. Sharpen it every day.",
    "Doubt your doubts before you doubt your abilities.",
    "The harder the battle, the sweeter the victory.",
    "Success is the sum of small efforts repeated day in and day out.",
    "You were not born to be average. Prove it.",
    "Weak moments are temporary. Your potential is permanent.",
    "Learn from yesterday, work for today, aim for tomorrow.",
    "The best time to study was yesterday. The second best time is now.",
    "Do not wait for motivation — build discipline instead.",
    "Every hour of focused study compounds over time.",
    "Outwork your excuses.",
    "Think like a topper. Work like a topper. Become one.",
    "Solve one problem at a time and the exam becomes manageable.",
    "The syllabus is finite. Your effort can be limitless.",
    "Start before you feel ready.",
    "Revision is not repetition — it is reinforcement.",
    "Struggle builds strength. Welcome it.",
    "The top rank belongs to those who refused to give up.",
    "Your rank is decided today, not on exam day.",
    "Be the student you needed when you were confused.",
    "Excellence is not a destination — it is a habit you build daily.",
]

# ── Conversation history (per user, max 12 turns) ─────────────────────────────
MAX_HISTORY = 12
history: dict[int, list[dict]] = defaultdict(list)

def build_messages(user_id: int, content: str | list) -> list[dict]:
    hist = history[user_id]
    hist.append({"role": "user", "content": content})
    if len(hist) > MAX_HISTORY * 2:
        del hist[:2]
    return [{"role": "system", "content": SYSTEM_PROMPT}] + hist

def record_reply(user_id: int, reply: str) -> None:
    history[user_id].append({"role": "assistant", "content": reply})

# ── OpenAI call ───────────────────────────────────────────────────────────────
async def ask(user_id: int, content: str | list) -> str:
    messages = build_messages(user_id, content)
    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-5.1",
            max_completion_tokens=500,
            messages=messages,
        )
        reply = resp.choices[0].message.content or "Could not generate a response. Please try again."
        record_reply(user_id, reply)
        return reply
    except Exception as e:
        logger.error("OpenAI error: %s", e)
        return "Something went wrong. Please try again in a moment."

# ── Off-topic handler: savage reply + meme ────────────────────────────────────
async def send_savage_reply(msg: Message, context: ContextTypes.DEFAULT_TYPE) -> None:
    savage = random.choice(SAVAGE_REPLIES)
    await msg.reply_text(savage)
    try:
        with open(MEME_PATH, "rb") as f:
            await msg.reply_photo(photo=f)
    except Exception as e:
        logger.warning("Could not send meme image: %s", e)

def is_off_topic_response(text: str) -> tuple[bool, str]:
    if text.startswith("[OFF_TOPIC]"):
        clean = text.replace("[OFF_TOPIC]", "").strip()
        return True, clean
    return False, text

# ── Photo utilities ────────────────────────────────────────────────────────────
async def photo_to_base64(msg: Message, context: ContextTypes.DEFAULT_TYPE) -> str:
    photo = msg.photo[-1]
    file  = await context.bot.get_file(photo.file_id)
    data  = await file.download_as_bytearray()
    return base64.standard_b64encode(data).decode()

# ── Text utilities ─────────────────────────────────────────────────────────────
def strip_mention(text: str) -> str:
    if not BOT_USERNAME:
        return text.strip()
    return " ".join(p for p in text.split() if p.lower() != f"@{BOT_USERNAME}").strip()

def is_group(update: Update) -> bool:
    return update.message.chat.type in ("group", "supergroup")

def bot_mentioned(text: str) -> bool:
    return bool(BOT_USERNAME) and f"@{BOT_USERNAME}" in text.lower()

# ── Command handlers ──────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "me"
    await update.message.reply_text(
        "Hello! I am your JEE Doubt Solver.\n\n"
        "/solve <question> — Step-by-step solution\n"
        "/hint <question> — A nudge, no full answer\n"
        "/formula <topic> — Key formulas instantly\n"
        "/motivate — Get a push to keep going\n"
        "/clear — Fresh conversation start\n"
        "/help — Show this guide\n\n"
        "Send an image of a question to solve it.\n"
        "Send an image with 'translate' in caption to translate.\n\n"
        f"In groups, tag {mention} with your question."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    history[update.effective_user.id].clear()
    await update.message.reply_text("History cleared. Starting fresh!")

async def cmd_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id  = update.effective_user.id
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text("Usage: /hint <your question>")
        return
    raw = await ask(user_id, f"Give only a HINT (no solution) for:\n{question}")
    off, clean = is_off_topic_response(raw)
    if off:
        await send_savage_reply(update.message, context)
    else:
        await update.message.reply_text(clean)

async def cmd_solve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id  = update.effective_user.id
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text("Usage: /solve <your question>")
        return
    raw = await ask(user_id, f"Solve step by step:\n{question}")
    off, clean = is_off_topic_response(raw)
    if off:
        await send_savage_reply(update.message, context)
    else:
        await update.message.reply_text(clean)

async def cmd_formula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    topic   = " ".join(context.args).strip() if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: /formula <topic>  e.g. /formula kinematics")
        return
    raw = await ask(
        user_id,
        f"List the most important JEE formulas for '{topic}'. "
        "Format: Name: formula. Plain text, no LaTeX."
    )
    off, clean = is_off_topic_response(raw)
    if off:
        await send_savage_reply(update.message, context)
    else:
        await update.message.reply_text(clean)

async def cmd_motivate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(random.choice(QUOTES))

async def cmd_tips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(random.choice(TIPS))

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "I am a JEE Doubt Solver bot — built to help you crack Physics, Chemistry, and Maths.\n\n"
        "What I can do:\n"
        "- Solve any JEE-level doubt instantly\n"
        "- Give hints without revealing the full answer\n"
        "- Read and solve questions from images\n"
        "- Translate text in images to English\n"
        "- Share key formulas for any topic\n"
        "- Motivate you when you need a push\n"
        "- Give study and stress management tips\n"
        "- Roast you (lovingly) if you go off-topic\n\n"
        "I remember your last 12 messages so I can follow your train of thought.\n\n"
        "Just ask your doubt — I am always here."
    )

# ── Photo handler ─────────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg     = update.message
    user_id = update.effective_user.id
    caption = msg.caption or ""

    if is_group(update) and not bot_mentioned(caption):
        return

    clean_caption  = strip_mention(caption).strip().lower()
    translate_mode = "translate" in clean_caption

    thinking = await msg.reply_text("Reading your image...")

    try:
        b64 = await photo_to_base64(msg, context)

        if translate_mode:
            instruction = (
                "Extract all text from this image exactly as written, "
                "then provide a clear English translation. "
                "Show original first, then translation."
            )
        else:
            extra = f" Student note: {strip_mention(caption)}" if caption.strip() else ""
            instruction = (
                "This is a JEE student's image — it may contain a question or diagram. "
                "Identify what is asked and solve step by step. "
                "Formulas in plain text. Keep it concise." + extra
            )

        content = [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        raw = await ask(user_id, content)
    except Exception as e:
        logger.error("Photo handler error: %s", e)
        raw = "I had trouble reading the image. Please try again."

    await thinking.delete()
    off, clean = is_off_topic_response(raw)
    if off:
        await send_savage_reply(msg, context)
    else:
        await msg.reply_text(clean)

# ── Text message handler ──────────────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg     = update.message
    text    = msg.text or ""
    user_id = update.effective_user.id

    if is_group(update) and not bot_mentioned(text):
        return

    question = strip_mention(text).strip()
    if not question:
        await msg.reply_text("Ask me any JEE doubt!")
        return

    if "hint" in question.lower():
        prompt = f"Give only a HINT (no solution) for: {question}"
    else:
        prompt = question

    raw = await ask(user_id, prompt)
    off, clean = is_off_topic_response(raw)

    kwargs = {"reply_to_message_id": msg.message_id} if is_group(update) else {}

    if off:
        await send_savage_reply(msg, context)
    else:
        await msg.reply_text(clean, **kwargs)

# ── Startup: register commands ────────────────────────────────────
def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("hint", cmd_hint))
    app.add_handler(CommandHandler("solve", cmd_solve))
    app.add_handler(CommandHandler("formula", cmd_formula))
    app.add_handler(CommandHandler("motivate", cmd_motivate))
    app.add_handler(CommandHandler("tips", cmd_tips))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
