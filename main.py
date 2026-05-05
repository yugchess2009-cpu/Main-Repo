import threading
import re
import json
import asyncio
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running')
    def log_message(self, format, *args):
        pass

threading.Thread(
    target=lambda: HTTPServer(('0.0.0.0', 8080), Handler).serve_forever(),
    daemon=True
).start()

import os
import base64
import random
import logging
from collections import defaultdict
from openai import AsyncOpenAI
import uuid
from telegram import Update, Message, BotCommand, MessageEntity, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Environment ────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "dummy")
BASE_DIR         = os.path.dirname(__file__)

# Auto-populated in post_init via get_me() — never read from env
BOT_USERNAME: str = ""   # e.g. "yugjeebot"  (no @)
BOT_NAME: str     = ""   # e.g. "Helper"
BOT_ID: int       = 0    # numeric Telegram user ID of the bot
MEME_PATH        = os.path.join(BASE_DIR, "assets", "padhai_meme.jpg")
LEADERBOARD_FILE = os.path.join(BASE_DIR, "leaderboard.json")
DAILY_FILE       = os.path.join(BASE_DIR, "daily_question.json")

text_client   = AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
vision_client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

TEXT_MODEL   = "llama-3.3-70b-versatile"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

TODAY = lambda: date.today().isoformat()          # "2026-05-05"
TODAY_LABEL = lambda: datetime.now().strftime("%d %b %Y")

# ── System prompt ──────────────────────────────────────────────────────────────
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
- Compliments, appreciation, thank you → respond warmly and encourage them.
- Questions about what the bot can do → answer kindly and briefly.
- Greetings → greet back warmly and invite them to ask a doubt.
- Study-related chat, exam stress, feeling stuck → be warm and supportive.

