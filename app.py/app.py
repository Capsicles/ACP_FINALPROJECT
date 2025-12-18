from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import random
import os
from datetime import datetime
import mysql.connector
from mysql.connector import Error

# Get the directory where this script is located
basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, 'templates')

app = Flask(__name__, template_folder=template_dir)
app.config['SECRET_KEY'] = 'game-secret-key'


DB_CONFIG = {
    'host': 'localhost',
    'database': 'hearmeout',  
    'user': 'root',
    'password': '',  
    'port': 3306
}

def get_db_connection():
    """Create and return database connection"""
    
    possible_names = ['hearmeout', 'hearmeout.db', 'hearmeout_db']
    
    for db_name in possible_names:
        try:
            config = DB_CONFIG.copy()
            config['database'] = db_name
            connection = mysql.connector.connect(**config)
            print(f"Successfully connected to database: {db_name}") 
         
            DB_CONFIG['database'] = db_name
            return connection
        except Error as e:
            print(f"Failed to connect to '{db_name}': {e}")
            continue
    
    try:
        root_config = DB_CONFIG.copy()
        root_config.pop('database', None)
        root_conn = mysql.connector.connect(**root_config)
        cur = root_conn.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS hearmeout_db CHARACTER SET utf8mb4")
        root_conn.commit()
        cur.close()
        root_conn.close()
        # Now connect to the newly created/ensured database
        cfg = DB_CONFIG.copy()
        cfg['database'] = 'hearmeout_db'
        created_conn = mysql.connector.connect(**cfg)
        DB_CONFIG['database'] = 'hearmeout_db'
        print("Created and connected to database: hearmeout_db")
        return created_conn
    except Error as e:
        print(f"Error: Could not connect or create database. Tried: {possible_names}. Reason: {e}")
        return None

