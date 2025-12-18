from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    session,
    redirect,
    url_for,
    flash,
)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import re
import os
import json
from functools import wraps
from config import Config

app = Flask(__name__)
app.config.from_object(Config)


# Database setup
def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'player',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """
    )

    # Scores table (per game)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, game),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """
    )

    # Notifications table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT NOT NULL,
            category TEXT DEFAULT 'announcement',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """
    )

    # Reports/Feedback table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """
    )

    # Game status table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS game_status (
            game TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            maintenance_message TEXT
        )
    """
    )

    # Insert default game status
    games = ["knowledge_check", "math_quick", "riddle", "vocabulary", "storytelling"]
    for game in games:
        cursor.execute(
            "INSERT OR IGNORE INTO game_status (game, enabled) VALUES (?, ?)", (game, 1)
        )

    # Create admin user if not exists
    hashed_admin_pw = generate_password_hash(Config.ADMIN_PASSWORD)
    cursor.execute(
        """
        INSERT OR IGNORE INTO users (username, email, password, role) 
        VALUES (?, ?, ?, ?)
    """,
        ("Administrator", Config.ADMIN_EMAIL, hashed_admin_pw, "admin"),
    )

    conn.commit()
    conn.close()


# Initialize database
with app.app_context():
    init_db()


# Helper functions
def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@gmail\.com$"
    return re.match(pattern, email) is not None


def get_user_stats(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(DISTINCT game) as games_played FROM scores WHERE user_id = ?",
        (user_id,),
    )
    games_played = cursor.fetchone()["games_played"] or 0

    cursor.execute(
        "SELECT SUM(score) as total_score FROM scores WHERE user_id = ?", (user_id,)
    )
    total_score = cursor.fetchone()["total_score"] or 0

    cursor.execute(
        """
        SELECT game, MAX(score) as best_score, MAX(last_played) as last_played 
        FROM scores WHERE user_id = ? GROUP BY game
    """,
        (user_id,),
    )
    game_scores = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "games_played": games_played,
        "total_score": total_score,
        "game_scores": game_scores,
    }


def get_user_rank(user_id, game=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    if game:
        cursor.execute(
            """
            SELECT user_id, SUM(score) as total_score,
                   RANK() OVER (ORDER BY SUM(score) DESC) as rank
            FROM scores 
            WHERE game = ? 
            GROUP BY user_id
        """,
            (game,),
        )
    else:
        cursor.execute(
            """
            SELECT user_id, SUM(score) as total_score,
                   RANK() OVER (ORDER BY SUM(score) DESC) as rank
            FROM scores 
            GROUP BY user_id
        """
        )

    rankings = cursor.fetchall()
    user_rank = None

    for row in rankings:
        if row["user_id"] == user_id:
            user_rank = row["rank"]
            break

    conn.close()
    return user_rank


# Authentication decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("signin"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("signin"))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()
        conn.close()

        if not user or user["role"] != "admin":
            flash("Admin access required", "error")
            return redirect(url_for("player_menu"))

        return f(*args, **kwargs)

    return decorated_function


# Routes
@app.route("/")
def home():
    if "user_id" in session:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()
        conn.close()

        if user and user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("player_menu"))
    return redirect(url_for("signin"))


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if not user:
            conn.close()
            flash("Invalid email or password", "error")
            return render_template("auth/signin.html")

        if not check_password_hash(user["password"], password):
            conn.close()
            flash("Invalid email or password", "error")
            return render_template("auth/signin.html")

        if user["status"] != "active":
            conn.close()
            flash("Account is deactivated. Contact admin.", "error")
            return render_template("auth/signin.html")

        # Update last login
        cursor.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (user["id"],),
        )
        conn.commit()
        conn.close()

        # Set session
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user["email"]
        session["role"] = user["role"]

        if user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("player_menu"))

    return render_template("auth/signin.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not is_valid_email(email):
            flash("Please use a valid Gmail address", "error")
            return render_template("auth/signup.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters", "error")
            return render_template("auth/signup.html")

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("auth/signup.html")

        # Generate username from email
        username = email.split("@")[0]

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            flash("Email already registered", "error")
            return render_template("auth/signup.html")

        # Check if username already exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            # Add numbers to make unique
            import random

            username = f"{username}{random.randint(100, 999)}"

        # Create user
        hashed_password = generate_password_hash(password)
        cursor.execute(
            """
            INSERT INTO users (username, email, password) 
            VALUES (?, ?, ?)
        """,
            (username, email, hashed_password),
        )

        conn.commit()
        conn.close()

        flash("Account created successfully! Please sign in.", "success")
        return redirect(url_for("signin"))

    return render_template("auth/signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("signin"))


# Player Routes
@app.route("/player/menu")
@login_required
def player_menu():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get enabled games
    cursor.execute("SELECT game FROM game_status WHERE enabled = 1")
    enabled_games = [row["game"] for row in cursor.fetchall()]

    # Get user stats
    stats = get_user_stats(session["user_id"])

    # Get unread notifications count
    cursor.execute(
        "SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0",
        (session["user_id"],),
    )
    unread_notifications = cursor.fetchone()["count"]

    conn.close()

    return render_template(
        "player/menu.html",
        enabled_games=enabled_games,
        stats=stats,
        unread_notifications=unread_notifications,
    )


@app.route("/player/leaderboard")
@login_required
def player_leaderboard():
    game = request.args.get("game", "")

    conn = get_db_connection()
    cursor = conn.cursor()

    if game:
        cursor.execute(
            """
            SELECT u.username, SUM(s.score) as total_score, 
                   MAX(s.last_played) as last_played
            FROM scores s
            JOIN users u ON s.user_id = u.id
            WHERE s.game = ? AND u.status = 'active'
            GROUP BY u.id
            ORDER BY total_score DESC, last_played DESC
            LIMIT 50
        """,
            (game,),
        )
    else:
        cursor.execute(
            """
            SELECT u.username, SUM(s.score) as total_score,
                   MAX(s.last_played) as last_played
            FROM scores s
            JOIN users u ON s.user_id = u.id
            WHERE u.status = 'active'
            GROUP BY u.id
            ORDER BY total_score DESC, last_played DESC
            LIMIT 50
        """
        )

    leaderboard = [dict(row) for row in cursor.fetchall()]

    # Get user rank
    user_rank = get_user_rank(session["user_id"], game if game else None)

    conn.close()

    return render_template(
        "player/leaderboard.html",
        leaderboard=leaderboard,
        game=game,
        user_rank=user_rank,
    )


@app.route("/player/scores")
@login_required
def player_scores():
    stats = get_user_stats(session["user_id"])
    return render_template("player/scores.html", stats=stats)


@app.route("/player/report", methods=["GET", "POST"])
@login_required
def player_report():
    if request.method == "GET":
        return render_template("player/report.html")

    elif request.method == "POST":
        try:
            # Get JSON data from AJAX request
            data = request.get_json()
            message = data.get("message", "").strip()

            if not message:
                return jsonify({"success": False, "message": "Message cannot be empty"})

            conn = get_db_connection()
            cursor = conn.cursor()

            # Insert report
            cursor.execute(
                """
                INSERT INTO reports (user_id, message) 
                VALUES (?, ?)
            """,
                (session["user_id"], message),
            )

            # Also create a notification for admin
            cursor.execute(
                "SELECT username FROM users WHERE id = ?", (session["user_id"],)
            )
            user = cursor.fetchone()
            admin_message = f"Report from {user['username']}: {message}"

            cursor.execute(
                """
                INSERT INTO notifications (user_id, message, category)
                SELECT id, ?, 'report'
                FROM users WHERE role = 'admin'
            """,
                (admin_message,),
            )

            conn.commit()
            conn.close()

            return jsonify({"success": True})

        except Exception as e:
            print(f"Error submitting report: {e}")
            return jsonify({"success": False, "message": "An error occurred"})


@app.route("/player/notifications")
@login_required
def player_notifications():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC
        LIMIT 50
    """,
        (session["user_id"],),
    )

    notifications = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(notifications)


