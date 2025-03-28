"""
This file contains the functional tests for the main.
These tests use GETs and POSTs to different URLs to check for the proper behavior.
Resources:
    https://flask.palletsprojects.com/en/1.1.x/testing/ 
    https://www.patricksoftwareblog.com/testing-a-flask-application-using-pytest/ 
"""
import os
import pytest
from app import create_app, db
from app.main.models import User, Post, Tag
from config import Config
import sqlalchemy as sqla


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SECRET_KEY = 'bad-bad-key'
    WTF_CSRF_ENABLED = False
    DEBUG = True
    TESTING = True


@pytest.fixture(scope='module')
def test_client():
    # create the flask application ; configure the app for tests
    flask_app = create_app(config_class=TestConfig)

    # Flask provides a way to test your application by exposing the Werkzeug test Client
    # and handling the context locals for you.
    testing_client = flask_app.test_client()
 
    # Establish an application context before running the tests.
    ctx = flask_app.app_context()
    ctx.push()
 
    yield  testing_client 
    # this is where the testing happens!
 
    ctx.pop()

def new_user(uname, uemail,passwd):
    user = User(username=uname, email=uemail)
    user.set_password(passwd)
    return user

def init_tags():
    # check if any tags are already defined in the database
    count = db.session.scalar(db.select(db.func.count(Tag.id)))
    print("**************", count)
    # initialize the tags
    if count == 0:
        tags = ['funny','inspiring', 'true-story', 'heartwarming', 'friendship']
        for t in tags:
            db.session.add(Tag(name=t))
        db.session.commit()
    return None

@pytest.fixture
def init_database():
    # Create the database and the database table
    db.create_all()
    # initialize the tags
    init_tags()
    #add a user    
    user1 = new_user(uname='snow', uemail='snow@wpi.edu',passwd='1234')
    # Insert user data
    db.session.add(user1)
    # Commit the changes for the users
    db.session.commit()

    yield  # this is where the testing happens!

    db.drop_all()

def test_register_page(test_client):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/user/register' page is requested (GET)
    THEN check that the response is valid
    """
    # Create a test client using the Flask application configured for testing
    response = test_client.get('/user/register')
    assert response.status_code == 200
    assert b"Register" in response.data

def test_register(test_client,init_database):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/user/register' form is submitted (POST)
    THEN check that the response is valid and the database is updated correctly
    """
    # Create a test client using the Flask application configured for testing
    response = test_client.post('/user/register', 
                          data=dict(username='john', email='john@wpi.edu',password="bad-bad-password",password2="bad-bad-password"),
                          follow_redirects = True)
    assert response.status_code == 200
    
    s = db.session.scalars(sqla.select(User).where(User.username == 'john')).first()
    s_count = db.session.scalar(sqla.select(db.func.count()).where(User.username == 'john'))
    
    assert s.email == 'john@wpi.edu'
    assert s_count == 1
    assert b"Congratulation, you are now registered" in response.data   
    assert b"Please log in to access this page." in response.data

def test_invalidlogin(test_client,init_database):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/user/login' form is submitted (POST) with wrong credentials
    THEN check that the response is valid and login is refused 
    """
    response = test_client.post('/user/login', 
                          data=dict(username='snow', password='12345',remember_me=False),
                          follow_redirects = True)
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data

# ------------------------------------
# Helper functions

def do_login(test_client, path , username, passwd):
    response = test_client.post(path, 
                          data=dict(username= username, password=passwd, remember_me=False),
                          follow_redirects = True)
    assert response.status_code == 200
    #Students should update this assertion condition according to their own page content
    assert b"The user snow has successfully logged in! Authenticated: True" in response.data  

def do_logout(test_client, path):
    response = test_client.get(path,                       
                          follow_redirects = True)
    assert response.status_code == 200
    # Assuming the application re-directs to login page after logout.
    #Students should update this assertion condition according to their own page content 
    assert b"Please log in to access this page." in response.data    
# ------------------------------------

def test_login_logout(request,test_client,init_database):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/user/login' form is submitted (POST) with correct credentials
    THEN check that the response is valid and login is succesfull 
    """
    do_login(test_client, path = '/user/login', username = 'snow', passwd = '1234')

    do_logout(test_client, path = '/user/logout')


