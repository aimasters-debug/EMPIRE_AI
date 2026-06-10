
import streamlit as st
import sqlite3
import hashlib
import secrets
import json
import os
import re
from datetime import datetime
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go

try:
    from groq import Groq
except Exception:
    Groq = None

try:
    import bcrypt
except Exception:
    bcrypt = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
except Exception:
    SimpleDocTemplate = None

APP_NAME = "EmpireOS AI"
DB_FILE = "empireos_ai.db"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
APP_ACCESS_PASSWORD = os.getenv("APP_ACCESS_PASSWORD", "")
groq_client = Groq(api_key=GROQ_API_KEY) if (Groq and GROQ_API_KEY) else None


def get_db():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            is_admin INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            profile_json TEXT NOT NULL,
            title TEXT,
            selected_business TEXT,
            empire_score INTEGER DEFAULT 0,
            risk_score INTEGER DEFAULT 0,
            startup_cost TEXT,
            income_estimate TEXT,
            full_report TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS progress_tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            plan_id INTEGER,
            task_title TEXT NOT NULL,
            task_type TEXT DEFAULT 'general',
            status TEXT DEFAULT 'pending',
            due_date TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS revenue_forecasts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            plan_id INTEGER,
            budget REAL DEFAULT 0,
            price_per_client REAL DEFAULT 0,
            monthly_clients INTEGER DEFAULT 0,
            monthly_cost REAL DEFAULT 0,
            forecast_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_scans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            profile_json TEXT NOT NULL,
            scan_report TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS v3_reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            module TEXT NOT NULL,
            title TEXT NOT NULL,
            input_json TEXT NOT NULL,
            report TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def hash_password(password):
    if bcrypt:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    salt = secrets.token_hex(16)
    iterations = 260000
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${pwd_hash}"


def verify_password(password, stored_hash):
    if stored_hash.startswith("$2") and bcrypt:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, pwd_hash = stored_hash.split("$", 3)
            new_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)).hex()
            return secrets.compare_digest(new_hash, pwd_hash)
        except Exception:
            return False
    return False


