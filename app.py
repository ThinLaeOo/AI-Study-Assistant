import os
import re
import random
import PyPDF2
import docx
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
from flask import (
    request, render_template, redirect,
    url_for, session, flash, abort
)
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from nltk.tokenize import sent_tokenize
from rake_nltk import Rake
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from flask_mail import Mail, Message

app = Flask(__name__)
# Email Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

mail = Mail(app)

app.config['SECRET_KEY'] = 'moonie_19'
csrf = CSRFProtect(app)

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
app.config['UPLOAD_FOLDER'] = os.path.join(
    app.root_path,
    'uploads'
)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    filename = db.Column(
        db.String(255),
        nullable=False
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False
    )


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


def summarize_text(text, max_sentences=5):
    """
    Extractive summary:
    ranks source sentences using TF-IDF scores,
    then returns selected sentences in source order.
    """
    if not text or not text.strip():
        return ""

    sentences = sent_tokenize(text)

    # Remove blank and duplicate sentences.
    unique_sentences = []
    seen = set()

    for sentence in sentences:
        sentence = sentence.strip()
        normalized = sentence.casefold()

        if sentence and normalized not in seen:
            unique_sentences.append(sentence)
            seen.add(normalized)

    if not unique_sentences:
        return ""

    if len(unique_sentences) <= max_sentences:
        return " ".join(unique_sentences)

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000
        )

        sentence_matrix = vectorizer.fit_transform(
            unique_sentences
        )

        # Sum the TF-IDF weights in each sentence.
        sentence_scores = sentence_matrix.sum(axis=1).A1

        # Select the highest-scoring sentences.
        ranked_indices = sorted(
            range(len(unique_sentences)),
            key=lambda i: sentence_scores[i],
            reverse=True
        )

        selected_indices = sorted(
            ranked_indices[:max_sentences]
        )

        return " ".join(
            unique_sentences[i] for i in selected_indices
        )

    except ValueError:
        # Handles text containing no usable vocabulary.
        return " ".join(unique_sentences[:max_sentences])

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
    """
    Generate source-grounded flashcards from
    definition-style sentences.

    min_cards is retained for compatibility,
    but we do not invent or duplicate cards
    to reach that number.
    """
    if not text or not text.strip():
        return []

    sentences = sent_tokenize(text)
    cards = []
    seen_questions = set()

    # Match definitions such as:
    # "Machine learning is a branch of AI."
    # "Neural networks are computational models."
    # "Photosynthesis refers to the process..."
    definition_pattern = re.compile(
        r"^(.{3,80}?)\s+"
        r"(is|are|refers to|means)\s+"
        r"(.+?)[.!?]?$",
        re.IGNORECASE
    )

    for sentence in sentences:
        sentence = sentence.strip()

        if len(sentence.split()) < 6:
            continue

        match = definition_pattern.match(sentence)

        if not match:
            continue

        concept = match.group(1).strip()
        verb = match.group(2).lower()
        definition = match.group(3).strip().rstrip(".!?")

        # Avoid excessively long or vague concepts.
        if len(concept.split()) > 8:
            continue

        if len(definition.split()) < 4:
            continue

        if verb == "are":
            question = f"What are {concept}?"
        else:
            question = f"What is {concept}?"

        normalized = question.casefold()

        if normalized in seen_questions:
            continue

        cards.append({
            "question": question,
            "answer": definition + "."
        })

        seen_questions.add(normalized)

        if len(cards) >= max_cards:
            break

    return cards