def init_database():
    """Initialize database and create table if not exists"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    player_name VARCHAR(100) NOT NULL,
                    score INT NOT NULL,
                    game VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_score (score DESC),
                    INDEX idx_player (player_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Ensure user_id column exists for tying scores to registered users
            try:
                cursor.execute("""
                    ALTER TABLE leaderboard
                    ADD COLUMN IF NOT EXISTS user_id INT NULL,
                    ADD INDEX IF NOT EXISTS idx_user (user_id)
                """)
            except Exception as _:
                try:
                    # Fallback for MySQL versions without IF NOT EXISTS on ADD COLUMN
                    cursor.execute("SHOW COLUMNS FROM leaderboard LIKE 'user_id'")
                    if cursor.fetchone() is None:
                        cursor.execute("ALTER TABLE leaderboard ADD COLUMN user_id INT NULL")
                        cursor.execute("CREATE INDEX idx_user ON leaderboard (user_id)")
                except Exception as __:
                    pass
            # Create users table for authentication
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role ENUM('user','admin') NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Seed a default admin user if not present
            cursor.execute("SELECT id FROM users WHERE username=%s", ("admin",))
            row = cursor.fetchone()
            if not row:
                admin_pw = generate_password_hash("admin123")
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                    ("admin", admin_pw, "admin")
                )
            connection.commit()
            cursor.close()
            print("Database initialized successfully!")
        except Error as e:
            print(f"Error initializing database: {e}")
        finally:
            connection.close()


_db_initialized = False

@app.before_request
def ensure_db_initialized_once():
    global _db_initialized
    if not _db_initialized:
        try:
            init_database()
        except Exception as e:
            print(f"Database init on first request failed: {e}")
        _db_initialized = True

# Sample data for games 
KNOWLEDGE_QUESTIONS = [
    {'question': 'What color do you get when you mix red and white?', 'options': ['Pink', 'Purple', 'Orange', 'Brown'], 'correct': 0},
    {'question': 'Who wrote "Romeo and Juliet"?', 'options': ['Charles Dickens', 'William Shakespeare', 'Jane Austen', 'Mark Twain'], 'correct': 1},
    {'question': 'What is the capital of France?', 'options': ['Berlin', 'Madrid', 'Paris', 'Rome'], 'correct': 2},
    {'question': 'How many continents are there?', 'options': ['5', '6', '7', '8'], 'correct': 2},
    {'question': 'What is the largest ocean on Earth?', 'options': ['Atlantic', 'Indian', 'Arctic', 'Pacific'], 'correct': 3},
    {'question': 'What gas do plants absorb from the atmosphere?', 'options': ['Oxygen', 'Carbon Dioxide', 'Nitrogen', 'Hydrogen'], 'correct': 1},
    {'question': 'Who painted the Mona Lisa?', 'options': ['Vincent Van Gogh', 'Pablo Picasso', 'Leonardo Da Vinci', 'Michel Angelo'], 'correct': 2},
    {'question': 'What is the smallest prime number?', 'options': ['0', '1', '2', '3'], 'correct': 2},
    {'question': 'Which planet is known as the red planet?', 'options': ['Venus', 'Mars', 'Jupiter', 'Saturn'], 'correct': 1},
    {'question': 'How many sides does a hexagon have?', 'options': ['3', '6', '7', '8'], 'correct': 1},
    {'question': 'What is the chemical symbol for water?', 'options': ['O2', 'H2O', 'CO2', 'H2'], 'correct': 1},
    {'question': 'Who invented the telephone?', 'options': ['Thomas Edison', 'Alexander Graham Bell', 'Nikola Tesla', 'Benjamin Franklin'], 'correct': 1},
    {'question': 'What is the largest mammal in the world?', 'options': ['African Elephant', 'Blue Whale', 'Giraffe', 'Polar Bear'], 'correct': 1},
    {'question': 'How many days are in a leap year?', 'options': ['364', '365', '366', '367'], 'correct': 2},
    {'question': 'What is the freezing point of water in celsius?', 'options': ['-10°C', '0°C', '10°C', '32°C'], 'correct': 1},
    {'question': 'Which country is home to the kangaroo?', 'options': ['New Zealand', 'South Africa', 'Australia', 'Brazil'], 'correct': 2},
    {'question': 'What is the square root of 144?', 'options': ['10', '11', '12', '13'], 'correct': 2},
    {'question': 'Who was the first president of the United States?', 'options': ['Thomas Jefferson', 'George Washington', 'John Adams', 'Benjamin Franklin'], 'correct': 1},
    {'question': 'What is the main ingredient in guacamole?', 'options': ['Tomato', 'Avocado', 'Pepper', 'Onion'], 'correct': 1},
    {'question': 'How many bones are in the adult human body?', 'options': ['196', '206', '216', '226'], 'correct': 1},
]

STORIES = [
    {
        'text': 'In the heart of a dense, ancient forest, a young explorer named Lila set out to find the legendary Silver Spring. For days, she trekked beneath towering trees, listening to the songs of hidden birds and the rustle of unseen animals. One evening, as the sun dipped below the horizon, Lila stumbled upon a clearing bathed in moonlight. In the center, the Silver Spring sparkled, its waters glowing with an otherworldly light. Lila knelt to drink, feeling a surge of energy and clarity. She knew she had found something magical, a secret of the forest that would remain with her forever.',
        'questions': [
            {'question': 'What was Lila searching for?', 'options': ['A lost city', 'The Silver Spring', 'A hidden cave', 'A rare animal'], 'correct': 1},
            {'question': 'Where did Lila find the Silver Spring?', 'options': ['By a river', 'On a mountain', 'In a clearing', 'Near a village'], 'correct': 2},
            {'question': 'What time of day did Lila find the spring?', 'options': ['Morning', 'Noon', 'Evening', 'Night'], 'correct': 2},
            {'question': 'What did Lila feel after drinking from the spring?', 'options': ['Sleepy', 'Energized and clear', 'Hungry', 'Afraid'], 'correct': 1},
            {'question': 'What will Lila do with the secret?', 'options': ['Tell everyone', 'Forget it', 'Keep it forever', 'Sell it'], 'correct': 2}
        ]
    },
    {
        'text': 'On the edge of a bustling city, there was a small, neglected garden. Every day, an old man named Mr. Ramos tended to the plants, talking and singing to them. One spring, children from the neighborhood noticed the garden blooming with the brightest flowers they had ever seen. Curious, they joined Mr. Ramos, learning how to care for the soil and water the roots. By summer, the garden had become a place of laughter and friendship, teaching everyone that even the smallest patch of earth could bring a community together.',
        'questions': [
            {'question': 'Where was the garden located?', 'options': ['In a forest', 'On a rooftop', 'On the city edge', 'In a park'], 'correct': 2},
            {'question': 'Who took care of the garden?', 'options': ['Children', 'Mr. Ramos', 'A dog', 'The mayor'], 'correct': 1},
            {'question': 'What made the children join Mr. Ramos?', 'options': ['The bright flowers', 'Free food', 'A contest', 'Rain'], 'correct': 1},
            {'question': 'What did the children learn?', 'options': ['To play soccer', 'To care for plants', 'To build houses', 'To paint'], 'correct': 1},
            {'question': 'What did the garden become for the community?', 'options': ['A playground', 'A meeting place', 'A place of laughter and friendship', 'A school'], 'correct': 2}
        ]
    },
    {
        'text': 'Far across the ocean, on a tiny island, lived a girl named Amara who loved to collect seashells. One stormy night, a huge wave washed a mysterious, glowing shell onto the shore. When Amara picked it up, she heard a soft voice telling her the secrets of the sea. From that day, Amara could predict the weather and help her village prepare for storms. The glowing shell became her most treasured possession, a symbol of her bond with the ocean.',
        'questions': [
            {'question': 'Where did Amara live?', 'options': ['On a mountain', 'In a city', 'On an island', 'In a forest'], 'correct': 2},
            {'question': 'What did Amara collect?', 'options': ['Rocks', 'Flowers', 'Seashells', 'Coins'], 'correct': 2},
            {'question': 'What happened on the stormy night?', 'options': ['A boat arrived', 'A glowing shell appeared', 'A tree fell', 'A rainbow appeared'], 'correct': 1},
            {'question': 'What power did the shell give Amara?', 'options': ['Talking to animals', 'Predicting the weather', 'Flying', 'Finding treasure'], 'correct': 1},
            {'question': 'What did the shell symbolize?', 'options': ['Wealth', 'Danger', 'Bond with the ocean', 'Luck'], 'correct': 2}
        ]
    },
    {
        'text': 'In a quiet mountain village, a young boy named Mateo dreamed of flying. He spent his days watching birds and building wings from sticks and feathers. One windy afternoon, Mateo climbed the tallest hill, strapped on his wings, and leapt into the air. For a moment, he soared above the rooftops, feeling the rush of wind and freedom. Though he landed in a haystack, Mateo’s spirit soared higher than ever, inspiring others in the village to chase their own dreams.',
        'questions': [
            {'question': 'What was Mateo’s dream?', 'options': ['To swim', 'To fly', 'To run fast', 'To be a chef'], 'correct': 1},
            {'question': 'How did Mateo try to fly?', 'options': ['With a kite', 'With a balloon', 'With wings he built', 'With a plane'], 'correct': 2},
            {'question': 'Where did Mateo jump from?', 'options': ['A tree', 'A roof', 'A hill', 'A bridge'], 'correct': 2},
            {'question': 'Where did Mateo land?', 'options': ['In a river', 'In a haystack', 'On the ground', 'In a tree'], 'correct': 1},
            {'question': 'How did Mateo’s actions affect others?', 'options': ['They laughed', 'They were scared', 'They were inspired', 'They ignored him'], 'correct': 2}
        ]
    },
    {
        'text': 'Deep beneath the city streets, a clever mouse named Pip built a maze of tunnels and rooms. Pip invited other animals to join him, creating an underground community where everyone shared food and stories. When a flood threatened their home, Pip led the animals to safety using secret passages he had built. After the danger passed, the animals celebrated Pip’s bravery, and the underground city became a legend among creatures both above and below.',
        'questions': [
            {'question': 'Who was Pip?', 'options': ['A cat', 'A mouse', 'A bird', 'A rabbit'], 'correct': 1},
            {'question': 'What did Pip build?', 'options': ['A house', 'A maze of tunnels', 'A bridge', 'A boat'], 'correct': 1},
            {'question': 'What threatened the animals’ home?', 'options': ['Fire', 'Humans', 'Flood', 'Snow'], 'correct': 2},
            {'question': 'How did Pip save the animals?', 'options': ['Fought the flood', 'Used secret passages', 'Called for help', 'Built a dam'], 'correct': 1},
            {'question': 'What happened after the flood?', 'options': ['The animals left', 'Pip became a legend', 'They found treasure', 'Pip moved away'], 'correct': 1}
        ]
    }
]

RIDDLES = [
    {'riddle': 'I speak without a mouth and hear without ears. What am I?', 'answer': 'echo'},
    {'riddle': 'What has keys but can\'t open locks?', 'answer': 'piano'},
    {'riddle': 'What has a head and tail but no body?', 'answer': 'coin'},
    {'riddle': 'What gets wet while drying?', 'answer': 'towel'},
    {'riddle': 'What can travel around the world while staying in a corner?', 'answer': 'stamp'},
    {'riddle': 'What has hands but cannot clap?', 'answer': 'clock'},
    {'riddle': 'What has a neck but no head?', 'answer': 'bottle'},
    {'riddle': 'What has words but never speaks?', 'answer': 'book'},
    {'riddle': 'What has legs but doesn\'t walk?', 'answer': 'table'},
    {'riddle': 'What has teeth but cannot bite?', 'answer': 'comb'},
    {'riddle': 'What comes down but never goes up?', 'answer': 'rain'},
    {'riddle': 'What has an eye but cannot see?', 'answer': 'needle'},
    {'riddle': 'What can fill a room but takes up no space?', 'answer': 'light'},
    {'riddle': 'The more you take, the more you leave behind. What am I?', 'answer': 'footsteps'},
    {'riddle': 'What begins with T, ends with T, and has T in it?', 'answer': 'teapot'},
    {'riddle': 'What has four fingers and a thumb but is not alive?', 'answer': 'glove'},
    {'riddle': 'What runs but never walks?', 'answer': 'water'},
    {'riddle': 'What has a face and two hands but no arms or legs?', 'answer': 'clock'},
    {'riddle': 'What goes up but never comes down?', 'answer': 'age'},
    {'riddle': 'What has one foot but no legs?', 'answer': 'ruler'},
    ]

VOCAB =  [
{"word":"benevolent","definition":"well meaning and kindly","choices":["kind","hostile","bored","funny"],"correct":0},
{"word":"swift","definition":"moving very fast","choices":["stiff","quick","slow","calm"],"correct":1},
{"word":"eloquent","definition":"fluent or persuasive in speaking","choices":["silent","articulate","loud","confused"],"correct":1},
{"word":"abundant","definition":"existing in large quantities","choices":["scarce","tiny","empty","plentiful"],"correct":3},
{"word":"diligent","definition":"showing care and effort in work","choices":["lazy","tired","hardworking","angry"],"correct":2},
{"word":"transparent","definition":"easy to see through","choices":["opaque","colorful","bright","clear"],"correct":3},
{"word":"courageous","definition":"not afraid of danger","choices":["weak","brave","fearful","nervous"],"correct":1},
{"word":"serene","definition":"calm and peaceful","choices":["chaotic","excited","peaceful","loud"],"correct":2},
{"word":"resilient","definition":"able to recover quickly","choices":["tough","fragile","broken","weak"],"correct":0},
{"word":"meticulous","definition":"showing great attention to detail","choices":["careless","rushed","careful","sloppy"],"correct":2},
{"word":"vibrant","definition":"full of energy and life","choices":["quiet","boring","dull","lively"],"correct":3},
{"word":"skeptical","definition":"not easily convinced","choices":["naive","doubtful","trusting","hopeful"],"correct":1},
{"word":"profound","definition":"very great or intense","choices":["shallow","simple","deep","light"],"correct":2},
{"word":"innovative","definition":"featuring new methods","choices":["traditional","boring","creative","old"],"correct":2},
{"word":"gregarious","definition":"fond of company","choices":["quiet","sociable","shy","lonely"],"correct":1},
{"word":"pragmatic","definition":"dealing with things practically","choices":["practical","dreamy","idealistic","unrealistic"],"correct":0},
{"word":"tenacious","definition":"persistent and determined","choices":["quitting","giving up","determined","weak"],"correct":2},
{"word":"versatile","definition":"able to adapt to many functions","choices":["limited","flexible","rigid","inflexible"],"correct":1},
{"word":"zealous","definition":"having great energy for a cause","choices":["bored","enthusiastic","tired","apathetic"],"correct":1},
{"word":"tranquil","definition":"free from disturbance","choices":["noisy","calm","busy","chaotic"],"correct":1}

]


SOUNDS = [
    {'label': 'Rain', 'file': '/static/sounds/rain.mp3', 'choices': ['Ocean Waves', 'Rain', 'Wind Blowing'], 'correct': 1},
    {'label': 'Doorbell', 'file': '/static/sounds/doorbell.mp3', 'choices': ['Phone Ringing', 'Alarm Clock', 'Doorbell'], 'correct': 2},
    {'label': 'Dog Barking', 'file': '/static/sounds/dog.mp3', 'choices': ['Cat Meowing', 'Dog Barking', 'Baby Crying'], 'correct': 1},
    {'label': 'Cat Meowing', 'file': '/static/sounds/cat.mp3', 'choices': ['Cat Meowing', 'Dog Barking', 'Birds Chirping'], 'correct': 0},
    {'label': 'Car Horn', 'file': '/static/sounds/horn.mp3', 'choices': ['Alarm Clock', 'Car Horn', 'Ambulance Siren'], 'correct': 1},
    {'label': 'Phone Ringing', 'file': '/static/sounds/phone.mp3', 'choices': ['Phone Ringing', 'Alarm Clock', 'Microwave Beep'], 'correct': 0},
    {'label': 'Thunder', 'file': '/static/sounds/thunder.mp3', 'choices': ['Rain', 'Fire Crackling', 'Thunder'], 'correct': 2},
    {'label': 'Birds Chirping', 'file': '/static/sounds/birds.mp3', 'choices': ['Cat Meowing', 'Birds Chirping', 'Wind Blowing'], 'correct': 1},
    {'label': 'Fire Crackling', 'file': '/static/sounds/fire.mp3', 'choices': ['Ocean Waves', 'Thunder', 'Fire Crackling'], 'correct': 2},
    {'label': 'Ocean Waves', 'file': '/static/sounds/waves.mp3', 'choices': ['Ocean Waves', 'Rain', 'Wind Blowing'], 'correct': 0},
    {'label': 'Alarm Clock', 'file': '/static/sounds/alarm.mp3', 'choices': ['Rain', 'Alarm Clock', 'Ocean Waves'], 'correct': 1},
    {'label': 'Keyboard Typing', 'file': '/static/sounds/typing.mp3', 'choices': ['Footsteps', 'Clock Ticking', 'Keyboard Typing'], 'correct': 2},
    {'label': 'Baby Crying', 'file': '/static/sounds/baby.mp3', 'choices': ['Baby Crying', 'Cat Meowing', 'Dog Barking'], 'correct': 0},
    {'label': 'Ambulance Siren', 'file': '/static/sounds/siren.mp3', 'choices': ['Car Horn', 'Ambulance Siren', 'Train Whistle'], 'correct': 1},
    {'label': 'Footsteps', 'file': '/static/sounds/footsteps.mp3', 'choices': ['Footsteps', 'Keyboard Typing', 'Wind Blowing'], 'correct': 0},
    {'label': 'Wind Blowing', 'file': '/static/sounds/wind.mp3', 'choices': ['Ocean Waves', 'Wind Blowing', 'Rain'], 'correct': 1},
    {'label': 'Clock Ticking', 'file': '/static/sounds/tick.mp3', 'choices': ['Keyboard Typing', 'Clock Ticking', 'Footsteps'], 'correct': 1},
    {'label': 'Guitar Strumming', 'file': '/static/sounds/guitar.mp3', 'choices': ['Guitar Strumming', 'Fire Crackling', 'Birds Chirping'], 'correct': 0},
    {'label': 'Microwave Beep', 'file': '/static/sounds/microwave.mp3', 'choices': ['Phone Ringing', 'Microwave Beep', 'Alarm Clock'], 'correct': 1},
    {'label': 'Train Whistle', 'file': '/static/sounds/train.mp3', 'choices': ['Train Whistle', 'Car Horn', 'Ambulance Siren'], 'correct': 0}
]


@app.route('/')
def home():
    # Always land on login page
    return redirect(url_for('auth'))

@app.route('/home')
def home_page():
    return render_template('index.html', player_name=session.get('player_name', ''))

@app.route('/api/signin', methods=['POST'])
def signin():
    data = request.json or {}
    player_name = data.get('name', '').strip()
    if player_name:
        session['player_name'] = player_name
        return jsonify({'success': True, 'message': f'Welcome, {player_name}!', 'player_name': player_name})
    return jsonify({'success': False, 'message': 'Please enter your name'})

@app.route('/api/get-player', methods=['GET'])
def get_player():
    player_name = session.get('player_name', '')
    return jsonify({'player_name': player_name})

@app.route('/api/set-player-name', methods=['POST'])
def api_set_player_name():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if len(name) > 50:
        name = name[:50]
    session['player_name'] = name
    return jsonify({'success': True, 'player_name': name})

@app.route('/leaderboard')
def leaderboard():
    # Fetch registered users with aggregated total points, sorted by total (highest first), limit to top 50
    connection = get_db_connection()
    players = []
    
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT u.username AS name,
                       COALESCE(SUM(l.score), 0) AS score,
                       'All' AS game
                FROM users u
                LEFT JOIN leaderboard l ON l.user_id = u.id
                WHERE u.role = 'user'
                GROUP BY u.id
                ORDER BY score DESC
                LIMIT 50
            """)
            players = cursor.fetchall()
            print(f"Fetched {len(players)} players from database")  # Debug output
            cursor.close()
        except Error as e:
            print(f"Error fetching leaderboard: {e}")
            import traceback
            traceback.print_exc()
        finally:
            connection.close()
    else:
        print("Failed to connect to database!")  # Debug output
    
    return render_template('page.html', players=players)

