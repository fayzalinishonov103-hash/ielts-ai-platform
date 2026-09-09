import os, json, sqlite3
from fastapi import FastAPI, Request, Form, HTTPException, Cookie, Depends, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
from typing import Optional



app = FastAPI(title="CEFR AI Platformasi")
templates = Jinja2Templates(directory="templates")

# Statik papkani ochish va ulash
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

MY_ADMIN_USERNAME = "nishonov_273"


def render(request: Request, name: str, context: dict = None):
    context = context or {}
    context["request"] = request
    return HTMLResponse(content=templates.env.get_template(name).render(context))


def get_db():
    conn = sqlite3.connect("cefr_database.db", timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def db_exec(query, params=(), fetchone=False, fetchall=False, commit=False):
    with get_db() as conn:
        c = conn.cursor()
        c.execute(query, params)
        res = c.fetchone() if fetchone else (c.fetchall() if fetchall else None)
        if commit:
            conn.commit()
        return res


def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                username TEXT UNIQUE,
                password TEXT,
                university TEXT,
                faculty TEXT,
                course TEXT,
                specialty TEXT,
                birth_date TEXT,
                address TEXT,
                level TEXT DEFAULT 'B2',
                goal TEXT,
                target_level TEXT,
                obstacle TEXT
            )
        """)
        c.execute("CREATE TABLE IF NOT EXISTS reading (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, passage_text TEXT, question TEXT, correct_answer TEXT, level TEXT DEFAULT 'B2')")
        c.execute("CREATE TABLE IF NOT EXISTS listening (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, audio_text TEXT, question TEXT, correct_answer TEXT, level TEXT DEFAULT 'B2')")
        c.execute("CREATE TABLE IF NOT EXISTS writing_topics (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, prompt_text TEXT, level TEXT DEFAULT 'B2')")
        c.execute("CREATE TABLE IF NOT EXISTS speaking_topics (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, level TEXT DEFAULT 'B2')")
        conn.commit()

    for t in ["reading", "listening", "writing_topics", "speaking_topics"]:
        cols = [col[1] for col in db_exec(f"PRAGMA table_info({t})", fetchall=True)]
        if "level" not in cols:
            try:
                db_exec(f"ALTER TABLE {t} ADD COLUMN level TEXT DEFAULT 'B2'", commit=True)
            except:
                pass

    user_cols = [col[1] for col in db_exec("PRAGMA table_info(users)", fetchall=True)]
    for col_name in ["level", "goal", "target_level", "obstacle"]:
        if col_name not in user_cols:
            try:
                db_exec(f"ALTER TABLE users ADD COLUMN {col_name} TEXT", commit=True)
            except:
                pass

init_db()


async def get_current_user_cookie(username: Optional[str] = Cookie(None)):
    if not username:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    return username


def verify_admin(username: str):
    if username != MY_ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Ruxsat etilmagan")


# --- AUTH & GENERAL ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return render(request, "index.html")


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return render(request, "register.html")


@app.post("/register")
async def register_user(
    name: str = Form(...), username: str = Form(...), password: str = Form(...),
    birth_date: str = Form(...), address: str = Form(...),
    education_type: Optional[str] = Form("universitet"), university: Optional[str] = Form(None),
    faculty: Optional[str] = Form(None), course: Optional[str] = Form(None),
    specialty: Optional[str] = Form(None), level: str = Form(...)
):
    try:
        db_exec(
            "INSERT INTO users (name, username, password, university, faculty, course, specialty, birth_date, address, level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, username, password, university or "Ko'rsatilmagan", faculty or education_type.capitalize(), course or "", specialty or "Ko'rsatilmagan", birth_date, address, level),
            commit=True
        )
        return RedirectResponse(url="/login", status_code=303)
    except:
        return RedirectResponse(url="/register", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return render(request, "login.html")


@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    user = db_exec("SELECT * FROM users WHERE username = ? AND password = ?", (username, password), fetchone=True)
    if user:
        target_url = "/admin" if username == MY_ADMIN_USERNAME else ("/dashboard" if user["goal"] else "/onboarding")
        resp = RedirectResponse(url=target_url, status_code=303)
        resp.set_cookie(key="username", value=user["username"])
        return resp
    return RedirectResponse(url="/login", status_code=303)


@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(key="username")
    return resp


# --- ONBOARDING ROUTES ---
@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_get(request: Request, username: str = Depends(get_current_user_cookie)):
    return render(request, "onboarding.html")


@app.post("/save-onboarding")
async def save_onboarding(
    request: Request,
    goal: str = Form(...),
    current_level: str = Form(...),
    target_level: str = Form(...),
    obstacle: str = Form(...),
    username: str = Depends(get_current_user_cookie)
):
    db_exec(
        "UPDATE users SET level = ?, goal = ?, target_level = ?, obstacle = ? WHERE username = ?",
        (current_level, goal, target_level, obstacle, username),
        commit=True
    )
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, username: str = Depends(get_current_user_cookie)):
    user = db_exec("SELECT * FROM users WHERE username = ?", (username,), fetchone=True)
    if not user or not user["goal"]:
        return RedirectResponse(url="/onboarding", status_code=303)

    counts = [db_exec(f"SELECT COUNT(*) FROM {tbl}", fetchone=True)[0] for tbl in ["reading", "listening", "writing_topics", "speaking_topics"]]
    return render(request, "profile.html", {"user": user, "total_tasks": sum(counts)})


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, username: str = Depends(get_current_user_cookie)):
    user = db_exec("SELECT * FROM users WHERE username = ?", (username,), fetchone=True)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    counts = [db_exec(f"SELECT COUNT(*) FROM {tbl}", fetchone=True)[0] for tbl in ["reading", "listening", "writing_topics", "speaking_topics"]]
    user_info = {**dict(user), "total_tasks": sum(counts), "reading_count": counts[0], "listening_count": counts[1], "writing_count": counts[2], "speaking_count": counts[3]}
    return render(request, "profile.html", {"user": user_info})


@app.post("/update-level")
async def update_user_level(level: str = Form(...), username: str = Depends(get_current_user_cookie)):
    if level not in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        raise HTTPException(status_code=400)
    db_exec("UPDATE users SET level = ? WHERE username = ?", (level, username), commit=True)
    return RedirectResponse(url="/reading", status_code=303)


# --- ADMIN PANEL ROUTES ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    total_users = db_exec("SELECT COUNT(*) FROM users", fetchone=True)[0]
    total_readings = db_exec("SELECT COUNT(*) FROM reading", fetchone=True)[0]
    total_listenings = db_exec("SELECT COUNT(*) FROM listening", fetchone=True)[0]
    total_writings = db_exec("SELECT COUNT(*) FROM writing_topics", fetchone=True)[0]
    total_speakings = db_exec("SELECT COUNT(*) FROM speaking_topics", fetchone=True)[0]

    return render(request, "admin.html", {
        "total_users": total_users,
        "total_readings": total_readings,
        "total_listenings": total_listenings,
        "total_writings": total_writings,
        "total_speakings": total_speakings
    })


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    users = db_exec("SELECT * FROM users", fetchall=True)
    return render(request, "admin.html", {"active_tab": "users", "users": users})


@app.get("/admin/analytics", response_class=HTMLResponse)
async def admin_analytics_page(request: Request, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    stats = {
        "users": db_exec("SELECT COUNT(*) FROM users", fetchone=True)[0],
        "reading": db_exec("SELECT COUNT(*) FROM reading", fetchone=True)[0],
        "listening": db_exec("SELECT COUNT(*) FROM listening", fetchone=True)[0],
        "writing": db_exec("SELECT COUNT(*) FROM writing_topics", fetchone=True)[0],
        "speaking": db_exec("SELECT COUNT(*) FROM speaking_topics", fetchone=True)[0],
    }
    return render(request, "admin.html", {"active_tab": "analytics", "stats": stats})


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    return render(request, "admin.html", {"active_tab": "settings"})


# --- 1. READING ---
@app.post("/admin/add-reading-ai")
async def add_reading_ai(title: str = Form(...), passage_text: str = Form(...), level: str = Form(...), username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    prompt = f'Matn asosida 1 ta savol va to\'g\'ri javob tuz. Matn: "{passage_text}" JSON: {{"question": "...", "correct_answer": "..."}}'
    ai_data = json.loads(client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.3, response_format={"type": "json_object"}).choices[0].message.content.strip())
    db_exec("INSERT INTO reading (title, passage_text, question, correct_answer, level) VALUES (?, ?, ?, ?, ?)", (title, passage_text, ai_data["question"], ai_data["correct_answer"], level), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/reading", response_class=HTMLResponse)
async def reading_page(request: Request, username: str = Depends(get_current_user_cookie)):
    user_level = db_exec("SELECT level FROM users WHERE username = ?", (username,), fetchone=True)
    lvl = user_level["level"] if user_level and user_level["level"] else "B2"
    items = db_exec("SELECT * FROM reading WHERE level = ?", (lvl,), fetchall=True) or db_exec("SELECT * FROM reading", fetchall=True)
    return render(request, "reading.html", {"items": items, "user_level": lvl})


@app.get("/reading/{item_id}", response_class=HTMLResponse)
async def reading_detail(request: Request, item_id: int, username: str = Depends(get_current_user_cookie)):
    item = db_exec("SELECT * FROM reading WHERE id = ?", (item_id,), fetchone=True)
    if not item:
        raise HTTPException(status_code=404)
    return render(request, "reading_detail.html", {"item": item})


class ReadingCheckRequest(BaseModel):
    item_id: int
    user_answer: str


@app.post("/api/check-reading")
async def check_reading_answer(req: ReadingCheckRequest):
    item = db_exec("SELECT question, correct_answer FROM reading WHERE id = ?", (req.item_id,), fetchone=True)
    if not item:
        raise HTTPException(status_code=404)
    try:
        prompt = f'Savol: "{item["question"]}" To\'g\'ri: "{item["correct_answer"]}" Javob: "{req.user_answer}". JSON: {{"is_correct": true/false, "comment": "..."}}'
        res = json.loads(client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.1, response_format={"type": "json_object"}).choices[0].message.content.strip())
        return {"is_correct": res.get("is_correct", False), "comment": res.get("comment", "")}
    except:
        return {"is_correct": req.user_answer.strip().lower() == item["correct_answer"].strip().lower(), "comment": ""}


@app.get("/admin/delete-reading/{item_id}")
async def delete_reading(item_id: int, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    db_exec("DELETE FROM reading WHERE id = ?", (item_id,), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


# --- 2. LISTENING ---
@app.post("/admin/add-listening-ai")
async def add_listening_ai(title: str = Form(...), audio_text: str = Form(...), level: str = Form(...), username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    prompt = f'Audio matn asosida 1 ta savol va to\'g\'ri javob tuz. Matn: "{audio_text}" JSON: {{"question": "...", "correct_answer": "..."}}'
    ai_data = json.loads(client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.3, response_format={"type": "json_object"}).choices[0].message.content.strip())
    db_exec("INSERT INTO listening (title, audio_text, question, correct_answer, level) VALUES (?, ?, ?, ?, ?)", (title, audio_text, ai_data["question"], ai_data["correct_answer"], level), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/listening", response_class=HTMLResponse)
async def listening_page(request: Request, username: str = Depends(get_current_user_cookie)):
    user_level = db_exec("SELECT level FROM users WHERE username = ?", (username,), fetchone=True)
    lvl = user_level["level"] if user_level else "B2"
    items = db_exec("SELECT * FROM listening WHERE level = ?", (lvl,), fetchall=True) or db_exec("SELECT * FROM listening", fetchall=True)
    return render(request, "listening.html", {"items": items, "user_level": lvl})


@app.get("/listening/{item_id}", response_class=HTMLResponse)
async def listening_detail(request: Request, item_id: int, username: str = Depends(get_current_user_cookie)):
    item = db_exec("SELECT * FROM listening WHERE id = ?", (item_id,), fetchone=True)
    if not item:
        raise HTTPException(status_code=404)
    return render(request, "listening_detail.html", {"item": item})


@app.get("/admin/delete-listening/{item_id}")
async def delete_listening(item_id: int, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    db_exec("DELETE FROM listening WHERE id = ?", (item_id,), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


class ListeningCheckRequest(BaseModel):
    item_id: int
    user_answer: str


@app.post("/api/check-listening")
async def check_listening_answer(req: ListeningCheckRequest):
    item = db_exec("SELECT question, correct_answer FROM listening WHERE id = ?", (req.item_id,), fetchone=True)
    if not item:
        raise HTTPException(status_code=404)
    try:
        prompt = f'Savol: "{item["question"]}" To\'g\'ri: "{item["correct_answer"]}" Javob: "{req.user_answer}". JSON: {{"is_correct": true/false, "comment": "..."}}'
        res = json.loads(client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.1, response_format={"type": "json_object"}).choices[0].message.content.strip())
        return {"is_correct": res.get("is_correct", False), "comment": res.get("comment", "")}
    except:
        return {"is_correct": req.user_answer.strip().lower() == item["correct_answer"].strip().lower(), "comment": ""}


@app.post("/api/text-to-speech")
async def text_to_speech(data: dict):
    path = "static/speech.mp3"
    client.audio.speech.create(model="tts-1", voice="alloy", input=data.get("text", "")).stream_to_file(path)
    return {"audio_url": f"/{path}"}


# --- 3. WRITING ---
@app.post("/admin/add-writing-ai")
async def add_writing_ai(title: str = Form(...), level: str = Form(...), username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    prompt = f"Write IELTS writing prompt for title: '{title}'. Level: {level}. JSON: {{\"prompt_text\": \"...\"}}"
    ai_data = json.loads(client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.3, response_format={"type": "json_object"}).choices[0].message.content.strip())
    db_exec("INSERT INTO writing_topics (title, prompt_text, level) VALUES (?, ?, ?)", (title, ai_data.get("prompt_text", title), level), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/writing", response_class=HTMLResponse)
async def writing_page(request: Request, username: str = Depends(get_current_user_cookie)):
    user_level = db_exec("SELECT level FROM users WHERE username = ?", (username,), fetchone=True)
    lvl = user_level["level"] if user_level else "B2"
    topics = db_exec("SELECT * FROM writing_topics WHERE level = ?", (lvl,), fetchall=True) or db_exec("SELECT * FROM writing_topics", fetchall=True)
    return render(request, "writing.html", {"topics": topics, "user_level": lvl})


@app.get("/writing/{topic_id}", response_class=HTMLResponse)
async def writing_detail(request: Request, topic_id: int, username: str = Depends(get_current_user_cookie)):
    topic = db_exec("SELECT * FROM writing_topics WHERE id = ?", (topic_id,), fetchone=True)
    if not topic:
        raise HTTPException(status_code=404)
    return render(request, "writing_detail.html", {"topic": topic})


@app.get("/admin/delete-writing/{topic_id}")
async def delete_writing(topic_id: int, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    db_exec("DELETE FROM writing_topics WHERE id = ?", (topic_id,), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


class WritingCheckRequest(BaseModel):
    essay_text: str
    level: str = "B2"


@app.post("/check-writing")
async def check_writing(req: WritingCheckRequest):
    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": f"CEFR Writing ekspertisiz. Tahlil qiling:\n{req.essay_text}"}], temperature=0.4)
    return {"feedback": res.choices[0].message.content}


# --- 4. SPEAKING ---
@app.post("/admin/add-speaking-topic")
async def add_speaking_topic(title: str = Form(...), level: str = Form(...), username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    db_exec("INSERT INTO speaking_topics (title, level) VALUES (?, ?)", (title, level), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/speaking", response_class=HTMLResponse)
async def speaking_page(request: Request, username: str = Depends(get_current_user_cookie)):
    user_level = db_exec("SELECT level FROM users WHERE username = ?", (username,), fetchone=True)
    lvl = user_level["level"] if user_level else "B2"
    topics = db_exec("SELECT * FROM speaking_topics WHERE level = ?", (lvl,), fetchall=True) or db_exec("SELECT * FROM speaking_topics", fetchall=True)
    return render(request, "speaking.html", {"topics": topics, "user_level": lvl})


@app.get("/speaking/{topic_id}", response_class=HTMLResponse)
async def speaking_detail(request: Request, topic_id: int, username: str = Depends(get_current_user_cookie)):
    topic = db_exec("SELECT * FROM speaking_topics WHERE id = ?", (topic_id,), fetchone=True)
    if not topic:
        raise HTTPException(status_code=404)
    return render(request, "speaking_detail.html", {"topic": topic})


@app.get("/admin/delete-speaking/{topic_id}")
async def delete_speaking(topic_id: int, username: str = Depends(get_current_user_cookie)):
    verify_admin(username)
    db_exec("DELETE FROM speaking_topics WHERE id = ?", (topic_id,), commit=True)
    return RedirectResponse(url="/admin", status_code=303)


class SpeakingCheckRequest(BaseModel):
    transcript: str


@app.post("/check-speaking")
async def check_speaking(req: SpeakingCheckRequest, username: str = Depends(get_current_user_cookie)):
    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": f"CEFR Speaking tahlili:\n{req.transcript}"}], temperature=0.4)
    return {"feedback": res.choices[0].message.content}


@app.post("/api/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...), username: str = Depends(get_current_user_cookie)):
    path = f"static/{file.filename}"
    try:
        with open(path, "wb") as f:
            f.write(await file.read())
        with open(path, "rb") as f:
            text = client.audio.transcriptions.create(model="whisper-1", file=f).text
        return {"transcript": text}
    finally:
        if os.path.exists(path):
            os.remove(path)


# --- GENERAL AI HELPER ---
class AIHelperRequest(BaseModel):
    text_content: str
    module_type: str


@app.post("/api/ai-helper")
async def ai_helper(req: AIHelperRequest):
    prompt = f"Sen CEFR va IELTS ekspertisan. {req.module_type} uchun:\n1. 5-6 ta kalit so'z.\n2. 3 ta maslahat.\nMaterial: {req.text_content}"
    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.4)
    return {"ai_help": res.choices[0].message.content}