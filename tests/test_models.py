import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timedelta
import unittest
from src import create_app, db
from src.database.models import User, Event, Task
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    
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
        """Test user password hashing functionality"""
        u = User(username='john', email='john.doe@example.com')
        u.set_password('testpassword')
        self.assertFalse(u.check_password('wrongpassword'))
        self.assertTrue(u.check_password('testpassword'))

    def test_user_creation(self):
        """Test basic user creation and properties"""
        u = User(username='testuser', email='test@example.com')
        u.set_password('testpass')
        db.session.add(u)
        db.session.commit()
        
        self.assertEqual(u.username, 'testuser')
        self.assertEqual(u.email, 'test@example.com')
        self.assertFalse(u.email_verified)
        self.assertEqual(u.failed_login_attempts, 0)
        self.assertIsNone(u.account_locked_until)

    def test_event_creation(self):
        """Test event creation and user relationship"""
        # Create user first
        u = User(username='eventowner', email='owner@example.com')
        u.set_password('password')
        db.session.add(u)
        db.session.commit()
        
        # Create event
        e = Event(
            name='Test Event',
            description='This is a test event',
            date=datetime(2024, 12, 25, 18, 0),
            user_id=u.id,
            strict_mode=False
        )
        db.session.add(e)
        db.session.commit()
        
        self.assertEqual(e.name, 'Test Event')
        self.assertEqual(e.description, 'This is a test event')
        self.assertEqual(e.user_id, u.id)
        self.assertFalse(e.strict_mode)
        self.assertEqual(e.user.username, 'eventowner')

    def test_task_creation_and_assignment(self):
        """Test task creation and user assignment"""
        # Create user
        u = User(username='taskuser', email='task@example.com')
        u.set_password('password')
        db.session.add(u)
        db.session.commit()
        
        # Create event
        e = Event(
            name='Task Event',
            description='Event with tasks',
            date=datetime(2024, 12, 25, 18, 0),
            user_id=u.id
        )
        db.session.add(e)
        db.session.commit()
        
        # Create task
        t = Task(
            description='Complete this task',
            note='Important task',
            completed=False,
            priority=2,
            due_date=datetime(2024, 12, 20, 12, 0),
            event_id=e.id,
            item='Task Item'
        )
        db.session.add(t)
        db.session.commit()
        
        # Assign task to user
        t.assigned_users.append(u)
        db.session.commit()
        
        self.assertEqual(t.description, 'Complete this task')
        self.assertEqual(t.note, 'Important task')
        self.assertFalse(t.completed)
        self.assertEqual(t.priority, 2)
        self.assertEqual(t.event_id, e.id)
        self.assertEqual(len(t.assigned_users), 1)
        self.assertEqual(t.assigned_users[0].username, 'taskuser')

    def test_user_friend_relationship(self):
        """Test user friendship functionality"""
        u1 = User(username='user1', email='user1@example.com')
        u2 = User(username='user2', email='user2@example.com')
        u1.set_password('password1')
        u2.set_password('password2')
        
        db.session.add(u1)
        db.session.add(u2)
        db.session.commit()
        
        # Test friendship
        self.assertFalse(u1.is_friend(u2))
        u1.add_friend(u2)
        db.session.commit()
        self.assertTrue(u1.is_friend(u2))

    def test_event_participants(self):
        """Test event participant relationship"""
        # Create users
        u1 = User(username='organizer', email='org@example.com')
        u2 = User(username='participant', email='part@example.com')
        u1.set_password('pass1')
        u2.set_password('pass2')
        db.session.add_all([u1, u2])
        db.session.commit()
        
        # Create event
        e = Event(
            name='Group Event',
            description='Event with multiple participants',
            date=datetime(2024, 12, 25, 18, 0),
            user_id=u1.id
        )
        db.session.add(e)
        db.session.commit()
        
        # Add participant
        e.participants.append(u2)
        db.session.commit()
        
        self.assertEqual(len(e.participants), 1)
        self.assertEqual(e.participants[0].username, 'participant')
        self.assertEqual(len(u2.participating_events), 1)
        self.assertEqual(u2.participating_events[0].name, 'Group Event')

    def test_user_email_verification(self):
        """Test user email verification functionality"""
        u = User(username='testverify', email='verify@example.com')
        u.set_password('password')
        db.session.add(u)
        db.session.commit()
        
        # Test email verification token generation
        token = u.generate_email_verification_token()
        self.assertIsNotNone(token)
        self.assertIsNotNone(u.email_verification_token)
        self.assertIsNotNone(u.email_verification_token_expiry)
        
        # Test token verification
        self.assertTrue(u.verify_email_verification_token(token))
        self.assertFalse(u.verify_email_verification_token('wrong_token'))
        
        # Test email verification
        self.assertFalse(u.is_email_verified())
        u.verify_email()
        self.assertTrue(u.is_email_verified())

    def test_user_password_reset(self):
        """Test user password reset functionality"""
        u = User(username='resetuser', email='reset@example.com')
        u.set_password('oldpassword')
        db.session.add(u)
        db.session.commit()
        
        # Test reset token generation
        token = u.generate_reset_token()
        self.assertIsNotNone(token)
        self.assertIsNotNone(u.reset_token)
        self.assertIsNotNone(u.reset_token_expiry)
        
        # Test token verification
        self.assertTrue(u.verify_reset_token(token))
        self.assertFalse(u.verify_reset_token('wrong_token'))
        
        # Test token clearing
        u.clear_reset_token()
        self.assertIsNone(u.reset_token)
        self.assertIsNone(u.reset_token_expiry)

    def test_account_lockout(self):
        """Test account lockout functionality"""
        u = User(username='locktest', email='lock@example.com')
        u.set_password('password')
        db.session.add(u)
        db.session.commit()
        
        # Test initial state
        self.assertFalse(u.is_account_locked())
        self.assertEqual(u.failed_login_attempts, 0)
        
        # Test failed login attempts
        for i in range(4):
            u.increment_failed_login()
            self.assertFalse(u.is_account_locked())
        
        # Test lockout after 5th failed attempt
        u.increment_failed_login()
        self.assertTrue(u.is_account_locked())
        
        # Test reset after successful login
        u.reset_failed_login_attempts()
        self.assertFalse(u.is_account_locked())
        self.assertEqual(u.failed_login_attempts, 0)
        self.assertIsNotNone(u.last_login)


if __name__ == '__main__':
    unittest.main(verbosity=1)