ONLY use [OFF_TOPIC] for messages clearly unrelated to JEE, studying, or the bot — like gossip, movies, cricket scores, politics, relationships.
When off-topic, reply with exactly:
[OFF_TOPIC]
Then one warm line gently nudging them back. Do NOT be rude."""

# ── Savage off-topic replies ───────────────────────────────────────────────────
SAVAGE_REPLIES = [
    "Arey laala, ye mera syllabus nahi hai.\nPadhle — aa, ek doubt pooch.",
    "Yaar, ye JEE mein nahi aati, lekin Newton ke laws zaroor aate hain.\nEk doubt bhej, solve karte hain!",
    "Galat jagah aa gaya thoda.\nMera kaam Physics, Chemistry aur Maths hai — kuch pooch.",
    "Haha, ye toh main nahi jaanta laala.\nLekin projectile motion zaroor jaanta hoon. Padh le!",
    "Padhle padhle — kyu nahi horhi padhai?\nBook khol, ek question pooch, main hoon na.",
    "JEE ke baad yeh sab poochna — tab baat karunga.\nAbhi ek doubt bhej de.",
    "Mujhe ye nahi aata, but integration aata hai.\nKuch aur nahi toh ek formula puch le!",
    "Bhai, ye topic mera nahi — Physics, Chem, Math mera kaam hai.\nAa, saath mein padhte hain.",
    "Laala, ye mera field nahi — lekin tera IIT ka sapna mera field hai.\nPadhle, main hoon yahan.",
]

# ── Tips & quotes ──────────────────────────────────────────────────────────────
TIPS = [
    "Pomodoro technique — 25 min study, 5 min break. Repeat 4x, then a long rest.",
    "When overwhelmed, write down every pending task. A clear list beats a foggy mind.",
    "Teach what you just learned to an imaginary student. If you can explain it simply, you truly understand it.",
    "5 deep breaths — inhale 4 counts, hold 4, exhale 4. Resets your nervous system instantly.",
    "Solve at least 10 problems on every new concept. Understanding without practice is incomplete.",
    "Step outside for 10 minutes. Sunlight and fresh air reset focus better than staring at a wall.",
    "Revise yesterday's topics for the first 15 minutes of each session. Spaced repetition works.",
    "Drink water. Most brain fog is just dehydration. Keep a bottle on your study table.",
    "Do the hardest subject first when energy is at its peak — usually morning.",
    "Stop comparing your chapter count with others. Your journey is not theirs.",
    "Make a formula sheet as you study each chapter. 5 min before sleep works wonders.",
    "Sleep 7-8 hours. Memory consolidation happens during sleep. All-nighters delete more than they add.",
    "Attempt previous year JEE papers topic-wise. It shows exactly what the exam expects.",
    "Avoid social media during study hours. Every distraction costs 20+ minutes of focus.",
    "Mark weak topics and schedule extra time for them instead of always revising strengths.",
    "Talk to someone you trust when pressure feels heavy. Bottling up stress makes it worse.",
    "Write your own short notes while studying. Writing reinforces memory far better than re-reading.",
    "Exercise for 20 minutes a day. It reduces cortisol and improves concentration significantly.",
    "Group similar concepts together. Connections make recall faster.",
    "Analyze each wrong answer in detail. Do not just check the answer and move on.",
    "Your worth is not your rank. You are more than your JEE result. Do your best.",
    "Read the question fully before solving. Half the JEE mistakes come from misreading.",
    "Celebrate small milestones — finished a chapter, solved a tough problem. Reward yourself.",
]

QUOTES = [
    "The expert in anything was once a beginner. Keep going.",
    "Consistency beats talent when talent doesn't show up every day.",
    "Hard work beats genius when genius doesn't work hard.",
    "The pain of discipline is far less than the pain of regret.",
    "Your future self is watching you right now. Make them proud.",
    "IIT is not a dream for those who chase it — it is a decision.",
    "Champions train when no one is watching.",
    "Pressure makes diamonds. Embrace it.",
    "You have survived every hard day so far. Today is no different.",
    "Study not to pass, but to know. Passing will follow.",
    "The rank you want is earned in the hours no one sees.",
    "A year from now you will wish you had started harder today.",
    "Focus on progress, not perfection. Rest if you must, but never quit.",
    "The goal is not to be better than others — it is to be better than your yesterday.",
    "Every formula you memorize today is a second saved on exam day.",
    "Mistakes are proof that you are trying.",
    "Small daily improvements lead to stunning long-term results.",
    "You are closer than you think. Do not stop now.",
    "Believe in the process. The result will take care of itself.",
    "Discipline is choosing what you want most over what you want now.",
    "Doubt your doubts before you doubt your abilities.",
    "Success is the sum of small efforts repeated day in and day out.",
    "Weak moments are temporary. Your potential is permanent.",
    "Do not wait for motivation — build discipline instead.",
    "Think like a topper. Work like a topper. Become one.",
    "The syllabus is finite. Your effort can be limitless.",
    "Start before you feel ready. Revision is not repetition — it is reinforcement.",
    "The top rank belongs to those who refused to give up.",
    "Excellence is not a destination — it is a habit you build daily.",
    "Outwork your excuses. Your rank is decided today, not on exam day.",
]

# ── Achievement badges ─────────────────────────────────────────────────────────
def get_badge(pct: float) -> str:
    if pct == 100:  return "PERFECT SCORE — Legend status!"
    if pct >= 90:   return "Elite Performer — IIT material!"
    if pct >= 75:   return "Strong Performance — Keep it up!"
    if pct >= 60:   return "Good Effort — Almost there!"
    if pct >= 40:   return "Keep Going — Practice makes perfect."
    return                  "Rookie Mode — Revisit this chapter."

def get_grade(pct: float) -> str:
    if pct == 100:  return "S"
    if pct >= 90:   return "A+"
    if pct >= 75:   return "A"
    if pct >= 60:   return "B"
    if pct >= 40:   return "C"
    return                  "D"

def progress_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"

def streak_fire(n: int) -> str:
    if n == 0:   return ""
    if n < 3:    return " (getting started!)"
    if n < 7:    return " (on a roll!)"
    if n < 14:   return " (unstoppable!)"
    if n < 30:   return " (LEGEND streak!)"
    return               " (GOD MODE!)"

# ── Leaderboard / stats persistence ───────────────────────────────────────────
def load_leaderboard() -> dict:
    try:
        with open(LEADERBOARD_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_leaderboard(lb: dict) -> None:
    try:
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump(lb, f, indent=2)
    except Exception as e:
        logger.error("Leaderboard save error: %s", e)

def record_quiz_score(uid: int, name: str, score: int, total: int, chapter: str, topic: str) -> None:
    lb  = load_leaderboard()
    key = str(uid)
    pct = round((score / total) * 100, 1)
    today = TODAY()

    entry = lb.get(key, {
        "name": name, "total_quizzes": 0, "total_correct": 0, "total_questions": 0,
        "best_pct": 0.0, "best_score": 0, "best_total": 0,
        "best_chapter": "", "best_topic": "", "best_date": "",
        "chapter_stats": {}, "streak": 0, "last_quiz_date": "", "quiz_history": [],
    })

    # ensure new fields exist on old entries
    entry.setdefault("chapter_stats", {})
    entry.setdefault("streak", 0)
    entry.setdefault("last_quiz_date", "")
    entry.setdefault("quiz_history", [])

    entry["name"] = name
    entry["total_quizzes"]   += 1
    entry["total_correct"]   += score
    entry["total_questions"] += total

    # chapter stats
    cs = entry["chapter_stats"]
    if chapter not in cs:
        cs[chapter] = {"correct": 0, "total": 0}
    cs[chapter]["correct"] += score
    cs[chapter]["total"]   += total

    # streak
    last = entry["last_quiz_date"]
    if last == today:
        pass  # same day, keep streak
    elif last == date.fromisoformat(today).replace(day=date.fromisoformat(today).day - 1).isoformat() if last else False:
        entry["streak"] += 1
    else:
        # check properly
        try:
            from datetime import timedelta
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if last == yesterday:
                entry["streak"] += 1
            elif last == today:
                pass
            else:
                entry["streak"] = 1
        except Exception:
            entry["streak"] = 1
    entry["last_quiz_date"] = today

    # best performance
    if pct >= entry["best_pct"]:
        entry["best_pct"]     = pct
        entry["best_score"]   = score
        entry["best_total"]   = total
        entry["best_chapter"] = chapter
        entry["best_topic"]   = topic
        entry["best_date"]    = TODAY_LABEL()

    # quiz history (keep last 10)
    entry["quiz_history"].append({
        "score": score, "total": total, "pct": pct,
        "chapter": chapter, "topic": topic, "date": TODAY_LABEL(),
    })
    entry["quiz_history"] = entry["quiz_history"][-10:]

    lb[key] = entry
    save_leaderboard(lb)

def get_user_entry(uid: int) -> dict | None:
    lb = load_leaderboard()
    return lb.get(str(uid))

def build_leaderboard_text() -> str:
    lb = load_leaderboard()
    if not lb:
        return "No scores yet — be the first! Type /quiz to start."

    entries = sorted(lb.values(), key=lambda e: (-e["best_pct"], -e.get("total_correct", 0)))
    medal_icons = ["GOLD", "SILVER", "BRONZE"]
    lines = ["=== JEE Quiz Leaderboard ===\n"]

    for i, e in enumerate(entries[:10]):
        rank    = medal_icons[i] if i < 3 else f"#{i+1}"
        overall = round(e["total_correct"] / e["total_questions"] * 100, 1) if e.get("total_questions") else 0
        streak  = e.get("streak", 0)
        streak_tag = f"  |  {streak}d streak{streak_fire(streak)}" if streak > 0 else ""
        lines.append(
            f"{rank}  {e['name']}\n"
            f"  Best: {e['best_score']}/{e['best_total']} ({e['best_pct']}%) — {e.get('best_chapter','')} : {e.get('best_topic','')}\n"
            f"  Overall: {e['total_correct']}/{e['total_questions']} ({overall}%)  |  {e['total_quizzes']} quiz(zes){streak_tag}"
        )

    lines.append("\nType /quiz to climb the ranks!")
    return "\n\n".join(lines)

def build_mystats_text(uid: int) -> str:
    e = get_user_entry(uid)
    if not e:
        return "You have not completed any quiz yet!\nType /quiz to get started and build your stats."

    overall = round(e["total_correct"] / e["total_questions"] * 100, 1) if e.get("total_questions") else 0
    streak  = e.get("streak", 0)
    cs      = e.get("chapter_stats", {})

    best_chap  = max(cs, key=lambda c: cs[c]["correct"] / cs[c]["total"] if cs[c]["total"] else 0, default=None)
    worst_chap = min(cs, key=lambda c: cs[c]["correct"] / cs[c]["total"] if cs[c]["total"] else 1, default=None)

    best_chap_pct  = round(cs[best_chap]["correct"]  / cs[best_chap]["total"]  * 100, 1) if best_chap  else 0
    worst_chap_pct = round(cs[worst_chap]["correct"] / cs[worst_chap]["total"] * 100, 1) if worst_chap else 0

    history = e.get("quiz_history", [])
    recent_lines = ""
    if history:
        recent_lines = "\nRecent Quizzes:\n"
        for h in reversed(history[-5:]):
            recent_lines += f"  {h['date']}  {h['score']}/{h['total']} ({h['pct']}%)  {h['chapter']}\n"

    streak_line = f"{streak} day(s){streak_fire(streak)}" if streak else "0 (take a quiz today!)"

    return (
        f"=== Your JEE Stats ===\n\n"
        f"Name          : {e['name']}\n"
        f"Total Quizzes : {e['total_quizzes']}\n"
        f"Overall Score : {e['total_correct']}/{e['total_questions']} ({overall}%)\n"
        f"{progress_bar(overall)}\n\n"
        f"Best Quiz  : {e['best_score']}/{e['best_total']} ({e['best_pct']}%)\n"
        f"Best Topic : {e.get('best_chapter','')} — {e.get('best_topic','')}\n"
        f"Best Date  : {e.get('best_date','')}\n\n"
        f"Strongest  : {best_chap} ({best_chap_pct}%)\n" if best_chap else ""
        f"Weakest    : {worst_chap} ({worst_chap_pct}%)\n" if worst_chap else ""
        f"Streak     : {streak_line}\n"
        f"{recent_lines}"
        f"\nType /rank to see your leaderboard position."
    )

def build_rank_text(uid: int, name: str) -> str:
    lb = load_leaderboard()
    if not lb or str(uid) not in lb:
        return "You have not completed any quiz yet — type /quiz to enter the rankings!"

    entries = sorted(lb.values(), key=lambda e: (-e["best_pct"], -e.get("total_correct", 0)))
    uid_str = str(uid)
    my_rank = next((i + 1 for i, e_pair in enumerate(
        sorted(lb.items(), key=lambda kv: (-kv[1]["best_pct"], -kv[1].get("total_correct", 0)))
    ) if e_pair[0] == uid_str), None)

    if my_rank is None:
        return "You are not on the leaderboard yet. Complete a quiz first!"

    me = lb[uid_str]
    total = len(entries)
    lines = [f"=== Your Rank ===\n\nYou are #{my_rank} out of {total} student(s)."]

    if my_rank == 1:
        lines.append("You are at the TOP! Keep defending that throne.")
    else:
        above = entries[my_rank - 2]
        gap   = round(above["best_pct"] - me["best_pct"], 1)
        lines.append(f"One above you: {above['name']} ({above['best_pct']}%)\nGap to beat: {gap}% — you can close this!")

    if my_rank < total:
        below = entries[my_rank]
        lines.append(f"One below you: {below['name']} ({below['best_pct']}%) — they are coming for you!")

    overall = round(me["total_correct"] / me["total_questions"] * 100, 1) if me.get("total_questions") else 0
    lines.append(f"\nYour best: {me['best_pct']}%  |  Overall: {overall}%\nType /quiz to improve your rank!")
    return "\n\n".join(lines)

# ── Daily question persistence ─────────────────────────────────────────────────
def load_daily() -> dict:
    try:
        with open(DAILY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_daily(data: dict) -> None:
    try:
        with open(DAILY_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Daily save error: %s", e)

async def get_or_generate_daily() -> dict | None:
    today = TODAY()
    data  = load_daily()
    if data.get("date") == today and data.get("question"):
        return data

    # pick a random JEE topic for the daily
    topics = [
        ("Kinematics",         "Projectile Motion"),
        ("Laws of Motion",     "Newton's Second Law"),
        ("Work Energy Power",  "Conservation of Energy"),
        ("Thermodynamics",     "Carnot Cycle"),
        ("Electrostatics",     "Coulomb's Law"),
        ("Current Electricity","Kirchhoff's Laws"),
        ("Optics",             "Refraction"),
        ("Organic Chemistry",  "SN1 and SN2 Reactions"),
        ("Electrochemistry",   "Nernst Equation"),
        ("Coordination Cmpds", "IUPAC Nomenclature"),
        ("Matrices",           "Determinants"),
        ("Limits",             "L'Hopital's Rule"),
        ("Integration",        "Integration by Parts"),
        ("Probability",        "Bayes' Theorem"),
        ("3D Geometry",        "Distance Between Lines"),
    ]
    chapter, topic = random.choice(topics)

    prompt = (
        f"Generate one JEE Advanced level multiple choice question on '{topic}' from '{chapter}'.\n"
        "Format EXACTLY:\n"
        "QUESTION: [full question text]\n"
        "A: [option]\nB: [option]\nC: [option]\nD: [option]\n"
        "ANSWER: [A/B/C/D]\n"
        "EXPLANATION: [one concise line]\n"
        "No LaTeX — plain text formulas only."
    )
    try:
        resp = await text_client.chat.completions.create(
            model=TEXT_MODEL, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content or ""
        questions = parse_questions(raw + "\n###")
        if not questions:
            return None
        q = questions[0]
        data = {"date": today, "chapter": chapter, "topic": topic, "question": q, "answered_by": []}
        save_daily(data)
        return data
    except Exception as e:
        logger.error("Daily question gen error: %s", e)
        return None

def record_daily_answer(uid: int) -> None:
    data = load_daily()
    if "answered_by" not in data:
        data["answered_by"] = []
    uid_str = str(uid)
    if uid_str not in data["answered_by"]:
        data["answered_by"].append(uid_str)
    save_daily(data)

# ── Per-user state ─────────────────────────────────────────────────────────────
MAX_HISTORY     = 12
history: dict[int, list[dict]]  = defaultdict(list)
identify_wait: set[int]         = set()
quiz_setup: dict[int, dict]     = {}
active_quiz: dict[int, dict]    = {}
daily_wait: set[int]            = set()
# ── Duel state ────────────────────────────────────────────────────────────────
pending_duels: dict[str, dict]  = {}  # duel_id -> awaiting acceptance
active_duels:  dict[str, dict]  = {}  # duel_id -> live duel
user_to_duel:  dict[int, str]   = {}  # uid -> duel_id
duel_setup:    dict[int, dict]  = {}  # challenger uid -> setup step

# ── Conversation history ───────────────────────────────────────────────────────
def build_messages(uid: int, content) -> list[dict]:
    hist = history[uid]
    hist.append({"role": "user", "content": content})
    if len(hist) > MAX_HISTORY * 2:
        del hist[:2]
    return [{"role": "system", "content": SYSTEM_PROMPT}] + hist

def record_reply(uid: int, reply: str) -> None:
    history[uid].append({"role": "assistant", "content": reply})

# ── AI calls ───────────────────────────────────────────────────────────────────
async def ask(uid: int, content, max_tok: int = 500) -> str:
    messages = build_messages(uid, content)
    try:
        resp = await text_client.chat.completions.create(
            model=TEXT_MODEL, max_tokens=max_tok, messages=messages,
        )
        reply = resp.choices[0].message.content or "Could not generate a response. Please try again."
        record_reply(uid, reply)
        return reply
    except Exception as e:
        logger.error("Groq text error: %s", e)
        return "Something went wrong. Please try again in a moment."

async def ask_vision(instruction: str, b64: str, max_tok: int = 700) -> str:
    try:
        resp = await vision_client.chat.completions.create(
            model=VISION_MODEL, max_tokens=max_tok,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}],
        )
        return resp.choices[0].message.content or "Could not read the image. Please try again."
    except Exception as e:
        logger.error("Groq vision error: %s", e)
        return "I had trouble reading the image. Please try again."

async def generate_quiz_questions(num: int, chapter: str, topic: str) -> list[dict] | None:
    prompt = (
        f"Generate exactly {num} JEE Advanced level multiple choice questions "
        f"on '{topic}' from '{chapter}'.\n\n"
        "Use this EXACT format for EVERY question, no deviations:\n\n"
        "QUESTION: [full question text here]\n"
        "A: [option A]\n"
        "B: [option B]\n"
        "C: [option C]\n"
        "D: [option D]\n"
        "ANSWER: [single letter A, B, C, or D only]\n"
        "EXPLANATION: [one concise line explaining why]\n"
        "###\n\n"
        "Important rules:\n"
        "- Use plain text formulas only, no LaTeX or symbols like \\frac\n"
        "- All 4 options must be plausible\n"
        "- ANSWER must be exactly one letter: A, B, C, or D\n"
        "- End every question with ###\n"
        f"- Generate exactly {num} questions"
    )
    max_tok = min(num * 250 + 500, 8000)
    try:
        resp = await text_client.chat.completions.create(
            model=TEXT_MODEL, max_tokens=max_tok,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content or ""
        logger.info("Quiz raw response (first 300 chars): %s", raw[:300])
        result = parse_questions(raw)
        logger.info("Parsed %d questions from quiz response", len(result))
        return result if result else None
    except Exception as e:
        logger.error("Quiz generation error: %s", e)
        return None

def parse_questions(raw: str) -> list[dict]:
    questions = []
    # Split by ### or by numbered question patterns
    blocks = [b.strip() for b in re.split(r"###|\n(?=Q\d+[\).])", raw) if b.strip()]
    for block in blocks:
        q: dict = {}
        lines = block.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            upper = line.upper()
            # Question line
            if upper.startswith("QUESTION:"):
                text = line[9:].strip()
                # collect continuation lines until next key
                i += 1
                while i < len(lines):
                    nxt = lines[i].strip()
                    if re.match(r"^(A|B|C|D|ANSWER|EXPLANATION)\s*:", nxt, re.IGNORECASE):
                        break
                    text += " " + nxt
                    i += 1
                q["q"] = text.strip()
                continue
            # Options A B C D
            m = re.match(r"^([ABCD])\s*[:.)\-]\s*(.+)", line, re.IGNORECASE)
            if m:
                q[m.group(1).upper()] = m.group(2).strip()
                i += 1
                continue
            # Answer
            if upper.startswith("ANSWER:"):
                ans = line[7:].strip().upper()
                q["ans"] = ans[0] if ans else ""
                i += 1
                continue
            # Explanation
            if upper.startswith("EXPLANATION:"):
                q["exp"] = line[12:].strip()
                i += 1
                continue
            i += 1
        # Fill missing explanation
        if "exp" not in q:
            q["exp"] = "Review this concept carefully."
        if all(k in q for k in ("q", "A", "B", "C", "D", "ans")) and q["ans"] in ("A","B","C","D"):
            questions.append(q)
    return questions

def format_question(q: dict, idx: int, total: int) -> str:
    return (
        f"Question {idx} of {total}\n\n"
        f"{q['q']}\n\n"
        f"A)  {q['A']}\n"
        f"B)  {q['B']}\n"
        f"C)  {q['C']}\n"
        f"D)  {q['D']}\n\n"
        "Reply with A, B, C, or D"
    )

def format_duel_question(q: dict, idx: int, total: int) -> str:
    return (
        f"[DUEL] Question {idx}/{total}\n\n"
        f"{q['q']}\n\n"
        f"A)  {q['A']}\nB)  {q['B']}\nC)  {q['C']}\nD)  {q['D']}\n\n"
        "Both players reply A, B, C, or D"
    )

def build_duel_result(duel: dict) -> str:
    cid = duel["challenger_id"]
    did = duel["challenged_id"]
    cs  = duel["scores"].get(cid, 0)
    ds  = duel["scores"].get(did, 0)
    tot = len(duel["questions"])
    if cs > ds:
        winner = f"{duel['challenger_name']} WINS!"
    elif ds > cs:
        winner = f"{duel['challenged_name']} WINS!"
    else:
        winner = "Dead tie! Both are legends."
    return (
        f"=== DUEL OVER ===\n\n"
        f"{duel['challenger_name']}  :  {cs}/{tot}\n"
        f"{duel['challenged_name']}  :  {ds}/{tot}\n\n"
        f"Chapter: {duel['chapter']} — {duel['topic']}\n\n"
        f"{winner}\n\n"
        "Type /challenge to rematch!"
    )

def quiz_result_text(score: int, total: int, chapter: str, topic: str) -> str:
    pct   = (score / total) * 100
    grade = get_grade(pct)
    badge = get_badge(pct)
    bar   = progress_bar(pct)
    return (
        f"=== Quiz Complete! ===\n\n"
        f"Chapter  : {chapter}\n"
        f"Topic    : {topic}\n\n"
        f"Score    : {score}/{total}  ({pct:.0f}%)\n"
        f"Grade    : {grade}\n"
        f"{bar}\n\n"
        f"{badge}\n\n"
        "Type /mystats to see all your stats\n"
        "Type /leaderboard to see rankings\n"
        "Type /quiz to go again!"
    )

# ── Utilities ──────────────────────────────────────────────────────────────────
async def send_savage_reply(msg: Message, context: ContextTypes.DEFAULT_TYPE) -> None:
    await msg.reply_text(random.choice(SAVAGE_REPLIES))
    try:
        with open(MEME_PATH, "rb") as f:
            await msg.reply_photo(photo=f)
    except Exception as e:
        logger.warning("Meme send error: %s", e)

def is_off_topic(text: str) -> tuple[bool, str]:
    if text.startswith("[OFF_TOPIC]"):
        return True, text.replace("[OFF_TOPIC]", "").strip()
    return False, text

async def photo_to_base64(msg: Message, context: ContextTypes.DEFAULT_TYPE) -> str:
    file = await context.bot.get_file(msg.photo[-1].file_id)
    data = await file.download_as_bytearray()
    return base64.standard_b64encode(data).decode()

def strip_mention(text: str) -> str:
    """Remove @username and bot name from text so the question is clean."""
    out = text
    if BOT_USERNAME:
        out = re.sub(rf"@{re.escape(BOT_USERNAME)}", "", out, flags=re.IGNORECASE)
    if BOT_NAME:
        out = re.sub(rf"\b{re.escape(BOT_NAME)}\b", "", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()

def is_group_chat(update: Update) -> bool:
    return update.message.chat.type in ("group", "supergroup")

def should_respond_in_group(update: Update, text: str = "") -> bool:
    """
    Decide whether the bot should respond to a group message.

    Priority order:
      1. User is inside an active bot flow (quiz / daily / identify) — always respond.
      2. Telegram entity-based @mention  (most reliable — official Telegram markup).
      3. Telegram TEXT_MENTION entity    (tag without username, matched by bot user-id).
      4. Direct reply to any of the bot's own messages.
      5. Bot display-name appears anywhere in the text (word-boundary match).
      6. Generic bot-addressing patterns: "bot, ...", "hey bot", message starts with "bot ".
    """
    msg      = update.message
    uid      = update.effective_user.id if update.effective_user else None
    raw_text = text or msg.text or msg.caption or ""
    t        = raw_text.lower().strip()

    # ── 1. Active per-user state ───────────────────────────────────────────────
    if uid and (uid in daily_wait or uid in identify_wait or
                uid in quiz_setup or uid in active_quiz or
                uid in duel_setup or uid in user_to_duel):
        return True

    # ── 2 & 3. Official Telegram entity mentions ──────────────────────────────
    # Telegram explicitly tags @mentions with MessageEntity.MENTION and
    # name-based mentions (no @) with MessageEntity.TEXT_MENTION.
    # This is far more reliable than scanning the raw string.
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    for ent in entities:
        if ent.type == MessageEntity.MENTION and BOT_USERNAME:
            # entity covers "@username" in raw_text; strip @ to compare
            handle = raw_text[ent.offset: ent.offset + ent.length].lstrip("@").lower()
            if handle == BOT_USERNAME.lower():
                return True
        elif ent.type == MessageEntity.TEXT_MENTION and BOT_ID:
            # Mention of a user who has no public username — matched by id
            if ent.user and ent.user.id == BOT_ID:
                return True

    # ── 4. Direct reply to the bot's own message ──────────────────────────────
    rt = msg.reply_to_message
    if rt and rt.from_user and rt.from_user.is_bot:
        replied_uname = (rt.from_user.username or "").lower()
        if not BOT_USERNAME or replied_uname == BOT_USERNAME.lower():
            return True

    # ── 5. Bot display-name in text (word-boundary, case-insensitive) ─────────
    if BOT_NAME and re.search(rf"\b{re.escape(BOT_NAME.lower())}\b", t):
        return True

    # ── 6. Generic bot-addressing patterns ────────────────────────────────────
    # Catches: "bot, solve this", "hey bot", "aye bot", "bot please help me"
    if re.search(r"(^|[\s,!?])bot[\s,!?:]", t) or t.startswith("bot "):
        return True

    return False

def get_display_name(user) -> str:
    return (user.username and f"@{user.username}") or user.full_name or "Unknown"

# ── Commands ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mention = f"@{BOT_USERNAME}" if BOT_USERNAME else "me"
    await update.message.reply_text(
        "Hello! I am your JEE Doubt Solver.\n\n"
        "=== DOUBT SOLVING ===\n"
        "/solve <question>   — Step-by-step solution\n"
        "/hint <question>    — A nudge, no full answer\n"
        "/formula <topic>    — Key formulas instantly\n"
        "/identify           — Identify anything in an image\n\n"
        "=== QUIZ & STATS ===\n"
        "/quiz               — Interactive JEE quiz\n"
        "/stopquiz           — Cancel current quiz\n"
        "/daily              — Today's challenge question\n"
        "/leaderboard        — Top scorer rankings\n"
        "/mystats            — Your personal stats\n"
        "/rank               — Your leaderboard position\n\n"
        "=== MOTIVATION ===\n"
        "/motivate           — Push to keep going\n"
        "/tips               — Study and stress tips\n\n"
        "=== OTHER ===\n"
        "/about              — Full feature list\n"
        "/clear              — Fresh start\n"
        "/help               — This guide\n\n"
        "Send a photo of any question to solve it.\n"
        "Add 'translate' in caption to translate it.\n\n"
        f"In groups, tag {mention} with your message."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "=== JEE Doubt Solver — Full Feature List ===\n\n"
        "SOLVING\n"
        "- Solve any JEE Physics, Chemistry, or Maths doubt\n"
        "- Hints without revealing the full answer\n"
        "- Solve questions directly from images\n"
        "- Identify people, objects, diagrams in images\n"
        "- Translate text in images to English\n"
        "- Key formulas for any topic on demand\n\n"
        "QUIZ SYSTEM\n"
        "- Full interactive quiz with your choice of chapter and topic\n"
        "- 1 to 50 questions per session\n"
        "- Instant feedback + explanation after each answer\n"
        "- Score, grade, and badge at the end\n"
        "- Daily challenge question (changes every day)\n\n"
        "STATS & RANKINGS\n"
        "- Personal stats: accuracy, streak, best/worst chapter\n"
        "- Leaderboard: top 10 ranked by best quiz score\n"
        "- Your rank + gap to beat the person above you\n"
        "- Study streak tracking (consecutive days of quizzes)\n"
        "- Quiz history: last 10 sessions saved\n\n"
        "EXTRAS\n"
        "- Motivational quotes + study/stress tips\n"
        "- Remembers last 12 messages for context\n"
        "- Works in groups (tag the bot)\n\n"
        "Just ask. I am always here."
    )

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    history[uid].clear()
    identify_wait.discard(uid)
    daily_wait.discard(uid)
    quiz_setup.pop(uid, None)
    active_quiz.pop(uid, None)
    await update.message.reply_text("All cleared! Starting completely fresh.")

async def cmd_solve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    q   = " ".join(context.args).strip() if context.args else ""
    if not q:
        await update.message.reply_text("Usage: /solve <your question>")
        return
    raw = await ask(uid, f"Solve step by step:\n{q}")
    off, clean = is_off_topic(raw)
    await (send_savage_reply(update.message, context) if off else update.message.reply_text(clean))

async def cmd_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    q   = " ".join(context.args).strip() if context.args else ""
    if not q:
        await update.message.reply_text("Usage: /hint <your question>")
        return
    raw = await ask(uid, f"Give only a HINT (no solution) for:\n{q}")
    off, clean = is_off_topic(raw)
    await (send_savage_reply(update.message, context) if off else update.message.reply_text(clean))

async def cmd_formula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid   = update.effective_user.id
    topic = " ".join(context.args).strip() if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: /formula <topic>  e.g. /formula kinematics")
        return
    raw = await ask(uid, f"List the most important JEE formulas for '{topic}'. Format: Name: formula. Plain text, no LaTeX.")
    off, clean = is_off_topic(raw)
    await (send_savage_reply(update.message, context) if off else update.message.reply_text(clean))

async def cmd_motivate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(random.choice(QUOTES))

async def cmd_tips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(random.choice(TIPS))

# ── /identify ─────────────────────────────────────────────────────────────────
async def cmd_identify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    identify_wait.add(update.effective_user.id)
    await update.message.reply_text(
        "Sure! Send me the image now.\n\n"
        "I can identify:\n"
        "- JEE questions and diagrams\n"
        "- Famous scientists and personalities\n"
        "- Scientific instruments and apparatus\n"
        "- Graphs, charts, and data visuals\n"
        "- Text, equations, or handwritten notes"
    )

# ── /quiz ─────────────────────────────────────────────────────────────────────
async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if uid in active_quiz:
        await update.message.reply_text(
            "You already have an active quiz running!\n"
            "Answer the current question or type /stopquiz to cancel."
        )
        return
    quiz_setup[uid] = {"step": "num"}
    await update.message.reply_text(
        "=== JEE Quiz ===\n\n"
        "How many questions would you like?\n"
        "Enter a number from 1 to 50."
    )

async def cmd_stopquiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    was = uid in active_quiz or uid in quiz_setup
    active_quiz.pop(uid, None)
    quiz_setup.pop(uid, None)
    await update.message.reply_text(
        "Quiz cancelled. Come back whenever you're ready!" if was
        else "No active quiz to cancel."
    )

# ── /leaderboard ──────────────────────────────────────────────────────────────
async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(build_leaderboard_text())

# ── /mystats ──────────────────────────────────────────────────────────────────
async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(build_mystats_text(update.effective_user.id))

# ── /challenge ────────────────────────────────────────────────────────────────
async def cmd_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_group_chat(update):
        await update.message.reply_text("Challenges only work in group chats — add me to a group!")
        return
    args = context.args
    if not args or not args[0].startswith("@"):
        await update.message.reply_text("Usage: /challenge @username [1-10 questions]\nExample: /challenge @rahul 5")
        return
    challenger = update.effective_user
    challenged_uname = args[0].lstrip("@").lower()
    if challenged_uname == BOT_USERNAME.lower():
        await update.message.reply_text("You can't challenge me — I'd ace every question!")
        return
    if challenger.username and challenged_uname == challenger.username.lower():
        await update.message.reply_text("You can't challenge yourself!")
        return
    num = 5
    if len(args) > 1 and args[1].isdigit():
        num = max(1, min(10, int(args[1])))
    duel_id = uuid.uuid4().hex[:8]
    pending_duels[duel_id] = {
        "chat_id":            update.message.chat_id,
        "challenger_id":      challenger.id,
        "challenger_name":    get_display_name(challenger),
        "challenged_username": challenged_uname,
        "num":                num,
    }
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Accept", callback_data=f"duel_accept:{duel_id}"),
        InlineKeyboardButton("Decline",  callback_data=f"duel_decline:{duel_id}"),
    ]])
    await update.message.reply_text(
        f"@{challenged_uname}\n\n"
        f"{get_display_name(challenger)} challenges you to a {num}-question JEE duel!\n"
        "Do you accept?",
        reply_markup=kb,
    )

async def handle_duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not query.data or ":" not in query.data:
        return
    action, duel_id = query.data.split(":", 1)
    if action not in ("duel_accept", "duel_decline"):
        return
    duel = pending_duels.get(duel_id)
    if not duel:
        await query.edit_message_text("This challenge has expired.")
        return
    user = query.from_user
    if user.username and user.username.lower() != duel["challenged_username"].lower():
        await query.answer("This challenge isn't for you!", show_alert=True)
        return
    if action == "duel_decline":
        pending_duels.pop(duel_id, None)
        await query.edit_message_text(f"{get_display_name(user)} declined. Scared of the competition!")
        return
    # Accepted
    pending_duels.pop(duel_id, None)
    active_duels[duel_id] = {
        "chat_id":         duel["chat_id"],
        "challenger_id":   duel["challenger_id"],
        "challenger_name": duel["challenger_name"],
        "challenged_id":   user.id,
        "challenged_name": get_display_name(user),
        "questions": [], "current": 0,
        "scores":  {duel["challenger_id"]: 0, user.id: 0},
        "answered": {},
        "chapter": "", "topic": "", "num": duel["num"], "started": False,
    }
    user_to_duel[duel["challenger_id"]] = duel_id
    user_to_duel[user.id]               = duel_id
    duel_setup[duel["challenger_id"]]   = {"step": "chapter", "duel_id": duel_id}
    await query.edit_message_text(
        f"{get_display_name(user)} accepted!\n\n"
        f"{duel['challenger_name']}, pick the battleground.\n"
        "Which chapter? (e.g. Kinematics, Organic Chemistry, Matrices)"
    )

async def cmd_cancelchallenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    duel_id = user_to_duel.pop(uid, None)
    duel_setup.pop(uid, None)
    if duel_id and duel_id in active_duels:
        duel = active_duels.pop(duel_id)
        other = duel["challenged_id"] if duel["challenger_id"] == uid else duel["challenger_id"]
        user_to_duel.pop(other, None)
    cancelled = [k for k, v in pending_duels.items() if v["challenger_id"] == uid]
    for k in cancelled:
        pending_duels.pop(k, None)
    await update.message.reply_text("Challenge cancelled." if (duel_id or cancelled) else "No active challenge to cancel.")

# ── /rank ─────────────────────────────────────────────────────────────────────
async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(build_rank_text(user.id, get_display_name(user)))

# ── /daily ────────────────────────────────────────────────────────────────────
async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    wait = await update.message.reply_text("Fetching today's challenge question...")

    data = await get_or_generate_daily()
    await wait.delete()

    if not data or not data.get("question"):
        await update.message.reply_text("Could not load today's question. Try again in a moment.")
        return

    answered = str(uid) in data.get("answered_by", [])
    q = data["question"]

    if answered:
        await update.message.reply_text(
            f"You already answered today's challenge!\n\n"
            f"Chapter: {data['chapter']} — {data['topic']}\n\n"
            f"{q['q']}\n\n"
            f"A)  {q['A']}\nB)  {q['B']}\nC)  {q['C']}\nD)  {q['D']}\n\n"
            f"Correct answer: {q['ans']}\n"
            f"Explanation: {q['exp']}\n\n"
            "Come back tomorrow for a new one!"
        )
        return

    daily_wait.add(uid)
    await update.message.reply_text(
        f"=== Daily Challenge — {TODAY_LABEL()} ===\n\n"
        f"Chapter: {data['chapter']} — {data['topic']}\n\n"
        f"{q['q']}\n\n"
        f"A)  {q['A']}\nB)  {q['B']}\nC)  {q['C']}\nD)  {q['D']}\n\n"
        "Reply with A, B, C, or D"
    )

# ── Photo handler ──────────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg     = update.message
    uid     = update.effective_user.id
    caption = msg.caption or ""

    if is_group_chat(update) and not should_respond_in_group(update, caption):
        return

    clean_cap      = strip_mention(caption).strip().lower()
    translate_mode = "translate" in clean_cap
    is_identify    = uid in identify_wait or any(k in clean_cap for k in [
        "identify", "who is", "who's", "what is this", "what's this",
    ])

    thinking = await msg.reply_text("Reading your image, please wait...")
    try:
        b64 = await photo_to_base64(msg, context)

        if translate_mode:
            instruction = (
                "Extract all text from this image exactly as written, "
                "then provide a clear English translation. "
                "Show original first, then translation below it."
            )
        elif is_identify:
            identify_wait.discard(uid)
            instruction = (
                "You are an expert image analyst. Carefully examine this image and identify everything in it.\n\n"
                "If there is a PERSON in the image:\n"
                "- State their full name confidently if you recognize them\n"
                "- What are they famous for?\n"
                "- One interesting fact about them\n"
                "- Their field (scientist, politician, athlete, etc.)\n\n"
                "If there is a SCIENTIFIC INSTRUMENT or APPARATUS:\n"
                "- Name it precisely\n"
                "- What is it used for?\n\n"
                "If there is a GRAPH, DIAGRAM or CHART:\n"
                "- What does it show?\n"
                "- What are the key takeaways?\n\n"
                "If there is a JEE QUESTION or EQUATION:\n"
                "- Identify the topic and concept\n"
                "- Solve it step by step\n\n"
                "Be direct and confident. Max 8 lines. If you genuinely cannot identify something, say so honestly."
            )
        else:
            extra = f" Student note: {strip_mention(caption)}" if caption.strip() else ""
            instruction = (
                "This is a JEE student's image. It likely contains a question, diagram, or problem. "
                "Identify what is being asked and solve it step by step. "
                "Write all formulas in plain text. Be concise and precise." + extra
            )

        reply = await ask_vision(instruction, b64)
    except Exception as e:
        logger.error("Photo handler error: %s", e)
        reply = "I had trouble reading the image. Please try again."

    await thinking.delete()
    off, clean = is_off_topic(reply)
    await (send_savage_reply(msg, context) if off else msg.reply_text(clean))

# ── Text handler ───────────────────────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg      = update.message
    text     = (msg.text or "").strip()
    uid      = update.effective_user.id
    user     = update.effective_user

    if is_group_chat(update) and not should_respond_in_group(update, text):
        return

    question = strip_mention(text).strip()
    if not question:
        await msg.reply_text("Ask me any JEE doubt!")
        return

    # ── Daily answer ──────────────────────────────────────────────────────────
    if uid in daily_wait:
        ans = question.strip().upper()
        if ans not in ("A", "B", "C", "D"):
            await msg.reply_text("Please reply with A, B, C, or D for the daily challenge.")
            return
        data = load_daily()
        q    = data.get("question")
        if not q:
            daily_wait.discard(uid)
            await msg.reply_text("Daily question not found. Type /daily to try again.")
            return

        correct  = q["ans"]
        is_right = ans == correct
        daily_wait.discard(uid)
        record_daily_answer(uid)

        if is_right:
            await msg.reply_text(
                f"Correct! Well done!\n\n"
                f"Explanation: {q['exp']}\n\n"
                "Come back tomorrow for a new challenge!"
            )
        else:
            await msg.reply_text(
                f"Incorrect. The correct answer is {correct}.\n\n"
                f"Explanation: {q['exp']}\n\n"
                "Better luck tomorrow! Type /quiz to practice more."
            )
        return

    # ── Quiz setup flow ───────────────────────────────────────────────────────
    if uid in quiz_setup:
        setup = quiz_setup[uid]
        step  = setup["step"]

        if step == "num":
            if not question.isdigit() or not (1 <= int(question) <= 50):
                await msg.reply_text("Please enter a number between 1 and 50.")
                return
            setup["num"]  = int(question)
            setup["step"] = "chapter"
            await msg.reply_text(
                f"Great — {setup['num']} question(s) it is!\n\n"
                "Which chapter?\n"
                "(e.g. Kinematics, Thermodynamics, Organic Chemistry, Matrices)"
            )
            return

        if step == "chapter":
            setup["chapter"] = question
            setup["step"]    = "topic"
            await msg.reply_text(
                f"Chapter: {setup['chapter']}\n\n"
                "Now the specific topic within this chapter.\n"
                "Be precise for the best questions.\n"
                "(e.g. Projectile Motion, Nernst Equation, Integration by Parts)"
            )
            return

        if step == "topic":
            setup["topic"] = question
            num     = setup["num"]
            chapter = setup["chapter"]
            topic   = setup["topic"]
            quiz_setup.pop(uid, None)

            wait_msg = await msg.reply_text(
                f"Generating {num} JEE-level question(s)...\n\n"
                f"Chapter : {chapter}\n"
                f"Topic   : {topic}\n\n"
                "Please wait..."
            )
            questions = await generate_quiz_questions(num, chapter, topic)

            if not questions:
                await wait_msg.delete()
                await msg.reply_text(
                    "Could not generate questions for this topic. "
                    "Try a more specific topic or a different chapter."
                )
                return

            actual = len(questions)
            active_quiz[uid] = {
                "questions": questions, "current": 0, "score": 0,
                "total": actual, "chapter": chapter, "topic": topic,
            }
            await wait_msg.delete()
            await msg.reply_text(
                f"=== Quiz Ready! ===\n\n"
                f"Chapter  : {chapter}\n"
                f"Topic    : {topic}\n"
                f"Questions: {actual}\n\n"
                "Answer each question with A, B, C, or D.\n"
                "Type /stopquiz at any time to cancel.\n\n"
                "Let's go!"
            )
            await msg.reply_text(format_question(questions[0], 1, actual))
            return

    # ── Quiz answer flow ──────────────────────────────────────────────────────
    if uid in active_quiz:
        quiz = active_quiz[uid]
        ans  = question.strip().upper()

        if ans not in ("A", "B", "C", "D"):
            await msg.reply_text("Please reply with A, B, C, or D.")
            return

        current_q = quiz["questions"][quiz["current"]]
        correct   = current_q["ans"]
        is_right  = ans == correct

        if is_right:
            quiz["score"] += 1

        feedback = (
            f"{'Correct!' if is_right else f'Incorrect. Answer is {correct}.'}\n"
            f"Explanation: {current_q['exp']}\n\n"
            f"Score: {quiz['score']}/{quiz['current'] + 1}"
        )
        await msg.reply_text(feedback)
        quiz["current"] += 1

        if quiz["current"] >= quiz["total"]:
            result = quiz_result_text(quiz["score"], quiz["total"], quiz["chapter"], quiz["topic"])
            record_quiz_score(uid, get_display_name(user), quiz["score"], quiz["total"], quiz["chapter"], quiz["topic"])
            active_quiz.pop(uid, None)
            await msg.reply_text(result)
        else:
            await msg.reply_text(format_question(quiz["questions"][quiz["current"]], quiz["current"] + 1, quiz["total"]))
        return

    # ── Duel setup flow (challenger picks chapter & topic) ────────────────────
    if uid in duel_setup:
        setup   = duel_setup[uid]
        duel_id = setup["duel_id"]
        if setup["step"] == "chapter":
            setup["chapter"] = question
            setup["step"]    = "topic"
            await msg.reply_text(f"Chapter: {question}\nNow the topic? (e.g. Projectile Motion, Le Chatelier's Principle)")
            return
        if setup["step"] == "topic":
            chapter = setup["chapter"]
            topic   = question
            num     = active_duels[duel_id]["num"]
            duel_setup.pop(uid, None)
            wait = await msg.reply_text(f"Generating {num} duel questions on {chapter} — {topic}...")
            questions = await generate_quiz_questions(num, chapter, topic)
            await wait.delete()
            if not questions:
                active_duels.pop(duel_id, None)
                user_to_duel.pop(active_duels.get(duel_id, {}).get("challenged_id"), None)
                user_to_duel.pop(uid, None)
                await msg.reply_text("Couldn't generate questions. Try /challenge again.")
                return
            duel = active_duels[duel_id]
            duel.update({"questions": questions, "chapter": chapter, "topic": topic, "started": True})
            await msg.reply_text(
                f"=== DUEL ===\n"
                f"{duel['challenger_name']}  vs  {duel['challenged_name']}\n"
                f"Chapter: {chapter} — {topic}  |  {len(questions)} questions\n\n"
                "Both players answer each question. Let the battle begin!"
            )
            await msg.reply_text(format_duel_question(questions[0], 1, len(questions)))
            return

    # ── Duel answer flow ──────────────────────────────────────────────────────
    if uid in user_to_duel:
        duel_id = user_to_duel[uid]
        duel    = active_duels.get(duel_id)
        if duel and duel.get("started"):
            ans = question.strip().upper()
            if ans not in ("A", "B", "C", "D"):
                await msg.reply_text("Reply with A, B, C, or D for the duel question.", **kwargs)
                return
            cur = duel["current"]
            duel["answered"].setdefault(cur, {})
            if uid in duel["answered"][cur]:
                await msg.reply_text("Already answered — waiting for your opponent.", **kwargs)
                return
            duel["answered"][cur][uid] = ans
            correct  = duel["questions"][cur]["ans"]
            is_right = ans == correct
            if is_right:
                duel["scores"][uid] += 1
            await msg.reply_text(
                f"{'Correct!' if is_right else f'Wrong — answer was {correct}.'} "
                f"(Your score: {duel['scores'][uid]})",
                **kwargs,
            )
            both = {duel["challenger_id"], duel["challenged_id"]}
            if set(duel["answered"][cur].keys()) == both:
                duel["current"] += 1
                if duel["current"] >= len(duel["questions"]):
                    result = build_duel_result(duel)
                    user_to_duel.pop(duel["challenger_id"], None)
                    user_to_duel.pop(duel["challenged_id"], None)
                    active_duels.pop(duel_id, None)
                    await msg.reply_text(result)
                else:
                    nq = duel["questions"][duel["current"]]
                    await msg.reply_text(format_duel_question(nq, duel["current"] + 1, len(duel["questions"])))
            return

    # ── Normal doubt solving ──────────────────────────────────────────────────
    prompt = f"Give only a HINT (no solution) for: {question}" if "hint" in question.lower() else question
    raw    = await ask(uid, prompt)
    off, clean = is_off_topic(raw)
    kwargs = {"reply_to_message_id": msg.message_id} if is_group_chat(update) else {}
    await (send_savage_reply(msg, context) if off else msg.reply_text(clean, **kwargs))

# ── Register commands with Telegram ───────────────────────────────────────────
async def post_init(app) -> None:
    global BOT_USERNAME, BOT_NAME, BOT_ID
    me = await app.bot.get_me()
    BOT_USERNAME = (me.username or "").lower()
    BOT_NAME     = me.first_name or ""
    BOT_ID       = me.id
    logger.info("Bot identity: id=%d  @%s  name='%s'", BOT_ID, BOT_USERNAME, BOT_NAME)

    await app.bot.set_my_commands([
        BotCommand("start",       "Welcome and usage guide"),
        BotCommand("help",        "Show all commands"),
        BotCommand("about",       "Full feature list"),
        BotCommand("solve",       "Step-by-step solution"),
        BotCommand("hint",        "Hint only — no full answer"),
        BotCommand("formula",     "Key formulas for any topic"),
        BotCommand("identify",    "Identify anything in an image"),
        BotCommand("quiz",        "Take an interactive JEE quiz"),
        BotCommand("stopquiz",    "Cancel the current quiz"),
        BotCommand("daily",       "Today's daily challenge question"),
        BotCommand("leaderboard", "Top quiz score rankings"),
        BotCommand("mystats",     "Your personal quiz stats"),
        BotCommand("rank",        "Your position on the leaderboard"),
        BotCommand("motivate",    "Get a motivational quote"),
        BotCommand("tips",            "Study and stress management tips"),
        BotCommand("challenge",       "Duel another student — /challenge @username"),
        BotCommand("cancelchallenge", "Cancel your current challenge"),
        BotCommand("clear",           "Reset conversation and quiz state"),
    ])
    logger.info("Commands registered with Telegram")

# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    logger.info("Starting JEE Doubt Solver bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("about",       cmd_about))
    app.add_handler(CommandHandler("clear",       cmd_clear))
    app.add_handler(CommandHandler("solve",       cmd_solve))
    app.add_handler(CommandHandler("hint",        cmd_hint))
    app.add_handler(CommandHandler("formula",     cmd_formula))
    app.add_handler(CommandHandler("identify",    cmd_identify))
    app.add_handler(CommandHandler("quiz",        cmd_quiz))
    app.add_handler(CommandHandler("stopquiz",    cmd_stopquiz))
    app.add_handler(CommandHandler("daily",       cmd_daily))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("mystats",     cmd_mystats))
    app.add_handler(CommandHandler("rank",        cmd_rank))
    app.add_handler(CommandHandler("motivate",        cmd_motivate))
    app.add_handler(CommandHandler("tips",            cmd_tips))
    app.add_handler(CommandHandler("challenge",       cmd_challenge))
    app.add_handler(CommandHandler("cancelchallenge", cmd_cancelchallenge))
    app.add_handler(CallbackQueryHandler(handle_duel_callback, pattern=r"^duel_(accept|decline):"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is polling for updates...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
