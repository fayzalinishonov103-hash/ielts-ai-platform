import os
import json
import sqlite3
from fastapi import FastAPI, Request, Form, HTTPException, Response, Cookie, Depends, status, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
from typing import Optional

app = FastAPI()
templates = Jinja2Templates(directory="templates")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"))
MY_ADMIN_USERNAME = "nishonov_273"


def init_db():
    conn = sqlite3.connect("cefr_database.db")
    cursor = conn.cursor()

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS users
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       name
                       TEXT,
                       username
                       TEXT
                       UNIQUE,
                       password
                       TEXT,
                       university
                       TEXT,
                       birth_date
                       TEXT,
                       address
                       TEXT,
                       level
                       TEXT
                       DEFAULT
                       'B2'
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS reading
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       title
                       TEXT,
                       passage_text
                       TEXT,
                       question
                       TEXT,
                       correct_answer
                       TEXT,
                       level
                       TEXT
                       DEFAULT
                       'B2'
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS listening
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       title
                       TEXT,
                       audio_text
                       TEXT,
                       question
                       TEXT,
                       correct_answer
                       TEXT,
                       level
                       TEXT
                       DEFAULT
                       'B2'
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS writing_topics
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       title
                       TEXT,
                       prompt_text
                       TEXT,
                       level
                       TEXT
                       DEFAULT
                       'B2'
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS speaking_topics
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       title
                       TEXT,
                       level
                       TEXT
                       DEFAULT
                       'B2'
                   )
                   """)

    tables = ["users", "reading", "listening", "writing_topics", "speaking_topics"]
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        if "level" not in columns:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN level TEXT DEFAULT 'B2'")
            except Exception:
                pass

    conn.commit()
    conn.close()


init_db()


async def get_current_user_cookie(username: Optional[str] = Cookie(None)):
    if not username:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return username


@app.post("/update-level")
async def update_user_level(level: str = Form(...), username: str = Depends(get_current_user_cookie)):
    if level not in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        raise HTTPException(status_code=400, detail="Noto'g'ri daraja tanlandi")

    conn = sqlite3.connect("cefr_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET level = ? WHERE username = ?", (level, username))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/reading", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        return HTMLResponse(
            content="<h3 style='color:white; background:black; text-align:center; padding:50px;'>Bu sahifaga faqat admin kira oladi! ⚠️</h3>",
            status_code=403)
    return templates.TemplateResponse(request, "admin.html", {})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {})


@app.post("/register")
async def register_user(
        name: str = Form(...), username: str = Form(...), password: str = Form(...),
        university: str = Form(...), birth_date: str = Form(...), address: str = Form(...), level: str = Form(...)
):
    try:
        conn = sqlite3.connect("cefr_database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, username, password, university, birth_date, address, level) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, username, password, university, birth_date, address, level))
        conn.commit()
        conn.close()
        return HTMLResponse(
            content="<script>alert('Muvaffaqiyatli ro\\'yxatdan o\\'tdingiz!'); window.location.href='/login';</script>")
    except sqlite3.IntegrityError:
        return HTMLResponse(content="<script>alert('Bu username allaqachon band!'); window.history.back();</script>")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        resp = HTMLResponse(
            content=f"<script>alert('Xush kelibsiz, {user['name']}!'); window.location.href='/profile';</script>")
        resp.set_cookie(key="username", value=user["username"])
        return resp
    else:
        return HTMLResponse(content="<script>alert('Login yoki parol xato!'); window.history.back();</script>")


@app.get("/logout")
async def logout():
    resp = HTMLResponse(content="<script>window.location.href='/login';</script>")
    resp.delete_cookie(key="username")
    return resp


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user_db = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM reading")
    reading_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM listening")
    listening_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM writing_topics")
    writing_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM speaking_topics")
    speaking_count = cursor.fetchone()[0]
    conn.close()

    if not user_db:
        return RedirectResponse(url="/login", status_code=303)

    user_info = {
        "name": user_db["name"],
        "username": user_db["username"],
        "university": user_db["university"] or "Andijan State Technical University",
        "faculty": "Intellectual Management and Computer Systems",
        "specialization": "Artificial Intelligence",
        "birth_date": user_db["birth_date"],
        "address": user_db["address"],
        "level": user_db["level"],
        "total_tasks": reading_count + listening_count + writing_count + speaking_count,
        "reading_count": reading_count,
        "listening_count": listening_count,
        "writing_count": writing_count,
        "speaking_count": speaking_count
    }
    return templates.TemplateResponse(request, "profile.html", {"user": user_info})


class AIHelperRequest(BaseModel):
    text_content: str
    module_type: str


@app.post("/api/ai-helper")
async def ai_helper(req: AIHelperRequest):
    try:
        prompt = f"""Sen CEFR va IELTS ekspertisan. Foydalanuvchi {req.module_type} uchun AI yordam rejimini yoqdi. 
        1. Mavzu bo'yicha eng muhim 5-6 ta kalit so'z va iboralar (inglizcha va o'zbekcha tarjimasi bilan).
        2. Ushbu mavzuda yuqori ball olish uchun 3 ta maslahat.
        Material:
        {req.text_content}"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        return {"ai_help": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 1. READING ---
@app.post("/admin/add-reading-ai")
async def add_reading_ai(title: str = Form(...), passage_text: str = Form(...), level: str = Form(...),
                         username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")
    try:
        prompt = f"""Matn asosida 1 ta savol va to'g'ri javob tuz. Matn: "{passage_text}"
        JSON formatida qaytar: {{"question": "...", "correct_answer": "..."}}"""
        response = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
            temperature=0.3, response_format={"type": "json_object"}
        )
        ai_data = json.loads(response.choices[0].message.content.strip())
        conn = sqlite3.connect("cefr_database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reading (title, passage_text, question, correct_answer, level) VALUES (?, ?, ?, ?, ?)",
            (title, passage_text, ai_data["question"], ai_data["correct_answer"], level))
        conn.commit()
        conn.close()
        return HTMLResponse(content="<script>alert('Reading qo\\'shildi!'); window.location.href='/admin';</script>")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reading", response_class=HTMLResponse)
async def reading_page(request: Request, username: str = Depends(get_current_user_cookie)):
    try:
        conn = sqlite3.connect("cefr_database.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        user_level = "B2"
        cursor.execute("SELECT level FROM users WHERE username = ?", (username,))
        user_row = cursor.fetchone()
        if user_row and "level" in user_row.keys() and user_row["level"]:
            user_level = user_row["level"]

        cursor.execute("SELECT * FROM reading WHERE level = ?", (user_level,))
        items = cursor.fetchall()

        if not items:
            cursor.execute("SELECT * FROM reading")
            items = cursor.fetchall()

        conn.close()

        return templates.TemplateResponse(
            request,
            "reading.html",
            {"items": items, "user_level": user_level}
        )
    except Exception as e:
        return HTMLResponse(content=f"<h3 style='color:red; padding:20px;'>Reading sahifasida xatolik: {str(e)}</h3>",
                            status_code=200)


@app.get("/reading/{item_id}", response_class=HTMLResponse)
async def reading_detail(request: Request, item_id: int, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reading WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()

    if not item:
        raise HTTPException(status_code=404, detail="Topilmadi")

    return templates.TemplateResponse(
        request,
        "reading_detail.html",
        {"item": item}
    )


class ReadingCheckRequest(BaseModel):
    item_id: int
    user_answer: str

@app.post("/api/check-reading")
async def check_reading_answer(req: ReadingCheckRequest):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT question, correct_answer FROM reading WHERE id = ?", (req.item_id,))
    item = cursor.fetchone()
    conn.close()
    if not item:
        raise HTTPException(status_code=404, detail="Topilmadi")

    try:
        prompt = f"""Savol: "{item['question']}" \nTo'g'ri javob: "{item['correct_answer']}" \nFoydalanuvchi javobi: "{req.user_answer}"
        Sinonimlar va ma'no jihatidan to'g'riligini tekshir. JSON formatida qaytar: {{"is_correct": true/false, "comment": "..."}}"""
        response = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
            temperature=0.1, response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content.strip())
        return {"is_correct": result.get("is_correct", False), "comment": result.get("comment", "")}
    except Exception:
        return {"is_correct": req.user_answer.strip().lower() == item["correct_answer"].strip().lower(), "comment": ""}

@app.get("/admin/delete-reading/{item_id}")
async def delete_reading(item_id: int, username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")
    conn = sqlite3.connect("cefr_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reading WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return HTMLResponse(content="<script>alert('O\\'chirildi!'); window.location.href='/reading';</script>")


# --- 2. LISTENING ---
@app.post("/admin/add-listening-ai")
async def add_listening_ai(title: str = Form(...), audio_text: str = Form(...), level: str = Form(...),
                           username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")
    try:
        prompt = f"""Audio matn asosida 1 ta savol va javob tuz: "{audio_text}"
        JSON formatida qaytar: {{"question": "...", "correct_answer": "..."}}"""
        response = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
            temperature=0.3, response_format={"type": "json_object"}
        )
        ai_data = json.loads(response.choices[0].message.content.strip())
        conn = sqlite3.connect("cefr_database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO listening (title, audio_text, question, correct_answer, level) VALUES (?, ?, ?, ?, ?)",
            (title, audio_text, ai_data["question"], ai_data["correct_answer"], level))
        conn.commit()
        conn.close()
        return HTMLResponse(content="<script>alert('Listening qo\\'shildi!'); window.location.href='/admin';</script>")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/listening", response_class=HTMLResponse)
async def listening_page(request: Request, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT level FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()
    user_level = user_row["level"] if user_row else "B2"
    cursor.execute("SELECT * FROM listening WHERE level = ?", (user_level,))
    items = cursor.fetchall()
    if not items:
        cursor.execute("SELECT * FROM listening")
        items = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request, "listening.html", {"items": items, "user_level": user_level})


@app.get("/listening/{item_id}", response_class=HTMLResponse)
async def listening_detail(request: Request, item_id: int, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM listening WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    if not item:
        raise HTTPException(status_code=404, detail="Topilmadi")
    return templates.TemplateResponse(request, "listening_detail.html", {"item": item})


class ListeningCheckRequest(BaseModel):
    item_id: int
    user_answer: str


@app.post("/api/check-listening")
async def check_listening_answer(req: ListeningCheckRequest):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT question, correct_answer FROM listening WHERE id = ?", (req.item_id,))
    item = cursor.fetchone()
    conn.close()
    if not item:
        raise HTTPException(status_code=404, detail="Topilmadi")

    try:
        prompt = f"""Savol: "{item['question']}" \nTo'g'ri javob: "{item['correct_answer']}" \nFoydalanuvchi: "{req.user_answer}"
        JSON formatida qaytar: {{"is_correct": true/false, "comment": "..."}}"""
        response = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
            temperature=0.1, response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content.strip())
        return {"is_correct": result.get("is_correct", False), "comment": result.get("comment", "")}
    except Exception:
        return {"is_correct": req.user_answer.strip().lower() == item["correct_answer"].strip().lower(), "comment": ""}


@app.post("/api/text-to-speech")
async def text_to_speech(data: dict):
    text = data.get("text", "")
    try:
        speech_file_path = "static/speech.mp3"
        response = client.audio.speech.create(model="tts-1", voice="alloy", input=text)
        response.stream_to_file(speech_file_path)
        return {"audio_url": f"/{speech_file_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 3. WRITING ---
@app.post("/admin/add-writing-ai")
async def add_writing_ai(title: str = Form(...), level: str = Form(...),
                         username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")
    try:
        prompt = f"Mavzu bo'yicha ko'rsatma tuz: '{title}'. JSON formatida qaytar: {{\"prompt_text\": \"...\"}}"
        response = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
            temperature=0.3, response_format={"type": "json_object"}
        )
        ai_data = json.loads(response.choices[0].message.content.strip())
        conn = sqlite3.connect("cefr_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO writing_topics (title, prompt_text, level) VALUES (?, ?, ?)",
                       (title, ai_data["prompt_text"], level))
        conn.commit()
        conn.close()
        return HTMLResponse(content="<script>alert('Writing qo\\'shildi!'); window.location.href='/admin';</script>")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/writing", response_class=HTMLResponse)
async def writing_page(request: Request, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT level FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()
    user_level = user_row["level"] if user_row else "B2"
    cursor.execute("SELECT * FROM writing_topics WHERE level = ?", (user_level,))
    topics = cursor.fetchall()
    if not topics:
        cursor.execute("SELECT * FROM writing_topics")
        topics = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request, "writing.html", {"topics": topics, "user_level": user_level})


@app.get("/writing/{topic_id}", response_class=HTMLResponse)
async def writing_detail(request: Request, topic_id: int, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM writing_topics WHERE id = ?", (topic_id,))
    topic = cursor.fetchone()
    conn.close()
    if not topic:
        raise HTTPException(status_code=404, detail="Topilmadi")
    return templates.TemplateResponse(request, "writing_detail.html", {"topic": topic})


@app.get("/admin/delete-writing/{topic_id}")
async def delete_writing(topic_id: int, username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")
    conn = sqlite3.connect("cefr_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM writing_topics WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()
    return HTMLResponse(content="<script>alert('O\\'chirildi!'); window.location.href='/writing';</script>")


class WritingCheckRequest(BaseModel):
    essay_text: str
    level: str = "B2"


@app.post("/check-writing")
async def check_writing(req: WritingCheckRequest):
    try:
        prompt = f"CEFR Writing ekspertisiz. Esseni tahlil qiling va o'zbek tilida batafsil baho bering:\n{req.essay_text}"
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
                                                  temperature=0.4)
        return {"feedback": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 4. SPEAKING ---
@app.post("/admin/add-speaking-topic")
async def add_speaking_topic(title: str = Form(...), level: str = Form(...),
                             username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")
    conn = sqlite3.connect("cefr_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO speaking_topics (title, level) VALUES (?, ?)", (title, level))
    conn.commit()
    conn.close()
    return HTMLResponse(content="<script>alert('Speaking qo\\'shildi!'); window.location.href='/admin';</script>")


@app.get("/speaking", response_class=HTMLResponse)
async def speaking_page(request: Request, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT level FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()
    user_level = user_row["level"] if user_row else "B2"
    cursor.execute("SELECT * FROM speaking_topics WHERE level = ?", (user_level,))
    topics = cursor.fetchall()
    if not topics:
        cursor.execute("SELECT * FROM speaking_topics")
        topics = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request, "speaking.html", {"topics": topics, "user_level": user_level})


@app.get("/speaking/{topic_id}", response_class=HTMLResponse)
async def speaking_detail(request: Request, topic_id: int, username: str = Depends(get_current_user_cookie)):
    conn = sqlite3.connect("cefr_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM speaking_topics WHERE id = ?", (topic_id,))
    topic = cursor.fetchone()
    conn.close()
    if not topic:
        raise HTTPException(status_code=404, detail="Topilmadi")
    return templates.TemplateResponse(request, "speaking_detail.html", {"topic": topic})


@app.get("/admin/delete-speaking/{topic_id}")
async def delete_speaking(topic_id: int, username: str = Depends(get_current_user_cookie)):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")
    conn = sqlite3.connect("cefr_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM speaking_topics WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()
    return HTMLResponse(content="<script>alert('O\\'chirildi!'); window.location.href='/speaking';</script>")


class SpeakingCheckRequest(BaseModel):
    transcript: str


@app.post("/check-speaking")
async def check_speaking(req: SpeakingCheckRequest, username: str = Depends(get_current_user_cookie)):
    try:
        prompt = f"CEFR Speaking ekspertisiz. Transkriptni tahlil qiling va maslahat bering:\n{req.transcript}"
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
                                                  temperature=0.4)
        return {"feedback": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...), username: str = Depends(get_current_user_cookie)):
    try:
        audio_path = f"static/{file.filename}"
        with open(audio_path, "wb") as buffer:
            buffer.write(await file.read())

        with open(audio_path, "rb") as audio_file:
            transcript_response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

        if os.path.exists(audio_path):
            os.remove(audio_path)

        return {"transcript": transcript_response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))