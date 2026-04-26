# Final version for deployment with PostgreSQL
from flask import Flask, request, jsonify, send_from_directory
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
import os
import json
from datetime import datetime, timezone
import google.generativeai as genai

# --- Database Connection ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("FATAL: DATABASE_URL environment variable is not set.")

# --- AI Configuration ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY environment variable is not set. AI features will be disabled.")

app = Flask(__name__)

# --- Constants ---
REVIEW_MIN_CHARS = 50
REVIEW_MAX_CHARS = 500

# --- Utility Functions ---
def calculate_level(score):
    if score < 50: return 1
    if score < 150: return 2
    if score < 300: return 3
    if score < 500: return 4
    if score < 750: return 5
    return 6

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- Database Initialization Functions ---
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, username TEXT UNIQUE NOT NULL, join_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE IF NOT EXISTS leaderboard (id SERIAL PRIMARY KEY, user_id INTEGER UNIQUE, score INTEGER DEFAULT 0, level INTEGER DEFAULT 1, last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id))")
            cur.execute("CREATE TABLE IF NOT EXISTS daily_quests (id SERIAL PRIMARY KEY, title TEXT UNIQUE NOT NULL, description TEXT, points INTEGER DEFAULT 10)")
            cur.execute("CREATE TABLE IF NOT EXISTS user_daily_progress (id SERIAL PRIMARY KEY, user_id INTEGER, quest_id INTEGER, date_completed DATE DEFAULT CURRENT_DATE, submission_data TEXT, shared_on_feed BOOLEAN DEFAULT FALSE, FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (quest_id) REFERENCES daily_quests(id))")
            cur.execute("CREATE TABLE IF NOT EXISTS posts (id SERIAL PRIMARY KEY, user_id INTEGER, content TEXT, is_review BOOLEAN DEFAULT FALSE, timestamp TIMESTAMPTZ, FOREIGN KEY (user_id) REFERENCES users(id))")
            cur.execute("CREATE TABLE IF NOT EXISTS comments (id SERIAL PRIMARY KEY, user_id INTEGER, post_id INTEGER, content TEXT, timestamp TIMESTAMPTZ, FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (post_id) REFERENCES posts(id))")
            cur.execute("CREATE TABLE IF NOT EXISTS post_likes (id SERIAL PRIMARY KEY, user_id INTEGER, post_id INTEGER, FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (post_id) REFERENCES posts(id), UNIQUE(user_id, post_id))")
            cur.execute("CREATE TABLE IF NOT EXISTS achievements (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT NOT NULL, icon TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS user_achievements (id SERIAL PRIMARY KEY, user_id INTEGER, achievement_id INTEGER, date_unlocked TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (achievement_id) REFERENCES achievements(id), UNIQUE(user_id, achievement_id))")
        conn.commit()

def add_dummy_data():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            quests = [("Read for 30 minutes", "Dive into any book for half an hour.", 25), ("Write a book review", "Review a recent chapter or book.", 50), ("Explore a new genre", "Start reading a book in a genre you haven't tried.", 30), ("Organize your bookshelf", "Tidy up your physical or digital library.", 15)]
            for q in quests: cur.execute("INSERT INTO daily_quests (title, description, points) VALUES (%s, %s, %s) ON CONFLICT (title) DO NOTHING", q)
            
            achievements = [("Town Crier", "Share your first post on the community feed.", "megaphone"), ("First Review", "Complete the 'Write a book review' quest for the first time.", "star"), ("Quest Novice", "Complete 5 daily quests.", "scroll"), ("Bookworm", "Reach Level 3.", "book-open"), ("Social Butterfly", "Post 5 comments on the feed.", "users"), ("Review Enthusiast", "Share 3 of your book reviews to the feed.", "award"), ("Community Pillar", "Receive 10 likes across all your posts.", "heart")]
            for a in achievements: cur.execute("INSERT INTO achievements (name, description, icon) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING", a)
        conn.commit()

def setup_database():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users LIMIT 1")
    except (psycopg2.errors.UndefinedTable, psycopg2.ProgrammingError):
        init_db()
        add_dummy_data()

setup_database()

def check_and_award_achievement(cursor, user_id, achievement_name):
    cursor.execute("SELECT id FROM achievements WHERE name = %s", (achievement_name,))
    ach_row = cursor.fetchone()
    if not ach_row: return
    achievement_id = ach_row['id']
    
    cursor.execute("SELECT id FROM user_achievements WHERE user_id = %s AND achievement_id = %s", (user_id, achievement_id))
    if cursor.fetchone(): return

    cursor.execute("INSERT INTO user_achievements (user_id, achievement_id) VALUES (%s, %s)", (user_id, achievement_id))

