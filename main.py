import os
import pathlib
import requests
import json
import math
from datetime import datetime
import win32com.client
import pythoncom
import string
import random

from flask import Flask, abort, render_template, url_for, request, session, redirect, flash
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import true
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import InputRequired, Email, Length
from werkzeug.security import generate_password_hash,check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
from google.oauth2 import id_token
from flask_ckeditor import CKEditor
from werkzeug.utils import secure_filename



with open('config.json', encoding="utf8") as c:
    params = json.load(c)["params"]

local_server = params['local_server']
app = Flask("Tech Bytes")
app.secret_key = params['secret-key']  # This is a super secret key that should not be easy to guess
app.config['UPLOAD_FOLDER'] = params['upload_location']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Add ckeditor
app.config['CKEDITOR_PKG_TYPE'] = 'standard'
ckeditor = CKEditor(app)

if(local_server):
    app.config['SQLALCHEMY_DATABASE_URI'] = params['local_uri']
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = params['prod_uri']

GOOGLE_CLIENT_ID = params['google-client-id']
client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")
flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_uri = "http://127.0.0.1:5000/callback"                         
             )

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Characters to generate password from
characters = list(string.ascii_letters + string.digits + "!@#$%^&*()")


Bootstrap(app)
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class LoginForm(FlaskForm):
    username = StringField('username', validators=[InputRequired(), Length(min=4, max=15)])
    password = PasswordField('password', validators=[InputRequired(), Length(min=8, max=80)])
    remember = BooleanField('remember me')
    
class RegisterForm(FlaskForm):
    email = StringField('email', validators=[InputRequired(), Email(message='Invalid email'), Length(max=50)])
    username = StringField('username', validators=[InputRequired(), Length(min=4, max=15)])
    name = StringField('name', validators=[InputRequired(), Length(min=4, max=30)])
    password = PasswordField('password', validators=[InputRequired(), Length(min=8, max=80)])
    
class Users(UserMixin, db.Model):
    def get_id(self):
           return (self.sno)
    sno = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(50), nullable=False, unique=True)
    username = db.Column(db.String(15), nullable=False, unique=True)
    name = db.Column(db.String(30), nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(6), nullable=False)

class Contacts(db.Model):
    sno = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    phone_num = db.Column(db.String(12), nullable=False)
    msg = db.Column(db.String(120), nullable=False)
    date = db.Column(db.String(12), nullable=True)
    email = db.Column(db.String(20), nullable=False)


class Posts(db.Model):
    sno = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(255), nullable=False)
    content = db.Column(db.String(120), nullable=False)
    tagline = db.Column(db.String(120), nullable=False)
    date = db.Column(db.String(12), nullable=True)
    img_file = db.Column(db.String(200), nullable=True)
    posted_by = db.Column(db.String(50), nullable=False)

# Random Password Generator
def generate_random_password():
    length = params['random-password-length']
    random.shuffle(characters)
    password = [random.choice(characters) for i in range(length)]
    return "".join(password)   

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))


@app.route("/")
def home():
    posts = Posts.query.order_by(Posts.date.desc()).all()
    last = math.ceil(len(posts)/int(params['no_of_posts']))
    page = request.args.get('page')
    if(not str(page).isnumeric()):
        page = 1
    page = int(page)
    posts = posts[(page-1)*int(params['no_of_posts']): (page-1)*int(params['no_of_posts'])+ int(params['no_of_posts'])]
    
    #Pagination Logic
    if (page==1):
        prev = "#"
        next = "/?page="+ str(page+1)
    elif(page==last):
        prev = "/?page=" + str(page - 1)
        next = "#"
    else:
        prev = "/?page=" + str(page - 1)
        next = "/?page=" + str(page + 1)
    posts_posted_by = [post.posted_by.split(":")[1].split(" ")[0] for post in posts]
    return render_template('index.html', params=params, posts=posts, posts_posted_by = posts_posted_by, prev=prev, next=next)


@app.route("/post/<string:post_slug>", methods=['GET'])
def post_route(post_slug):
    post = Posts.query.filter_by(slug=post_slug).first()
    posted_by = post.posted_by.split(":")[1].split(" ")[0]
    return render_template('post.html', params=params, post=post, posted_by=posted_by)

@app.route("/about")
def about():
    return render_template('about.html', params=params)

def send_email(mailTo, mailFrom, mailBody):
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch('outlook.application')
    mail = outlook.CreateItem(0)
    mail.To = mailTo
    mail.Subject = 'New message from ' + mailFrom
    mail.Body = mailBody
    mail.Send()
    
@app.route("/contact", methods = ['GET', 'POST'])
def contact():
    if(request.method=='POST'):
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        message = request.form.get('message')
        entry = Contacts(name=name, phone_num = phone, msg = message, date= datetime.now(),email = email )
        try:
            db.session.add(entry)
            db.session.commit()
            send_email(params['gmail-user'], name, message + "\n\n" + "Contact:\n" + phone + "\n" + email)
            flash("Thanks for contacting us. We will get back to you soon...", "success")
        except Exception as e:
            print(e)
            flash("Uh Oh!. Something went wrong. Can you try resubmitting the form for us?")
        
    return render_template('contact.html', params=params)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    
    if form.validate_on_submit():
        user = Users.query.filter_by(username=form.username.data).first()
        if user:
            if check_password_hash(user.password, form.password.data):
                login_user(user, remember=form.remember.data)
                return redirect(url_for('dashboard'))
        # flash("Invalid username or password!", "danger")
    return render_template('login.html', form=form, login_image=params['login_image'], sign_in_btn_name=params['signInBtnName'])

