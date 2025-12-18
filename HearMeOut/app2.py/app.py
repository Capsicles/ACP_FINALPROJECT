from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import random
import json
import re
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'game-secret-key'

# SQLite database setup
DATABASE = os.path.join(os.path.dirname(__file__), 'game_hub.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # Create DB and necessary tables if they don't exist
    first_time = not os.path.exists(DATABASE)
    conn = get_db_connection()
    cursor = conn.cursor()
    # users table with status column
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            role TEXT DEFAULT 'Player',
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # scores table for leaderboards (per game)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            score INTEGER NOT NULL,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    # notifications table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

def migrate_db():
    # Add missing columns if upgrading from older schema
    conn = get_db_connection()
    cursor = conn.cursor()
    # ensure users.status exists
    cursor.execute("PRAGMA table_info(users)")
    cols = [r['name'] for r in cursor.fetchall()]
    if 'status' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'Active'")
    if 'role' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'Player'")
    conn.commit()
    conn.close()

migrate_db()


def recompute_user_scores():
    """Recalculate users.score as SUM of scores table for data consistency."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # For each active user, compute sum
        cursor.execute("SELECT id FROM users")
        uids = [r['id'] for r in cursor.fetchall()]
        for uid in uids:
            cursor.execute('SELECT COALESCE(SUM(score),0) AS total FROM scores WHERE user_id = ?', (uid,))
            row = cursor.fetchone()
            total = row['total'] if row else 0
            cursor.execute('UPDATE users SET score = ? WHERE id = ?', (total, uid))
        conn.commit()
        conn.close()
    except Exception:
        pass

# Recompute on startup to fix any previous inconsistencies
recompute_user_scores()

@app.route("/")
def home():
    if 'user_email' not in session:
        return redirect(url_for('signin'))
    # fetch user score to display
    user_score = 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT score FROM users WHERE email = ?', (session.get('user_email'),))
        row = cursor.fetchone()
        if row:
            user_score = row['score'] or 0
        conn.close()
    except Exception:
        user_score = 0
    return render_template("index.html", user_score=user_score)

@app.route("/signup")
def signup():
    if 'user_email' in session:
        return redirect(url_for('home'))
    return render_template("signup.html")

@app.route("/signin")
def signin():
    if 'user_email' in session:
        return redirect(url_for('home'))
    return render_template("signin.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('signin'))

# Game routes
@app.route("/knowledge_check")
def knowledge_check():
    if 'user_email' not in session:
        return redirect(url_for('signin'))
    return render_template("knowledge_check.html")

@app.route("/math_quick")
def math_quick():
    if 'user_email' not in session:
        return redirect(url_for('signin'))
    return render_template("math_quick.html")

@app.route("/riddle")
def riddle():
    if 'user_email' not in session:
        return redirect(url_for('signin'))
    return render_template("riddle.html")

@app.route("/vocabulary")
def vocabulary():
    if 'user_email' not in session:
        return redirect(url_for('signin'))
    return render_template("vocabulary.html")

@app.route("/storytelling")
def storytelling():
    if 'user_email' not in session:
        return redirect(url_for('signin'))
    return render_template("storytelling.html")

@app.route("/leaderboard")
def leaderboard():
    if 'user_email' not in session:
        return redirect(url_for('signin'))
    game = request.args.get('game')
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor()
    if game:
        cursor.execute('''
            SELECT u.username, SUM(s.score) AS score, MAX(s.last_played) AS last_played, s.game
            FROM scores s JOIN users u ON s.user_id = u.id
            WHERE s.game = ? AND u.status = 'Active'
            GROUP BY u.id
            ORDER BY score DESC
            LIMIT ? OFFSET ?
        ''', (game, per_page, offset))
        # approximate total (number of distinct users who played this game)
        cursor.execute('SELECT COUNT(DISTINCT user_id) as cnt FROM scores s JOIN users u ON s.user_id = u.id WHERE s.game = ? AND u.status = \'Active\'', (game,))
        total = cursor.fetchone()['cnt']
    else:
        cursor.execute('''
            SELECT u.username, SUM(s.score) AS score, MAX(s.last_played) AS last_played
            FROM scores s JOIN users u ON s.user_id = u.id
            WHERE u.status = 'Active'
            GROUP BY u.id
            ORDER BY score DESC
            LIMIT ? OFFSET ?
        ''', (per_page, offset))
        cursor.execute('SELECT COUNT(*) as cnt FROM users WHERE status = \'Active\'')
        total = cursor.fetchone()['cnt']
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('leaderboard.html', rows=rows, game=game, page=page, total_pages=total_pages)

# API endpoints
@app.route("/api/get-questions/<game_type>")
def get_questions(game_type):
    count = request.args.get('count', 5, type=int)
    
    # Hardcoded questions to ensure they work
    if game_type == 'storytelling':
        stories = [
            {
                'story': 'Once upon a time, in a small village nestled between rolling hills, there lived a young girl named Lily who loved to explore. Every day after finishing her chores, she would venture into the nearby forest, discovering hidden paths and observing the wildlife. One sunny afternoon, while following a trail of colorful butterflies, Lily stumbled upon an ancient map hidden under a large oak tree. The map was old and fragile, with mysterious symbols marking a path to what appeared to be a hidden treasure. Excited by her discovery, Lily decided to follow the map and embark on an adventure that would change her life forever.',
                'questions': [
                    {
                        'question': 'What was the name of the young girl in the story?',
                        'options': ['Lucy', 'Lily', 'Laura', 'Lena'],
                        'answer': 1
                    },
                    {
                        'question': 'Where did Lily find the ancient map?',
                        'options': ['In a cave', 'Under an oak tree', 'By the river', 'In her backyard'],
                        'answer': 1
                    },
                    {
                        'question': 'What led Lily to discover the map?',
                        'options': ['A talking bird', 'Colorful butterflies', 'A dream', 'An old book'],
                        'answer': 1
                    },
                    {
                        'question': 'What did the map contain?',
                        'options': ['Secret recipes', 'Mysterious symbols', 'Family history', 'Weather patterns'],
                        'answer': 1
                    },
                    {
                        'question': 'What did Lily do after finding the map?',
                        'options': ['She forgot about it', 'She showed it to her friends', 'She followed the map on an adventure', 'She sold it at the market'],
                        'answer': 2
                    }
                ]
            }
        ]
        return jsonify(stories[:count])
    
    # For other game types, return empty for now
    return jsonify([])

# Authentication API endpoints
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@app.route("/api/signup", methods=['POST'])
def api_signup():
    data = request.json
    # username optional — will be generated from email if not provided
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    password_confirm = data.get('password_confirm', '')


    # Validation
    if not is_valid_email(email):
        return jsonify({'message': 'Invalid email format'}), 400

    if len(password) < 6:
        return jsonify({'message': 'Password must be at least 6 characters'}), 400

    if password != password_confirm:
        return jsonify({'message': 'Passwords do not match'}), 400

    if not re.search(r'\d', password):
        return jsonify({'message': 'Password must contain at least one number'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute('SELECT email FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            return jsonify({'message': 'Email already registered'}), 409
        # Generate username from email if not provided
        if not username:
            base = email.split('@')[0]
            # sanitize base (allow alnum and underscore)
            base = re.sub(r'[^a-zA-Z0-9_]', '', base)
            if len(base) < 3:
                base = base + str(random.randint(10,99))
            candidate = base
            i = 1
            while True:
                cursor.execute('SELECT id FROM users WHERE username = ?', (candidate,))
                if not cursor.fetchone():
                    username = candidate
                    break
                candidate = f"{base}{i}"
                i += 1

        # Check if username already exists (defensive)
        cursor.execute('SELECT username FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            return jsonify({'message': 'Username already taken'}), 409

        # Create user with role 'Player'
        hashed_password = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO users (username, email, password, score, role) VALUES (?, ?, ?, ?, ?)',
            (username, email, hashed_password, 0, 'Player')
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Account created successfully'}), 201
    
    except Exception as e:
        return jsonify({'message': 'An error occurred during signup'}), 500

@app.route("/api/signin", methods=['POST'])
def api_signin():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    remember = data.get('remember', False)

    try:
        # Check hardcoded admin first
        if email == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            # optionally set admin email in session
            session['user_email'] = email
            session['username'] = 'Administrator'
            if remember:
                session.permanent = True
                app.permanent_session_lifetime = 604800
            return jsonify({'success': True, 'message': 'Signed in as admin', 'admin': True}), 200
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'message': 'Invalid email or password'}), 401

        # Check if deactivated
        if user['status'] and user['status'].lower() == 'deactivated':
            return jsonify({'message': 'Account deactivated'}), 403

        # Check password
        if not check_password_hash(user['password'], password):
            return jsonify({'message': 'Invalid email or password'}), 401
        
        # Create session
        session['user_email'] = email
        session['username'] = user['username']
        if remember:
            session.permanent = True
            app.permanent_session_lifetime = 604800  # 7 days
        
        return jsonify({'success': True, 'message': 'Signed in successfully'}), 200
    
    except Exception as e:
        return jsonify({'message': 'An error occurred during signin'}), 500


def send_notification(user_id, message):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (user_id, message))
        conn.commit()
        conn.close()
    except Exception:
        pass


@app.route('/api/notifications')
def api_notifications():
    if 'user_email' not in session:
        return jsonify([])
    email = session['user_email']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify([])
    user_id = row['id']
    cursor.execute('SELECT id, message, is_read, created_at FROM notifications WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    notes = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(notes)


@app.route('/api/notifications/mark-read', methods=['POST'])
def api_notifications_mark_read():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    data = request.get_json() or {}
    email = session.get('user_email')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404
    user_id = row['id']

    # Mark all notifications for the user as read
    if data.get('all'):
        cursor.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    # Mark a single notification id (if it belongs to the user)
    nid = data.get('id')
    try:
        nid = int(nid)
    except Exception:
        nid = None

    if nid:
        cursor.execute('SELECT id FROM notifications WHERE id = ? AND user_id = ?', (nid, user_id))
        if cursor.fetchone():
            cursor.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (nid,))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        else:
            conn.close()
            return jsonify({'success': False, 'message': 'Notification not found'}), 404

    conn.close()
    return jsonify({'success': False, 'message': 'No action taken'}), 400


@app.route('/api/change-username', methods=['POST'])
def api_change_username():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    data = request.get_json() or {}
    new_username = (data.get('username') or '').strip()
    if not new_username or len(new_username) < 3:
        return jsonify({'success': False, 'message': 'Username must be at least 3 characters'}), 400
    # sanitize: allow letters, numbers, underscore, dash
    if not re.match(r'^[A-Za-z0-9_\-]+$', new_username):
        return jsonify({'success': False, 'message': 'Username contains invalid characters'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    # check uniqueness
    cursor.execute('SELECT id FROM users WHERE username = ? AND email != ?', (new_username, session.get('user_email')))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Username already taken'}), 409

    # update
    try:
        cursor.execute('UPDATE users SET username = ? WHERE email = ?', (new_username, session.get('user_email')))
        conn.commit()
        conn.close()
        session['username'] = new_username
        return jsonify({'success': True, 'message': 'Username updated', 'username': new_username}), 200
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': 'Could not update username'}), 500

# ---------------------- Admin Section ----------------------

ADMIN_USERNAME = 'admin@gmail.com'
ADMIN_PASSWORD = 'admin123'

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapped


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        # accept either 'email' or legacy 'username' form field
        u = request.form.get('email') or request.form.get('username')
        p = request.form.get('password')
        if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_panel'))
        return render_template('admin_login.html', error='Invalid credentials')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    # Clear admin and user session data and send to shared signin page
    session.pop('is_admin', None)
    session.pop('user_email', None)
    session.pop('username', None)
    return redirect(url_for('signin'))


@app.route('/admin')
@admin_required
def admin_panel():
    return render_template('admin_panel.html')


@app.route('/admin/recompute-scores', methods=['POST'])
@admin_required
def admin_recompute_scores():
    recompute_user_scores()
    return redirect(url_for('admin_panel'))


@app.route('/admin/db-check')
@admin_required
def admin_db_check():
    conn = get_db_connection()
    cursor = conn.cursor()
    # find mismatches where users.score != sum(scores)
    cursor.execute('SELECT id, username, email, score FROM users')
    users = [dict(r) for r in cursor.fetchall()]
    mismatches = []
    for u in users:
        uid = u['id']
        cursor.execute('SELECT COALESCE(SUM(score),0) as total FROM scores WHERE user_id = ?', (uid,))
        total = cursor.fetchone()['total']
        if (u['score'] or 0) != total:
            mismatches.append({'id': uid, 'username': u['username'], 'email': u['email'], 'users_score': u['score'], 'computed_total': total})
    conn.close()
    return render_template('admin_db_check.html', mismatches=mismatches)


@app.route('/admin/players')
@admin_required
def admin_players():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, status, created_at FROM users ORDER BY created_at DESC')
    players = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('admin_players.html', players=players)


@app.route('/admin/deactivate/<int:user_id>', methods=['POST'])
@admin_required
def admin_deactivate(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET status = ? WHERE id = ?', ('Deactivated', user_id))
    conn.commit()
    # send notification
    send_notification(user_id, 'Your account has been deactivated by admin.')
    conn.close()
    return redirect(url_for('admin_players'))


@app.route('/admin/archive')
@admin_required
def admin_archive():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, status, created_at FROM users WHERE status = 'Deactivated' ORDER BY created_at DESC")
    archived = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('admin_archive.html', players=archived)


@app.route('/admin/reactivate/<int:user_id>', methods=['POST'])
@admin_required
def admin_reactivate(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET status = ? WHERE id = ?', ('Active', user_id))
    conn.commit()
    send_notification(user_id, 'Your account has been reactivated by admin.')
    conn.close()
    return redirect(url_for('admin_archive'))


@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT n.id, n.message, n.is_read, n.created_at, u.username, u.email
        FROM notifications n LEFT JOIN users u ON n.user_id = u.id
        ORDER BY n.created_at DESC
    ''')
    notes = [dict(r) for r in cursor.fetchall()]
    # also load active users for the send-notification form
    cursor.execute("SELECT id, username, email FROM users WHERE status = 'Active' ORDER BY username")
    users = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('admin_notifications.html', notes=notes, users=users)


@app.route('/admin/send-notification', methods=['POST'])
@admin_required
def admin_send_notification():
    target = request.form.get('target')
    user_id = request.form.get('user_id')
    message = request.form.get('message', '').strip()
    game = request.form.get('game')
    if not message:
        return redirect(url_for('admin_notifications'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if target == 'user' and user_id:
        try:
            uid = int(user_id)
            cursor.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (uid, message))
        except Exception:
            pass
    else:
        # send to all active users (or for a game message we still notify all players)
        cursor.execute("SELECT id FROM users WHERE status = 'Active'")
        uids = [r['id'] for r in cursor.fetchall()]
        for uid in uids:
            try:
                cursor.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (uid, message))
            except Exception:
                pass

    conn.commit()
    conn.close()
    return redirect(url_for('admin_notifications'))


@app.route('/admin/seed-notifications', methods=['POST'])
@admin_required
def admin_seed_notifications():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Try to find a user named 'player1'
    cursor.execute("SELECT id FROM users WHERE username = ? LIMIT 1", ('player1',))
    row = cursor.fetchone()
    if row:
        player1_id = row['id']
        cursor.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (player1_id, "Player1: I'm worried my account shows incorrect scores after the last reset — can you check?"))

    # Send admin/system messages to all active users
    cursor.execute("SELECT id FROM users WHERE status = 'Active'")
    uids = [r['id'] for r in cursor.fetchall()]
    for uid in uids:
        try:
            cursor.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (uid, 'Admin (system): All scores have been reset. Your progress has been set to zero across all games.'))
            cursor.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (uid, 'Admin (game): Your Knowledge Check scores have been reset by an administrator. Please contact support if you think this was a mistake.'))
        except Exception:
            pass

    conn.commit()
    conn.close()
    return redirect(url_for('admin_notifications'))


@app.route('/admin/leaderboard')
@admin_required
def admin_leaderboard():
    game = request.args.get('game')
    conn = get_db_connection()
    cursor = conn.cursor()
    if game:
        # aggregate per-user total score for the given game
        cursor.execute('''
            SELECT u.username, SUM(s.score) AS score, MAX(s.last_played) AS last_played, s.game
            FROM scores s JOIN users u ON s.user_id = u.id
            WHERE s.game = ? AND u.status = 'Active'
            GROUP BY u.id
            ORDER BY score DESC
        ''', (game,))
    else:
        # aggregate across all games per user
        cursor.execute('''
            SELECT u.username, SUM(s.score) AS score, MAX(s.last_played) AS last_played
            FROM scores s JOIN users u ON s.user_id = u.id
            WHERE u.status = 'Active'
            GROUP BY u.id
            ORDER BY score DESC
        ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('admin_leaderboard.html', rows=rows, game=game)


@app.route('/admin/reset-scores', methods=['POST'])
@admin_required
def admin_reset_scores():
    game = request.form.get('game')
    conn = get_db_connection()
    cursor = conn.cursor()
    if game and game != 'all':
        # find affected users first
        cursor.execute('SELECT DISTINCT user_id FROM scores WHERE game = ?', (game,))
        users = [r['user_id'] for r in cursor.fetchall()]
        cursor.execute('UPDATE scores SET score = 0 WHERE game = ?', (game,))
        for uid in users:
            send_notification(uid, f'Scores for game {game} have been reset by admin.')
    else:
        cursor.execute('SELECT DISTINCT user_id FROM scores')
        users = [r['user_id'] for r in cursor.fetchall()]
        cursor.execute('UPDATE scores SET score = 0')
        for uid in users:
            send_notification(uid, 'All scores have been reset by admin.')
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))


@app.route('/api/add-score', methods=['POST'])
def api_add_score():
    data = request.json
    player_email = data.get('email') or session.get('user_email')
    score = int(data.get('score', 0))
    game = data.get('game', 'Unknown')
    # find user
    conn = get_db_connection()
    cursor = conn.cursor()
    if not player_email:
        conn.close()
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    cursor.execute('SELECT id, status FROM users WHERE email = ?', (player_email,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404
    if user['status'] and user['status'].lower() == 'deactivated':
        conn.close()
        return jsonify({'success': False, 'message': 'Account deactivated'}), 403
    user_id = user['id']
    cursor.execute('INSERT INTO scores (user_id, game, score, last_played) VALUES (?, ?, ?, CURRENT_TIMESTAMP)', (user_id, game, score))
    # update cumulative score on users table
    try:
        cursor.execute('UPDATE users SET score = COALESCE(score,0) + ? WHERE id = ?', (score, user_id))
    except Exception:
        pass
    conn.commit()
    conn.close()
    return jsonify({'success': True})


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5005)