@app.route('/api/leaderboard', methods=['GET'])
def api_leaderboard():
    game = (request.args.get('game') or '').strip()
    # Normalize 'All' selections
    if game.lower() in ('', 'all', 'all scores', '7'):
        game = 'All'

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database unavailable.'}), 500
    try:
        cur = conn.cursor(dictionary=True)
        if game == 'All':
            cur.execute(
                """
                SELECT u.username AS name,
                       COALESCE(SUM(l.score), 0) AS score,
                       'All' AS game
                FROM users u
                LEFT JOIN leaderboard l ON l.user_id = u.id
                WHERE u.role = 'user'
                GROUP BY u.id
                ORDER BY score DESC
                LIMIT 50
                """
            )
        else:
            cur.execute(
                """
                SELECT u.username AS name,
                       COALESCE(SUM(l.score), 0) AS score,
                       %s AS game
                FROM users u
                JOIN leaderboard l ON l.user_id = u.id AND l.game = %s
                WHERE u.role = 'user'
                GROUP BY u.id
                HAVING score > 0
                ORDER BY score DESC
                LIMIT 50
                """,
                (game, game)
            )
        rows = cur.fetchall()
        cur.close()
        return jsonify({'success': True, 'players': rows, 'game': game})
    except Error as e:
        print('api_leaderboard error:', e)
        return jsonify({'success': False, 'message': 'Query failed.'}), 500
    finally:
        conn.close()

