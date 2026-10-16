import os
import re
import random
import PyPDF2
import docx
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from nltk.tokenize import sent_tokenize
from rake_nltk import Rake
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'moonie_19'

ALLOWED_EXTENSIONS = {
    'txt',
    'pdf',
    'docx',
    'png',
    'jpg',
    'jpeg',
    'gif',
    'webp'
}
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize RAKE
r = Rake()

# MySQL connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/ai_study_assistant'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ---------------- Models ----------------

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    avatar = db.Column(db.String(255))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    confirmed = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), default='student')
    streak_count = db.Column(db.Integer, default=0)
    last_study_date = db.Column(db.Date)


class FileUpload(db.Model):
    __tablename__ = 'file_uploads'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))


class Quiz(db.Model):
    __tablename__ = 'quizzes'

    id = db.Column(db.Integer, primary_key=True)

    question = db.Column(db.Text)

    option_a = db.Column(db.String(255))
    option_b = db.Column(db.String(255))
    option_c = db.Column(db.String(255))
    option_d = db.Column(db.String(255))

    correct_answer = db.Column(db.String(255))

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

class Flashcard(db.Model):
    __tablename__ = 'flashcards'

    id = db.Column(db.Integer, primary_key=True)

    topic = db.Column(db.Text)
    explanation = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

class GenerationHistory(db.Model):
    __tablename__ = 'generation_history'

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id')
    )

    feature = db.Column(db.String(50))
    title = db.Column(db.String(255))

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

# ---------------- Utility Functions ----------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text(filepath):
    if filepath.endswith('.txt'):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    elif filepath.endswith('.pdf'):
        text = ""
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
        return text
    elif filepath.endswith('.docx'):
        doc = docx.Document(filepath)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""


def summarize_topic(paragraph):
    r.extract_keywords_from_text(paragraph)
    key_phrases = r.get_ranked_phrases()
    if key_phrases:
        return " ".join(key_phrases[0].split()[:6])
    return "General Concept"


def clean_keyword(kw):
    kw = re.sub(r'[^a-zA-Z0-9\s]', '', kw).strip()
    if len(kw.split()) < 2:
        return None
    return kw


def extract_main_concept(paragraph):
    r.extract_keywords_from_text(paragraph)
    key_phrases = r.get_ranked_phrases()
    for kw in key_phrases:
        cleaned = clean_keyword(kw)
        if cleaned:
            return cleaned
    return "this concept"


def generate_flashcards(text, min_cards=3, max_cards=10):
    paragraphs = sent_tokenize(text)
    paragraphs = paragraphs[:max_cards] if len(
        paragraphs) > max_cards else paragraphs
    while len(paragraphs) < min_cards:
        paragraphs.extend(paragraphs)
        paragraphs = paragraphs[:min_cards]

    cards = []
    for p in paragraphs:
        topic = summarize_topic(p)
        explanation = p.strip()
        cards.append({"question": topic, "answer": explanation})
    return cards


def generate_quizzes(text, min_q=3, max_q=10):
    paragraphs = sent_tokenize(text)
    paragraphs = paragraphs[:max_q] if len(paragraphs) > max_q else paragraphs
    while len(paragraphs) < min_q:
        paragraphs.extend(paragraphs)
        paragraphs = paragraphs[:min_q]

    quizzes = []
    for p in paragraphs:
        concept = extract_main_concept(p)
        question = f"Which of the following best describes {concept}?"
        correct_answer = p.strip()
        distractor_pool = ["Robotics", "Blockchain",
                           "Data Science", "Economics", "Physics", "Chemistry"]
        distractors = random.sample(distractor_pool, 3)
        options = [correct_answer] + distractors
        random.shuffle(options)

        quizzes.append(
            {"question": question, "options": options, "answer": correct_answer})
    return quizzes

# ---------------- Routes ----------------