def generate_quizzes(text, min_q=3, max_q=10):
    """
    Generate multiple-choice definition questions
    using concepts found in the source text.

    Returns fewer questions when the source does
    not contain enough distinct definitions.
    """
    if not text or not text.strip():
        return []

    # Reuse the tested flashcard extraction function.
    cards = generate_flashcards(
        text,
        min_cards=0,
        max_cards=50
    )

    # Each flashcard contains a question and answer.
    # Extract the original concept from its question.
    concepts = []

    for card in cards:
        question = card["question"].strip()

        match = re.match(
            r"^What (?:is|are) (.+?)\?$",
            question,
            re.IGNORECASE
        )

        if not match:
            continue

        concept = match.group(1).strip()
        definition = card["answer"].strip()

        if not concept or not definition:
            continue

        concepts.append({
            "concept": concept,
            "definition": definition
        })

    # Remove duplicate concept names.
    unique_concepts = []
    seen = set()

    for item in concepts:
        key = item["concept"].casefold()

        if key not in seen:
            unique_concepts.append(item)
            seen.add(key)

    # Four distinct concepts are required to build
    # four distinct answer options.
    if len(unique_concepts) < 4:
        return []

    quizzes = []

    for item in unique_concepts:
        correct_answer = item["concept"]

        # Select three other source concepts.
        distractor_candidates = [
            other["concept"]
            for other in unique_concepts
            if other["concept"].casefold()
            != correct_answer.casefold()
        ]

        distractors = random.sample(
            distractor_candidates, 3
        )

        options = [correct_answer] + distractors
        random.shuffle(options)

        
        definition = item["definition"].rstrip(".!?")

        question_templates = [
            f"Which term is described as: '{definition}'?",
            f"What concept is defined as: '{definition}'?",
            f"Which of the following concepts best matches "
            f"this description: '{definition}'?",
            f"Identify the concept associated with "
            f"the following definition: '{definition}'."
        ]

        question = question_templates[
            len(quizzes) % len(question_templates)
        ]


        quizzes.append({
            "question": question,
            "options": options,
            "answer": correct_answer
        })

        if len(quizzes) >= max_q:
            break

    return quizzes

def get_current_admin():
    user_id = session.get("user_id")

    if not user_id:
        abort(401)

    admin = db.session.get(User, user_id)

    if not admin or admin.role != "admin":
        abort(403)

    return admin


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

        if user and check_password_hash(
            user.password_hash,
            password
        ):

            session['user_id'] = user.id
            session['role'] = user.role

            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))

            return redirect(url_for('user_dashboard'))

    return render_template('login.html')

def is_admin():
    return session.get('role') == 'admin'

# ---------------- Registration and Logout ----------------


@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Validate input
        if not name or not email or not password:
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('register'))

        if len(password) < 8:
            flash('Password must contain at least 8 characters.', 'danger')
            return redirect(url_for('register'))

        if len(name) > 100 or len(email) > 120:
            flash('Name or email is too long.', 'danger')
            return redirect(url_for('register'))

        # Check for existing email
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash('This email is already registered.', 'warning')
            return redirect(url_for('register'))

        # Create account
        hashed_pw = generate_password_hash(password)

        new_user = User(
            name=name,
            email=email,
            password_hash=hashed_pw,
            role='student'
        )

        try:
            db.session.add(new_user)
            db.session.commit()

        except IntegrityError:
            db.session.rollback()
            flash('This email is already registered.', 'warning')
            return redirect(url_for('register'))

        # Send welcome email
        try:
            msg = Message(
                subject='Welcome to AI Study Assistant!',
                recipients=[email]
            )

            msg.body = f"""
                Hello {name},

                Welcome to AI Study Assistant!

                Your account has been registered successfully.

                You can now use our learning features:

                - Summarize your study notes
                - Generate flashcards
                - Practice with quizzes

                We hope you enjoy your learning experience.

                Best regards,
                AI Study Assistant Team
                """

            mail.send(msg)

            flash(
                'Registration successful! '
                'A welcome email has been sent.',
                'success'
            )

        except Exception:
            app.logger.exception('Welcome email failed')

            flash(
                'Your account was created successfully, '
                'but the welcome email could not be sent.',
                'warning'
            )

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

    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    # Load the student's previously uploaded files
    previous_files = FileUpload.query.filter_by(
        user_id=user_id
    ).order_by(
        FileUpload.id.desc()
    ).all()

    if request.method == 'POST':

        selected_file_id = request.form.get(
            'previous_file_id', ''
        ).strip()

        file = request.files.get('file')

        # OPTION 1: Upload a new document
        if file and file.filename:

            if not allowed_file(file.filename):
                flash('Unsupported file format.', 'danger')
                return redirect(url_for('upload'))

            original_filename = secure_filename(file.filename)

            if not original_filename:
                flash('Invalid filename.', 'danger')
                return redirect(url_for('upload'))

            extension = original_filename.rsplit(
                '.', 1
            )[-1].lower()

            # Prevent overwriting existing uploads
            stored_filename = (
                f"{uuid.uuid4().hex}.{extension}"
            )

            os.makedirs(
                app.config['UPLOAD_FOLDER'],
                exist_ok=True
            )

            filepath = os.path.join(
                app.config['UPLOAD_FOLDER'],
                stored_filename
            )

            try:
                file.save(filepath)

                text = extract_text(filepath)
                summary = summarize_text(text)

                # Register the upload in MySQL
                new_record = FileUpload(
                    filename=stored_filename,
                    user_id=user_id
                )

                db.session.add(new_record)
                db.session.commit()

            except Exception:
                db.session.rollback()

                if os.path.exists(filepath):
                    os.remove(filepath)

                app.logger.exception('Upload failed')

                flash(
                    'Unable to process the document.',
                    'danger'
                )
                return redirect(url_for('upload'))

            if not summary:
                summary = (
                    "No readable text was extracted "
                    "from this file. Please try a "
                    "text-based PDF, DOCX, or TXT file."
                )

            return render_template(
                'summarize.html',
                summary=summary,
                uploaded_file=original_filename
            )

        # OPTION 2: Select a previously uploaded document
        elif selected_file_id:

            try:
                file_id = int(selected_file_id)
            except ValueError:
                flash('Invalid file selection.', 'danger')
                return redirect(url_for('upload'))

            # Prevent access to another student's files
            record = FileUpload.query.filter_by(
                id=file_id,
                user_id=user_id
            ).first()

            if not record:
                flash('File not found.', 'danger')
                return redirect(url_for('upload'))

            # Ensure the stored filename is safe
            if os.path.basename(record.filename) != record.filename:
                flash('Invalid stored filename.', 'danger')
                return redirect(url_for('upload'))

            filepath = os.path.join(
                app.config['UPLOAD_FOLDER'],
                record.filename
            )

            if not os.path.isfile(filepath):
                flash(
                    'The selected document is missing.',
                    'warning'
                )
                return redirect(url_for('upload'))

            try:
                text = extract_text(filepath)
                summary = summarize_text(text)

            except Exception:
                app.logger.exception(
                    'Failed to process previous upload'
                )

                flash(
                    'Unable to process the selected document.',
                    'danger'
                )
                return redirect(url_for('upload'))

            if not summary:
                summary = (
                    'No readable text was extracted '
                    'from this document.'
                )

            return render_template(
                'summarize.html',
                summary=summary,
                uploaded_file=record.filename
            )

        else:
            flash(
                'Please upload or select a document.',
                'warning'
            )
            return redirect(url_for('upload'))

    return render_template(
        'upload.html',
        previous_files=previous_files
    )


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
            summary = summarize_text(extracted_text)
            uploaded_file = filename
        elif text:
            summary = summarize_text(text)
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

            quizzes = generated_quizzes

            if not generated_quizzes:
                return render_template(
                    "quizzes.html",
                    quizzes=[],
                    error=(
                        "Not enough distinct definitions were found. "
                        "Please provide notes containing at least "
                        "four clearly defined concepts."
                    )
                )

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


