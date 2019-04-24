from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

import os, jwt, uuid
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

from tweepy import API
from tweepy import Cursor
from tweepy import OAuthHandler

import twitter_credentials
import re
from textblob import TextBlob
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sys.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SECRET_KEY'] = 'socrwihncfhonwiefwhc'



CORS(app, resources={r"/api/*": {"origins": "*"}})

db = SQLAlchemy(app)
session = db.session
db.create_all()

## Models ##

class User(db.Model):
    __tablename__='users'
    username=db.Column(db.String(255), primary_key=True)
    public_id = db.Column(db.String(255), unique=True)
    password=db.Column(db.String(50))
    email = db.Column(db.String(120))

    def __init__(self, username, email ,public_id, password):
        self.username = username
        self.email = email
        self.public_id = public_id
        self.password = password

    def toDict(self):
        return {
            'username': self.username,
            'email': self.email
        }

class UserRequest(db.Model):
    requestid = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.String(80))
    request = db.Column(db.String(80))

    def toDict(self):
        return {
            'requestid': self.requestid,
            'userid': self.userid,
            'request': self.request
        }

class RequestData(db.Model):
    dataId = db.Column(db.Integer, primary_key=True)
    requestid = db.Column(db.Integer)
    name = db.Column(db.String(80))
    text = db.Column(db.String(200))
    location = db.Column(db.String(80))
    retweet_count = db.Column(db.Integer)
    favorite_count = db.Column(db.Integer)
    created_at = db.Column(db.String(80))

    def toDict(self):
        return {
            'dataId': self.dataId,
            'requestid': self.requestid,
            'name': self.name,
            'text': self.text,
            'location': self.location,
            'retweet_count': self.retweet_count,
            'favourite_count': self.favorite_count,
            'created_at': self.created_at
        }

# # # # TWITTER AUTHENTICATER # # # #
class TwitterAuthenticator():

    def authenticate_twitter_app(self):
        auth = OAuthHandler(twitter_credentials.CONSUMER_KEY, twitter_credentials.CONSUMER_SECRET)# import consumer credentials from twitter_credentials.py file
        auth.set_access_token(twitter_credentials.ACCESS_TOKEN, twitter_credentials.ACCESS_TOKEN_SECRET)# import access credentials from twitter_credentials.py file
        return auth

# # # # TWITTER CLIENT # # # #
class TwitterClient():
    def __init__(self, twitter_user=None):
        self.auth = TwitterAuthenticator().authenticate_twitter_app()
        self.twitter_client = API(self.auth)
        self.twitter_user = twitter_user

    def get_twitter_client_api(self):
        return self.twitter_client

class TweetAnalysis():

    def __init__(self):
        self.tweets = []
        self.json_data = []
        self.searchTerm = ""

    def sanitize(self):
        self.tweets = []
        self.json_data = []
        self.searchTerm = ""

    def tweetFavouritesData(self, api, searchTerm, noOfTerms, date):
        self.tweets = []
        self.json_data = []
        r_max = 0
        f_max = 0
        format_str = '%Y-%m-%d'
        s_date = datetime.strptime(date, format_str)
        date_now = datetime.now()
        while ((date_now-s_date).days + 1) > 0:
            for tweet in Cursor(api.search, q=searchTerm, until = date, lang="en").items(noOfTerms):
                self.tweets.append(tweet._json)
                if tweet.retweet_count > r_max:
                    r_max = tweet.retweet_count
                    self.json_data.append(tweet._json)
                if tweet.favorite_count > f_max:
                    f_max = tweet.retweet_count
                    self.json_data.append(tweet._json)
            s_date = s_date + timedelta(days=1)
            date = s_date.strftime("%Y-%m-%d")
        return self.json_data


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        exists = os.path.isfile('token.txt')
        if not exists:
            return render_template('login')
        else:
            with open('token.txt') as fp:
                user_token = fp.read()
            try:
                data = jwt.decode(user_token,app.config['SECRET_KEY'])
                current_user = User.query.filter_by(public_id=data['public_id']).first()
            except:
                return render_template('login')
            return f(current_user, *args, **kwargs)
    return decorated

