import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timedelta
import unittest
from app import create_app, db
from app.main.models import User, Post, Tag
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    
class TestModels(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_password_hashing(self):
        u = User(username='john', email='john.yates@wpi.edu')
        u.set_password('covid')
        self.assertFalse(u.check_password('flu'))
        self.assertTrue(u.check_password('covid'))

    def test_post_1(self):
        u1 = User(username='john', email='john.yates@wpi.com')
        db.session.add(u1)
        db.session.commit()
        self.assertEqual(len(u1.get_user_posts()), 0)
        p1 = Post(title='My post', body='This is my test post.', happiness_level=1, userid=u1.id)
        db.session.add(p1)
        db.session.commit()
        self.assertEqual(len(u1.get_user_posts()), 1)
        self.assertEqual(u1.get_user_posts()[0].title, 'My post')
        self.assertEqual(u1.get_user_posts()[0].body, 'This is my test post.')
        self.assertEqual(u1.get_user_posts()[0].happiness_level, 1)

    def test_post_2(self):
        u1 = User(username='john', email='john.yates@wpi.com')
        u2 = User(username='amit', email='amit.khan@wpi.com')
        db.session.add(u1)
        db.session.add(u2)
        db.session.commit()
        self.assertEqual(len(u1.get_user_posts()), 0)
        self.assertEqual(len(u2.get_user_posts()), 0)
        p1 = Post(title='My post 1', body='This is my first test post.', happiness_level=1, userid=u1.id)
        db.session.add(p1)
        p2 = Post(title='My post 2', body='This is my second test post.', happiness_level=3, userid=u1.id)
        db.session.add(p2)
        db.session.commit()
        p3 = Post(title='Another post', body='This is a post by somebody else.', happiness_level=2, userid=u2.id)
        db.session.add(p3)
        db.session.commit()
        # test the posts by the first user
        self.assertEqual(len(u1.get_user_posts()), 2)
        self.assertEqual(u1.get_user_posts()[1].title, 'My post 2')
        self.assertEqual(u1.get_user_posts()[1].body, 'This is my second test post.')
        self.assertEqual(u1.get_user_posts()[1].happiness_level, 3)
        # test the posts by the second user
        self.assertEqual(len(u2.get_user_posts()), 1)
        self.assertEqual(u2.get_user_posts()[0].title, 'Another post')
        self.assertEqual(u2.get_user_posts()[0].body, 'This is a post by somebody else.')
        self.assertEqual(u2.get_user_posts()[0].happiness_level, 2)


if __name__ == '__main__':
    unittest.main(verbosity=1)