@app.route('/api/leaderboard/games', methods=['GET'])
def api_leaderboard_games():
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'games': []})
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT game FROM leaderboard WHERE game IS NOT NULL AND game<>'' ORDER BY game ASC")
        games = [r[0] for r in cur.fetchall()]
        cur.close()
        # Ensure "All Scores" is present as final option for UI
        if 'All Scores' not in games:
            games.append('All Scores')
        return jsonify({'success': True, 'games': games})
    except Error as e:
        print('api_leaderboard_games error:', e)
        return jsonify({'success': False, 'games': []})
    finally:
        conn.close()

@app.route('/knowledge')
def knowledge():
    return render_template('knowledge.html', questions=KNOWLEDGE_QUESTIONS)


@app.route('/storytelling')
def storytelling():
    story = random.choice(STORIES)
    return render_template('storytelling.html', story=story)

@app.route('/riddle')
def riddle():
    # pass all riddles so frontend can cycle through them
    return render_template('riddle.html', riddles=RIDDLES)

@app.route('/vocabulary')
def vocabulary():
    return render_template('vocabulary.html', vocab=VOCAB)

@app.route('/sound-id')
def sound_id():
    import copy
    randomized_sounds = []
    for sound in SOUNDS:
        s = copy.deepcopy(sound)
        random.shuffle(s['choices'])
        randomized_sounds.append(s)
    return render_template('sound_identification.html', sounds=randomized_sounds)