def register_user(username, password):
    init_db()
    username = username.strip()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    conn = get_db()
    cur = conn.cursor()
    try:
        is_admin = 1 if username.lower() in ["admin", "rai", "rai.azam221"] else 0
        cur.execute(
            "INSERT INTO users(username,password_hash,plan,is_admin,created_at) VALUES(?,?,?,?,?)",
            (username, hash_password(password), "admin" if is_admin else "free", is_admin, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()


def login_user(username, password):
    init_db()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE username=?", (username.strip(),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False, "Username not found."
    if not verify_password(password, row[0]):
        return False, "Wrong password."
    return True, "Login successful."


def get_user_plan(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT plan,is_admin FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return "free"
    return "admin" if row[1] else (row[0] or "free")


def save_plan(username, profile, title, selected_business, empire_score, risk_score, startup_cost, income_estimate, full_report):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO plans(username,profile_json,title,selected_business,empire_score,risk_score,startup_cost,income_estimate,full_report,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        username, json.dumps(profile, ensure_ascii=False), title, selected_business,
        int(empire_score or 0), int(risk_score or 0), startup_cost or "",
        income_estimate or "", full_report or "", datetime.now().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()


def get_user_plans(username, limit=50):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, profile_json, title, selected_business, empire_score, risk_score, startup_cost, income_estimate, full_report, created_at
        FROM plans WHERE username=? ORDER BY id DESC LIMIT ?
    """, (username, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_plan_by_id(plan_id, username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, profile_json, title, selected_business, empire_score, risk_score, startup_cost, income_estimate, full_report, created_at
        FROM plans WHERE id=? AND username=?
    """, (plan_id, username))
    row = cur.fetchone()
    conn.close()
    return row


def delete_plan(plan_id, username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM plans WHERE id=? AND username=?", (plan_id, username))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted > 0


def save_chat(username, role, message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO chats(username,role,message,created_at) VALUES(?,?,?,?)",
                (username, role, message, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def get_chats(username, limit=30):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT role,message,created_at FROM chats WHERE username=? ORDER BY id DESC LIMIT ?", (username, limit))
    rows = cur.fetchall()
    conn.close()
    return list(reversed(rows))


def admin_stats():
    conn = get_db()
    cur = conn.cursor()
    stats = {}
    for key, table in [("users","users"),("plans","plans"),("chats","chats"),("tasks","progress_tasks"),("scans","opportunity_scans"),("memory","user_memory"),("v3_reports","v3_reports")]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            stats[key] = cur.fetchone()[0]
        except Exception:
            stats[key] = 0
    cur.execute("SELECT username, COUNT(*) c FROM plans GROUP BY username ORDER BY c DESC LIMIT 10")
    stats["top_users"] = cur.fetchall()
    cur.execute("SELECT username,title,selected_business,empire_score,created_at FROM plans ORDER BY id DESC LIMIT 10")
    stats["recent"] = cur.fetchall()
    conn.close()
    return stats

# ============================================================
# V2 OPPORTUNITY LIBRARY
# Used by Opportunity Scanner and Empire Score Lab
# ============================================================
V2_OPPORTUNITY_LIBRARY = [
    {
        "name": "AI Automation Agency",
        "best_for": ["developer", "ai", "python", "software", "automation", "coding", "streamlit", "app", "web", "dashboard"],
        "startup_cost": "$100-$500",
        "time_to_income": "14-45 days",
        "difficulty": "Medium",
        "income": "$500-$5000/month",
        "platforms": ["Upwork", "Fiverr", "LinkedIn", "GitHub"],
    },
    {
        "name": "Painting + Wall Art Service",
        "best_for": ["painter", "paint", "painting", "art", "wall", "artist", "drawing", "design"],
        "startup_cost": "$50-$300",
        "time_to_income": "3-21 days",
        "difficulty": "Low",
        "income": "$200-$2000/month",
        "platforms": ["Facebook Marketplace", "Instagram", "WhatsApp", "Fiverr"],
    },
    {
        "name": "Online Tutoring + Worksheet Shop",
        "best_for": ["teacher", "teaching", "education", "english", "tutor", "school", "student"],
        "startup_cost": "$0-$200",
        "time_to_income": "7-30 days",
        "difficulty": "Low",
        "income": "$300-$3000/month",
        "platforms": ["Preply", "Facebook Groups", "YouTube", "Udemy"],
    },
    {
        "name": "Trading Education + Journal Templates",
        "best_for": ["trader", "trading", "forex", "crypto", "gold", "nasdaq", "stock", "market"],
        "startup_cost": "$0-$250",
        "time_to_income": "30-90 days",
        "difficulty": "Medium",
        "income": "$200-$3000/month",
        "platforms": ["TradingView", "YouTube", "Notion", "Google Sheets"],
    },
    {
        "name": "Local Digital Marketing Service",
        "best_for": ["marketing", "sales", "facebook", "social", "content", "ads", "canva"],
        "startup_cost": "$50-$400",
        "time_to_income": "7-45 days",
        "difficulty": "Medium",
        "income": "$300-$4000/month",
        "platforms": ["Facebook", "Instagram", "LinkedIn", "WhatsApp"],
    },
    {
        "name": "Email Management / Virtual Assistant Service",
        "best_for": ["computer", "email", "admin", "assistant", "english", "office", "support"],
        "startup_cost": "$0-$100",
        "time_to_income": "14-45 days",
        "difficulty": "Low",
        "income": "$250-$2500/month",
        "platforms": ["Upwork", "Fiverr", "LinkedIn", "Freelancer"],
    },
    {
        "name": "YouTube Automation / Short Video Content Service",
        "best_for": ["youtube", "video", "editing", "content", "canva", "social", "tiktok"],
        "startup_cost": "$0-$300",
        "time_to_income": "30-90 days",
        "difficulty": "Medium",
        "income": "$200-$4000/month",
        "platforms": ["YouTube Studio", "Instagram", "TikTok", "Fiverr"],
    },
    {
        "name": "Ecommerce Product Research + Store Setup",
        "best_for": ["ecommerce", "shopify", "amazon", "daraz", "product", "sales"],
        "startup_cost": "$200-$1000",
        "time_to_income": "30-120 days",
        "difficulty": "Medium",
        "income": "$300-$5000/month",
        "platforms": ["Shopify", "Daraz", "Amazon", "Facebook"],
    },
]

def parse_money(value, default=0.0):
    try:
        s = str(value or "").replace("$", "").replace(",", "").strip()
        nums = re.findall(r"\\d+(?:\\.\\d+)?", s)
        return float(nums[0]) if nums else float(default)
    except Exception:
        return float(default)

def save_task(username, plan_id, title, task_type="general", due_date="", notes=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO progress_tasks(username,plan_id,task_title,task_type,status,due_date,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?)
    """, (username, plan_id, title, task_type, "pending", due_date, notes, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def get_tasks(username, limit=200):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, plan_id, task_title, task_type, status, due_date, notes, created_at
        FROM progress_tasks WHERE username=? ORDER BY id DESC LIMIT ?
    """, (username, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def update_task_status(task_id, username, status):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE progress_tasks SET status=? WHERE id=? AND username=?", (status, task_id, username))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok

def delete_task(task_id, username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM progress_tasks WHERE id=? AND username=?", (task_id, username))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok

def save_opportunity_scan(username, profile, report):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO opportunity_scans(username,profile_json,scan_report,created_at) VALUES(?,?,?,?)",
                (username, json.dumps(profile, ensure_ascii=False), report, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def get_opportunity_scans(username, limit=20):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, profile_json, scan_report, created_at FROM opportunity_scans WHERE username=? ORDER BY id DESC LIMIT ?", (username, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def calculate_local_opportunities(profile):
    text = (str(profile.get("skills","")) + " " + str(profile.get("interests","")) + " " + str(profile.get("experience",""))).lower()
    budget = parse_money(profile.get("budget"), 100)
    results = []
    for item in V2_OPPORTUNITY_LIBRARY:
        score = 45
        for kw in item["best_for"]:
            if kw in text:
                score += 12
        if budget >= 500:
            score += 6
        elif budget >= 100:
            score += 3
        if profile.get("mode") == "Online" and any(x in item["platforms"] for x in ["Upwork", "Fiverr", "LinkedIn", "GitHub"]):
            score += 6
        if profile.get("risk_level") == "Low" and item["difficulty"] == "Low":
            score += 7
        score = max(1, min(99, score))
        results.append({**item, "score": score})
    return sorted(results, key=lambda x: x["score"], reverse=True)



# ============================================================
# EMPIREOS FULL PREMIUM INTELLIGENCE LAYER
# ============================================================

COUNTRY_INTELLIGENCE_DB = {
    "pakistan": {
        "currency": "PKR",
        "payment_methods": ["Easypaisa", "JazzCash", "Bank Transfer", "Raast", "Cash on Delivery"],
        "platforms": ["Daraz", "Rozee.pk", "Mustakbil", "OLX Pakistan", "Facebook Groups", "WhatsApp Business", "LinkedIn Pakistan"],
        "local_channels": ["WhatsApp marketing", "Facebook city groups", "Local shop visits", "School/academy networks", "Real estate/dealer networks"],
        "business_notes": "Pakistan is strong for low-cost services, education, digital marketing, ecommerce support, design, tutoring, AI tools for SMEs, and WhatsApp-based local selling.",
        "risk_notes": "Validate payment reliability, avoid heavy ad spend before proof, keep pricing affordable, and use written terms before starting client work."
    },
    "uae": {
        "currency": "AED",
        "payment_methods": ["Bank Transfer", "PayPal", "Stripe where available", "Cash", "Payment links"],
        "platforms": ["Dubizzle", "Naukrigulf", "Bayt", "LinkedIn UAE", "Facebook Groups UAE", "Instagram", "Upwork"],
        "local_channels": ["LinkedIn outreach", "Business communities", "Real estate networks", "Local service directories", "Instagram portfolio"],
        "business_notes": "UAE is strong for premium services, business support, real estate services, digital marketing, design, automation, and B2B packages.",
        "risk_notes": "Check licensing requirements, avoid unrealistic income claims, and position services professionally."
    },
    "usa": {
        "currency": "USD",
        "payment_methods": ["Stripe", "PayPal", "Bank Transfer", "Wise", "Cash App", "Venmo"],
        "platforms": ["Upwork", "Fiverr", "LinkedIn", "Thumbtack", "Craigslist", "Facebook Marketplace", "Google Business Profile"],
        "local_channels": ["Cold email", "LinkedIn outreach", "Google Maps lead lists", "Local business visits", "Niche communities"],
        "business_notes": "USA is strong for niche B2B services, automation, home services, consulting, education products, and productized services.",
        "risk_notes": "Competition is high; niche down, show proof, use clear contracts, and avoid broad generic offers."
    },
    "uk": {
        "currency": "GBP",
        "payment_methods": ["Stripe", "PayPal", "Bank Transfer", "Wise"],
        "platforms": ["PeoplePerHour", "Bark", "LinkedIn UK", "Gumtree", "Upwork", "Fiverr", "Facebook Groups UK"],
        "local_channels": ["Bark leads", "LinkedIn outreach", "Local community groups", "Google Maps outreach", "Portfolio website"],
        "business_notes": "UK works well for freelance services, tutoring, creative services, local services, and B2B support packages.",
        "risk_notes": "Build trust through reviews, portfolio, professional profiles, and clear service terms."
    },
    "india": {
        "currency": "INR",
        "payment_methods": ["UPI", "Bank Transfer", "Razorpay", "Paytm", "Cash"],
        "platforms": ["IndiaMART", "Justdial", "Urban Company", "LinkedIn India", "Internshala", "Fiverr", "Upwork"],
        "local_channels": ["WhatsApp communities", "LinkedIn", "Local directories", "Instagram reels", "College/school networks"],
        "business_notes": "India is strong for digital services, tutoring, tech, content, design, ecommerce support, and high-volume delivery.",
        "risk_notes": "Competition is intense; differentiate by niche, speed, proof, and clear pricing."
    },
    "global": {
        "currency": "USD",
        "payment_methods": ["PayPal", "Wise", "Stripe", "Bank Transfer"],
        "platforms": ["Upwork", "Fiverr", "LinkedIn", "Facebook Groups", "Instagram", "YouTube", "Product Hunt"],
        "local_channels": ["Online communities", "Cold outreach", "Freelance platforms", "Content marketing"],
        "business_notes": "Global strategy should focus on niche positioning, proof, portfolio, and consistent outreach.",
        "risk_notes": "Avoid fake guarantees, validate demand before spending, and use clear delivery terms."
    }
}

def normalize_country_name(country):
    c = str(country or "").strip().lower()
    if "pak" in c:
        return "pakistan"
    if "uae" in c or "emirates" in c or "dubai" in c:
        return "uae"
    if "usa" in c or "america" in c or "united states" in c:
        return "usa"
    if c in ["uk", "united kingdom", "england", "britain", "great britain"]:
        return "uk"
    if "india" in c:
        return "india"
    return c if c in COUNTRY_INTELLIGENCE_DB else "global"

def get_country_intelligence(profile):
    key = normalize_country_name(profile.get("country", "global"))
    return key, COUNTRY_INTELLIGENCE_DB.get(key, COUNTRY_INTELLIGENCE_DB["global"])

def skill_category(profile):
    text = (str(profile.get("skills","")) + " " + str(profile.get("interests","")) + " " + str(profile.get("experience","")) + " " + str(profile.get("goal",""))).lower()
    if any(x in text for x in ["paint", "painter", "art", "artist", "drawing", "wall", "mural"]):
        return "painting_art"
    if any(x in text for x in ["developer", "coding", "python", "ai", "software", "app", "web", "streamlit", "dashboard"]):
        return "ai_software"
    if any(x in text for x in ["teacher", "teaching", "education", "tutor", "school", "english", "student"]):
        return "education"
    if any(x in text for x in ["trader", "trading", "forex", "crypto", "gold", "nasdaq", "stock"]):
        return "trading_education"
    if any(x in text for x in ["marketing", "sales", "ads", "facebook", "instagram", "content"]):
        return "marketing_sales"
    if any(x in text for x in ["email", "admin", "assistant", "virtual assistant", "support"]):
        return "admin_va"
    return "general_service"

def dynamic_website_recommendations(profile):
    country_key, country = get_country_intelligence(profile)
    category = skill_category(profile)
    global_platforms = ["Fiverr", "Upwork", "LinkedIn", "Facebook Groups", "Instagram", "Canva", "Google Sheets", "Notion"]
    skill_platforms = {
        "painting_art": ["Facebook Marketplace", "Instagram", "Behance", "Pinterest", "WhatsApp Business", "Google Business Profile"],
        "ai_software": ["GitHub", "Hugging Face", "Replit", "Product Hunt", "Upwork", "Fiverr", "LinkedIn"],
        "education": ["Preply", "Superprof", "Udemy", "Teachable", "YouTube Studio", "Google Forms", "Facebook Groups"],
        "trading_education": ["TradingView", "BabyPips", "Investopedia", "Forex Factory", "Myfxbook", "YouTube Studio", "Google Sheets"],
        "marketing_sales": ["Meta Business Suite", "Canva", "LinkedIn", "Facebook Groups", "Instagram", "Google Business Profile"],
        "admin_va": ["Upwork", "Fiverr", "LinkedIn", "Freelancer", "Google Workspace", "Notion"],
        "general_service": ["Fiverr", "Upwork", "LinkedIn", "Facebook Groups", "Instagram", "WhatsApp Business"]
    }
    platforms = []
    for p in country.get("platforms", []) + skill_platforms.get(category, []) + global_platforms:
        if p not in platforms:
            platforms.append(p)
    return {"country_key": country_key, "country_data": country, "category": category, "platforms": platforms[:14]}


PLATFORM_URLS = {
    "Fiverr": "https://www.fiverr.com",
    "Upwork": "https://www.upwork.com",
    "LinkedIn": "https://www.linkedin.com",
    "GitHub": "https://github.com",
    "Facebook Groups": "https://www.facebook.com/groups",
    "Facebook Marketplace": "https://www.facebook.com/marketplace",
    "Facebook": "https://www.facebook.com",
    "Instagram": "https://www.instagram.com",
    "WhatsApp": "https://www.whatsapp.com",
    "WhatsApp Business": "https://business.whatsapp.com",
    "Behance": "https://www.behance.net",
    "Pinterest": "https://www.pinterest.com",
    "TradingView": "https://www.tradingview.com",
    "BabyPips": "https://www.babypips.com",
    "Investopedia": "https://www.investopedia.com",
    "Forex Factory": "https://www.forexfactory.com",
    "Myfxbook": "https://www.myfxbook.com",
    "YouTube": "https://www.youtube.com",
    "YouTube Studio": "https://studio.youtube.com",
    "Google Sheets": "https://sheets.google.com",
    "Google Forms": "https://forms.google.com",
    "Google Workspace": "https://workspace.google.com",
    "Google Business Profile": "https://www.google.com/business",
    "Notion": "https://www.notion.so",
    "Preply": "https://preply.com",
    "Superprof": "https://www.superprof.com",
    "Udemy": "https://www.udemy.com",
    "Teachable": "https://teachable.com",
    "Hugging Face": "https://huggingface.co",
    "Replit": "https://replit.com",
    "Product Hunt": "https://www.producthunt.com",
    "Freelancer": "https://www.freelancer.com",
    "Shopify": "https://www.shopify.com",
    "Amazon": "https://www.amazon.com",
    "Daraz": "https://www.daraz.pk",
    "TikTok": "https://www.tiktok.com",
    "Canva": "https://www.canva.com",
    "Meta Business Suite": "https://business.facebook.com",
    "Rozee.pk": "https://www.rozee.pk",
    "Mustakbil": "https://www.mustakbil.com",
    "OLX Pakistan": "https://www.olx.com.pk",
    "Dubizzle": "https://www.dubizzle.com",
    "Naukrigulf": "https://www.naukrigulf.com",
    "Bayt": "https://www.bayt.com",
    "PeoplePerHour": "https://www.peopleperhour.com",
    "Bark": "https://www.bark.com",
    "Gumtree": "https://www.gumtree.com",
    "IndiaMART": "https://www.indiamart.com",
    "Justdial": "https://www.justdial.com",
    "Urban Company": "https://www.urbancompany.com",
    "Internshala": "https://internshala.com",
}

PLATFORM_ICON_URLS = {
    "Fiverr": "https://www.google.com/s2/favicons?domain=fiverr.com&sz=64",
    "Upwork": "https://www.google.com/s2/favicons?domain=upwork.com&sz=64",
    "LinkedIn": "https://www.google.com/s2/favicons?domain=linkedin.com&sz=64",
    "GitHub": "https://www.google.com/s2/favicons?domain=github.com&sz=64",
    "Facebook Groups": "https://www.google.com/s2/favicons?domain=facebook.com&sz=64",
    "Facebook Marketplace": "https://www.google.com/s2/favicons?domain=facebook.com&sz=64",
    "Facebook": "https://www.google.com/s2/favicons?domain=facebook.com&sz=64",
    "Instagram": "https://www.google.com/s2/favicons?domain=instagram.com&sz=64",
    "WhatsApp": "https://www.google.com/s2/favicons?domain=whatsapp.com&sz=64",
    "WhatsApp Business": "https://www.google.com/s2/favicons?domain=whatsapp.com&sz=64",
    "Behance": "https://www.google.com/s2/favicons?domain=behance.net&sz=64",
    "Pinterest": "https://www.google.com/s2/favicons?domain=pinterest.com&sz=64",
    "TradingView": "https://www.google.com/s2/favicons?domain=tradingview.com&sz=64",
    "BabyPips": "https://www.google.com/s2/favicons?domain=babypips.com&sz=64",
    "Investopedia": "https://www.google.com/s2/favicons?domain=investopedia.com&sz=64",
    "Forex Factory": "https://www.google.com/s2/favicons?domain=forexfactory.com&sz=64",
    "Myfxbook": "https://www.google.com/s2/favicons?domain=myfxbook.com&sz=64",
    "YouTube": "https://www.google.com/s2/favicons?domain=youtube.com&sz=64",
    "YouTube Studio": "https://www.google.com/s2/favicons?domain=youtube.com&sz=64",
    "Google Sheets": "https://www.google.com/s2/favicons?domain=google.com&sz=64",
    "Google Forms": "https://www.google.com/s2/favicons?domain=google.com&sz=64",
    "Google Workspace": "https://www.google.com/s2/favicons?domain=google.com&sz=64",
    "Google Business Profile": "https://www.google.com/s2/favicons?domain=google.com&sz=64",
    "Notion": "https://www.google.com/s2/favicons?domain=notion.so&sz=64",
    "Preply": "https://www.google.com/s2/favicons?domain=preply.com&sz=64",
    "Superprof": "https://www.google.com/s2/favicons?domain=superprof.com&sz=64",
    "Udemy": "https://www.google.com/s2/favicons?domain=udemy.com&sz=64",
    "Teachable": "https://www.google.com/s2/favicons?domain=teachable.com&sz=64",
    "Hugging Face": "https://www.google.com/s2/favicons?domain=huggingface.co&sz=64",
    "Replit": "https://www.google.com/s2/favicons?domain=replit.com&sz=64",
    "Product Hunt": "https://www.google.com/s2/favicons?domain=producthunt.com&sz=64",
    "Freelancer": "https://www.google.com/s2/favicons?domain=freelancer.com&sz=64",
    "Shopify": "https://www.google.com/s2/favicons?domain=shopify.com&sz=64",
    "Amazon": "https://www.google.com/s2/favicons?domain=amazon.com&sz=64",
    "Daraz": "https://www.google.com/s2/favicons?domain=daraz.pk&sz=64",
    "TikTok": "https://www.google.com/s2/favicons?domain=tiktok.com&sz=64",
    "Canva": "https://www.google.com/s2/favicons?domain=canva.com&sz=64",
    "Meta Business Suite": "https://www.google.com/s2/favicons?domain=facebook.com&sz=64",
    "Rozee.pk": "https://www.google.com/s2/favicons?domain=rozee.pk&sz=64",
    "Mustakbil": "https://www.google.com/s2/favicons?domain=mustakbil.com&sz=64",
    "OLX Pakistan": "https://www.google.com/s2/favicons?domain=olx.com.pk&sz=64",
    "Dubizzle": "https://www.google.com/s2/favicons?domain=dubizzle.com&sz=64",
    "Naukrigulf": "https://www.google.com/s2/favicons?domain=naukrigulf.com&sz=64",
    "Bayt": "https://www.google.com/s2/favicons?domain=bayt.com&sz=64",
    "PeoplePerHour": "https://www.google.com/s2/favicons?domain=peopleperhour.com&sz=64",
    "Bark": "https://www.google.com/s2/favicons?domain=bark.com&sz=64",
    "Gumtree": "https://www.google.com/s2/favicons?domain=gumtree.com&sz=64",
    "IndiaMART": "https://www.google.com/s2/favicons?domain=indiamart.com&sz=64",
    "Justdial": "https://www.google.com/s2/favicons?domain=justdial.com&sz=64",
    "Urban Company": "https://www.google.com/s2/favicons?domain=urbancompany.com&sz=64",
    "Internshala": "https://www.google.com/s2/favicons?domain=internshala.com&sz=64",
}

def platform_card_markdown(platform):
    url = PLATFORM_URLS.get(platform, "")
    icon = PLATFORM_ICON_URLS.get(platform, "")
    if url and icon:
        return (
            f'<a href="{url}" target="_blank" style="text-decoration:none;">'
            f'<img src="{icon}" width="28" height="28" style="vertical-align:middle;border-radius:6px;margin-right:8px;">'
            f'<b>{platform}</b></a><br>'
            f'🌐 <a href="{url}" target="_blank">{url}</a><br>'
            f'How to use: Create profile, upload 3 samples, publish one clear package, contact prospects daily, and track responses.'
        )
    if url:
        return (
            f'🔗 <b>{platform}</b><br>'
            f'🌐 <a href="{url}" target="_blank">{url}</a><br>'
            f'How to use: Create profile, upload 3 samples, publish one clear package, contact prospects daily, and track responses.'
        )
    return f"<b>{platform}</b> — Create profile, upload 3 samples, publish one clear package, contact prospects daily, and track responses."


def dynamic_platform_links_text(profile):
    info = dynamic_website_recommendations(profile)
    country = info["country_data"]
    lines = [
        "## Dynamic Website Recommendations",
        "",
        f"**Country focus:** {info['country_key'].title()}",
        f"**Currency/payment context:** {country.get('currency')} | {', '.join(country.get('payment_methods', []))}",
        "",
        "### Recommended platforms and how to use them",
        "",
    ]

    for i, platform in enumerate(info["platforms"], 1):
        lines.append(f"### {i}. {platform}")
        lines.append(platform_card_markdown(platform))
        lines.append("")

    lines.append("### Local channels")
    for ch in country.get("local_channels", []):
        lines.append(f"- {ch}")
    lines.append("")
    lines.append(f"**Country note:** {country.get('business_notes')}")
    lines.append(f"**Risk note:** {country.get('risk_notes')}")
    return "\n".join(lines)

def country_specific_strategy_text(profile):
    key, data = get_country_intelligence(profile)
    return f"""
# Country-Specific Recommendations

Country focus: {key.title()}
Currency context: {data.get('currency')}
Payment methods: {', '.join(data.get('payment_methods', []))}

Best local channels:
{chr(10).join('- ' + x for x in data.get('local_channels', []))}

Local business note:
{data.get('business_notes')}

Local risk note:
{data.get('risk_notes')}
"""

def competitor_research_structure_text(profile, business="the business"):
    return f"""
# Competitor Research Structure

Business to research: {business}

Collect this data from 10 competitors:
- Offer, price, target customer, promise/result, proof/testimonials
- Weaknesses, response speed, content style, sales channel
- Guarantee/refund policy

SWOT:
- Strengths: What they do better.
- Weaknesses: Where they are slow, expensive, unclear, or poor quality.
- Opportunities: Gaps you can attack.
- Threats: Why customers might choose them.

Competitor monitoring:
- Check 5 competitors weekly.
- Track price, promise, testimonials, content, and objections.
- Improve your offer every 7 days.
"""

def local_market_validation_text(profile, business="the business"):
    return f"""
# Local Market Validation

Business to validate: {business}

7-day validation plan:
Day 1: Write one-line offer and list 30 possible customers.
Day 2: Contact 10 people and ask about their current problem.
Day 3: Contact 10 more people and offer a small sample/demo.
Day 4: Ask 5 people what price feels fair and record objections.
Day 5: Improve offer and create one proof sample.
Day 6: Post offer in 2 relevant groups/channels and message 20 prospects.
Day 7: Review replies. If at least 3 serious replies appear, continue. If not, change customer, offer, price, or channel.

Strong demand signs:
- People ask price quickly.
- People ask when you can start.
- People share specific pain.
- People compare you with another provider.

Weak demand signs:
- Nobody responds.
- Everyone says “later.”
- People praise but do not pay or book.
"""

def ai_followup_questions_text(profile):
    return """
# AI Follow-Up Questions

Ask these before final execution if more precision is needed:
1. Exact monthly income target?
2. Daily available hours?
3. Quick income or long-term brand?
4. Online, offline, or hybrid?
5. Existing proof/samples?
6. Strongest skill?
7. Biggest weakness?
8. Laptop and stable internet?
9. Which city/country first?
10. Ready to contact customers daily?
11. Budget you can risk without stress?
12. Result you can confidently deliver within 7 days?
"""

def multi_step_reasoning_text(profile, business="the business"):
    return f"""
# Multi-Step Reasoning Report

Step 1: User profile analysis
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Budget: {profile.get('budget')}
Country: {profile.get('country')}
Goal: {profile.get('goal')}

Step 2: Opportunity analysis
Match business with skills, budget, time, and risk.

Step 3: Market analysis
Identify urgent customer pain and where customers already spend time.

Step 4: Competitor analysis
Find direct/indirect competitors and look for weak proof, slow service, unclear pricing, or poor follow-up.

Step 5: Financial analysis
Estimate startup cost, first sale timeline, and minimum customers required.

Step 6: Risk analysis
Validate before spending; avoid paid ads until manual outreach converts.

Step 7: Recommendation logic
Choose the simplest offer that can get a paid response fastest.
"""

def automatic_execution_checklist_text(profile, business="the business"):
    return f"""
# Automatic Execution Checklist

## Day 1
[ ] Choose one customer type.
[ ] Write one-line offer.
[ ] Create business/profile name.
[ ] Create first proof sample.
[ ] Make simple price list.

## Day 2
[ ] Create/upgrade professional profile.
[ ] Upload first 3 samples.
[ ] Write cold message.

## Day 3
[ ] Contact 20 prospects.
[ ] Track responses in a sheet.
[ ] Save objections.

## Day 4
[ ] Follow up with all prospects.
[ ] Improve offer based on objections.

## Day 5
[ ] Contact 20 more prospects.
[ ] Post offer in 2 groups/channels.
[ ] Ask 5 people about pricing.

## Day 6
[ ] Create mini case study/demo.
[ ] Offer low-risk starter package.

## Day 7
[ ] Review leads, replies, objections, and conversion.
[ ] Decide: continue, adjust offer, change customer, or change channel.
"""

def auto_swot_analysis_text(profile, business="the business"):
    return f"""
# Auto SWOT Analysis

Business: {business}

Strengths:
- Uses user skills: {profile.get('skills')}
- Can start with budget: {profile.get('budget')}
- Can be tested with proof and outreach.

Weaknesses:
- May lack testimonials at the start.
- May need better portfolio/samples.
- Needs consistent outreach discipline.

Opportunities:
- Local and online customer acquisition.
- Productized packages.
- Repeat service or monthly support.
- Niche positioning based on country and skill.

Threats:
- Existing competitors with proof.
- Low-price competitors.
- Customer trust issues.
- Poor delivery or unclear pricing.
"""

def business_validation_score(profile, business=""):
    budget = parse_money(profile.get("budget"), 100)
    text = (str(profile.get("skills","")) + " " + str(profile.get("experience","")) + " " + str(profile.get("goal","")) + " " + str(business)).lower()
    skill = 75 + (8 if len(text) > 80 else 0)
    if any(x in text for x in ["client", "customer", "sales", "teaching", "painting", "developer", "trading", "marketing"]):
        skill += 8
    budget_score = 85 if budget >= 300 else 72 if budget >= 100 else 58
    proof_score = 70 if any(x in text for x in ["portfolio", "sample", "experience", "client", "teaching", "project"]) else 55
    market_score = 76 if profile.get("country") else 62
    execution_score = 82 if profile.get("daily_hours") in ["3 hours", "4-6 hours", "Full time"] else 68
    validation = int((skill + budget_score + proof_score + market_score + execution_score) / 5)
    risk = max(5, min(95, 100 - validation + 15))
    return {
        "Skill Fit": min(99, skill),
        "Budget Fit": min(99, budget_score),
        "Proof Readiness": min(99, proof_score),
        "Market Access": min(99, market_score),
        "Execution Capacity": min(99, execution_score),
        "Business Validation Score": min(99, validation),
        "Risk Score": risk,
    }

def opportunity_score_v3(profile):
    base = calculate_local_opportunities(profile)
    country_key, country = get_country_intelligence(profile)
    category = skill_category(profile)
    upgraded = []
    for item in base:
        score = item.get("score", 50)
        if category == "ai_software" and "AI" in item["name"]:
            score += 8
        if category == "painting_art" and "Painting" in item["name"]:
            score += 10
        if category == "education" and "Tutoring" in item["name"]:
            score += 10
        if category == "trading_education" and "Trading" in item["name"]:
            score += 10
        if country_key == "pakistan" and any(x in item["platforms"] for x in ["Facebook", "WhatsApp", "Daraz"]):
            score += 4
        upgraded.append({**item, "v3_score": max(1, min(99, score))})
    return sorted(upgraded, key=lambda x: x["v3_score"], reverse=True)

def full_premium_context_block(profile, business="the business"):
    validation = business_validation_score(profile, business)
    return f"""
{country_specific_strategy_text(profile)}

{dynamic_platform_links_text(profile)}

{competitor_research_structure_text(profile, business)}

{local_market_validation_text(profile, business)}

{ai_followup_questions_text(profile)}

{multi_step_reasoning_text(profile, business)}

{auto_swot_analysis_text(profile, business)}

# Business Validation Score
{json.dumps(validation, indent=2)}

{automatic_execution_checklist_text(profile, business)}
"""

def create_tasks_from_execution_checklist(username, plan_id, business_title):
    checklist = [
        ("Day 1", "Choose one customer type"),
        ("Day 1", "Write one-line offer"),
        ("Day 1", "Create first proof sample"),
        ("Day 1", "Make simple price list"),
        ("Day 2", "Create/upgrade professional profile"),
        ("Day 2", "Upload first 3 samples"),
        ("Day 3", "Contact 20 prospects"),
        ("Day 3", "Track responses in a sheet"),
        ("Day 4", "Follow up with all prospects"),
        ("Day 4", "Improve offer based on objections"),
        ("Day 5", "Contact 20 more prospects"),
        ("Day 5", "Post offer in 2 groups/channels"),
        ("Day 6", "Create mini case study/demo"),
        ("Day 6", "Offer low-risk starter package"),
        ("Day 7", "Review leads, replies, objections, and conversion"),
    ]
    existing = get_tasks(username, limit=500)
    if [t for t in existing if t[1] == plan_id]:
        return
    for due, title in checklist:
        save_task(username, plan_id, f"{title} — {business_title}", "premium_execution", due, "")

def premium_progress_dashboard(username):
    tasks = get_tasks(username, limit=500)
    total = len(tasks)
    done = len([t for t in tasks if str(t[4]).lower() == "done"])
    pending = total - done
    completion = int((done / total) * 100) if total else 0
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Premium Progress Tracking Dashboard")
    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Total Tasks", total)
    with c2: kpi_card("Done", done)
    with c3: kpi_card("Pending", pending)
    with c4: kpi_card("Completion %", f"{completion}%")
    if tasks:
        df = pd.DataFrame(tasks, columns=["ID", "Plan ID", "Task", "Type", "Status", "Due", "Notes", "Created"])
        st.dataframe(df[["Task", "Type", "Status", "Due", "Created"]].head(25), use_container_width=True, hide_index=True)
    else:
        st.info("No execution tasks yet. Generate a plan and create tasks from its checklist.")
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# END EMPIREOS FULL PREMIUM INTELLIGENCE LAYER
# ============================================================

def empire_answer_quality_rules():
    return """
EMPIREOS AI FULL PREMIUM ANSWER QUALITY RULES (MANDATORY):

You are EmpireOS AI, an elite practical business strategist, startup operator, market analyst, sales coach, investor analyst, and execution mentor.
Your job is to produce serious, useful, practical, investor-grade execution reports.

Every answer must be:
- Deep, authentic, realistic, and practical.
- Long-form when strategic; never generic.
- Personalized to country, budget, skills, experience, daily time, risk level, interests, and goal.
- Country-specific with local platforms, payment methods, customer channels, and risks.
- Dynamic with websites/platforms based on country + skill + business type.
- Validation-first before spending money.
- Competitor-aware with direct/indirect competitors, gaps, and differentiation.
- Actionable with exact steps, scripts, tools, pricing, timelines, checklists, mistakes, and measurable targets.
- Honest: never invent fake live facts, company names, statistics, guaranteed income, or certainty.

Mandatory structure for strategic answers:
1. Executive Summary
2. User Situation Diagnosis
3. Clarifying Follow-Up Questions if needed
4. Multi-Step Reasoning Summary
5. Best Recommendation
6. Country-Specific Recommendations
7. Dynamic Website / Platform Recommendations
8. Why This Fits / Why Other Options Are Weaker
9. Practical Business Model
10. Market / Customer Logic
11. Competitor Research Structure
12. Auto SWOT Analysis
13. Local Market Validation Plan
14. Business Validation Score
15. Offer + Pricing Packages
16. First Asset / Proof To Build
17. First 24 Hours Plan
18. 7-Day Validation Plan
19. 30-Day Launch Plan
20. 90-Day Growth Plan
21. Tools, Platforms, and Setup Steps
22. Client Acquisition / Sales System
23. Ready-to-Copy Scripts
24. Risk, Mistakes, and Failure Warnings
25. Tracking Metrics
26. Automatic Execution Checklist
27. Final Verdict

Style rules:
- Clear headings and bullet points.
- Realistic ranges, not fake exact numbers.
- Examples wherever possible.
- State assumptions clearly.
- For trading, no profit promises or guaranteed signals; focus on education, journaling, risk tools, and compliance.
- Explain like a mentor sitting beside a beginner.
"""

def opportunity_scan_prompt(profile, local_options):
    local_options_v3 = opportunity_score_v3(profile)
    options = "\n".join([
        f"- {o['name']}: V3 score {o.get('v3_score', o.get('score'))}/100, cost {o['startup_cost']}, time {o['time_to_income']}, platforms {', '.join(o['platforms'])}"
        for o in local_options_v3[:8]
    ])
    business = local_options_v3[0]["name"] if local_options_v3 else "best-fit opportunity"
    return f"""
Create a FULL PREMIUM Opportunity Scanner report.

{empire_answer_quality_rules()}

User profile:
Country: {profile.get('country')}
Budget: {profile.get('budget')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Daily time: {profile.get('daily_hours')}
Risk level: {profile.get('risk_level')}
Interests: {profile.get('interests')}
Goal: {profile.get('goal')}

V3 scoring options:
{options}

Premium intelligence block:
{full_premium_context_block(profile, business)}

Return a detailed execution-ready report with ranked opportunities, country strategy, dynamic websites, competitor research, local validation, validation score, 7-day plan, 30-day plan, first customer strategy, risks, and automatic checklist.
"""

def investor_prompt(profile, idea):
    return f"""
Act as a FULL PREMIUM investor analyst. Analyze this idea for a beginner founder.

{empire_answer_quality_rules()}

Founder profile:
Country: {profile.get('country')}
Budget: {profile.get('budget')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Risk level: {profile.get('risk_level')}

Business idea:
{idea}

Premium intelligence block:
{full_premium_context_block(profile, idea)}

Return investor summary, market demand assumptions, country context, competitors, Auto SWOT, revenue model, startup cost, break-even estimate, validation score, local validation plan, risks, MVP, pitch, checklist, and go/no-go verdict.
"""

def marketplace_guide_prompt(profile, business):
    links = platform_links_for_profile(profile)
    return f"""
Create a FULL PREMIUM marketplace launch guide for this business:
{business}

{empire_answer_quality_rules()}

User:
Country: {profile.get('country')}
Skills: {profile.get('skills')}
Budget: {profile.get('budget')}
Experience: {profile.get('experience')}

Dynamic platform links:
{links}

Premium intelligence block:
{full_premium_context_block(profile, business)}

For each relevant platform explain why it fits, account setup, profile title, description, samples, first message, daily action plan, mistakes, validation before spending money, and tracking method.
"""

def build_task_templates(plan_title):
    return [
        ("Day 1", f"Write one-line offer for {plan_title}"),
        ("Day 1", "Create business/profile name"),
        ("Day 1", "Create 3 proof samples"),
        ("Day 2", "Create price list with Starter, Standard, Premium"),
        ("Day 2", "Set up WhatsApp Business / LinkedIn / Fiverr profile"),
        ("Day 3", "Contact first 20 prospects"),
        ("Day 4", "Follow up with all prospects"),
        ("Day 5", "Create one case study/demo"),
        ("Week 2", "Contact 100 total prospects"),
        ("Week 3", "Close first paid customer or trial client"),
        ("Week 4", "Collect testimonial and improve portfolio"),
    ]

def save_default_tasks_for_plan(username, plan_id, plan_title):
    existing = get_tasks(username, limit=500)
    existing_for_plan = [t for t in existing if t[1] == plan_id]
    if existing_for_plan:
        return
    for due, title in build_task_templates(plan_title):
        save_task(username, plan_id, title, "launch", due, "")

def build_forecast_table(budget, price_per_client, monthly_clients, monthly_cost):
    budget = float(budget or 0)
    price_per_client = float(price_per_client or 0)
    monthly_clients = int(monthly_clients or 0)
    monthly_cost = float(monthly_cost or 0)
    rows = []
    total_profit = -budget
    for m in range(1, 13):
        clients = max(0, monthly_clients + (m // 3))
        revenue = clients * price_per_client
        cost = monthly_cost + (budget * 0.05 if m == 1 else 0)
        profit = revenue - cost
        total_profit += profit
        rows.append({
            "Month": f"Month {m}",
            "Clients": clients,
            "Revenue": revenue,
            "Cost": cost,
            "Profit": profit,
            "Cumulative Profit": total_profit
        })
    return pd.DataFrame(rows)

def save_revenue_forecast(username, plan_id, budget, price, clients, cost, df):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO revenue_forecasts(username,plan_id,budget,price_per_client,monthly_clients,monthly_cost,forecast_json,created_at)
        VALUES(?,?,?,?,?,?,?,?)
    """, (username, plan_id, float(budget or 0), float(price or 0), int(clients or 0), float(cost or 0), df.to_json(orient="records"), datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def v2_score_breakdown(profile):
    options = calculate_local_opportunities(profile)
    top = options[0] if options else {"score": 70}
    budget = parse_money(profile.get("budget"), 100)
    skill_fit = top["score"]
    affordability = 90 if budget >= 300 else 75 if budget >= 100 else 60
    demand = min(95, 65 + len(str(profile.get("skills",""))) // 4)
    scalability = 82 if profile.get("mode") in ["Online", "Hybrid"] else 68
    risk = 100 - int((skill_fit + affordability + demand + scalability) / 4)
    final = int((skill_fit + affordability + demand + scalability + (100-risk)) / 5)
    return {
        "Skill fit": skill_fit,
        "Startup affordability": affordability,
        "Market demand": demand,
        "Scalability": scalability,
        "Risk control": 100-risk,
        "Final Empire Score": final,
        "Risk Score": risk,
    }
# ============================================================
# END EMPIREOS AI V2 MODULES
# ============================================================

# ============================================================
# EMPIREOS AI V3 PREMIUM MODULES
# ============================================================

def save_v3_report(username, module, title, input_data, report):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO v3_reports(username,module,title,input_json,report,created_at) VALUES(?,?,?,?,?,?)",
                (username, module, title or module, json.dumps(input_data or {}, ensure_ascii=False), report or "", datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def save_memory(username, memory_type, title, content):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO user_memory(username,memory_type,title,content,created_at) VALUES(?,?,?,?,?)",
                (username, memory_type, title, content, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def get_memory(username, limit=30):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,memory_type,title,content,created_at FROM user_memory WHERE username=? ORDER BY id DESC LIMIT ?", (username, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_memory(memory_id, username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_memory WHERE id=? AND username=?", (memory_id, username))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok

def user_context_summary(username):
    plans = get_user_plans(username, limit=5)
    tasks = get_tasks(username, limit=20)
    memories = get_memory(username, limit=10)
    out = []
    if plans:
        out.append("Recent saved plans:")
        for r in plans:
            out.append(f"- {r[2]} | {r[3]} | score {r[4]} | created {r[9]}")
    if tasks:
        out.append("Recent tasks:")
        for t in tasks[:10]:
            out.append(f"- {t[2]} | status {t[4]} | due {t[5]}")
    if memories:
        out.append("Saved memories:")
        for m in memories:
            out.append(f"- {m[1]}: {m[2]} — {m[3][:220]}")
    return "\n".join(out) if out else "No saved context yet."

def competitor_intelligence_prompt(profile, business, country):
    return f"""
Create a FULL PREMIUM Competitor Intelligence Report.

{empire_answer_quality_rules()}

Profile:
Country: {profile.get('country') or country}
Budget: {profile.get('budget')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Goal: {profile.get('goal')}

Business: {business}
Target market: {country}

Premium intelligence block:
{full_premium_context_block(profile, business)}

Return competitor categories, direct/indirect competitor types, research questions, SWOT, pricing comparison, strengths, weaknesses, market gaps, differentiation, market opportunity score, first 10 customers strategy, positioning, pricing, red flags, monitoring strategy, and 30-day checklist.
Do not invent fake live company facts.
"""

def empire_roadmap_prompt(profile, current_income, target_income, timeframe, business):
    return f"""
Create a FULL PREMIUM Empire Roadmap Engine report.

{empire_answer_quality_rules()}

Profile:
Country: {profile.get('country')}
Budget: {profile.get('budget')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Daily time: {profile.get('daily_hours')}
Goal: {profile.get('goal')}

Business: {business}
Current monthly income: {current_income}
Target monthly income: {target_income}
Timeframe: {timeframe}

Premium intelligence block:
{full_premium_context_block(profile, business)}

Return diagnosis, target gap, country-specific roadmap, dynamic platforms, validation roadmap, competitor roadmap, month 1/2/3/6/12 plans, weekly milestones, daily routine, lead targets, revenue targets, skills, tracking fields, risks, and checklist.
"""

def business_blueprint_prompt(profile, business):
    return f"""
Create a FULL PREMIUM Business Blueprint for: {business}

{empire_answer_quality_rules()}

Profile:
Country: {profile.get('country')}
Budget: {profile.get('budget')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Goal: {profile.get('goal')}

Premium intelligence block:
{full_premium_context_block(profile, business)}

Return business concept, reasoning, country recommendations, dynamic platforms, local validation, competitor structure, Auto SWOT, validation score, name ideas, customer avatar, pain points, offer, packages, pricing, delivery, funnel, landing page copy, portfolio requirements, first 5 products/services, payment method, guarantee, 30-day checklist, 90-day checklist, business model canvas, and operating system.
"""

def client_acquisition_prompt(profile, business, target_customer):
    return f"""
Create a FULL PREMIUM Client Acquisition Engine plan.

{empire_answer_quality_rules()}

Profile:
Country: {profile.get('country')}
Budget: {profile.get('budget')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Daily time: {profile.get('daily_hours')}

Business: {business}
Target customer: {target_customer}

Premium intelligence block:
{full_premium_context_block(profile, business)}

Return best customer type, country-specific channels, online platforms, local sources, competitor customer source research, first 100 prospects strategy, daily outreach, WhatsApp, Facebook, LinkedIn, Fiverr/Upwork, local pitch, lead tracker columns, follow-up, conversion, validation, 7-day lead plan, 30-day client plan, checklist, and mistakes.
"""

def sales_script_prompt(profile, business, offer):
    return f"""
Generate FULL PREMIUM ready-to-copy sales scripts.

{empire_answer_quality_rules()}

Profile:
Country: {profile.get('country')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}

Business: {business}
Offer: {offer}

Premium intelligence block:
{full_premium_context_block(profile, business)}

Generate one-line pitch, localized pitch, WhatsApp cold message, WhatsApp follow-ups, cold email, email follow-up, LinkedIn message, Facebook post, phone script, local visit script, objections, closing script, proposal, testimonial request, referral request, 10 ad copies, lead tracker, daily checklist, and 7-day testing plan.
"""

def memory_prompt(username, user_question):
    context = user_context_summary(username)
    return f"""
You are EmpireOS AI with improved premium memory.

{empire_answer_quality_rules()}

Saved user context:
{context}

User question:
{user_question}

Use saved plans, tasks, chats, reports, and memories to continue from where the user left off.

Return what you remember, current diagnosis, best next move, country-specific suggestions if known, validation before spending, execution checklist for today, follow-up questions, and final recommendation.
"""

# ============================================================
# GLOBAL APP ACCESS PASSWORD LOCK
# ============================================================

def access_password_hash():
    pwd = str(os.getenv("APP_ACCESS_PASSWORD", APP_ACCESS_PASSWORD) or "").strip()
    if not pwd:
        return ""
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

def require_global_access():
    current_pwd = str(os.getenv("APP_ACCESS_PASSWORD", APP_ACCESS_PASSWORD) or "").strip()

    if not current_pwd:
        return True

    current_hash = access_password_hash()

    if st.session_state.get("access_hash") != current_hash:
        st.session_state["global_access_granted"] = False
        st.session_state.pop("logged_in", None)
        st.session_state.pop("username", None)

    if st.session_state.get("global_access_granted") is True and st.session_state.get("access_hash") == current_hash:
        return True

    st.markdown("""
    <div style="max-width:560px;margin:80px auto 24px auto;background:#ffffff;border:1px solid #E5E7EB;border-radius:24px;padding:34px;box-shadow:0 20px 60px rgba(15,23,42,.10);text-align:center;">
        <div style="font-size:48px;margin-bottom:12px;">🔐</div>
        <h1 style="margin:0 0 8px 0;color:#0F172A;font-size:32px;font-weight:900;">EmpireOS Access Locked</h1>
        <p style="color:#475569;font-size:15px;margin:0;">Enter the private access password to open this tool.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("global_access_password_form", clear_on_submit=False):
        access_password = st.text_input("Access Password", type="password", placeholder="Enter access password")
        submit_access = st.form_submit_button("Unlock EmpireOS", use_container_width=True)

    if submit_access:
        if secrets.compare_digest(access_password.strip(), current_pwd):
            st.session_state["global_access_granted"] = True
            st.session_state["access_hash"] = current_hash
            st.success("Access granted.")
            st.rerun()
        else:
            st.error("Wrong access password.")

    st.stop()

def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
    :root{
        --blue:#2563EB;
        --blue2:#1D4ED8;
        --navy:#071B37;
        --navy2:#031126;
        --text:#0F172A;
        --muted:#64748B;
        --line:#E5EAF3;
        --soft:#F8FAFC;
        --card:#FFFFFF;
    }
    *{font-family:Inter,Arial,sans-serif!important;box-sizing:border-box!important;}
    html,body,.stApp,[data-testid="stAppViewContainer"]{
        background:#F8FAFC!important;color:var(--text)!important;
    }
    [data-testid="stHeader"]{background:transparent!important;}
    .block-container{
        max-width:1500px!important;
        padding:1.15rem 1.55rem 2rem!important;
    }
    h1,h2,h3,h4,h5,h6,p,span,div,label,small,.stMarkdown,.stMarkdown *{
        color:var(--text)!important;
    }

    /* sidebar */
    section[data-testid="stSidebar"]{
        width:292px!important;
        min-width:292px!important;
        background:linear-gradient(180deg,#061A36 0%,#031126 100%)!important;
        border-right:1px solid rgba(255,255,255,.08)!important;
        box-shadow:12px 0 35px rgba(15,23,42,.10)!important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"]{
        padding:1.05rem .85rem 1rem!important;
    }
    section[data-testid="stSidebar"] *{
        color:#FFFFFF!important;
        -webkit-text-fill-color:#FFFFFF!important;
    }
    .side-brand{
        display:flex;align-items:center;gap:12px;margin:2px 4px 18px 4px;padding:2px 0 8px;
    }
    .side-logo{
        width:44px;height:44px;border-radius:10px;
        display:grid;place-items:center;background:#123CFF;color:#fff;font-size:22px;
        box-shadow:0 10px 24px rgba(37,99,235,.32);
    }
    .side-title{font-size:1.2rem;font-weight:900;line-height:1.05;color:#fff!important;}
    .side-user{font-size:.76rem;color:#DCEAFE!important;-webkit-text-fill-color:#DCEAFE!important;margin-top:5px;}
    .side-divider{height:1px;background:rgba(255,255,255,.10);margin:15px 0!important;}
    section[data-testid="stSidebar"] .stButton{margin:.15rem 0!important;}
    section[data-testid="stSidebar"] .stButton>button{
        width:100%!important;
        justify-content:flex-start!important;
        text-align:left!important;
        min-height:40px!important;height:40px!important;
        padding:0 14px!important;
        border-radius:8px!important;
        background:linear-gradient(180deg,#0E4EC0 0%,#083B8D 100%)!important;
        border:1px solid rgba(118,168,255,.18)!important;
        color:#fff!important;
        -webkit-text-fill-color:#fff!important;
        font-weight:650!important;
        font-size:.92rem!important;
        box-shadow:none!important;
    }
    section[data-testid="stSidebar"] .stButton>button:hover{
        background:linear-gradient(180deg,#2563EB 0%,#1D4ED8 100%)!important;
        border-color:rgba(255,255,255,.22)!important;
        transform:translateY(-1px);
    }
    section[data-testid="stSidebar"] .stButton>button[kind="primary"]{
        background:linear-gradient(180deg,#2F70FF 0%,#1557E8 100%)!important;
    }
    .logout-gap{height:22px;}

    /* dashboard */
    .dash-wrap{width:100%;}
    .hero{
        background:var(--card)!important;
        border:1px solid var(--line)!important;
        border-radius:15px!important;
        padding:24px 28px!important;
        margin:0 0 18px!important;
        box-shadow:0 10px 26px rgba(15,23,42,.045)!important;
        position:relative;
    }
    .hero-topline{
        position:absolute;right:24px;top:22px;display:flex;gap:10px;align-items:center;
        font-size:.78rem;font-weight:800;color:#0F172A!important;
    }
    .status-pill{
        display:inline-flex;align-items:center;gap:8px;
        border:1px solid var(--line);border-radius:12px;padding:9px 14px;background:#fff;
        box-shadow:0 4px 14px rgba(15,23,42,.04);
    }
    .status-dot{width:8px;height:8px;border-radius:999px;background:#10B981;display:inline-block;}
    .title{font-size:2rem!important;font-weight:950!important;line-height:1.05!important;letter-spacing:-.035em!important;margin:0!important;color:#050B18!important;}
    .subtitle{font-size:.98rem!important;color:#334155!important;margin-top:10px!important;line-height:1.45!important;max-width:850px;}

    .kpi{
        background:#fff!important;
        border:1px solid var(--line)!important;
        border-radius:12px!important;
        padding:18px 20px!important;
        min-height:116px!important;
        display:flex!important;
        align-items:center!important;
        gap:18px!important;
        box-shadow:0 10px 24px rgba(15,23,42,.045)!important;
    }
    .kpi-icon{
        width:56px;height:56px;border-radius:18px;background:#EFF6FF;
        display:grid;place-items:center;color:#2563EB!important;
        -webkit-text-fill-color:#2563EB!important;font-size:27px;font-weight:900;
        border:1px solid #E3EDFF;
    }
    .kpi-label{
        font-size:.78rem!important;color:#1E2A44!important;font-weight:900!important;text-transform:uppercase!important;letter-spacing:.015em!important;
    }
    .kpi-value{
        font-size:2rem!important;font-weight:950!important;color:#2563EB!important;
        -webkit-text-fill-color:#2563EB!important;margin-top:5px!important;line-height:1!important;
    }
    .panel-card{
        background:#fff!important;border:1px solid var(--line)!important;border-radius:14px!important;
        padding:20px!important;margin:0!important;box-shadow:0 10px 24px rgba(15,23,42,.045)!important;
    }
    .card{background:#fff!important;border:1px solid var(--line)!important;border-radius:14px!important;padding:20px!important;margin:12px 0!important;box-shadow:0 10px 24px rgba(15,23,42,.045)!important;}
    .panel-title{display:flex;align-items:center;gap:10px;font-size:1.1rem;font-weight:900;color:#0F172A!important;margin:0 0 14px!important;}
    .panel-icon{width:26px;height:26px;display:grid;place-items:center;border-radius:8px;background:#EFF6FF;color:#2563EB!important;-webkit-text-fill-color:#2563EB!important;}
    .stDataFrame{border-radius:12px!important;overflow:hidden!important;border:1px solid #EDF1F7!important;}
    .stDataFrame div{font-size:.86rem!important;}
    .module-grid{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:12px;margin-top:10px;}
    .module-pill{
        min-height:43px;border-radius:11px;border:1px solid #D9E7FF;background:#F8FBFF;
        color:#1D4ED8!important;-webkit-text-fill-color:#1D4ED8!important;
        display:flex;align-items:center;justify-content:center;gap:8px;font-weight:850;font-size:.84rem;
    }
    .module-pill .mi{font-size:17px;color:#2563EB!important;-webkit-text-fill-color:#2563EB!important;}
    .view-link{font-weight:800;color:#1D4ED8!important;-webkit-text-fill-color:#1D4ED8!important;font-size:.86rem;margin-top:10px;}

    /* forms/buttons globally */
    .stButton>button,.stDownloadButton>button,button,[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-secondary"]{
        background:#2563EB!important;color:#FFF!important;-webkit-text-fill-color:#FFF!important;
        border:1px solid #1D4ED8!important;border-radius:10px!important;font-weight:850!important;
        opacity:1!important;box-shadow:none!important;
    }
    .stButton>button *,.stDownloadButton>button *,button *{color:#FFF!important;-webkit-text-fill-color:#FFF!important;}
    input,textarea,[data-baseweb="select"] div{
        background:#FFF!important;color:#000!important;-webkit-text-fill-color:#000!important;border-color:#D1D5DB!important;
    }
    .stTabs [data-baseweb="tab-list"]{background:#FFF!important;border:1px solid #D1D5DB!important;border-radius:12px!important;padding:5px!important;}
    .stTabs [data-baseweb="tab"]{background:#2563EB!important;color:#FFF!important;-webkit-text-fill-color:#FFF!important;border-radius:10px!important;margin:2px!important;font-weight:900!important;opacity:1!important;}
    .stTabs [data-baseweb="tab"] *{color:#FFF!important;-webkit-text-fill-color:#FFF!important;}
    table,td,th,tr,thead,tbody{background:#FFF!important;color:#000!important;}
    @media(max-width:1100px){
        .module-grid{grid-template-columns:repeat(3,1fr);}
        section[data-testid="stSidebar"]{width:260px!important;min-width:260px!important;}
    }
    
    .login-shell{
        display:grid!important;
        grid-template-columns:1.1fr .9fr!important;
        gap:0!important;
        min-height:560px!important;
        border:1px solid #E5E7EB!important;
        border-radius:24px!important;
        overflow:hidden!important;
        background:#FFF!important;
        box-shadow:0 20px 60px rgba(15,23,42,.08)!important;
        margin:10px 0 22px!important;
    }
    .login-brand{
        background:linear-gradient(135deg,#2563EB 0%,#4F46E5 70%,#7C3AED 100%)!important;
        padding:56px 48px!important;
        color:#0F172A!important;
    }
    .login-logo{
        width:76px!important;height:76px!important;
        border-radius:24px!important;
        background:rgba(255,255,255,.18)!important;
        display:flex!important;align-items:center!important;justify-content:center!important;
        font-size:36px!important;margin-bottom:32px!important;
    }
    .login-brand h1{
        font-size:3rem!important;
        font-weight:1000!important;
        margin:0 0 18px!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
    }
    .login-brand p{
        font-size:1.15rem!important;
        line-height:1.7!important;
        max-width:720px!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
    }
    .login-grid{
        display:grid!important;
        grid-template-columns:1fr 1fr!important;
        gap:18px!important;
        margin-top:34px!important;
    }
    .login-grid div{
        background:rgba(255,255,255,.15)!important;
        border:1px solid rgba(255,255,255,.28)!important;
        border-radius:18px!important;
        padding:18px!important;
    }
    .login-grid b{
        display:block!important;
        font-size:1.05rem!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
        margin-bottom:8px!important;
    }
    .login-grid span{
        color:#172033!important;
        -webkit-text-fill-color:#172033!important;
        font-size:.92rem!important;
    }
    .login-panel{
        padding:64px 52px 8px!important;
        text-align:center!important;
        background:#FFFFFF!important;
    }
    .lock-icon{font-size:48px!important;margin-bottom:18px!important;}
    .login-panel h2{
        font-size:2.35rem!important;
        font-weight:1000!important;
        margin:0 0 14px!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
    }
    .login-panel p{
        color:#374151!important;
        -webkit-text-fill-color:#374151!important;
        font-size:1rem!important;
        margin-bottom:22px!important;
    }
    @media(max-width:900px){
        .login-shell{grid-template-columns:1fr!important;}
        .login-brand{padding:34px 26px!important;}
        .login-panel{padding:34px 26px 8px!important;}
    }

    
    .login-brand-card{
        min-height:560px!important;
        border-radius:28px!important;
        background:linear-gradient(135deg,#2563EB 0%,#4F46E5 70%,#7C3AED 100%)!important;
        padding:56px 48px!important;
        box-shadow:0 20px 60px rgba(15,23,42,.10)!important;
        overflow:hidden!important;
    }
    .login-logo{
        width:76px!important;height:76px!important;
        border-radius:24px!important;
        background:rgba(255,255,255,.18)!important;
        display:flex!important;align-items:center!important;justify-content:center!important;
        font-size:36px!important;margin-bottom:32px!important;
    }
    .login-brand-card h1{
        font-size:3rem!important;
        font-weight:1000!important;
        margin:0 0 18px!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
    }
    .login-brand-card p{
        font-size:1.15rem!important;
        line-height:1.7!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
    }
    .login-grid{
        display:grid!important;
        grid-template-columns:1fr 1fr!important;
        gap:18px!important;
        margin-top:34px!important;
    }
    .login-grid div{
        background:rgba(255,255,255,.15)!important;
        border:1px solid rgba(255,255,255,.28)!important;
        border-radius:18px!important;
        padding:18px!important;
    }
    .login-grid b{
        display:block!important;
        font-size:1.05rem!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
        margin-bottom:8px!important;
    }
    .login-grid span{
        color:#172033!important;
        -webkit-text-fill-color:#172033!important;
        font-size:.92rem!important;
    }
    .login-access-head{
        min-height:215px!important;
        padding:70px 10px 10px!important;
        text-align:center!important;
        background:#FFFFFF!important;
    }
    .lock-icon{font-size:48px!important;margin-bottom:18px!important;}
    .login-access-head h2{
        font-size:2.35rem!important;
        font-weight:1000!important;
        margin:0 0 14px!important;
        color:#0F172A!important;
        -webkit-text-fill-color:#0F172A!important;
    }
    .login-access-head p{
        color:#374151!important;
        -webkit-text-fill-color:#374151!important;
        font-size:1rem!important;
        margin-bottom:10px!important;
    }
    @media(max-width:900px){
        .login-brand-card{min-height:420px!important;padding:34px 26px!important;}
        .login-access-head{padding:30px 10px 8px!important;min-height:180px!important;}
        .login-grid{grid-template-columns:1fr!important;}
    }

    </style>
    """, unsafe_allow_html=True)

def platform_links_for_profile(profile):
    return dynamic_platform_links_text(profile)

def fallback_ai_response(profile=None):
    profile = profile or {}
    skills_text = str(profile.get("skills", "") + " " + profile.get("interests", "") + " " + profile.get("experience", "")).lower()
    country = profile.get("country", "your country")
    budget = profile.get("budget", "your budget")
    goal = profile.get("goal", "build income")
    links = platform_links_for_profile(profile)

    if any(x in skills_text for x in ["paint", "painter", "art", "artist", "drawing", "wall"]):
        business = "Painting service + custom wall-art brand"
        exact_product = "Room painting, shop painting, wall texture, custom wall art, before/after renovation painting, and small home improvement packages."
        first_asset = "10 photo samples: 5 before/after painting samples, 3 color-combination samples, and 2 price posters."
    elif any(x in skills_text for x in ["developer", "coding", "program", "python", "ai", "software", "app", "web"]):
        business = "AI automation and small-business dashboard agency"
        exact_product = "Small AI tools, Streamlit dashboards, automation scripts, PDF report generators, lead trackers, and business data dashboards."
        first_asset = "3 demo projects: invoice tracker, AI report generator, and WhatsApp lead tracker."
    elif any(x in skills_text for x in ["trade", "trader", "forex", "crypto", "gold", "nasdaq", "stock"]):
        business = "Trading education and risk-management tools brand"
        exact_product = "Trading journal templates, risk calculators, beginner education, market notes, and disciplined learning content. Do not sell guaranteed profit signals."
        first_asset = "A trading journal Google Sheet, a risk calculator, and 10 educational posts about risk management."
    elif any(x in skills_text for x in ["teacher", "teaching", "education", "tutor", "school", "english"]):
        business = "Online tutoring and printable education resources"
        exact_product = "Tutoring sessions, worksheets, exam notes, lesson plans, quizzes, and monthly student support packages."
        first_asset = "5 worksheets, 3 demo lessons, and one tutoring offer poster."
    else:
        business = "Low-cost service business based on your strongest skill"
        exact_product = "A simple service that solves one clear problem for one clear customer type."
        first_asset = "3 samples, one price list, and one simple offer message."

    return f"""
# Complete Beginner Business Blueprint

This report is written as if you are starting from zero. Follow it step by step. Do not skip the first steps.

## 1. Direct recommendation

**Best business for you:** {business}

**Why:** You are in {country}, your budget is {budget}, and your goal is {goal}. This business is better than a complex startup because it can start with simple tools, proof, daily outreach, and a small first customer.

## 2. What exactly you will sell

You will sell:

{exact_product}

Do not start with a big company idea. Start with one simple offer that a real person can buy this week.

## 3. What to build first

Build this first:

**{first_asset}**

This is your proof. Without proof, people will not trust you. Your first goal is not profit. Your first goal is proof.

{links}

## 4. First 24 hours plan

Hour 1: Write your one-line offer.  
Example: “I help small businesses get better results using my skill at an affordable monthly price.”

Hour 2: Create a simple name for your service. Do not waste more than 30 minutes on the name.

Hour 3: Create a WhatsApp Business profile or professional social profile.

Hour 4: Make your first sample. It does not need to be perfect. It must be clear.

Hour 5: Make your second sample.

Hour 6: Make a price list with 3 packages.

Hour 7: Write your first client message.

Hour 8: Send message to 10 people.

Before sleeping: Write what happened, who replied, and what you will improve tomorrow.

## 5. First 7 days plan

### Day 1
Create offer, profile, samples, and price packages.

### Day 2
Create 3 more samples. Post them on WhatsApp status, Facebook, Instagram, LinkedIn or the platform that fits your work.

### Day 3
Contact 20 potential customers. Do not sell hard. Offer a small sample or consultation.

### Day 4
Follow up with everyone. Improve your message if nobody replies.

### Day 5
Create one strong case study or demo.

### Day 6
Post proof again. Contact another 20 people.

### Day 7
Review results. Choose the best performing offer and repeat it for 30 days.

## 6. 30-day launch roadmap

### Week 1: Setup
Goal: Create proof and contact first 50 people.

### Week 2: Outreach
Goal: Contact 100 people total. Get 5 serious replies.

### Week 3: First customer
Goal: Close one small paid job, even at a low price, to get proof.

### Week 4: Testimonial and improvement
Goal: Deliver good work, collect feedback, make a better portfolio, and raise price slightly.

## 7. 90-day growth roadmap

### Month 1
Target: First paying customer.

### Month 2
Target: 3 paying customers or 3 completed projects.

### Month 3
Target: Package your service, increase price, and create repeatable process.

## 8. Pricing packages

Starter package: Low price, small result, easy yes.  
Standard package: Main offer with better value.  
Premium package: Full service with support, report, and follow-up.

## 9. Client message script

Hello, I am offering a simple service that can help you improve your business/results. I can show you a small sample first. If you like it, we can start with a small package.

## 10. Daily routine

If you have 1 hour:
- 20 minutes improve sample
- 20 minutes contact people
- 20 minutes follow up

If you have 3 hours:
- 1 hour build proof
- 1 hour outreach
- 1 hour delivery/learning

If full time:
- 2 hours building
- 3 hours outreach
- 2 hours delivery
- 1 hour content

## 11. Common mistakes

1. Waiting for perfect design.
2. Changing idea every day.
3. Not contacting people.
4. Asking AI again and again but not taking action.
5. Starting with expensive ads before proof.
6. Selling too many services at once.

## 12. Final checklist

1. Choose one offer.
2. Choose one customer type.
3. Make 3 samples.
4. Make one price list.
5. Create WhatsApp/Facebook/LinkedIn/Fiverr profile.
6. Contact 20 people.
7. Follow up next day.
8. Improve message.
9. Deliver first small job.
10. Collect testimonial.
11. Raise price.
12. Repeat daily for 30 days.
"""

def groq_ai(prompt, max_tokens=7000, profile=None):
    if not groq_client:
        return fallback_ai_response(profile)
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": empire_answer_quality_rules()
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.65,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI error: {e}\\n\\n" + fallback_ai_response(profile)

def build_profile_prompt(profile):
    links = platform_links_for_profile(profile)
    return f"""
You are creating a very long, complete, beginner-friendly business blueprint.

{empire_answer_quality_rules()}

The user is starting from ZERO. Explain everything like a mentor sitting with him.
Do NOT give a short answer.
Do NOT give generic same answer to everyone.
Do NOT simply say "start a business." Tell exact first action, exact websites, exact profile setup, exact client message, exact 24-hour plan, exact 7-day plan, exact 30-day plan.

IMPORTANT PERSONALIZATION RULE:
If skills say painter, recommend painting, wall art, home improvement, local service, online art portfolio, or custom design business.
If skills say AI developer, recommend AI automation, software, dashboards, chatbots, SaaS, or freelance development.
If skills say trader, recommend trading education, journal templates, risk-management tools, research content, and compliant education. Do not promise profit or guaranteed signals.
If skills say teacher, recommend tutoring, course, worksheets, notes, exam-prep business.
If skills say designer, recommend design service, portfolio, social media content, branding.
If skills say no skill, recommend a low-skill service and learning roadmap.

USER PROFILE:
Name: {profile.get('name')}
Country: {profile.get('country')}
Budget: {profile.get('budget')}
Skills: {profile.get('skills')}
Experience: {profile.get('experience')}
Daily available time: {profile.get('daily_hours')}
Risk level: {profile.get('risk_level')}
Interests: {profile.get('interests')}
Online/Offline preference: {profile.get('mode')}
Main goal: {profile.get('goal')}

MANDATORY WEBSITE LINKS SECTION:
Include these platform links and explain exactly how to use each one:
{links}

FULL PREMIUM INTELLIGENCE BLOCK:
{full_premium_context_block(profile, profile.get('goal') or 'the business')}

WRITE A LONG 5-10 PAGE STYLE REPORT WITH THESE SECTIONS:

# 1. Direct recommendation
Choose ONE best business for this user. Explain why it fits.

# 2. What exactly the user should build first
Explain the first asset/product/service/profile/sample to build.
Explain what it should contain.
Explain how long it should take.

# 3. Website links and how to use them
For each website/platform, explain:
- Why to use it
- What account/profile to create
- What to upload
- What to write
- How to get first lead/customer from it

# 4. Why not other businesses
Explain why 2-3 other options are weaker for this user.

# 5. Empire Score
Give:
- Profit potential /100
- Skill fit /100
- Startup affordability /100
- Market demand /100
- Scalability /100
- Automation potential /100
- Risk /100
- Final Empire Score /100

# 6. Exact business model
Explain:
- What the user sells
- Who buys it
- Why they buy it
- Price
- Delivery method
- Repeat purchase method

# 7. First 24 hours plan
Give detailed step-by-step actions for the first day. Assume the user knows nothing.

# 8. First 7 days plan
Day 1 to Day 7 with clear tasks.

# 9. 30-day launch roadmap
Week 1, Week 2, Week 3, Week 4 with measurable targets.

# 10. 90-day growth roadmap
Month 1, Month 2, Month 3 with revenue targets and actions.

# 11. Tools needed
Free tools and paid tools.

# 12. Client/customer acquisition
Give local, online, social media, WhatsApp, Fiverr, Upwork, LinkedIn, Facebook strategy depending on the user's profile.

# 13. Scripts
Write:
- WhatsApp message
- Cold email
- Facebook/LinkedIn message
- Fiverr/Upwork gig description if relevant
- Phone/local pitch if relevant
- Follow-up message

# 14. Pricing packages
Starter, Standard, Premium with realistic prices.

# 15. Daily routine
Daily routine for 1 hour, 3 hours, and full-time.

# 16. Growth system
How to scale, hire, automate, raise prices, and build repeat sales.

# 17. Risks and warnings
What can go wrong and how to avoid it.

# 18. Final checklist
Give 30 clear actions.

# 19. Authenticity and verification
Clearly separate facts, estimates, and assumptions. Tell the user what should be verified before spending money. Do not pretend to have live market data unless the user provided it.

# 20. Practical execution templates
Include at least one offer template, one lead tracker table structure, one daily scorecard, and one simple SOP for delivery.

Make it very detailed, practical, zero-to-hero style, customized, strong, and useful enough that the user can start execution immediately.
"""

def build_brand_prompt(profile, business):
    return f"""
Generate a brand kit for this business:
Business: {business}
Country: {profile.get('country')}
Skills: {profile.get('skills')}
Budget: {profile.get('budget')}

Return business names, slogans, colors, brand voice, website sections, social bio, Fiverr/Upwork title, WhatsApp pitch, and content ideas.
"""


def extract_score(text):
    nums = []
    for token in text.replace("/", " ").replace(":", " ").replace("%", " ").split():
        try:
            n = int(token)
            if 0 <= n <= 100:
                nums.append(n)
        except Exception:
            pass
    return max(nums) if nums else 82


def estimate_risk(score):
    return max(5, min(95, 100 - int(score)))


def make_title(profile):
    return f"{profile.get('country') or 'Global'} {profile.get('goal') or 'Business'} Plan"


def parse_selected_business(report):
    lines = [l.strip().replace("*", "").replace("#", "") for l in report.splitlines() if l.strip()]
    for line in lines:
        if "business" in line.lower() and len(line) < 140:
            return line[:120]
    return "AI-powered service business"


def forecast_data(score):
    base = max(50, score * 4)
    return pd.DataFrame([
        {"Month": "Month 1", "Low": base * .4, "Expected": base * .8, "High": base * 1.2},
        {"Month": "Month 3", "Low": base * 1.2, "Expected": base * 2.4, "High": base * 4.2},
        {"Month": "Month 6", "Low": base * 2.4, "Expected": base * 5.0, "High": base * 8.0},
        {"Month": "Year 1", "Low": base * 5.0, "Expected": base * 12.0, "High": base * 20.0},
    ])


def create_pdf(title, text):
    if not SimpleDocTemplate:
        return text.encode("utf-8")
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=22, textColor=colors.HexColor("#111827"), spaceAfter=16)
    body_style = ParagraphStyle("BodyX", parent=styles["BodyText"], fontSize=10, leading=15, textColor=colors.HexColor("#111827"))
    story = [Paragraph(title, title_style), Spacer(1, 12)]
    for block in text.split("\n\n"):
        safe = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.append(Paragraph(safe, body_style))
        story.append(Spacer(1, 8))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def download_buttons(title, report, key_prefix):
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download TXT", report, file_name=f"{title.replace(' ','_')}.txt", mime="text/plain", use_container_width=True, key=f"{key_prefix}_txt")
    with c2:
        st.download_button("Download PDF", create_pdf(title, report), file_name=f"{title.replace(' ','_')}.pdf", mime="application/pdf", use_container_width=True, key=f"{key_prefix}_pdf")


def kpi_card(label, value):
    icons = {
        "Saved plans": "▱",
        "Best score": "🏆",
        "Tasks done": "☑",
        "Pending tasks": "◷",
        "Users": "👤",
        "Plans": "▱",
        "Chats": "💬",
        "Tasks": "☑",
        "Scans": "⌕",
        "Memory": "🧠",
        "V3 Reports": "▣",
    }
    icon = icons.get(str(label), "▣")
    st.markdown(
        f"""
        <div class="kpi">
            <div class="kpi-icon">{icon}</div>
            <div>
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def score_chart(score, risk):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": "Empire Score"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#2563EB"}, "bgcolor": "#FFFFFF", "bordercolor": "#D1D5DB"}
    ))
    fig.update_layout(height=300, paper_bgcolor="#FFFFFF", font=dict(color="#111827"), margin=dict(t=50, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)


def revenue_chart(df):
    fig = go.Figure()
    for col in ["Low", "Expected", "High"]:
        fig.add_trace(go.Scatter(x=df["Month"], y=df[col], name=col, mode="lines+markers"))
    fig.update_layout(title="Revenue forecast", height=360, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", font=dict(color="#111827"), xaxis=dict(gridcolor="#E5E7EB"), yaxis=dict(gridcolor="#E5E7EB", title="USD estimate"), margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig, use_container_width=True)


def profile_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Create new empire plan")
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Name", placeholder="Your name")
        country = st.text_input("Country", placeholder="Pakistan, UAE, USA")
        budget = st.text_input("Budget", placeholder="$100, $500, $2000")
        daily_hours = st.selectbox("Daily available time", ["1 hour", "2 hours", "3 hours", "4-6 hours", "Full time"])
    with c2:
        skills = st.text_area("Skills", placeholder="English, computer, sales, teaching, design", height=90)
        experience = st.text_area("Experience", placeholder="Teaching, freelancing, shop, trading, no experience", height=90)
        risk_level = st.selectbox("Risk level", ["Low", "Medium", "High"])
        mode = st.selectbox("Preference", ["Online", "Offline", "Hybrid"])
    interests = st.text_area("Interests", placeholder="AI, YouTube, ecommerce, agency, education", height=80)
    goal = st.text_input("Main goal", placeholder="Earn $1000/month, start agency")
    st.markdown('</div>', unsafe_allow_html=True)
    return {"name": name.strip(), "country": country.strip(), "budget": budget.strip(), "skills": skills.strip(), "experience": experience.strip(), "daily_hours": daily_hours, "risk_level": risk_level, "mode": mode, "interests": interests.strip(), "goal": goal.strip()}


def validate_profile(profile):
    missing = [x for x in ["country", "budget", "skills", "goal"] if not profile.get(x)]
    return missing


# ============================================================
# DISTINCT MODULE INPUT FORMS
# These forms prevent every page from looking like the same profile form.
# ============================================================

def compact_profile_from_fields(**kwargs):
    return {
        "name": kwargs.get("name", ""),
        "country": kwargs.get("country", ""),
        "budget": kwargs.get("budget", ""),
        "skills": kwargs.get("skills", ""),
        "experience": kwargs.get("experience", ""),
        "daily_hours": kwargs.get("daily_hours", ""),
        "risk_level": kwargs.get("risk_level", "Medium"),
        "mode": kwargs.get("mode", "Online"),
        "interests": kwargs.get("interests", ""),
        "goal": kwargs.get("goal", ""),
    }

def opportunity_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Opportunity Scan Setup")
    a, b, c = st.columns(3)
    with a:
        country = st.text_input("Market country", placeholder="Pakistan, UAE, USA", key="opp_country")
        city = st.text_input("City / local market", placeholder="Dipalpur, Lahore, Dubai", key="opp_city")
        budget = st.select_slider("Available capital", options=["$0-$50", "$50-$100", "$100-$300", "$300-$500", "$500-$1000", "$1000+"], key="opp_budget")
    with b:
        skill_category = st.selectbox("Main skill category", ["Painting / Art", "AI / Coding", "Teaching", "Trading", "Marketing", "Sales", "Admin / Email", "No clear skill yet"], key="opp_skill_cat")
        daily_hours = st.selectbox("Daily time", ["1 hour", "2 hours", "3 hours", "4-6 hours", "Full time"], key="opp_hours")
        mode = st.radio("Work style", ["Online", "Offline", "Hybrid"], horizontal=True, key="opp_mode")
    with c:
        desired_income = st.text_input("Desired monthly income", placeholder="$500, $1000, $5000", key="opp_income")
        risk_level = st.selectbox("Risk comfort", ["Low", "Medium", "High"], key="opp_risk")
        internet = st.selectbox("Internet / laptop access", ["Strong", "Average", "Mobile only", "Weak"], key="opp_internet")
    interests = st.text_area("What kind of work do you like?", placeholder="Painting houses, AI apps, tutoring, trading education...", height=90, key="opp_interests")
    st.markdown('</div>', unsafe_allow_html=True)
    skills = f"{skill_category}; internet access: {internet}; city: {city}"
    goal = f"Find best opportunity to reach {desired_income}"
    return compact_profile_from_fields(country=country, budget=budget, skills=skills, daily_hours=daily_hours, risk_level=risk_level, mode=mode, interests=interests, goal=goal)

def diagnostics_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Empire Diagnostics Input")
    c1, c2 = st.columns([.55, .45])
    with c1:
        country = st.text_input("Country", key="diag_country")
        current_income = st.text_input("Current monthly income", placeholder="$0", key="diag_current_income")
        monthly_expense = st.text_input("Monthly business/personal expense", placeholder="$100", key="diag_expense")
        skills = st.multiselect("Skill assets", ["Sales", "Writing", "English", "Coding", "Design", "Painting", "Teaching", "Trading", "Marketing", "Management"], key="diag_skills")
    with c2:
        budget = st.text_input("Startup budget", placeholder="$100", key="diag_budget")
        customers = st.number_input("Existing customers/clients", min_value=0, value=0, key="diag_customers")
        risk_level = st.select_slider("Risk appetite", options=["Low", "Medium", "High"], key="diag_risk")
        mode = st.radio("Scale direction", ["Online", "Offline", "Hybrid"], horizontal=True, key="diag_mode")
    goal = st.text_input("Score goal", placeholder="Check if I can reach $1000/month", key="diag_goal")
    st.markdown('</div>', unsafe_allow_html=True)
    return compact_profile_from_fields(country=country, budget=budget, skills=", ".join(skills), experience=f"Income {current_income}, expense {monthly_expense}, customers {customers}", risk_level=risk_level, mode=mode, goal=goal)

def branding_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Brand Studio Brief")
    c1, c2 = st.columns(2)
    with c1:
        business = st.text_input("Business / brand idea", key="brand_business")
        audience = st.text_input("Target audience", placeholder="Small shops, students, homeowners", key="brand_audience")
        tone = st.selectbox("Brand tone", ["Premium", "Friendly", "Bold", "Trustworthy", "Luxury", "Simple"], key="brand_tone")
    with c2:
        country = st.text_input("Market country", key="brand_country")
        budget = st.text_input("Branding budget", placeholder="$0-$100", key="brand_budget")
        style = st.text_input("Style keywords", placeholder="modern, clean, blue, professional", key="brand_style")
    notes = st.text_area("Brand notes", placeholder="What should the brand feel like?", height=80, key="brand_notes")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(country=country, budget=budget, skills=f"Brand tone {tone}; style {style}", interests=notes, goal=f"Create brand for {business} targeting {audience}")
    return profile, business

def investor_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Venture Analyzer Input")
    c1, c2 = st.columns([.5, .5])
    with c1:
        idea = st.text_area("Business idea", placeholder="AI automation agency for local clinics...", height=120, key="inv_idea")
        country = st.text_input("Target country / market", key="inv_country")
        budget = st.text_input("Available investment", placeholder="$500", key="inv_budget")
    with c2:
        founder_strength = st.text_area("Founder strengths", placeholder="Sales, coding, teaching, local network...", height=90, key="inv_strength")
        customer = st.text_input("Target customer", placeholder="Clinics, schools, shops...", key="inv_customer")
        risk_level = st.selectbox("Risk level", ["Low", "Medium", "High"], key="inv_risk")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(country=country, budget=budget, skills=founder_strength, experience=f"Target customer: {customer}", risk_level=risk_level, goal=f"Analyze venture: {idea}")
    return profile, idea

def marketplace_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Marketplace Launch Setup")
    c1, c2, c3 = st.columns(3)
    with c1:
        business = st.text_input("Service to launch", placeholder="Painting service, AI dashboard agency...", key="mp_business")
        country = st.text_input("Country", key="mp_country")
    with c2:
        platform_focus = st.multiselect("Platform focus", ["Fiverr", "Upwork", "LinkedIn", "Facebook", "Instagram", "WhatsApp", "Local visits"], default=["Fiverr", "Facebook"], key="mp_platforms")
        budget = st.text_input("Launch budget", placeholder="$0-$100", key="mp_budget")
    with c3:
        proof = st.text_input("Available proof", placeholder="Photos, demos, samples, portfolio", key="mp_proof")
        daily_hours = st.selectbox("Daily time", ["1 hour", "2 hours", "3 hours", "4-6 hours", "Full time"], key="mp_hours")
    notes = st.text_area("Offer details", height=80, key="mp_notes")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(country=country, budget=budget, skills=f"Platforms: {', '.join(platform_focus)}; proof: {proof}", daily_hours=daily_hours, interests=notes, goal=f"Launch {business} on marketplaces")
    return profile, business

def competitor_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Competitor Research Brief")
    c1, c2 = st.columns(2)
    with c1:
        business = st.text_input("Business category", placeholder="Painting service, tutoring, AI agency", key="comp_business")
        market = st.text_input("Target city/country", placeholder="Lahore, Pakistan", key="comp_market")
        price_level = st.selectbox("Your planned price level", ["Low cost", "Mid range", "Premium", "Not decided"], key="comp_price")
    with c2:
        target_customer = st.text_input("Target customer", placeholder="Homeowners, clinics, students", key="comp_customer")
        advantage = st.text_area("Your possible advantage", placeholder="Fast delivery, low price, better quality...", height=90, key="comp_adv")
        budget = st.text_input("Research / launch budget", placeholder="$100", key="comp_budget")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(country=market, budget=budget, skills=f"Advantage: {advantage}; price level {price_level}", experience=f"Target customer: {target_customer}", goal=f"Beat competitors in {business}")
    return profile, business, market

def roadmap_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Income Roadmap Builder")
    c1, c2, c3 = st.columns(3)
    with c1:
        business = st.text_input("Business / skill", key="road_business")
        current_income = st.text_input("Current monthly income", placeholder="$0", key="road_current")
    with c2:
        target_income = st.text_input("Target monthly income", placeholder="$1000", key="road_target")
        timeframe = st.selectbox("Timeframe", ["3 months", "6 months", "12 months", "24 months"], key="road_timeframe")
    with c3:
        daily_hours = st.selectbox("Daily available time", ["1 hour", "2 hours", "3 hours", "4-6 hours", "Full time"], key="road_hours")
        budget = st.text_input("Budget", placeholder="$100", key="road_budget")
    blockers = st.text_area("Biggest blockers", placeholder="No clients, no portfolio, no skill, no confidence...", height=80, key="road_blockers")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(budget=budget, skills=business, daily_hours=daily_hours, experience=f"Current income {current_income}; blockers {blockers}", goal=f"Reach {target_income} in {timeframe}")
    return profile, current_income, target_income, timeframe, business

def blueprint_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Business Blueprint Builder")
    c1, c2 = st.columns([.45, .55])
    with c1:
        business = st.text_input("Business idea", key="bp_business")
        country = st.text_input("Market country", key="bp_country")
        budget = st.text_input("Startup budget", key="bp_budget")
        team = st.selectbox("Team size", ["Solo", "2 people", "Small team", "Already have team"], key="bp_team")
    with c2:
        customer = st.text_input("Ideal customer", key="bp_customer")
        offer = st.text_area("Offer / service idea", height=90, key="bp_offer")
        pricing_goal = st.text_input("Pricing goal", placeholder="$50, $100, $500 package", key="bp_pricing")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(country=country, budget=budget, skills=f"Team: {team}; offer: {offer}", experience=f"Customer: {customer}; pricing goal: {pricing_goal}", goal=f"Build blueprint for {business}")
    return profile, business

def acquisition_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Client Acquisition Setup")
    c1, c2, c3 = st.columns(3)
    with c1:
        business = st.text_input("Your service", key="acq_business")
        target_customer = st.text_input("Target customer", key="acq_customer")
    with c2:
        avg_price = st.text_input("Average price", placeholder="$100", key="acq_price")
        location = st.text_input("Location / market", key="acq_location")
    with c3:
        channel = st.multiselect("Preferred channels", ["WhatsApp", "Facebook", "LinkedIn", "Fiverr", "Upwork", "Local visits", "Instagram"], default=["WhatsApp", "Facebook"], key="acq_channels")
        daily_target = st.number_input("Daily outreach target", min_value=5, value=20, key="acq_daily")
    offer = st.text_area("Your offer", height=80, key="acq_offer")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(country=location, budget=avg_price, skills=f"Channels: {', '.join(channel)}; offer: {offer}", experience=f"Daily target {daily_target}", goal=f"Get clients for {business}")
    return profile, business, target_customer

def sales_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Sales Script Brief")
    c1, c2 = st.columns(2)
    with c1:
        business = st.text_input("Business/service", key="sales_business")
        offer = st.text_input("Main offer", key="sales_offer")
        price = st.text_input("Price/package", key="sales_price")
    with c2:
        customer = st.text_input("Customer type", key="sales_customer")
        tone = st.selectbox("Script tone", ["Friendly", "Professional", "Direct", "Premium", "Local simple language"], key="sales_tone")
        objection = st.text_input("Common objection", placeholder="Too expensive, no need, call later", key="sales_objection")
    st.markdown('</div>', unsafe_allow_html=True)
    profile = compact_profile_from_fields(skills=f"Sales tone: {tone}; objection: {objection}", experience=f"Customer: {customer}", goal=f"Sell {offer} at {price}")
    return profile, business, offer

def memory_input_form():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Memory Command Center")
    return
# ============================================================
# END DISTINCT MODULE INPUT FORMS
# ============================================================

def login_page():
    left, right = st.columns([1.12, .88], gap="large")

    with left:
        st.markdown("""
        <div class="login-brand-card">
            <div class="login-logo">👑</div>
            <h1>EmpireOS AI</h1>
            <p>Build. Plan. Launch. Grow.</p>
            <div class="login-grid">
                <div><b>1–10 Plans</b><span>Business blueprints</span></div>
                <div><b>PDF Reports</b><span>Export ready</span></div>
                <div><b>Saved History</b><span>Full reports</span></div>
                <div><b>AI Analysis</b><span>Groq-powered</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown("""
        <div class="login-access-head">
            <div class="lock-icon">🔐</div>
            <h2>Access Dashboard</h2>
            <p>Login or create your secure account</p>
        </div>
        """, unsafe_allow_html=True)

        auth_msg = st.empty()
        tab_login, tab_register = st.tabs(["Login", "Register"])

        with tab_login:
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", key="login_username", placeholder="Enter username")
                password = st.text_input("Password", type="password", key="login_password", placeholder="Enter password")
                submitted = st.form_submit_button("Login to EmpireOS", use_container_width=True)

            if submitted:
                ok, msg = login_user(username, password)
                if ok:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username.strip()
                    st.session_state["page"] = "Dashboard"
                    auth_msg.success(msg)
                    st.rerun()
                else:
                    auth_msg.error(str(msg))

        with tab_register:
            with st.form("register_form", clear_on_submit=False):
                new_username = st.text_input("Username", key="reg_username", placeholder="Choose username")
                new_password = st.text_input("Password", type="password", key="reg_password", placeholder="Minimum 6 characters")
                submitted = st.form_submit_button("Create Account", use_container_width=True)

            if submitted:
                ok, msg = register_user(new_username, new_password)
                if ok:
                    auth_msg.success("Account created. Now login with your username and password.")
                else:
                    auth_msg.error(str(msg))

def dashboard_page(username):
    rows = get_user_plans(username, limit=100)
    tasks = get_tasks(username, limit=200)
    total = len(rows)
    best_score = max([r[4] for r in rows], default=0)
    done_tasks = sum(1 for t in tasks if t[4] == "done")
    pending_tasks = sum(1 for t in tasks if t[4] != "done")

    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-topline">
                <span>••• CONNECTING</span>
            </div>
            <div class="title">Welcome, {username} 👑</div>
            <div class="subtitle">
                EmpireOS AI V2: business advisor, opportunity scanner, revenue planner, progress CRM, marketplace guide and investor mode.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Saved plans", total)
    with c2: kpi_card("Best score", best_score)
    with c3: kpi_card("Tasks done", done_tasks)
    with c4: kpi_card("Pending tasks", pending_tasks)

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    left, right = st.columns([.60, .40], gap="large")
    with left:
        st.markdown('<div class="panel-card"><div class="panel-title"><span class="panel-icon">▤</span>Recent plans</div>', unsafe_allow_html=True)
        if rows[:8]:
            df = pd.DataFrame([{
                "Date": r[9][:16].replace("T", " "),
                "Title": r[2] or "Untitled plan",
                "Business": r[3] or "Business plan",
            } for r in rows[:8]])
            st.dataframe(df, use_container_width=True, hide_index=True, height=330)
            st.markdown('<div class="view-link">View all plans →</div>', unsafe_allow_html=True)
        else:
            st.info("No saved plans yet. Create your first plan.")
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel-card"><div class="panel-title">Execution snapshot</div>', unsafe_allow_html=True)
        if tasks:
            chart_df = pd.DataFrame([
                {"Status": "Pending", "Count": pending_tasks},
                {"Status": "Done", "Count": done_tasks},
            ])
            colors = ["#0B72D9", "#9CCEFF"]
            fig = go.Figure(go.Pie(
                labels=chart_df["Status"],
                values=chart_df["Count"],
                hole=.48,
                marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
                textinfo="percent",
                sort=False
            ))
            fig.update_layout(
                height=330,
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                font=dict(color="#0F172A", size=13),
                margin=dict(t=5,b=5,l=5,r=5),
                legend=dict(orientation="v", x=.84, y=.78)
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No tasks yet. Open a saved plan and create launch tasks.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="panel-card">
            <div class="panel-title"><span class="panel-icon">▣</span>V2 modules</div>
            <div class="module-grid">
                <div class="module-pill"><span class="mi">⌕</span>Opportunity Scanner</div>
                <div class="module-pill"><span class="mi">⌁</span>Revenue Planner</div>
                <div class="module-pill"><span class="mi">☑</span>Progress CRM</div>
                <div class="module-pill"><span class="mi">$</span>Investor Mode</div>
                <div class="module-pill"><span class="mi">▢</span>Marketplace Guide</div>
                <div class="module-pill"><span class="mi">🤖</span>AI Co-Founder Pro</div>
                <div class="module-pill"><span class="mi">◎</span>Competitor Intelligence</div>
                <div class="module-pill"><span class="mi">▰</span>Empire Roadmap</div>
                <div class="module-pill"><span class="mi">▤</span>Business Blueprint</div>
                <div class="module-pill"><span class="mi">♟</span>Client Acquisition</div>
                <div class="module-pill"><span class="mi">💬</span>Sales Scripts</div>
                <div class="module-pill"><span class="mi">▥</span>Empire Memory</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def new_plan_page(username):
    profile = profile_form()
    if st.button("Generate Empire Plan", use_container_width=True):
        missing = validate_profile(profile)
        if missing:
            st.error("Please fill: " + ", ".join(missing))
            return
        with st.spinner("EmpireOS AI is building a very detailed zero-to-hero business plan with platform links..."):
            report = groq_ai(build_profile_prompt(profile), max_tokens=7500, profile=profile)
        score = extract_score(report)
        risk = estimate_risk(score)
        business = parse_selected_business(report)
        title = make_title(profile)
        save_plan(username, profile, title, business, score, risk, profile.get("budget", ""), "See forecast and AI report", report)
        latest_rows = get_user_plans(username, limit=1)
        if latest_rows:
            save_default_tasks_for_plan(username, latest_rows[0][0], title)
        st.session_state["latest_report"] = report
        st.session_state["latest_profile"] = profile
        st.session_state["latest_score"] = score
        st.session_state["latest_risk"] = risk
        st.success("Plan generated and saved.")
    if st.session_state.get("latest_report"):
        report = st.session_state["latest_report"]
        score = st.session_state.get("latest_score", 82)
        risk = st.session_state.get("latest_risk", 100-score)
        profile = st.session_state.get("latest_profile", {})
        c1, c2 = st.columns([.35, .65])
        with c1: score_chart(score, risk)
        with c2: revenue_chart(forecast_data(score))
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Full Detailed Empire Plan")
        st.markdown(report, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons(make_title(profile), report, "latest_plan")


def saved_plans_page(username):
    rows = get_user_plans(username, limit=100)
    st.markdown('<div class="hero"><div class="title">Saved Plans</div><div class="subtitle">Open any full plan exactly as it was generated.</div></div>', unsafe_allow_html=True)
    if not rows:
        st.info("No saved plans yet.")
        return
    left, right = st.columns([.35, .65])
    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Plan library")
        for r in rows:
            plan_id, profile_json, title, business, score, risk, cost, income, report, created = r
            st.markdown(f"**{title or 'Untitled'}**  \n{business}  \nScore: {score} • {created[:10]}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Open", key=f"open_{plan_id}", use_container_width=True):
                    st.session_state["open_plan_id"] = plan_id
                    st.rerun()
            with c2:
                if st.button("Delete", key=f"delete_{plan_id}", use_container_width=True):
                    delete_plan(plan_id, username)
                    st.rerun()
            st.markdown("---")
        st.markdown('</div>', unsafe_allow_html=True)
    open_id = st.session_state.get("open_plan_id", rows[0][0])
    plan = get_plan_by_id(open_id, username) or rows[0]
    plan_id, profile_json, title, business, score, risk, cost, income, report, created = plan
    with right:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader(title or "Saved plan")
        st.write(f"**Business:** {business}")
        st.write(f"**Empire Score:** {score}/100")
        st.write(f"**Risk Score:** {risk}/100")
        st.write(f"**Created:** {created[:16].replace('T',' ')}")
        st.markdown('</div>', unsafe_allow_html=True)
        c1, c2 = st.columns([.35, .65])
        with c1: score_chart(score, risk)
        with c2: revenue_chart(forecast_data(score))
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(report or "No report saved.")
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons(title or "EmpireOS Plan", report or "", f"saved_{plan_id}")


def branding_page(username):
    st.markdown('<div class="hero"><div class="title">Branding Studio</div><div class="subtitle">Different input flow: brand tone, audience, style and market.</div></div>', unsafe_allow_html=True)
    profile, business = branding_input_form()
    if st.button("Generate brand kit", use_container_width=True):
        if not business:
            st.error("Enter business idea.")
            return
        with st.spinner("Generating brand kit..."):
            kit = groq_ai(build_brand_prompt(profile, business), max_tokens=3500, profile=profile)
        st.session_state["brand_kit"] = kit
        save_plan(username, profile, f"Brand Kit - {business}", business, 80, 20, profile.get("budget", ""), "Branding output", kit)
    if st.session_state.get("brand_kit"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["brand_kit"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("EmpireOS Brand Kit", st.session_state["brand_kit"], "brandkit")

def cofounder_page(username):
    st.markdown('<div class="hero"><div class="title">AI Co-Founder Chat</div><div class="subtitle">Ask for business decisions, pricing, first client, growth, hiring, and risk.</div></div>', unsafe_allow_html=True)
    for role, msg, created in get_chats(username, limit=20):
        who = "You" if role == "user" else "EmpireOS AI"
        st.markdown(f'<div class="card"><b>{who}:</b><br>{msg}</div>', unsafe_allow_html=True)
    q = st.text_area("Ask your AI co-founder", height=110)
    if st.button("Ask AI Co-Founder", use_container_width=True):
        if not q.strip():
            st.error("Write your question.")
            return
        save_chat(username, "user", q)
        with st.spinner("Thinking..."):
            ans = groq_ai("Act as my practical business co-founder. Use the user saved plans and current business context if needed. Give a detailed step-by-step answer, not a short reply. Question:\n\n" + q, max_tokens=4000)
        save_chat(username, "assistant", ans)
        st.rerun()


def opportunity_scanner_page(username):
    st.markdown('<div class="hero"><div class="title">Opportunity Scanner</div><div class="subtitle">Different input flow: market, capital, skill category, work style and income target.</div></div>', unsafe_allow_html=True)
    profile = opportunity_input_form()
    local_options = calculate_local_opportunities(profile)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Opportunity ranking")
    df = pd.DataFrame([{
        "Rank": i + 1,
        "Opportunity": o["name"],
        "Score": o["score"],
        "Startup cost": o["startup_cost"],
        "Time to income": o["time_to_income"],
        "Difficulty": o["difficulty"],
        "Income": o["income"],
        "Platforms": ", ".join(o["platforms"])
    } for i, o in enumerate(local_options)])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([.35, .65])
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Top match")
        if local_options:
            top = local_options[0]
            st.metric("Best opportunity", top["name"])
            st.metric("Fit score", f"{top['score']}/100")
            st.write("Platforms:", ", ".join(top["platforms"]))
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        if st.button("Generate AI Opportunity Scan", use_container_width=True):
            with st.spinner("Scanning best opportunities..."):
                report = groq_ai(opportunity_scan_prompt(profile, local_options), max_tokens=5000, profile=profile)
            save_opportunity_scan(username, profile, report)
            st.session_state["latest_scan"] = report
            st.success("Opportunity scan saved.")

    if st.session_state.get("latest_scan"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["latest_scan"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Opportunity Scan", st.session_state["latest_scan"], "opportunity_scan")

def revenue_planner_page(username):
    st.markdown('<div class="hero"><div class="title">Revenue Planner</div><div class="subtitle">Estimate income, break-even and 12-month growth.</div></div>', unsafe_allow_html=True)
    rows = get_user_plans(username, limit=100)
    plan_map = {f"{r[2]} — {r[3]}": r[0] for r in rows}
    selected = st.selectbox("Attach forecast to saved plan", ["No plan"] + list(plan_map.keys()))
    plan_id = plan_map.get(selected)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        budget = st.number_input("Startup budget ($)", min_value=0.0, value=200.0, step=50.0)
    with c2:
        price = st.number_input("Price per client ($)", min_value=0.0, value=150.0, step=25.0)
    with c3:
        clients = st.number_input("Starting monthly clients", min_value=0, value=2, step=1)
    with c4:
        cost = st.number_input("Monthly cost ($)", min_value=0.0, value=50.0, step=25.0)

    df = build_forecast_table(budget, price, clients, cost)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("12-month forecast")
    st.dataframe(df, use_container_width=True, hide_index=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Month"], y=df["Revenue"], name="Revenue", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=df["Month"], y=df["Profit"], name="Profit", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=df["Month"], y=df["Cumulative Profit"], name="Cumulative Profit", mode="lines+markers"))
    fig.update_layout(height=420, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", font=dict(color="#111827"), margin=dict(l=20,r=20,t=40,b=20))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Save forecast", use_container_width=True):
        save_revenue_forecast(username, plan_id, budget, price, clients, cost, df)
        st.success("Forecast saved.")


def progress_crm_page(username):
    premium_progress_dashboard(username)
    st.markdown('<div class="hero"><div class="title">Progress CRM</div><div class="subtitle">Track daily launch tasks, first customer actions and growth progress.</div></div>', unsafe_allow_html=True)

    rows = get_user_plans(username, limit=100)
    plan_map = {f"{r[2]} — {r[3]}": (r[0], r[2]) for r in rows}
    selected = st.selectbox("Create tasks from saved plan", ["Select plan"] + list(plan_map.keys()))
    if selected != "Select plan":
        plan_id, title = plan_map[selected]
        if st.button("Create default 30-day launch tasks", use_container_width=True):
            save_default_tasks_for_plan(username, plan_id, title)
            st.success("Tasks created.")
            st.rerun()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Add custom task")
    c1, c2, c3 = st.columns([.5, .25, .25])
    with c1:
        task_title = st.text_input("Task title")
    with c2:
        due_date = st.text_input("Due date", placeholder="Today / Day 3 / Week 1")
    with c3:
        task_type = st.selectbox("Type", ["general", "outreach", "delivery", "learning", "launch"])
    notes = st.text_area("Notes", height=70)
    if st.button("Add task", use_container_width=True):
        if task_title.strip():
            save_task(username, None, task_title, task_type, due_date, notes)
            st.success("Task added.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    tasks = get_tasks(username, limit=200)
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Task board")
    if not tasks:
        st.info("No tasks yet.")
    else:
        for task_id, plan_id, title, task_type, status, due, notes, created in tasks:
            cols = st.columns([.5, .16, .14, .1, .1])
            with cols[0]:
                st.markdown(f"**{title}**  \n{task_type} • {due or 'No due'}")
                if notes:
                    st.caption(notes)
            with cols[1]:
                st.write(status.upper())
            with cols[2]:
                if st.button("Done", key=f"done_{task_id}", use_container_width=True):
                    update_task_status(task_id, username, "done")
                    st.rerun()
            with cols[3]:
                if st.button("Pending", key=f"pending_{task_id}", use_container_width=True):
                    update_task_status(task_id, username, "pending")
                    st.rerun()
            with cols[4]:
                if st.button("Delete", key=f"del_task_{task_id}", use_container_width=True):
                    delete_task(task_id, username)
                    st.rerun()
            st.markdown("---")
    st.markdown('</div>', unsafe_allow_html=True)


def investor_mode_page(username):
    st.markdown('<div class="hero"><div class="title">Venture Analyzer</div><div class="subtitle">Different input flow: idea, target customer, founder strengths, market and risk.</div></div>', unsafe_allow_html=True)
    profile, idea = investor_input_form()

    if st.button("Generate venture analysis", use_container_width=True):
        if not idea.strip():
            st.error("Write business idea first.")
            return
        with st.spinner("Building investor-style analysis..."):
            report = groq_ai(investor_prompt(profile, idea), max_tokens=5000, profile=profile)
        st.session_state["investor_report"] = report
        save_plan(username, profile, "Venture Analysis", idea[:120], 80, 25, profile.get("budget",""), "Venture analyzer", report)

    if st.session_state.get("investor_report"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["investor_report"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Venture Analysis", st.session_state["investor_report"], "investor_mode")

def marketplace_guide_page(username):
    st.markdown('<div class="hero"><div class="title">Marketplace Guide</div><div class="subtitle">Different input flow: platform focus, proof, offer and launch budget.</div></div>', unsafe_allow_html=True)
    profile, business = marketplace_input_form()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(platform_links_for_profile(profile))
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Generate full marketplace launch guide", use_container_width=True):
        if not business.strip():
            st.error("Enter business/service first.")
            return
        with st.spinner("Generating platform-by-platform launch guide..."):
            report = groq_ai(marketplace_guide_prompt(profile, business), max_tokens=5000, profile=profile)
        st.session_state["marketplace_report"] = report
        save_plan(username, profile, f"Marketplace Guide - {business}", business, 78, 22, profile.get("budget",""), "Marketplace guide", report)

    if st.session_state.get("marketplace_report"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["marketplace_report"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Marketplace Guide", st.session_state["marketplace_report"], "marketplace_guide")

def score_lab_page(username):
    st.markdown('<div class="hero"><div class="title">Empire Diagnostics</div><div class="subtitle">Different input flow: income, expenses, customers, skills and risk appetite.</div></div>', unsafe_allow_html=True)
    profile = diagnostics_input_form()
    score = v2_score_breakdown(profile)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Diagnostic score breakdown")
    df = pd.DataFrame([{"Factor": k, "Score": v} for k, v in score.items()])
    st.dataframe(df, use_container_width=True, hide_index=True)
    fig = go.Figure(go.Bar(x=df["Factor"], y=df["Score"], text=df["Score"], textposition="auto"))
    fig.update_layout(height=420, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", font=dict(color="#111827"), yaxis=dict(range=[0,100]), margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Quick diagnosis")
    final_score = score.get("Final Empire Score", 0)
    if final_score >= 80:
        st.success("Strong profile. Focus on execution and outreach.")
    elif final_score >= 60:
        st.warning("Good potential. Improve proof, offer and customer targeting.")
    else:
        st.error("Needs foundation. Start with skill, proof and low-risk service.")
    st.markdown('</div>', unsafe_allow_html=True)

def competitor_intelligence_page(username):
    st.markdown('<div class="hero"><div class="title">Competitor Intelligence</div><div class="subtitle">Different input flow: market, competitor type, price level, advantage and target customer.</div></div>', unsafe_allow_html=True)
    profile, business, market = competitor_input_form()
    if st.button("Generate Competitor Intelligence", use_container_width=True):
        if not business.strip():
            st.error("Enter business first.")
            return
        with st.spinner("Analyzing competitors..."):
            report = groq_ai(competitor_intelligence_prompt(profile, business, market), max_tokens=5500, profile=profile)
        st.session_state["competitor_report"] = report
        save_v3_report(username, "Competitor Intelligence", business, {"profile": profile, "business": business, "market": market}, report)
        save_memory(username, "competitor", f"Competitor report: {business}", report[:1200])
        st.success("Competitor intelligence saved.")
    if st.session_state.get("competitor_report"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["competitor_report"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Competitor Intelligence", st.session_state["competitor_report"], "competitor_intel")

def empire_roadmap_page(username):
    st.markdown('<div class="hero"><div class="title">Empire Roadmap Engine</div><div class="subtitle">Different input flow: current income, target income, timeframe, blockers and business.</div></div>', unsafe_allow_html=True)
    profile, current_income, target_income, timeframe, business = roadmap_input_form()
    if st.button("Generate Empire Roadmap", use_container_width=True):
        if not business.strip():
            st.error("Enter business/skill/idea first.")
            return
        with st.spinner("Building roadmap..."):
            report = groq_ai(empire_roadmap_prompt(profile, current_income, target_income, timeframe, business), max_tokens=6000, profile=profile)
        st.session_state["roadmap_report"] = report
        save_v3_report(username, "Empire Roadmap", business, {"profile": profile, "current_income": current_income, "target_income": target_income, "timeframe": timeframe, "business": business}, report)
        save_memory(username, "roadmap", f"Roadmap: {business} to {target_income}", report[:1200])
        st.success("Roadmap saved.")
    if st.session_state.get("roadmap_report"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["roadmap_report"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Empire Roadmap", st.session_state["roadmap_report"], "empire_roadmap")

def business_blueprint_page(username):
    st.markdown('<div class="hero"><div class="title">Business Blueprint</div><div class="subtitle">Different input flow: customer, offer, team size, pricing and business model.</div></div>', unsafe_allow_html=True)
    profile, business = blueprint_input_form()
    if st.button("Generate Business Blueprint", use_container_width=True):
        if not business.strip():
            st.error("Enter business idea first.")
            return
        with st.spinner("Building blueprint..."):
            report = groq_ai(business_blueprint_prompt(profile, business), max_tokens=6000, profile=profile)
        st.session_state["blueprint_report"] = report
        save_v3_report(username, "Business Blueprint", business, {"profile": profile, "business": business}, report)
        save_memory(username, "blueprint", f"Blueprint: {business}", report[:1200])
        st.success("Business blueprint saved.")
    if st.session_state.get("blueprint_report"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["blueprint_report"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Business Blueprint", st.session_state["blueprint_report"], "business_blueprint")

def client_acquisition_page(username):
    st.markdown('<div class="hero"><div class="title">Client Acquisition Engine</div><div class="subtitle">Different input flow: channels, outreach target, customer type and offer.</div></div>', unsafe_allow_html=True)
    profile, business, target_customer = acquisition_input_form()
    if st.button("Generate Client Acquisition Plan", use_container_width=True):
        if not business.strip():
            st.error("Enter business first.")
            return
        with st.spinner("Building client acquisition system..."):
            report = groq_ai(client_acquisition_prompt(profile, business, target_customer), max_tokens=5500, profile=profile)
        st.session_state["client_report"] = report
        save_v3_report(username, "Client Acquisition", business, {"profile": profile, "business": business, "target_customer": target_customer}, report)
        save_memory(username, "client_acquisition", f"Client acquisition: {business}", report[:1200])
        st.success("Client acquisition plan saved.")
    if st.session_state.get("client_report"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["client_report"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Client Acquisition", st.session_state["client_report"], "client_acquisition")

def sales_scripts_page(username):
    st.markdown('<div class="hero"><div class="title">Sales Script Generator</div><div class="subtitle">Different input flow: offer, price, customer, tone and objection.</div></div>', unsafe_allow_html=True)
    profile, business, offer = sales_input_form()
    if st.button("Generate Sales Scripts", use_container_width=True):
        if not business.strip() or not offer.strip():
            st.error("Enter business and offer first.")
            return
        with st.spinner("Writing scripts..."):
            report = groq_ai(sales_script_prompt(profile, business, offer), max_tokens=5000, profile=profile)
        st.session_state["sales_report"] = report
        save_v3_report(username, "Sales Scripts", business, {"profile": profile, "business": business, "offer": offer}, report)
        save_memory(username, "sales_scripts", f"Sales scripts: {business}", report[:1200])
        st.success("Sales scripts saved.")
    if st.session_state.get("sales_report"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state["sales_report"])
        st.markdown('</div>', unsafe_allow_html=True)
        download_buttons("Sales Scripts", st.session_state["sales_report"], "sales_scripts")

def empire_memory_page(username):
    st.markdown('<div class="hero"><div class="title">Empire Memory</div><div class="subtitle">Save goals and continue later with context.</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Add memory")
    c1, c2 = st.columns([.35, .65])
    with c1:
        mem_type = st.selectbox("Memory type", ["goal", "business", "progress", "client", "idea", "note"])
        title = st.text_input("Title")
    with c2:
        content = st.text_area("Memory content", height=110)
    if st.button("Save memory", use_container_width=True):
        if title.strip() and content.strip():
            save_memory(username, mem_type, title, content)
            st.success("Memory saved.")
            st.rerun()
        else:
            st.error("Title and content required.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Ask with memory")
    q = st.text_area("Question", placeholder="Continue my latest business plan. What should I do today?", height=100)
    if st.button("Ask Empire Memory", use_container_width=True):
        if not q.strip():
            st.error("Write question first.")
        else:
            with st.spinner("Using saved memory..."):
                ans = groq_ai(memory_prompt(username, q), max_tokens=4500)
            st.session_state["memory_answer"] = ans
            save_chat(username, "user", q)
            save_chat(username, "assistant", ans)
    if st.session_state.get("memory_answer"):
        st.markdown(st.session_state["memory_answer"])
        download_buttons("Empire Memory Answer", st.session_state["memory_answer"], "memory_answer")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Saved memory")
    memories = get_memory(username, limit=50)
    if not memories:
        st.info("No memory saved yet.")
    else:
        for mem_id, mem_type, title, content, created in memories:
            cols = st.columns([.15, .25, .45, .15])
            with cols[0]: st.write(mem_type)
            with cols[1]: st.write(title)
            with cols[2]: st.caption(content[:300])
            with cols[3]:
                if st.button("Delete", key=f"del_mem_{mem_id}", use_container_width=True):
                    delete_memory(mem_id, username)
                    st.rerun()
            st.markdown("---")
    st.markdown('</div>', unsafe_allow_html=True)

def admin_page(username):
    if get_user_plan(username) != "admin":
        st.error("Admin only.")
        return
    stats = admin_stats()
    st.markdown('<div class="hero"><div class="title">Admin Dashboard</div><div class="subtitle">Users, plans, tasks, scans, memory and V3 usage overview.</div></div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Users", stats["users"])
    with c2: kpi_card("Plans", stats["plans"])
    with c3: kpi_card("Chats", stats["chats"])
    with c4: kpi_card("Tasks", stats.get("tasks", 0))
    c5, c6, c7 = st.columns(3)
    with c5: kpi_card("Scans", stats.get("scans", 0))
    with c6: kpi_card("Memory", stats.get("memory", 0))
    with c7: kpi_card("V3 Reports", stats.get("v3_reports", 0))
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Top users")
    st.dataframe(pd.DataFrame(stats["top_users"], columns=["Username", "Plans"]), use_container_width=True, hide_index=True)
    st.subheader("Recent plans")
    st.dataframe(pd.DataFrame(stats["recent"], columns=["Username", "Title", "Business", "Score", "Created"]), use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    require_global_access()
    st.set_page_config(page_title=APP_NAME, page_icon="👑", layout="wide", initial_sidebar_state="expanded")
    inject_css()
    init_db()
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("username", "")
    st.session_state.setdefault("page", "Dashboard")
    if not st.session_state["logged_in"]:
        login_page()
        return

    username = st.session_state["username"]
    plan = get_user_plan(username)

    page_icons = {
        "Dashboard": "🏠",
        "New Empire Plan": "▣",
        "Opportunity Scanner": "⌕",
        "Empire Score Lab": "▥",
        "Revenue Planner": "⌁",
        "Progress CRM": "☑",
        "Marketplace Guide": "▢",
        "Branding Studio": "◉",
        "AI Co-Founder": "🤖",
        "Competitor Intelligence": "◎",
        "Empire Roadmap": "▰",
        "Business Blueprint": "▤",
        "Client Acquisition": "♟",
        "Sales Scripts": "💬",
        "Empire Memory": "▥",
        "Investor Mode": "$",
        "Saved Plans": "▱",
        "Admin": "🛡",
    }

    with st.sidebar:
        st.markdown(
            f"""
            <div class="side-brand">
                <div class="side-logo">👑</div>
                <div>
                    <div class="side-title">{APP_NAME}</div>
                    <div class="side-user">User: {username} • {plan.upper()}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        pages = ["Dashboard", "New Empire Plan", "Opportunity Scanner", "Empire Score Lab", "Revenue Planner", "Progress CRM", "Marketplace Guide", "Branding Studio", "AI Co-Founder", "Competitor Intelligence", "Empire Roadmap", "Business Blueprint", "Client Acquisition", "Sales Scripts", "Empire Memory", "Investor Mode", "Saved Plans"]
        for p in pages:
            label = f"{page_icons.get(p, '•')}   {p}"
            if st.button(label, use_container_width=True, key=f"nav_{p}"):
                st.session_state["page"] = p
                st.rerun()

        st.markdown('<div class="side-divider"></div>', unsafe_allow_html=True)
        if plan == "admin":
            if st.button(f"{page_icons['Admin']}   Admin", use_container_width=True, key="nav_admin"):
                st.session_state["page"] = "Admin"
                st.rerun()

        st.markdown('<div class="logout-gap"></div>', unsafe_allow_html=True)
        if st.button("↪   Logout", use_container_width=True, key="logout_btn"):
            st.session_state.clear()
            st.rerun()

    page = st.session_state["page"]
    if page == "Dashboard":
        dashboard_page(username)
    elif page == "New Empire Plan":
        new_plan_page(username)
    elif page == "Saved Plans":
        saved_plans_page(username)
    elif page == "Opportunity Scanner":
        opportunity_scanner_page(username)
    elif page == "Revenue Planner":
        revenue_planner_page(username)
    elif page == "Progress CRM":
        progress_crm_page(username)
    elif page == "Investor Mode":
        investor_mode_page(username)
    elif page == "Marketplace Guide":
        marketplace_guide_page(username)
    elif page == "Empire Score Lab":
        score_lab_page(username)
    elif page == "Competitor Intelligence":
        competitor_intelligence_page(username)
    elif page == "Empire Roadmap":
        empire_roadmap_page(username)
    elif page == "Business Blueprint":
        business_blueprint_page(username)
    elif page == "Client Acquisition":
        client_acquisition_page(username)
    elif page == "Sales Scripts":
        sales_scripts_page(username)
    elif page == "Empire Memory":
        empire_memory_page(username)
    elif page == "AI Co-Founder":
        cofounder_page(username)
    elif page == "Branding Studio":
        branding_page(username)
    elif page == "Admin":
        admin_page(username)
    else:
        dashboard_page(username)


if __name__ == "__main__":
    main()