@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            return redirect(url_for('user_dashboard'))
        return "Invalid credentials"
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        hashed_pw = generate_password_hash(password)
        new_user = User(name=name, email=email, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/user_dashboard')
def user_dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    recent_flashcards = Flashcard.query.order_by(
        Flashcard.id.desc()
    ).limit(5).all()

    recent_quizzes = Quiz.query.order_by(
        Quiz.id.desc()
    ).limit(5).all()

    return render_template(
        'user_dashboard.html',
        user=user,
        recent_flashcards=recent_flashcards,
        recent_quizzes=recent_quizzes
    )


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            text = extract_text(filepath)
            return render_template('summarize.html', summary=text[:200], uploaded_file=filename)
        return "Invalid file type"
    return render_template('upload.html')


@app.route('/summarize', methods=['GET', 'POST'])
def summarize():
    summary = None
    input_text = None
    uploaded_file = None
    if request.method == 'POST':
        file = request.files.get('file')
        text = request.form.get('text')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            extracted_text = extract_text(filepath)
            summary = extracted_text[:200]  # quick summary
            uploaded_file = filename
        elif text:
            summary = text[:200]
            input_text = text
        else:
            summary = "No input provided."
    return render_template('summarize.html', summary=summary, input_text=input_text, uploaded_file=uploaded_file)


@app.route('/quizzes', methods=['GET', 'POST'])
def quizzes():
    quizzes = []
    if request.method == 'POST':
        text = request.form.get('text')
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            text = extract_text(filepath)
        if text:
            generated_quizzes = generate_quizzes(text)

            for q in generated_quizzes:

                quiz = Quiz(
                    question=q['question'],
                    option_a=q['options'][0],
                    option_b=q['options'][1],
                    option_c=q['options'][2],
                    option_d=q['options'][3],
                    correct_answer=q['answer']
                )

                db.session.add(quiz)

            db.session.commit()
    return render_template('quizzes.html', quizzes=quizzes)


@app.route('/flashcards', methods=['GET', 'POST'])
def flashcards():

    cards = []

    if request.method == 'POST':

        text = request.form.get('text')
        file = request.files.get('file')

        if file and allowed_file(file.filename):

            filename = secure_filename(file.filename)

            filepath = os.path.join(
                app.config['UPLOAD_FOLDER'],
                filename
            )

            file.save(filepath)

            text = extract_text(filepath)

        if text:
            cards = generate_flashcards(text)

            for card in cards:

                flashcard = Flashcard(
                    topic=card['question'],
                    explanation=card['answer']
                )

                db.session.add(flashcard)

            db.session.commit()

    # ALWAYS RETURN SOMETHING
    return render_template(
        'flashcards.html',
        cards=cards
    )

@app.route('/settings', methods=['GET', 'POST'])
def settings():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    message = None

    if request.method == 'POST':

        # Email update
        new_email = request.form.get('email')

        if new_email and new_email != user.email:
            user.email = new_email
            message = "Email updated successfully."

        # Password update
        new_password = request.form.get('new_password')
        current_password = request.form.get('current_password')

        if new_password and current_password:

            if check_password_hash(user.password_hash, current_password):
                user.password_hash = generate_password_hash(new_password)
                message = "Password updated successfully."
            else:
                message = "Current password is incorrect."

        # Avatar upload
        avatar = request.files.get('avatar')

        if avatar and avatar.filename != "":

            upload_folder = os.path.join(
                app.root_path,
                'static',
                'uploads'
            )

            os.makedirs(upload_folder, exist_ok=True)

            filename = secure_filename(avatar.filename)

            avatar.save(
                os.path.join(upload_folder, filename)
            )

            user.avatar = filename

            message = "Profile updated successfully."

        db.session.commit()

    return render_template(
        'settings.html',
        user=user,
        message=message
    )

if __name__ == '__main__':
    # Wrap db.create_all() inside the app context
    with app.app_context():
        db.create_all()   # creates tables if they don't exist
    app.run(debug=True)
