import os
from dotenv import load_dotenv
import gdown
import pickle
import requests
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
# import concurrent.futures
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt


# Load environment variables from the .env file
load_dotenv()


def download_similarity_model():
    file_path = 'similarity.pkl'
    if not os.path.exists(file_path):
        print("Downloading similarity model from Google Drive...")
        gdrive_url = os.getenv('GDRIVE_MODEL_URL')  # Fetch URL from .env
        gdown.download(gdrive_url, file_path, quiet=False)
    else:
        print("Similarity model already exists locally.")


# Call the download function
download_similarity_model()


# Initialize the Flask application
app = Flask(__name__)

# Configuration for the application
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable track modifications
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
GDRIVE_MODEL_URL = os.getenv('GDRIVE_MODEL_URL')



# Initialize database and authentication extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # Redirect to login page if user tries to access a protected route

# Specify the login view to be used when an unauthenticated user tries to access a protected route
login_manager.login_view = 'login'  # This tells Flask-Login to redirect unauthenticated users to 'login' route

# User model for authentication
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Load the pickled data for movie recommendations
movies_dict = pickle.load(open('movie_dict.pkl', 'rb'))
movies = pd.DataFrame(movies_dict)
similarity = pickle.load(open('similarity.pkl', 'rb'))



# Function to fetch movie poster from OMDb using movie title
def fetch_movie_poster(movie_title):
    url = f"http://www.omdbapi.com/?t={movie_title}&apikey={OMDB_API_KEY}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if 'Poster' in data and data['Poster'] != "N/A":
            return data['Poster']
    print(f"No poster found for the movie: {movie_title}")
    return None


def fetch_movie_trailer(movie_title):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={movie_title}+official+trailer&type=video&maxResults=1&key={YOUTUBE_API_KEY}"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            video_id = data['items'][0]['id']['videoId']
            return f"https://www.youtube.com/watch?v={video_id}"
    return None



# Function to recommend movies based on similarity
def recommend(movie):

    # Check if the movie is None or an empty string before proceeding
    if movie is None or movie.strip() == "":
        print("No movie selected.")  # Debug message for when no movie is selected
        return [], []  # Return empty recommendations and posters

    # Normalize user input: strip spaces and convert to lowercase
    movie = movie.strip().lower()

    # Normalize the movie titles in the DataFrame to avoid mismatches
    movies['title'] = movies['title'].str.strip().str.lower()

    # Check if movie is not in the list of movies
    if movie not in movies['title'].values:
        print(f"Movie '{movie}' not found in the list.")  # Debugging info
        return [], []
    
    movie_index = movies[movies['title'] == movie].index[0]
    distances = similarity[movie_index]
    movies_list = sorted(list(enumerate(distances)), reverse=True, key=lambda x: x[1])[1:21]

    recommended_movies = []
    recommended_posters = []
    trailers = []

    for i in movies_list:
        movie_title = movies.iloc[i[0]].title
        recommended_movies.append(movie_title)
        poster_url = fetch_movie_poster(movie_title)
        recommended_posters.append(poster_url)
        trailer_url = fetch_movie_trailer(movie_title)  # Fetch trailer URL
        trailers.append(trailer_url)

    return recommended_movies, recommended_posters, trailers

# Authentication loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Home route
@app.route('/')
def home():
    movie_list = movies['title'].values
    return render_template('index.html', movie_list=movie_list)

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check if the user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.')
            return redirect(url_for('register'))
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')  # Get the 'next' URL if it exists
            return redirect(next_page or url_for('home'))  # Redirect to 'next' or home
        else:
            flash('Login failed. Check username and password.', 'danger')
    
    return render_template('login.html')

# Route for the Collection page


# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Dashboard route
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', name=current_user.username)

# Recommendation route
@app.route('/recommend', methods=['POST'])
@login_required  # Require user to be logged in to access recommendations
def recommend_movies():
    selected_movie = request.form.get('movie')
    recommendations, posters, trailers = recommend(selected_movie)
    return render_template('index.html', 
                           movie_list=movies['title'].values, 
                           recommendations=recommendations, 
                           posters=posters,
                           trailers=trailers, 
                           selected_movie=selected_movie, 
                           zip=zip)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

    