@app.route('/math-quick')
def math_quick():
    return render_template('math_quick.html')

@app.route('/admin')
def admin():
    # Restrict access to admins
    if not session.get('user_id') or session.get('role') != 'admin':
        return redirect(url_for('auth'))
    return render_template('admin.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/about')
def about():
    return render_template('about.html')

# Serve images from the local images directory
@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory(os.path.join(basedir, 'images'), filename)

# Authentication routes
@app.route('/auth')
def auth():
    return render_template('auth.html')

@app.route('/settings')
def settings():
    if not session.get('user_id'):
        return redirect(url_for('auth'))
    return render_template('settings.html', player_name=session.get('player_name', ''), username=session.get('username'))

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400
    if len(username) < 3 or len(password) < 4:
        return jsonify({'success': False, 'message': 'Username must be ≥3 chars and password ≥4 chars.'}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database unavailable.'}), 500
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cur.fetchone():
            return jsonify({'success': False, 'message': 'Username already exists.'}), 409
        pw_hash = generate_password_hash(password)
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)", (username, pw_hash, 'user'))
        conn.commit()
        # Seed leaderboard with 0 points for this new user so they appear immediately
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        u = cur.fetchone()
        if u and u.get('id'):
            try:
                cur2 = conn.cursor()
                cur2.execute(
                    """
                    INSERT INTO leaderboard (user_id, player_name, score, game)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (u['id'], username, 0, 'All')
                )
                conn.commit()
                cur2.close()
            except Exception as _:
                conn.rollback()
        return jsonify({'success': True, 'message': 'Registration successful.'})
    except Error as e:
        print('Register error:', e)
        conn.rollback()
        return jsonify({'success': False, 'message': 'Registration failed.'}), 500
    finally:
        conn.close()

@app.route('/api/change-password', methods=['POST'])
def api_change_password():
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Not authenticated.'}), 401
    data = request.json or {}
    current_password = (data.get('current_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()
    if not current_password or not new_password:
        return jsonify({'success': False, 'message': 'Current and new password are required.'}), 400
    if len(new_password) < 4:
        return jsonify({'success': False, 'message': 'New password must be at least 4 characters.'}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database unavailable.'}), 500
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, password_hash FROM users WHERE id=%s", (session['user_id'],))
        user = cur.fetchone()
        if not user or not check_password_hash(user['password_hash'], current_password):
            return jsonify({'success': False, 'message': 'Current password is incorrect.'}), 401
        new_hash = generate_password_hash(new_password)
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, session['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Password updated.'})
    except Error as e:
        print('Change password error:', e)
        conn.rollback()
        return jsonify({'success': False, 'message': 'Password update failed.'}), 500
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database unavailable.'}), 500
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, password_hash, role FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({'success': True, 'message': 'Logged in.', 'role': user['role']})
    except Error as e:
        print('Login error:', e)
        return jsonify({'success': False, 'message': 'Login failed.'}), 500
    finally:
        conn.close()

@app.route('/api/admin-login', methods=['POST'])
def api_admin_login():
    # Reuse normal login but enforce admin role
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database unavailable.'}), 500
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, password_hash, role FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        if not user or not check_password_hash(user['password_hash'], password) or user['role'] != 'admin':
            return jsonify({'success': False, 'message': 'Invalid admin credentials.'}), 401
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({'success': True, 'message': 'Admin logged in.', 'role': user['role']})
    except Error as e:
        print('Admin login error:', e)
        return jsonify({'success': False, 'message': 'Admin login failed.'}), 500
    finally:
        conn.close()

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out.'}) if request.method == 'POST' else redirect(url_for('auth'))

@app.route('/api/admin/reset-scores', methods=['POST'])
def admin_reset_scores():
    if not session.get('user_id') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Admin privileges required.'}), 403
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database unavailable.'}), 500
    try:
        cur = conn.cursor(dictionary=True)
        # Clear all scores
        cur.execute("DELETE FROM leaderboard")
        conn.commit()
        # Repopulate zero entries for all regular users so they appear on the board
        cur.execute("SELECT id, username FROM users WHERE role='user'")
        users = cur.fetchall() or []
        if users:
            cur2 = conn.cursor()
            for u in users:
                cur2.execute(
                    "INSERT INTO leaderboard (user_id, player_name, score, game) VALUES (%s, %s, %s, %s)",
                    (u['id'], u['username'], 0, 'All')
                )
            conn.commit()
            cur2.close()
        cur.close()
        return jsonify({'success': True, 'message': 'All scores reset to 0 for all users.'})
    except Error as e:
        print('admin_reset_scores error:', e)
        conn.rollback()
        return jsonify({'success': False, 'message': 'Failed to reset scores.'}), 500
    finally:
        conn.close()

@app.route('/api/add-score', methods=['POST'])
def add_score():
    data = request.json or {}
    # Require login (user or admin)
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Login required to save scores.'}), 401

    provided_name = (data.get('name') or '').strip()
    try:
        score = int(data.get('score', 0))
    except Exception:
        score = 0
    game = (data.get('game') or 'Unknown').strip()

    target_user_id = session.get('user_id')
    target_player_name = session.get('username') or ''

    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'message': 'Database unavailable.'}), 500

    rank = None
    try:
        cur = connection.cursor(dictionary=True)
        # If admin and a username is provided, add score for that user
        if session.get('role') == 'admin' and provided_name:
            cur.execute("SELECT id, username FROM users WHERE username=%s", (provided_name,))
            tgt = cur.fetchone()
            if not tgt:
                cur.close()
                return jsonify({'success': False, 'message': 'User not found.'}), 404
            target_user_id = tgt['id']
            target_player_name = tgt['username']

        # Insert score tied to the target user
        cur2 = connection.cursor()
        cur2.execute(
            """
            INSERT INTO leaderboard (user_id, player_name, score, game)
            VALUES (%s, %s, %s, %s)
            """,
            (target_user_id, target_player_name, score, game)
        )
        connection.commit()
        cur2.close()

        # Compute total points for this user
        cur.execute(
            "SELECT COALESCE(SUM(score),0) AS total FROM leaderboard WHERE user_id=%s",
            (target_user_id,)
        )
        row = cur.fetchone()
        total_points = (row or {}).get('total', 0)

        # Compute rank among users by total points
        cur.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM (
                SELECT l.user_id, SUM(l.score) AS total
                FROM leaderboard l
                JOIN users u ON u.id = l.user_id
                WHERE l.user_id IS NOT NULL AND u.role = 'user'
                GROUP BY l.user_id
                HAVING total > %s
            ) t
            """,
            (total_points,)
        )
        r = cur.fetchone()
        if r and 'rank' in r:
            rank = r['rank']

        cur.close()
    except Error as e:
        print(f"Error adding score: {e}")
        connection.rollback()
        return jsonify({'success': False, 'message': 'Failed to add score.'}), 500
    finally:
        connection.close()

    return jsonify({
        'success': True,
        'message': f"Score added for {target_player_name}!",
        'player_name': target_player_name,
        'rank': rank
    })

if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5005)