# --- Static File & API Routes ---
@app.route('/')
def serve_index(): return send_from_directory('.', 'Index.html')
@app.route('/feedsbtn.html')
def serve_feeds_btn(): return send_from_directory('.', 'feedsbtn.html')
@app.route('/<path:path>')
def serve_file(path): return send_from_directory('.', path)

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    hashed_pw = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (email, password, username) VALUES (%s, %s, %s) RETURNING id", (data['email'], hashed_pw.decode('utf-8'), data['username']))
                user_id = cur.fetchone()[0]
                cur.execute("INSERT INTO leaderboard (user_id) VALUES (%s)", (user_id,))
            conn.commit()
        return jsonify({"status": "success", "message": "Registration successful!", "user_id": user_id, "username": data['username']}), 201
    except psycopg2.errors.UniqueViolation:
        return jsonify({"status": "error", "message": "Email or Username already taken."}), 409
    except (Exception, psycopg2.Error) as error:
        return jsonify({"status": "error", "message": "An unexpected database error occurred."}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (data['email'],))
            user = cur.fetchone()
    if user and bcrypt.checkpw(data['password'].encode('utf-8'), user['password'].encode('utf-8')):
        return jsonify({"status": "success", "message": "Login successful!", "user_id": user['id'], "username": user['username']})
    return jsonify({"status": "error", "message": "Invalid email or password!"}), 400

@app.route('/quests', methods=['GET'])
def get_quests():
    user_id = request.args.get('user_id', type=int)
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, title, description, points FROM daily_quests ORDER BY id DESC")
            all_quests = cur.fetchall()
            completed_ids = set()
            if user_id:
                cur.execute("SELECT quest_id FROM user_daily_progress WHERE user_id = %s AND date_completed = CURRENT_DATE", (user_id,))
                completed_ids = {row['quest_id'] for row in cur.fetchall()}
    quests = [dict(q, completed_today=(q['id'] in completed_ids)) for q in all_quests]
    return jsonify(quests)

@app.route('/submit_review', methods=['POST'])
def submit_review():
    data = request.get_json()
    user_id, quest_id, submission_text = data['user_id'], data['quest_id'], data.get('submission_text', '')
    
    if not (REVIEW_MIN_CHARS <= len(submission_text) <= REVIEW_MAX_CHARS):
        return jsonify({"status": "error", "message": f"Review must be between {REVIEW_MIN_CHARS} and {REVIEW_MAX_CHARS} characters."}), 400

    if GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            prompt = f"You are a reading platform moderator. Does this text look like a genuine attempt at writing a book review? Respond with strictly 'YES' or 'NO'. Text to evaluate: '{submission_text}'"
            response = model.generate_content(prompt)
            if "NO" in response.text.upper():
                return jsonify({"status": "error", "message": "AI detected this doesn't look like a real book review."}), 400
        except Exception as e:
            print(f"AI error: {e}")

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM user_daily_progress WHERE user_id = %s AND quest_id = %s AND date_completed = CURRENT_DATE", (user_id, quest_id))
            if cur.fetchone(): return jsonify({"status": "error", "message": "Quest already completed today!"}), 409

            cur.execute("SELECT points FROM daily_quests WHERE id = %s", (quest_id,))
            quest = cur.fetchone()
            if not quest: return jsonify({"status": "error", "message": "Quest not found."}), 404
            
            cur.execute("UPDATE leaderboard SET score = score + %s, last_updated = CURRENT_TIMESTAMP WHERE user_id = %s", (quest['points'], user_id))
            cur.execute("SELECT score, level FROM leaderboard WHERE user_id = %s", (user_id,))
            lb_data = cur.fetchone()
            new_level, level_message = calculate_level(lb_data['score']), ""
            if new_level > lb_data['level']:
                cur.execute("UPDATE leaderboard SET level = %s WHERE user_id = %s", (new_level, user_id))
                level_message = f" Congratulations! You reached Level {new_level}!"
                if new_level >= 3: check_and_award_achievement(cur, user_id, "Bookworm")

            cur.execute("INSERT INTO user_daily_progress (user_id, quest_id, submission_data) VALUES (%s, %s, %s)", (user_id, quest_id, submission_text))
            check_and_award_achievement(cur, user_id, "First Review")
            conn.commit()
            return jsonify({"status": "success", "message": f"Review submitted! +{quest['points']} points.{level_message}", "new_score": lb_data['score'], "new_level": new_level})

@app.route('/complete_quest', methods=['POST'])
def complete_quest():
    data = request.get_json()
    user_id, quest_id = data['user_id'], data['quest_id']
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM user_daily_progress WHERE user_id = %s AND quest_id = %s AND date_completed = CURRENT_DATE", (user_id, quest_id))
            if cur.fetchone(): return jsonify({"status": "error", "message": "Quest already completed today!"}), 409

            cur.execute("SELECT points FROM daily_quests WHERE id = %s", (quest_id,))
            quest = cur.fetchone()
            if not quest: return jsonify({"status": "error", "message": "Quest not found."}), 404
            
            cur.execute("UPDATE leaderboard SET score = score + %s, last_updated = CURRENT_TIMESTAMP WHERE user_id = %s", (quest['points'], user_id))
            cur.execute("SELECT score, level FROM leaderboard WHERE user_id = %s", (user_id,))
            lb_data = cur.fetchone()
            new_level, level_message = calculate_level(lb_data['score']), ""
            if new_level > lb_data['level']:
                cur.execute("UPDATE leaderboard SET level = %s WHERE user_id = %s", (new_level, user_id))
                level_message = f" Congratulations! You reached Level {new_level}!"
                if new_level >= 3: check_and_award_achievement(cur, user_id, "Bookworm")

            cur.execute("SELECT COUNT(*) as count FROM user_daily_progress WHERE user_id = %s", (user_id,))
            total_quests = cur.fetchone()['count']
            cur.execute("INSERT INTO user_daily_progress (user_id, quest_id) VALUES (%s, %s)", (user_id, quest_id))
            if total_quests == 4: check_and_award_achievement(cur, user_id, "Quest Novice")
            conn.commit()
            return jsonify({"status": "success", "message": f"Quest completed! +{quest['points']} points.{level_message}", "new_score": lb_data['score'], "new_level": new_level})