@app.route("/player/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE notifications 
        SET is_read = 1 
        WHERE user_id = ? AND is_read = 0
    """,
        (session["user_id"],),
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True})


@app.route("/player/update-username", methods=["POST"])
@login_required
def update_username():
    new_username = request.json.get("username", "").strip()

    if len(new_username) < 3:
        return jsonify(
            {"success": False, "message": "Username must be at least 3 characters"}
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if username exists
    cursor.execute(
        "SELECT id FROM users WHERE username = ? AND id != ?",
        (new_username, session["user_id"]),
    )
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Username already taken"})

    cursor.execute(
        "UPDATE users SET username = ? WHERE id = ?", (new_username, session["user_id"])
    )
    conn.commit()
    conn.close()

    session["username"] = new_username

    return jsonify({"success": True, "username": new_username})


# Game Routes
@app.route("/game/<game_name>")
@login_required
def game_page(game_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT enabled, maintenance_message FROM game_status WHERE game = ?",
        (game_name,),
    )
    game_status = cursor.fetchone()

    if not game_status or game_status["enabled"] == 0:
        conn.close()
        return render_template(
            f"games/{game_name}.html",
            disabled=True,
            message=(
                game_status["maintenance_message"]
                if game_status
                else "Game under maintenance"
            ),
        )

    conn.close()

    # Log game access without overwriting existing score
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scores (user_id, game, last_played)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, game) DO UPDATE SET last_played = CURRENT_TIMESTAMP
    """,
        (session["user_id"], game_name),
    )
    conn.commit()
    conn.close()

    return render_template(f"games/{game_name}.html")