twitter_client = TwitterClient()
api = twitter_client.get_twitter_client_api()
tweet_analysis = TweetAnalysis()
tweets = []

@app.before_first_request
def setup():
    exists = os.path.isfile('token.txt')
    if exists:
        os.remove('token.txt')
    db.Model.metadata.drop_all(bind=db.engine)
    db.Model.metadata.create_all(bind=db.engine)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


@app.route('/')
def hello():
    return redirect(url_for('homepage'))

@app.route('/api')
def homepage():
    return render_template('index')

@app.route('/api/hashtag')
@token_required
def getHashtag(current_user):
    return render_template('hashtag')


@app.route('/api/hashtag_search', methods=['POST'])
@token_required
def sendHashtag(current_user):
    index = request.form['hashtag_name']
    num = int(request.form['num_vals'])
    time_period = request.form['time_period']

    newRequest = UserRequest(userid = current_user.username, request = index)
    db.session.add(newRequest)
    db.session.commit()

    tweet_analysis.sanitize()
    tweets = tweet_analysis.tweetFavouritesData(api,index,num,time_period)

    for tweet in tweets:
        tweetName = tweet.get("user", "")
        tweetUser = tweetName.get("screen_name", "")
        tweetLocation = tweetName.get("location", "")
        tweetdate = tweet.get("created_at","")
        tweetdate2 = tweetdate[:20] + tweetdate[26:]
        newTweet = RequestData(requestid = newRequest.requestid, text=tweet.get("text") ,name = tweetUser, location = tweetLocation, retweet_count = tweet.get("retweet_count", ""), favorite_count = tweet.get("favorite_count", ""), created_at = tweetdate2)
        db.session.add(newTweet)
        db.session.commit()
    return render_template('display', tweets = tweets, id = newRequest.requestid)

@app.route('/api/search_history', methods=['GET'])
@token_required
def search_results(current_user):
    user_request = UserRequest.query.filter_by(userid=current_user.username)
    user_request_records = [rec.toDict() for rec in user_request]
    return render_template("user_request_list", users = user_request_records )

@app.route('/api/tweets_request/<int:id>', methods=['POST'])
def tweets_request(id):
    tweet_data = RequestData.query.filter_by(requestid=id)
    tweet_data_records = [rec.toDict() for rec in tweet_data]
    return render_template("tweet_listing", tweets = tweet_data_records, id = id)

@app.route('/api/tweets_request_del/<int:id>', methods=['POST'])
@token_required
def tweets_request_del(current_user, id):
    tweets_request = UserRequest.query.get(id)
    session.delete(tweets_request)
    session.commit()
    user_request = UserRequest.query.filter_by(userid=current_user.username)
    user_request_records = [rec.toDict() for rec in user_request]
    return render_template("user_request_list", users = user_request_records)


def cleanTweet(tweet):
    return ' '.join(re.sub("(@[A-Za-z0-9]+)|([^0-9A-Za-z \t]) | (\w +:\ / \ / \S +)", " ", tweet).split())

def percentage(part, whole):
    temp = 100 * float(part) / float(whole)
    return format(temp, '.2f')

