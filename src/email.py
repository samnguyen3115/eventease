"""
Email service for sending various types of emails
"""
from flask import current_app, render_template
from flask_mail import Message
from src import mail
import threading


def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        try:
            mail.send(msg)
            current_app.logger.info(f"Email sent successfully to {msg.recipients}")
        except Exception as e:
            current_app.logger.error(f"Failed to send email to {msg.recipients}: {str(e)}")
            raise e


def send_email(subject, sender, recipients, text_body, html_body):
    """Send email with both text and HTML versions"""
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    
    # Check if email is configured
    if not current_app.config.get('MAIL_USERNAME'):
        # Development mode - log email instead of sending
        current_app.logger.info("="*50)
        current_app.logger.info("📧 EMAIL WOULD BE SENT (Development Mode)")
        current_app.logger.info(f"To: {recipients}")
        current_app.logger.info(f"Subject: {subject}")
        current_app.logger.info(f"Body: {text_body}")
        current_app.logger.info("="*50)
        return
    
    try:
        # Send asynchronously in production
        thr = threading.Thread(target=send_async_email, args=(current_app._get_current_object(), msg))
        thr.start()
        current_app.logger.info(f"Email queued for sending to {recipients}: {subject}")
    except Exception as e:
        current_app.logger.error(f"Failed to queue email: {str(e)}")
        raise e


def send_email_verification_email(user):
    """Send email verification email to user"""
    token = user.generate_email_verification_token()
    
    subject = "[EventEase] Please verify your email address"
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [user.email]
    
    text_body = render_template('app\templates\email\verify_email.txt', 
                               user=user, token=token)
    html_body = render_template('app\templates\email\verify_email.html', 
                               user=user, token=token)
    
    send_email(subject, sender, recipients, text_body, html_body)


def send_password_reset_email(user):
    """Send password reset email to user"""
    token = user.generate_reset_token()
    
    subject = "[EventEase] Reset your password"
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [user.email]
    
    text_body = render_template('email/reset_password.txt', 
                               user=user, token=token)
    html_body = render_template('email/reset_password.html', 
                               user=user, token=token)
    
    send_email(subject, sender, recipients, text_body, html_body)


def send_welcome_email(user):
    """Send welcome email after successful verification"""
    subject = "[EventEase] Welcome to EventEase!"
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [user.email]
    
    text_body = render_template('email/welcome.txt', user=user)
    html_body = render_template('email/welcome.html', user=user)
    
    send_email(subject, sender, recipients, text_body, html_body)


def send_password_change_notification(user):
    """Send notification when password is changed"""
    subject = "[EventEase] Password changed successfully"
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    recipients = [user.email]
    
    text_body = render_template('email/password_changed.txt', user=user)
    html_body = render_template('email/password_changed.html', user=user)
    
    send_email(subject, sender, recipients, text_body, html_body)