@app.route("/api/submit-score", methods=["POST"])
@login_required
def submit_score():
    data = request.json
    game = data.get("game")
    score = data.get("score", 0)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scores (user_id, game, score, last_played)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, game) DO UPDATE SET score = score + excluded.score, last_played = CURRENT_TIMESTAMP
    """,
        (session["user_id"], game, score),
    )

    conn.commit()

    # return updated stats so frontend can refresh UI
    stats = get_user_stats(session["user_id"])
    conn.close()

    return jsonify({"success": True, "stats": stats})


@app.route("/api/add-score", methods=["POST"])
@login_required
def add_score():
    data = request.json
    score = data.get("score", 0)
    game = data.get("game", "")

    if not game:
        return jsonify({"success": False, "message": "Game not specified"})

    conn = get_db_connection()
    cursor = conn.cursor()
    # Insert or increment score without replacing the row (preserve other fields)
    cursor.execute(
        """
        INSERT INTO scores (user_id, game, score, last_played)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, game) DO UPDATE SET score = score + excluded.score, last_played = CURRENT_TIMESTAMP
    """,
        (session["user_id"], game, score),
    )

    conn.commit()

    # return updated stats so frontend can refresh UI
    stats = get_user_stats(session["user_id"])
    conn.close()

    return jsonify({"success": True, "stats": stats})


# Questions API Endpoint
@app.route("/api/get-questions/<game_type>")
@login_required
def get_questions(game_type):
    try:
        # Ensure the data directory exists
        if not os.path.exists("data"):
            os.makedirs("data")

        questions_file = "data/questions.json"

        # Check if file exists
        if not os.path.exists(questions_file):
            return jsonify({"error": "Questions file not found"}), 404

        # Load the questions
        with open(questions_file, "r") as f:
            questions_data = json.load(f)

        # Handle different game types
        if game_type in ["knowledge_check", "math_quick", "riddle", "vocabulary"]:
            if game_type in questions_data:
                # Format questions for MCQ games
                formatted_questions = []
                for q in questions_data[game_type]:
                    formatted_q = {
                        "question": q["question"],
                        "options": q["options"],
                        "correct": q["options"][q["answer"]],
                        "correct_index": q["answer"],
                        "points": 10,  # Default points for MCQ games
                    }
                    formatted_questions.append(formatted_q)
                return jsonify(formatted_questions)
            else:
                return jsonify({"error": "Game type not found"}), 404

        elif game_type == "storytelling":
            if game_type in questions_data:
                # For storytelling, return stories with questions
                formatted_stories = []
                for story_data in questions_data[game_type]:
                    formatted_story = {"story": story_data["story"], "questions": []}

                    # Format each question in the story
                    for q in story_data["questions"]:
                        formatted_q = {
                            "question": q["question"],
                            "options": q["options"],
                            "correct": q["options"][q["answer"]],
                            "correct_index": q["answer"],
                            "points": 5,  # Points per story question
                        }
                        formatted_story["questions"].append(formatted_q)

                    formatted_stories.append(formatted_story)

                return jsonify(formatted_stories)
            else:
                return jsonify({"error": "Game type not found"}), 404

        else:
            return jsonify({"error": "Invalid game type"}), 400

    except Exception as e:
        print(f"Error loading questions: {e}")
        return jsonify({"error": "Could not load questions"}), 500


# Admin Routes
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Stats
    cursor.execute("SELECT COUNT(*) as total_players FROM users WHERE role = 'player'")
    total_players = cursor.fetchone()["total_players"]

    cursor.execute(
        "SELECT COUNT(*) as active_players FROM users WHERE role = 'player' AND status = 'active'"
    )
    active_players = cursor.fetchone()["active_players"]

    cursor.execute(
        "SELECT COUNT(*) as archived_players FROM users WHERE role = 'player' AND status = 'archived'"
    )
    archived_players = cursor.fetchone()["archived_players"]

    cursor.execute(
        "SELECT COUNT(*) as total_reports FROM reports WHERE status = 'pending'"
    )
    pending_reports = cursor.fetchone()["total_reports"]

    conn.close()

    return render_template(
        "admin/dashboard.html",
        total_players=total_players,
        active_players=active_players,
        archived_players=archived_players,
        pending_reports=pending_reports,
    )


@app.route("/admin/players")
@admin_required
def admin_players():
    search = request.args.get("search", "")
    status_filter = request.args.get("status", "active")

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM users WHERE role = 'player'"
    params = []

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    if search:
        query += " AND (username LIKE ? OR email LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    players = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return render_template(
        "admin/players.html",
        players=players,
        search=search,
        status_filter=status_filter,
    )


@app.route("/admin/player/<int:player_id>/deactivate", methods=["POST"])
@admin_required
def deactivate_player(player_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE users SET status = 'archived' WHERE id = ?", (player_id,))

    # Send notification to player
    cursor.execute("SELECT username FROM users WHERE id = ?", (player_id,))
    player = cursor.fetchone()

    cursor.execute(
        """
        INSERT INTO notifications (user_id, message, category)
        VALUES (?, ?, 'warning')
    """,
        (player_id, "Your account has been deactivated by admin."),
    )

    conn.commit()
    conn.close()

    flash("Player deactivated successfully", "success")
    return redirect(url_for("admin_players"))


@app.route("/admin/player/<int:player_id>/reactivate", methods=["POST"])
@admin_required
def reactivate_player(player_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE users SET status = 'active' WHERE id = ?", (player_id,))

    # Send notification to player
    cursor.execute(
        """
        INSERT INTO notifications (user_id, message, category)
        VALUES (?, ?, 'announcement')
    """,
        (player_id, "Your account has been reactivated by admin."),
    )

    conn.commit()
    conn.close()

    flash("Player reactivated successfully", "success")
    return redirect(url_for("admin_archived"))


@app.route("/admin/archived")
@admin_required
def admin_archived():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE role = 'player' AND status = 'archived' ORDER BY created_at DESC"
    )
    players = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return render_template("admin/archived.html", players=players)


@app.route("/admin/leaderboard")
@admin_required
def admin_leaderboard():
    game = request.args.get("game", "")

    conn = get_db_connection()
    cursor = conn.cursor()

    if game:
        cursor.execute(
            """
            SELECT u.username, SUM(s.score) as total_score,
                   MAX(s.last_played) as last_played
            FROM scores s
            JOIN users u ON s.user_id = u.id
            WHERE s.game = ? AND u.status = 'active'
            GROUP BY u.id
            ORDER BY total_score DESC
            LIMIT 100
        """,
            (game,),
        )
    else:
        cursor.execute(
            """
            SELECT u.username, SUM(s.score) as total_score,
                   MAX(s.last_played) as last_played
            FROM scores s
            JOIN users u ON s.user_id = u.id
            WHERE u.status = 'active'
            GROUP BY u.id
            ORDER BY total_score DESC
            LIMIT 100
        """
        )

    leaderboard = [dict(row) for row in cursor.fetchall()]

    # Add rank with tie handling
    current_rank = 0
    previous_score = None
    same_rank_count = 0

    for i, player in enumerate(leaderboard):
        if player["total_score"] != previous_score:
            current_rank = i + 1
            same_rank_count = 0
        else:
            same_rank_count += 1

        player["rank"] = current_rank - same_rank_count
        previous_score = player["total_score"]

    conn.close()

    return render_template("admin/leaderboard.html", leaderboard=leaderboard, game=game)


@app.route("/admin/reset-scores", methods=["POST"])
@admin_required
def reset_scores():
    game = request.form.get("game", "")

    conn = get_db_connection()
    cursor = conn.cursor()

    if game == "all":
        cursor.execute("DELETE FROM scores")
        cursor.execute("SELECT id FROM users WHERE role = 'player'")
        players = [row["id"] for row in cursor.fetchall()]

        for player_id in players:
            cursor.execute(
                """
                INSERT INTO notifications (user_id, message, category)
                VALUES (?, ?, 'announcement')
            """,
                (player_id, "All scores have been reset by admin."),
            )

        flash("All scores reset successfully", "success")
    else:
        cursor.execute("DELETE FROM scores WHERE game = ?", (game,))

        cursor.execute(
            """
            SELECT DISTINCT user_id FROM scores WHERE game = ?
            UNION
            SELECT id FROM users WHERE role = 'player'
        """,
            (game,),
        )

        players = [row[0] for row in cursor.fetchall()]

        for player_id in players:
            cursor.execute(
                """
                INSERT INTO notifications (user_id, message, category)
                VALUES (?, ?, 'announcement')
            """,
                (player_id, f"Scores for {game} have been reset by admin."),
            )

        flash(f"Scores for {game} reset successfully", "success")

    conn.commit()
    conn.close()

    return redirect(url_for("admin_leaderboard"))


@app.route("/admin/notifications", methods=["GET", "POST"])
@admin_required
def admin_notifications():
    if request.method == "POST":
        target = request.form.get("target")
        user_id = request.form.get("user_id")
        category = request.form.get("category", "announcement")
        message = request.form.get("message", "").strip()

        if not message:
            flash("Message cannot be empty", "error")
            return redirect(url_for("admin_notifications"))

        conn = get_db_connection()
        cursor = conn.cursor()

        if target == "all":
            cursor.execute(
                "SELECT id FROM users WHERE role = 'player' AND status = 'active'"
            )
            players = [row["id"] for row in cursor.fetchall()]

            for player_id in players:
                cursor.execute(
                    """
                    INSERT INTO notifications (user_id, message, category)
                    VALUES (?, ?, ?)
                """,
                    (player_id, message, category),
                )
        else:
            cursor.execute(
                """
                INSERT INTO notifications (user_id, message, category)
                VALUES (?, ?, ?)
            """,
                (user_id, message, category),
            )

        conn.commit()
        conn.close()

        flash("Notification sent successfully", "success")
        return redirect(url_for("admin_notifications"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT n.*, u.username, u.email 
        FROM notifications n
        LEFT JOIN users u ON n.user_id = u.id
        ORDER BY n.created_at DESC
        LIMIT 100
    """
    )

    notifications = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        "SELECT id, username, email FROM users WHERE role = 'player' AND status = 'active' ORDER BY username"
    )
    players = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return render_template(
        "admin/notifications.html", notifications=notifications, players=players
    )