@app.route('/api/s_analyis', methods=['GET'])
def hashtagData():
    all_tweets = tweet_analysis.tweets
    searchTerm = tweet_analysis.searchTerm
    total_tweets = 0
    positive = 0
    wpositive = 0
    spositive = 0
    negative = 0
    wnegative = 0
    snegative = 0
    neutral = 0

    for tweet in all_tweets:
        analysis = TextBlob(cleanTweet(tweet['text']))
        val = analysis.sentiment.polarity


        if (val == 0):
            neutral += 1
        elif (val > 0 and val <= 0.3):
            wpositive += 1
        elif (val > 0.3 and val <= 0.6):
            positive += 1
        elif (val > 0.6 and val <= 1):
            spositive += 1
        elif (val > -0.3 and val <= 0):
            wnegative += 1
        elif (val > -0.6 and val <= -0.3):
            negative += 1
        elif (val > -1 and val <= -0.6):
            snegative += 1

        total_tweets += 1

    a_positive = percentage(positive, total_tweets)
    a_wpositive = percentage(wpositive, total_tweets)
    a_spositive = percentage(spositive, total_tweets)
    a_negative = percentage(negative, total_tweets)
    a_wnegative = percentage(wnegative, total_tweets)
    a_snegative = percentage(snegative, total_tweets)
    a_neutral = percentage(neutral, total_tweets)

    labels = ['Positive', 'Weakly Positive', 'Strongly Positive', 'Neutral', 'Negative', 'Weakly Negative', 'Strongly Negative']
    values = [a_positive, a_wpositive, a_spositive, a_neutral, a_negative, a_wnegative, a_snegative]
    title = 'How people are reacting on ' + searchTerm + ' by analyzing ' + str(total_tweets) + ' Tweets.'
    return render_template('sent_analysis', labels = labels, values=values, title=title)

@app.route('/api/users')
@token_required
def get_all_users(current_user):
    users = User.query.all()
    records = [rec.toDict() for rec in users]
    return jsonify(records)

@app.route('/api/login')
def login():
    return render_template("login")

@app.route("/api/validate",methods=["POST"])
def validate():
    if request.method == "POST":
        uname = request.form["uname"]
        password = str(request.form["passw"])
        if not uname or not password:
            return render_template('login')
        else:
            user = User.query.filter_by(username = uname).first()
            if not user:
                return render_template('login')
            if check_password_hash(user.password,password):
                token = jwt.encode({'public_id': user.public_id, 'exp': datetime.utcnow() + timedelta(minutes=30)}, app.config['SECRET_KEY'])
                user_token = token.decode('UTF-8')
                fo= open("token.txt", "w")
                filebuffer = user_token
                fo.writelines(filebuffer)
                fo.close()
                return render_template('index')
            return render_template("login")

@app.route("/api/register", methods=["POST", "GET"])
def register():
    if request.method == "POST":
        uname = request.form['uname']
        mail = request.form['mail']
        passw = request.form['passw']
        hashed_password = generate_password_hash(passw,method='sha256')
        new_user = User(username = uname, email = mail, password = hashed_password, public_id=str(uuid.uuid4()))
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register")

@app.route("/api/charts/barchart/<int:id>", methods=["GET","POST"])
def barchart(id):
    data = RequestData.query.filter_by(requestid=id).all()
    twitterNames =[]
    favorite_count1 =[]
    retweet_count1 =[]

    for tweet in data:
        twitterNames.append(tweet.name)
        favorite_count1.append(tweet.favorite_count)
        retweet_count1.append(tweet.retweet_count)

    return render_template("barchart", twitterNames = twitterNames, favorite_count1 = favorite_count1, retweet_count1= retweet_count1, id=id)

@app.route("/api/charts/barchart2/<int:id>", methods=["GET","POST"])
def barchart2(id):
    data = RequestData.query.filter_by(requestid=id).all()
    twitterNames =[]
    favorite_count1 =[]
    retweet_count1 =[]

    for tweet in data:
        twitterNames.append(tweet.name)
        favorite_count1.append(tweet.favorite_count)
        retweet_count1.append(tweet.retweet_count)

    return render_template("barchart2", twitterNames = twitterNames, favorite_count1 = favorite_count1, retweet_count1= retweet_count1, id=id)

@app.route("/api/charts/linechart/<int:id>", methods=["GET","POST"])
def linechart(id):
    data = RequestData.query.filter_by(requestid=id).all()
    dates =[]
    favorite_count1 =[]
    retweet_count1 =[]

    for tweet in data:
        dates.append(tweet.created_at)
        favorite_count1.append(tweet.favorite_count)
        retweet_count1.append(tweet.retweet_count)

    return render_template("linechart", dates = dates, favorite_count1 = favorite_count1, retweet_count1= retweet_count1, id=id)