#OAuth
@app.route('/oAuthLogin')
def oAuthLogin():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    flow.fetch_token(authorization_response = request.url)
    
    if not session["state"] == request.args["state"]:
        abort(500) # State does not match!
        
    credentials = flow.credentials
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session = cached_session)
    
    id_info = id_token.verify_oauth2_token(
        id_token = credentials.id_token,
        request = token_request,
        audience = GOOGLE_CLIENT_ID
    )
    
    username = id_info.get("sub")
    if(len(username) > 15):
        username = username[0:15]
    else:
        username = username
    user = Users.query.filter_by(username=username).first()
    if not user:
        # If user doesn't exist..create user
        hashed_password = generate_password_hash(generate_random_password(), "sha256")
        user = Users(username=username, name=id_info.get("name"), email=id_info.get("email"), password = hashed_password, role = "author")
        db.session.add(user)
        db.session.commit()
    login_user(user, remember=true)
    return redirect(url_for('dashboard'))
        
        
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = RegisterForm()
    
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, "sha256")
        new_user = Users(username=form.username.data, name=form.name.data, email=form.email.data, password=hashed_password, role = "author")
        try:
            db.session.add(new_user)
            db.session.commit()
            # flash("Registered you successfully!. You can login now", "success")
            return redirect(url_for('login'))
        except Exception as e:
            print(e)
            # flash("Something went wrong. Couldn't register you!", "danger")
    return render_template('signup.html', form=form, login_image=params['login_image'])

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user.name.split(' ')[0]
    # If Logged In User has admin rights...Fetch all posts
    if(current_user.role == "admin"):
        posts = Posts.query.order_by(Posts.date.desc()).all()    
        posts_posted_by = [post.posted_by.split(":")[1].split(" ")[0] for post in posts]
        return render_template('dashboard.html', params=params, posts=posts, user=user, role=current_user.role, posts_posted_by = posts_posted_by, current_user_username=current_user.username, current_user_name=current_user.name)
    # If Logged In User is just an author ...Fetch only posts made by him
    else:
        posted_by = current_user.username+":"+current_user.name
        posts = Posts.query.filter_by(posted_by = posted_by).order_by(Posts.date.desc()).all()
        return render_template('dashboard.html', params=params, posts=posts, user=user, role=current_user.role, current_user_username=current_user.username, current_user_name=current_user.name)
    

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/edit/<string:sno>", methods = ['GET', 'POST'])
@login_required
def edit(sno):
    if request.method == 'POST':
        box_title = request.form.get('title')
        tline = request.form.get('tline')
        slug = request.form.get('slug')
        content = request.form.get('content')
        # img_file = request.form.get('img_file')
        img_file = ""

        # If creating a new post...
        if sno=='0':
            # Creating a new post...i neeed to upload an image
            if request.files:
                image = request.files["image"]
                try:    
                    image.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image.filename) ))
                    flash("Image Uploaded Successfully!", "success")
                    img_file = image.filename
                except Exception as e:
                    print(e)
                    flash("Something went wrong. File couldn't be uploaded")
                    return redirect('/edit/'+sno)
            # Now insert post data into database...
            try:
                post = Posts(title=box_title, slug=slug, content=content, tagline=tline, img_file=img_file, date=datetime.now(), posted_by=current_user.username+":"+current_user.name)
                db.session.add(post)
                db.session.commit()
                flash("Post added successfully", "success")
            except Exception as e:
                flash("Post couldn't be added. Something went wrong", "danger")
                return redirect('/edit/'+sno)
        
        # If editing an existing post...
        else:
            post = Posts.query.filter_by(sno=sno).first()
            post.title = box_title
            post.slug = slug
            post.content = content
            post.tagline = tline
            
            # If user trying to change image...upload this new image
            image = request.files["image"]
            if image.filename !='':
                try:    
                    image.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image.filename) ))
                    flash("Image Uploaded Successfully!", "success")
                    post.img_file = image.filename
                except Exception as e:
                    print(e)
                    flash("Something went wrong. File couldn't be uploaded")
                    return redirect('/edit/'+sno)
            # Now commit these changes...
            try:
                db.session.commit()
                flash("Post edited successfully", "success")
            except Exception as e:
                flash("Post couldn't be modified. Something went wrong", "danger")
            return redirect('/edit/'+sno)
    
    post = Posts.query.filter_by(sno=sno).first()
    return render_template('edit.html', params=params, post=post, sno=sno)


@app.route("/uploader", methods = ['GET', 'POST'])
@login_required
def uploader():
    if (request.method == 'POST'):
        f = request.files['file1']
        try:    
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(f.filename) ))
            flash("Image Uploaded Successfully!", "success")
        except Exception as e:
            print(e)
            flash("Something went wrong. File couldn't be uploaded")
        return redirect('/dashboard')

@app.route("/delete/<string:sno>", methods = ['GET', 'POST'])
@login_required
def delete(sno):
    post = Posts.query.filter_by(sno=sno).first()
    try:         
        db.session.delete(post)
        db.session.commit()
        flash("Post deleted successfully", "success")
    except Exception as e:
        print(e)
        flash("Post couldn't be deleted. Something went wrong", "danger")
    return redirect('/dashboard')

# Custom error pages
# Invalid URL
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html", params=params), 404

# Internal Server Error
@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html", params=params), 500

if __name__ == '__main__':
    app.run(debug=True)