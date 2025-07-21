
from flask import render_template, flash, redirect, url_for, request, jsonify
from flask_login import current_user, login_user, logout_user, login_required
from urllib.parse import urlsplit
from src import db
from src.auth import auth_blueprint as bp_auth 
from src.auth.auth_forms import (RegistrationForm, LoginForm, RequestPasswordResetForm, 
                                ResetPasswordForm, ChangePasswordForm)
from src.email import (send_email_verification_email, send_password_reset_email, 
                       send_welcome_email, send_password_change_notification)
import sqlalchemy as sqla
from src.database.models import User
from datetime import datetime


@bp_auth.route('/user/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    rform = RegistrationForm()
    if rform.validate_on_submit():
        try:
            user = User(username=rform.username.data, email=rform.email.data)
            user.set_password(rform.password.data)
            db.session.add(user)
            db.session.commit()
            
            # Send verification email
            send_email_verification_email(user)
            db.session.commit()  # Save the verification token
            
            flash('Registration successful! Please check your email to verify your account before logging in.', 'info')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'error')
    
    return render_template('register.html', form=rform)

@bp_auth.route('/user/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    lform = LoginForm()
    if lform.validate_on_submit():
        query = sqla.select(User).where(User.email == lform.email.data)
        user = db.session.scalars(query).first()
        
        if user is None:
            flash('Invalid email or password', 'error')
            return redirect(url_for('auth.login'))
        
        # Check if email is verified
        if not user.is_email_verified():
            flash('Please verify your email address before logging in. Check your email for verification link.', 'warning')
            return redirect(url_for('auth.login'))
            
        # Check if account is locked
        if user.is_account_locked():
            flash('Account temporarily locked due to multiple failed login attempts. Please try again later.', 'error')
            return redirect(url_for('auth.login'))
            
        if not user.check_password(lform.password.data):
            # Increment failed login attempts
            user.increment_failed_login()
            db.session.commit()
            
            attempts_left = 5 - user.failed_login_attempts
            if attempts_left > 0:
                flash(f'Invalid email or password. {attempts_left} attempts remaining.', 'error')
            else:
                flash('Account locked due to multiple failed attempts. Please try again in 15 minutes.', 'error')
            return redirect(url_for('auth.login'))
        
        # Successful login - reset failed attempts
        user.reset_failed_login_attempts()
        db.session.commit()
        
        login_user(user, remember=lform.remember_me.data)
        flash(f'Welcome back, {user.username}!', 'success')
        
        # Handle next page redirect
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)

    return render_template('login.html', form=lform)

@bp_auth.route('/user/logout', methods=['GET'])
@login_required
def logout():
    username = current_user.username
    logout_user()
    flash(f'Goodbye, {username}! You have been logged out successfully.', 'info')
    return redirect(url_for('main.root'))


@bp_auth.route('/user/request_password_reset', methods=['GET', 'POST'])
def request_password_reset():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = RequestPasswordResetForm()
    if form.validate_on_submit():
        query = sqla.select(User).where(User.email == form.email.data)
        user = db.session.scalars(query).first()
        if user and user.is_email_verified():  # Only send reset to verified emails
            send_password_reset_email(user)
            db.session.commit()  # Save the reset token
            
        flash('If an account with that email exists and is verified, a password reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
        
    return render_template('request_password_reset.html', form=form)


@bp_auth.route('/user/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    # Find user with this token
    query = sqla.select(User).where(User.reset_token == token)
    user = db.session.scalars(query).first()
    
    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('auth.login'))
        
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.clear_reset_token()
        db.session.commit()
        
        flash('Your password has been reset successfully.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('reset_password.html', form=form)


@bp_auth.route('/user/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('auth.change_password'))
            
        current_user.set_password(form.new_password.data)
        db.session.commit()
        
        # Send notification email
        send_password_change_notification(current_user)
        
        flash('Your password has been changed successfully.', 'success')
        return redirect(url_for('main.display_profile'))
        
    return render_template('change_password.html', form=form)


@bp_auth.route('/user/account_status', methods=['GET'])
@login_required
def account_status():
    """API endpoint to check account security status"""
    return jsonify({
        'last_login': current_user.last_login.isoformat() if current_user.last_login else None,
        'failed_attempts': current_user.failed_login_attempts,
        'account_locked': current_user.is_account_locked(),
        'email_verified': current_user.is_email_verified()
    })


@bp_auth.route('/user/verify_email/<token>', methods=['GET'])
def verify_email(token):
    """Verify email address using token"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    # Find user with this verification token
    query = sqla.select(User).where(User.email_verification_token == token)
    user = db.session.scalars(query).first()
    
    if not user or not user.verify_email_verification_token(token):
        flash('Invalid or expired verification token.', 'error')
        return redirect(url_for('auth.login'))
    
    # Verify the user's email
    user.verify_email()
    db.session.commit()
    
    # Send welcome email
    send_welcome_email(user)
    
    flash('Email verified successfully! You can now log in to your account.', 'success')
    return redirect(url_for('auth.login'))


@bp_auth.route('/user/resend_verification', methods=['GET', 'POST'])
def resend_verification():
    """Resend email verification"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        if email:
            query = sqla.select(User).where(User.email == email)
            user = db.session.scalars(query).first()
            
            if user and not user.is_email_verified():
                send_email_verification_email(user)
                db.session.commit()
                flash('Verification email has been resent. Please check your inbox.', 'info')
            else:
                flash('If an unverified account with that email exists, a verification email has been sent.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('resend_verification.html')


@bp_auth.route('/test_email')
def test_email():
    """Test email configuration - Remove this route in production!"""
    from src.email import send_email
    from flask import current_app
    
    # Check if email is configured
    mail_config = {
        'MAIL_SERVER': current_app.config.get('MAIL_SERVER'),
        'MAIL_PORT': current_app.config.get('MAIL_PORT'),
        'MAIL_USERNAME': current_app.config.get('MAIL_USERNAME'),
        'MAIL_PASSWORD': '***' if current_app.config.get('MAIL_PASSWORD') else None,
        'MAIL_DEFAULT_SENDER': current_app.config.get('MAIL_DEFAULT_SENDER'),
    }
    
    if not current_app.config.get('MAIL_USERNAME'):
        return jsonify({
            'status': 'error',
            'message': 'Email not configured. Please set MAIL_USERNAME and MAIL_PASSWORD environment variables.',
            'config': mail_config
        })
    
    try:
        test_recipient = current_app.config.get('MAIL_USERNAME')  # Send test email to yourself
        send_email(
            subject="🧪 Test Email from EventEase",
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            recipients=[test_recipient],
            text_body="This is a test email from EventEase! If you receive this, email is working correctly.",
            html_body="<h1>🎉 Email Test Successful!</h1><p>This is a test email from EventEase!</p><p>If you receive this, your email configuration is working correctly.</p>"
        )
        return jsonify({
            'status': 'success',
            'message': f'Test email sent successfully to {test_recipient}!',
            'config': mail_config
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error sending email: {str(e)}',
            'config': mail_config
        })