@app.route('/posts', methods=['GET', 'POST'])
def handle_posts():
    if request.method == 'POST':
        data = request.get_json()
        timestamp = datetime.now(timezone.utc)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO posts (user_id, content, is_review, timestamp) VALUES (%s, %s, %s, %s)", (data['user_id'], data['content'], data.get('is_review', False), timestamp))
                cur.execute("SELECT COUNT(*) as count FROM posts WHERE user_id = %s", (data['user_id'],))
                if cur.fetchone()[0] == 1: check_and_award_achievement(cur, data['user_id'], "Town Crier")
            conn.commit()
        return jsonify({"status": "success"}), 201

    user_id = request.args.get('user_id', 0, type=int)
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT p.id, p.content, p.timestamp, p.is_review, u.username as author,
                       (SELECT COUNT(*) FROM post_likes WHERE post_id = p.id) as like_count,
                       (SELECT COUNT(*) FROM comments WHERE post_id = p.id) as comment_count,
                       (SELECT COUNT(*) FROM post_likes WHERE post_id = p.id AND user_id = %s) > 0 as liked_by_user
                FROM posts p JOIN users u ON p.user_id = u.id ORDER BY p.timestamp DESC
            """, (user_id,))
            return jsonify(cur.fetchall())

# --- IDEA 2: AI Recommendations Route ---
@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    user_id = request.args.get('user_id', type=int)
    if not user_id: return jsonify({"status": "error", "message": "User ID required"}), 400

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT submission_data FROM user_daily_progress WHERE user_id = %s AND submission_data IS NOT NULL", (user_id,))
            reviews = cur.fetchall()

    if not reviews: return jsonify({"status": "error", "message": "You haven't written any reviews yet! Complete some review quests first."}), 400
    if not GEMINI_API_KEY: return jsonify({"status": "error", "message": "AI is disabled."}), 500

    past_reviews_text = "\n".join([r['submission_data'] for r in reviews])
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Based on the following book reviews, recommend 3 new books. Keep it short, a numbered list with title, author, and 1 sentence why.\n\nReviews:\n{past_reviews_text}"
        return jsonify({"status": "success", "recommendations": model.generate_content(prompt).text})
    except Exception as e:
        return jsonify({"status": "error", "message": "Failed to get recommendations."}), 500

# --- IDEA 3: Dynamic AI Quests Route ---
@app.route('/generate_surprise_quest', methods=['POST'])
def generate_surprise_quest():
    if not GEMINI_API_KEY: return jsonify({"status": "error", "message": "AI is disabled."}), 500
        
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = """
        Generate a unique, creative, and fun daily reading quest for a book app. 
        Return ONLY a valid JSON object. No markdown.
        Keys: "title" (catchy string), "description" (1-sentence string), "points" (integer between 15 and 50)
        """
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        quest_data = json.loads(clean_text)
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO daily_quests (title, description, points) VALUES (%s, %s, %s) ON CONFLICT (title) DO NOTHING RETURNING id",
                    (quest_data['title'], quest_data['description'], quest_data['points'])
                )
                new_quest = cur.fetchone()
            conn.commit()
        
        if not new_quest: return jsonify({"status": "error", "message": "Duplicate generated. Try again!"}), 409
        return jsonify({"status": "success", "message": "Quest generated!"})
    except Exception as e:
        return jsonify({"status": "error", "message": "Failed to generate AI quest."}), 500

@app.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT u.username, l.score, l.level FROM users u JOIN leaderboard l ON u.id = l.user_id ORDER BY l.score DESC, l.last_updated ASC")
            return jsonify(cur.fetchall())

@app.route('/achievements', methods=['GET'])
def get_achievements():
    user_id = request.args.get('user_id', type=int)
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT a.id, a.name, a.description, a.icon, CASE WHEN ua.user_id IS NOT NULL THEN 1 ELSE 0 END as unlocked FROM achievements a LEFT JOIN user_achievements ua ON a.id = ua.achievement_id AND ua.user_id = %s", (user_id,))
            return jsonify(cur.fetchall())

if __name__ == '__main__':
    app.run(debug=True)