def test_post(test_client,init_database):
    """
    GIVEN a Flask application configured for testing , after user logs in,
    WHEN the '/post' page is requested (GET)  AND PostForm' form is submitted (POST)
    THEN check that response is valid and the class is successfully created in the database
    """
    #login
    do_login(test_client, path = '/user/login', username = 'snow', passwd = '1234')
    
    #test the "post" form 
    response = test_client.get('/post')
    assert response.status_code == 200
    assert b"Post New Smile" in response.data
    
    all_tags = db.session.scalars(sqla.select(Tag)).all()
    #test posting a smile story
    tags1 = list( map(lambda t: t.id, all_tags[:3]))  # should only pass 'id's of the tags. See https://stackoverflow.com/questions/62157168/how-to-send-queryselectfield-form-data-to-a-flask-view-in-a-unittest
    response = test_client.post('/post', 
                          data=dict(title='My test post', body='This is my first test post.',happiness_level=2, tag = tags1),
                          follow_redirects = True)
    #checking the page content after redirect
    assert response.status_code == 200
    assert b"Your new smile post is created" in response.data
    assert b"Welcome to Smile Portal!" in response.data
    assert b"My test post" in response.data 
    assert b"This is my first test post." in response.data 

    #checking whether the database is updated correctly with the post request 
    thepost = db.session.scalars(sqla.select(Post).where(Post.title =='My test post')).first()
    tags_of_post = thepost.get_tags()
    assert (len(tags_of_post))== 3 #should have 3 tags
    assert all_tags[0] in tags_of_post  #first tag should be one of the tags of the post. 
    
    tags2 = list( map(lambda t: t.id, all_tags[1:3]))  # should only pass 'id's of the tags. See https://stackoverflow.com/questions/62157168/how-to-send-queryselectfield-form-data-to-a-flask-view-in-a-unittest
    response = test_client.post('/post', 
                          data=dict(title='Second post', body='Here is another post.',happiness_level=1, tag = tags2),
                          follow_redirects = True)
    #checking the page content after redirect  
    assert response.status_code == 200
    assert b"Your new smile post is created" in response.data
    assert b"Welcome to Smile Portal!" in response.data
    assert b"Second post" in response.data 
    assert b"Here is another post." in response.data 

    #checking whether the database is updated correctly with the post request 
    thepost = db.session.scalars(sqla.select(Post).where(Post.title =='Second post')).first()
    tags_of_post = thepost.get_tags()
    assert (len(tags_of_post))== 2 #should have 2 tags
    assert all_tags[1] in tags_of_post  #second tag should be one of the tags of the post. 

    #there should be total two posts
    all_posts = db.session.scalars(sqla.select(Post)).all()
    assert len(all_posts) == 2

    #finally logout
    do_logout(test_client, path = '/user/logout') 

"""
    Assumes the /post/<post_id>/like route returns the update like cours as JSON.
    For example : {"like_count": 1,  "post_id": 2 }
"""
def test_like_smile(test_client,init_database):
    """
    GIVEN a Flask application configured for testing , after user logs-in,
     post/<post_id>/like form is submitted (POST)
    THEN check that response is valid and the like count is updated in the database
    """
    #login
    do_login(test_client, path = '/user/login', username = 'snow', passwd = '1234')
    
    #first post two smile stories
    all_tags = db.session.scalars(sqla.select(Tag)).all()
    tags1 = list( map(lambda t: t.id, all_tags[:3]))  # should only pass 'id's of the tags. See https://stackoverflow.com/questions/62157168/how-to-send-queryselectfield-form-data-to-a-flask-view-in-a-unittest
    response = test_client.post('/post', 
                          data=dict(title='My test post', body='This is my first test post.',happiness_level=2, tag = tags1),
                          follow_redirects = True)
    assert response.status_code == 200
    post1 = db.session.scalars(sqla.select(Post).where(Post.title =='My test post')).first()
    assert post1 is not None #There should be at least one post with body "My test post"

    tags2 = list( map(lambda t: t.id, all_tags[1:3]))  # should only pass 'id's of the tags. See https://stackoverflow.com/questions/62157168/how-to-send-queryselectfield-form-data-to-a-flask-view-in-a-unittest
    response = test_client.post('/post', 
                          data=dict(title='Second post', body='Here is another post.',happiness_level=1, tag = tags2),
                          follow_redirects = True)
    assert response.status_code == 200
    post2 = db.session.scalars(sqla.select(Post).where(Post.body =='Here is another post.')).first()
    assert post2 is not None  #There should be at least one post with body "Here is another post."

    #there should be total two posts
    all_posts = db.session.scalars(sqla.select(Post)).all()
    assert len(all_posts) == 2

    #like the second post 
    response = test_client.post('/post/'+str(post2.id)+'/like', 
                          data={},
                          follow_redirects = True)
    assert response.status_code == 200
    #Will return the updated count as JSON
    data = eval(response.data)
    assert data['post_id'] == post2.id
    assert data['like_count'] == 1
    #check whether the likecount was updated successfully
    first_post = db.session.get(Post, post1.id)
    assert first_post.likes == 0 
    second_post = db.session.get(Post, post2.id)
    assert second_post.likes == 1  

    #finally logout
    do_logout(test_client, path = '/user/logout')    

    