@app.route('/admin/dashboard')
def admin_dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return redirect(url_for('user_dashboard'))

    total_users = User.query.count()
    total_files = FileUpload.query.count()

    recent_logins = 0
    alerts = 0

    recent_activities = GenerationHistory.query.order_by(
        GenerationHistory.created_at.desc()
    ).limit(5).all()

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_files=total_files,
        recent_logins=recent_logins,
        alerts=alerts,
        recent_activities=recent_activities
    )



@app.route("/admin/users")
def manage_users():
    admin = get_current_admin()

    search = request.args.get("search", "").strip()

    query = User.query

    if search:
        query = query.filter(
            or_(
                User.name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    users = query.order_by(User.id.desc()).all()

    return render_template(
        "manage_users.html",
        users=users,
        search=search,
        current_admin_id=admin.id
    )


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    user = db.session.get(User, user_id)

    if not user:
        return redirect(url_for("login"))

    if user.role != "admin":
        abort(403)

    if request.method == "POST":

        action = request.form.get("action")

        if action == "update_avatar":

            avatar = request.files.get("avatar")

            if not avatar or not avatar.filename:
                flash("Please select an image.", "warning")
                return redirect(url_for("admin_settings"))

            allowed_extensions = {
                "png", "jpg", "jpeg", "webp"
            }

            filename = secure_filename(avatar.filename)
            extension = (
                filename.rsplit(".", 1)[-1].lower()
                if "." in filename else ""
            )

            if extension not in allowed_extensions:
                flash("Invalid image format.", "danger")
                return redirect(url_for("admin_settings"))

            # Limit the avatar to 2 MB.
            avatar.stream.seek(0, os.SEEK_END)
            file_size = avatar.stream.tell()
            avatar.stream.seek(0)

            if file_size > 2 * 1024 * 1024:
                flash("Image must be smaller than 2 MB.", "danger")
                return redirect(url_for("admin_settings"))

            # Check the actual image format, not only its extension.
            from PIL import Image, UnidentifiedImageError

            try:
                image = Image.open(avatar.stream)
                image.verify()
                avatar.stream.seek(0)

                image = Image.open(avatar.stream)
                image.load()

                if image.format not in {
                    "PNG", "JPEG", "WEBP"
                }:
                    raise ValueError("Unsupported image format")

                # Re-encode the image to a safe, standard format.
                image = image.convert("RGB")

            except (
                UnidentifiedImageError,
                OSError,
                ValueError
            ):
                flash("Please upload a valid image.", "danger")
                return redirect(url_for("admin_settings"))

            upload_folder = os.path.join(
                app.static_folder,
                "uploads"
            )

            os.makedirs(upload_folder, exist_ok=True)

            new_filename = f"{uuid.uuid4().hex}.jpg"

            filepath = os.path.join(
                upload_folder,
                new_filename
            )

            image.thumbnail((512, 512))
            image.save(filepath, format="JPEG", quality=85)

            # Store only the filename in MySQL.
            user.avatar = new_filename

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                os.remove(filepath)
                flash("Could not update avatar.", "danger")
                return redirect(url_for("admin_settings"))

            flash("Profile picture updated!", "success")
            return redirect(url_for("admin_settings"))

    return render_template(
        "admin_settings.html",
        user=user
    )


@app.route("/admin/users/<int:user_id>/edit",
           methods=["POST"])
def update_user(user_id):
    admin = get_current_admin()

    user = db.session.get(User, user_id)

    if not user:
        abort(404)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", user.role).strip()

    if not name or not email or "@" not in email:
        flash("Please enter a valid name and email.", "danger")
        return redirect(url_for("manage_users"))

    if len(name) > 100 or len(email) > 120:
        flash("Name or email is too long.", "danger")
        return redirect(url_for("manage_users"))

    if role not in ("admin", "student") and user.id != admin.id:
        flash("Invalid user role.", "danger")
        return redirect(url_for("manage_users"))

    existing = User.query.filter(
        User.email == email,
        User.id != user.id
    ).first()

    if existing:
        flash("Email is already in use.", "warning")
        return redirect(url_for("manage_users"))

    user.name = name
    user.email = email

    # Prevent changing your own admin role.
    if user.id != admin.id:
        user.role = role

    try:
        db.session.commit()
        flash("User updated successfully.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Could not update user.", "danger")

    return redirect(url_for("manage_users"))


@app.route("/admin/users/<int:user_id>/delete",
           methods=["POST"])
def delete_user(user_id):
    admin = get_current_admin()

    user = db.session.get(User, user_id)

    if not user:
        abort(404)

    if user.id == admin.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("manage_users"))

    # Avoid deleting users who still own records.
    has_files = FileUpload.query.filter_by(
        user_id=user.id
    ).first() is not None

    has_history = GenerationHistory.query.filter_by(
        user_id=user.id
    ).first() is not None

    if has_files or has_history:
        flash(
            "This user has associated records. "
            "Account deletion has been blocked.",
            "warning"
        )
        return redirect(url_for("manage_users"))

    try:
        db.session.delete(user)
        db.session.commit()
        flash("User deleted successfully.", "success")
    except IntegrityError:
        db.session.rollback()
        flash(
            "User has related database records "
            "and cannot be deleted yet.",
            "danger"
        )

    return redirect(url_for("manage_users"))


# ---------------- Manage Files ----------------

@app.route("/admin/files")
def manage_files():
    get_current_admin()

    files = FileUpload.query.order_by(
        FileUpload.id.desc()
    ).all()

    owner_ids = {
        file.user_id
        for file in files
        if file.user_id is not None
    }

    users = User.query.filter(
        User.id.in_(owner_ids)
    ).all() if owner_ids else []

    owners = {
        user.id: user.name
        for user in users
    }

    return render_template(
        "manage_files.html",
        files=files,
        owners=owners
    )


@app.route("/admin/files/<int:file_id>/delete",
           methods=["POST"])
def delete_file(file_id):
    get_current_admin()

    file = db.session.get(FileUpload, file_id)

    if not file:
        abort(404)

    # Delete only the database record for now.
    # Do not remove the physical file because
    # filenames may be shared by multiple uploads.
    try:
        db.session.delete(file)
        db.session.commit()
        flash("File record deleted.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Could not delete file record.", "danger")

    return redirect(url_for("manage_files"))


if __name__ == '__main__':
    # Wrap db.create_all() inside the app context
    with app.app_context():
        db.create_all()   # creates tables if they don't exist
    app.run(debug=True)
