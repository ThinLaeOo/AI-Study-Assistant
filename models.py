from app import db

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    confirmed = db.Column(db.Boolean, default=False)
    role = db.Column(db.Enum('student', 'admin'), default='student')

    # Relationships
    uploads = db.relationship('FileUpload', backref='user', lazy=True)


class FileUpload(db.Model):
    __tablename__ = 'file_uploads'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    summaries = db.relationship('Summary', backref='file', lazy=True)


class Summary(db.Model):
    __tablename__ = 'summaries'
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('file_uploads.id'), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    flashcards = db.relationship('Flashcard', backref='summary', lazy=True)
    quizzes = db.relationship('Quiz', backref='summary', lazy=True)


class Flashcard(db.Model):
    __tablename__ = 'flashcards'
    id = db.Column(db.Integer, primary_key=True)
    summary_id = db.Column(db.Integer, db.ForeignKey('summaries.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)


class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    summary_id = db.Column(db.Integer, db.ForeignKey('summaries.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(255))
    option_b = db.Column(db.String(255))
    option_c = db.Column(db.String(255))