@app.route("/admin/notifications/mark-all-read", methods=["POST"])
@admin_required
def mark_all_notifications_read_admin():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE notifications 
        SET is_read = 1 
        WHERE is_read = 0
    """
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True})


@app.route("/admin/notifications/<int:notification_id>/mark-read", methods=["POST"])
@admin_required
def mark_notification_read(notification_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE notifications 
        SET is_read = 1 
        WHERE id = ?
    """,
        (notification_id,),
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True})


@app.route("/admin/reports")
@admin_required
def admin_reports():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT r.*, u.username, u.email 
        FROM reports r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC
    """
    )

    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template("admin/reports.html", reports=reports)


@app.route("/admin/report/<int:report_id>/resolve", methods=["POST"])
@admin_required
def resolve_report(report_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE reports SET status = 'resolved' WHERE id = ?
    """,
        (report_id,),
    )

    conn.commit()
    conn.close()

    flash("Report marked as resolved", "success")
    return redirect(url_for("admin_reports"))


@app.route("/admin/report/<int:report_id>/delete", methods=["POST"])
@admin_required
def delete_report(report_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM reports WHERE id = ?", (report_id,))

    conn.commit()
    conn.close()

    flash("Report deleted successfully", "success")
    return redirect(url_for("admin_reports"))


@app.route("/admin/game-status", methods=["GET", "POST"])
@admin_required
def admin_game_status():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        game = request.form.get("game")
        enabled = 1 if request.form.get("enabled") == "on" else 0
        maintenance_message = request.form.get("maintenance_message", "")

        cursor.execute(
            """
            INSERT OR REPLACE INTO game_status (game, enabled, maintenance_message)
            VALUES (?, ?, ?)
        """,
            (game, enabled, maintenance_message),
        )

        conn.commit()
        flash("Game status updated successfully", "success")

    cursor.execute("SELECT * FROM game_status ORDER BY game")
    games = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return render_template("admin/game_status.html", games=games)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5006)
