from fastapi import FastAPI, Request
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from google import genai
from google.genai import types
from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import BackgroundTasks
import sqlite3
import json
import os


from write_sheet import save_row_to_sheet


load_dotenv()


DB_FILE = "conversations.db"
TURN_LIMIT = 10
GEMINI_MODRL = "gemini-2.5-flash-lite"


SYSTEM_INSTRUCTION = """
あなたは、路地裏にある落ち着いた雰囲気の喫茶店の「マスター」です。
あなたの目的は、来店した客（ユーザー）と4ターン程度の短い雑談を行い、客の現在の「感情」や「その感情に至った背景」をできるだけ多く言葉として引き出すことです。
集められた客の発言は、後に感情推定AIの入力データとして使用されます。

以下の振る舞いの指針に従ってロールプレイを行ってください。

## キャラクター設定
- **口調:** 穏やかで親しみやすく、包容力のある敬語（〜ですね、〜ですか）。
- **性格:** 聞き上手。客の話を否定せず、まずは共感する。
- **雰囲気:** 相手がホッと息をつけるような、温かい雰囲気を作る。

## 会話のガイドライン
1.  **会話の長さ:** - 全体で4往復（4ターン）程度で会話を構成してください。
    - 4ターン目で会話を自然に締めくくり、「少々お待ちくださいね」と注文の品（紅茶）を用意する動作に移ってください。

2.  **引き出しテクニック（重要）:**
    - 客が「疲れた」等の短い言葉を発した場合、**「何かあったのですか？」**や**「それは大変でしたね、具体的にどのようなことが？」**といった、背景にあるエピソードを引き出す質問を投げかけてください。
    - 客が感情を隠しているように見える場合、**「ここだけの話ですから、愚痴でも自慢でも構いませんよ」**と心理的安全性を確保し、吐露を促してください。
    - Plutchikの8感情（喜び、信頼、恐れ、驚き、悲しみ、嫌悪、怒り、期待）のいずれかが含まれるようなエピソードを語らせることを目指します。

3.  **禁止事項:**
    - あなた（マスター）が自分語りをしすぎないこと。主役はあくまで客です。
    - AIのような機械的な応答を避けること。
    - まだ紅茶を提供しないこと（会話が終わった後にシステムが選定するため）。

## 会話のフロー例

**ターン1（導入）:**
「いらっしゃいませ。今日もお疲れ様です。……ふふ、少し表情が硬いようですが、何かありましたか？」
（※客の状態を推測し、話題を振る）

**ターン2（深掘り）:**
客：「いや、実は仕事でミスをしてしまって…」
あなた：「おや、それは気がかりですね。よろしければ聞かせてくれませんか？ 言葉にすると少し軽くなるかもしれませんよ。」
（※否定せず受け止め、詳細を話すよう促す）

**ターン3（共感と確認）:**
客：「上司に理不尽なことで怒鳴られて、腹が立って…」
あなた：「なるほど、理不尽なのは堪えますね……。それは怒りを感じて当然です。ずっと我慢されていたんですね。」
（※感情（ここでは怒り）を肯定し、更に本音が出やすいようにする）

**ターン4（締め）:**
客：「そうなんです、本当に悔しくて…」
あなた：「吐き出していただけてよかったです。……さて、そんな今のあなたにぴったりの一杯を淹れましょう。少々お待ちくださいね。」
（※会話を切り上げ、推論フェーズへ移行する合図を出す）
ターン4で全ての会話が終わった時には、必ず、出力の最後に、「END_OF_CONVERSATION」を付け加えてください。
"""


# =================================================
# Initialize Gemini
# =================================================

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def create_chat():
    return client.chats.create(
        model=GEMINI_MODRL,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
    )


# =================================================
# Database
# =================================================


def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS utterances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        turn Integer,
        FOREIGN KEY (subject_id) REFERENCES subjects (id)
    );
    """)

    conn.commit()
    conn.close()


# =================================================
# FastAPI
# =================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    pass


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


sessions = {}


# =================================================
# Input model
# =================================================


class ChatRequest(BaseModel):
    name: str
    message: str


# ================================================
# Templates
# ================================================

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# =================================================
# Get data
# =================================================


@app.get("/conversations")
async def get_conversations(token: str = Query(...)):
    if token != os.getenv("ADMIN_TOKEN"):
        return {"error": "Unauthorized"}

    data = get_conversations_json()

    return data


# =================================================
# API Endpoints
# =================================================


@app.post("/chat")
def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    name = req.name
    message = req.message

    if name not in sessions:
        sessions[name] = {
            "chat": create_chat(),
            "user_utterances": [],
            "ai_utterances": [],
            "turn_count": 0,
        }

    session = sessions[name]

    response = session["chat"].send_message(message).text

    session["user_utterances"].append(message)
    session["ai_utterances"].append(response)
    session["turn_count"] += 1

    if "END_OF_CONVERSATION" in response or session["turn_count"] >= TURN_LIMIT:
        save_conversation(name, session["user_utterances"], session["ai_utterances"])
        background_tasks.add_task(
            save_row_to_sheet,
            name,
            session["user_utterances"],
            session["ai_utterances"],
        )
        del sessions[name]

        print(" Conversation saved and session ended.")

        return {"response": response, "ended": True}

    return {"response": response, "ended": False}


def save_conversation(name, user_utterances, ai_utterances):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
    subject_id = cur.lastrowid

    for turn, (user_u, ai_u) in enumerate(zip(user_utterances, ai_utterances), start=1):
        cur.execute(
            "INSERT INTO utterances (subject_id, role, content, turn) VALUES (?, ?, ?, ?)",
            (subject_id, "user", user_u, turn),
        )
        cur.execute(
            "INSERT INTO utterances (subject_id, role, content, turn) VALUES (?, ?, ?, ?)",
            (subject_id, "ai", ai_u, turn),
        )

    conn.commit()
    conn.close()


def get_conversations_json():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, name FROM subjects")
    subjects = cur.fetchall()

    data = []

    for subject_id, name in subjects:
        cur.execute(
            """
            SELECT role, content, turn FROM utterances
            WHERE subject_id = ?
            ORDER BY turn, role
        """,
            (subject_id,),
        )

        user_utterances = []
        ai_utterances = []

        for role, content, _ in cur.fetchall():
            if role == "user":
                user_utterances.append(content)
            else:
                ai_utterances.append(content)

        data.append(
            {
                "name": name,
                "user_utterances": user_utterances,
                "ai_utterances": ai_utterances,
            }
        )

        conn.close()
        return data
