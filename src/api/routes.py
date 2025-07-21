
from flask import Response, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
import os
from ics import Calendar
from ics import Event as IcsEvent
from src import db
from flask_login import current_user
from src.database.models import Event, Task, User, event_participants
import sqlalchemy as sqla
from werkzeug.utils import secure_filename
from src.form.forms import ProfileForm
from flask import current_app
from datetime import  timedelta
from flask import current_app
from flask import Blueprint

bp_main = Blueprint('main', __name__)

UPLOAD_FOLDER = 'static/profile_pics'  # Define where images should be stored
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp_main.route('/', methods=['GET'])
def root():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    else:
        return redirect(url_for('chatbot_router.chatbot'))


@bp_main.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    # Fetch events created by the current user
    user_events = db.session.scalars(
        sqla.select(Event).where(Event.user_id ==
                                 current_user.id).order_by(Event.date.asc())
    ).all()

    # Fetch events shared with the current user
    shared_events = db.session.scalars(
        sqla.select(Event)
        .join(event_participants)
        .where(event_participants.c.user_id == current_user.id)
        .order_by(Event.date.asc())
    ).all()

    # Combine both lists and remove duplicates
    all_events = {event.id: event for event in user_events +
                  shared_events}.values()

    # Calculate progress for each event
    for event in all_events:
        total_tasks = len(event.tasks)
        completed_tasks = len([task for task in event.tasks if task.completed])
        event.progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return render_template('index.html', events=all_events)




@bp_main.route('/display_profile', methods=['GET'])
@login_required
def display_profile():
    user = current_user  # Use the currently logged-in user
    return render_template('display_profile.html', user=user)


@bp_main.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = ProfileForm()
    if request.method == 'POST' and form.validate_on_submit():
        # Save the updated profile picture if provided
        if form.profile_picture.data:
            file = form.profile_picture.data
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(
                    current_app.static_folder, 'profile_pics', filename)
                file.save(file_path)
                # Save the relative path to the database
                current_user.profile_picture = f'profile_pics/{filename}'

        # Update other fields
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.language = form.language.data
        db.session.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for('main.display_profile'))

    # Render the edit profile form for GET requests
    return render_template('edit_profile.html', form=form, user=current_user)


@bp_main.route('/calendar.ics', methods=['GET'])
@login_required
def calendar_feed():
    try:
        # Fetch tasks assigned to the current user
        tasks = db.session.scalars(
            sqla.select(Task).where(
                Task.assigned_users.any(User.id == current_user.id))
        ).all()

        calendar = Calendar()  # Create a new calendar

        for task in tasks:
            if task.due_date is not None:
                # Create an event for each task
                e = IcsEvent()
                e.name = task.description  # Set the name of the event
                e.begin = task.due_date  # Set the start time of the event
                # Set the end time (1 day duration)
                e.end = task.due_date + timedelta(days=1)
                # Add priority (customize as needed)
                e.priority = task.priority
                e.description = task.event.name if task.event else 'No Event Description'  # Add description

                calendar.events.add(e)  # Add the event to the calendar

        # Return the calendar feed as a downloadable response
        response = Response(str(calendar), mimetype="text/calendar")
        response.headers["Content-Disposition"] = "attachment; filename=calendar.ics"
        return response

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@bp_main.route('/add_friend', methods=['POST'])
@login_required
def add_friend():
    try:
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({"success": False, "error": "Email is required."}), 400

        friend_email = data.get('email')

        friend = db.session.scalar(sqla.select(User).where(User.email == friend_email))
        if not friend:
            return jsonify({"success": False, "error": "User not found."}), 404

        if current_user.is_friend(friend):
            return jsonify({"success": False, "error": "User is already your friend."}), 400

        current_user.add_friend(friend)
        db.session.commit()
        print(f"Friend added successfully: {friend.username}")  # Debugging log

        return jsonify({"success": True, "message": f"{friend.username} has been added as a friend."})
    except Exception as e:
        # Log the error for debugging
        print(f"Error in add_friend route: {e}")
        return jsonify({"success": False, "error": f"An internal error occurred: {str(e)}"}), 500

@bp_main.route('/remove_friend', methods=['POST'])
@login_required
def remove_friend():
    data = request.get_json()
    friend_email = data.get('email')

    friend = db.session.scalar(sqla.select(User).where(User.email == friend_email))
    if not friend:
        return jsonify({"success": False, "error": "User not found."}), 404

    if not current_user.is_friend(friend):
        return jsonify({"success": False, "error": "User is not your friend."}), 400

    current_user.remove_friend(friend)
    db.session.commit()
    return jsonify({"success": True, "message": f"{friend.username} has been removed from your friends list."})


@bp_main.route('/friends', methods=['GET'])
@login_required
def list_friends():
    friends = current_user.friends.all()
    return jsonify({
        "friends": [{"id": friend.id, "username": friend.username, "email": friend.email} for friend in friends]
    })
    
@bp_main.route('/friends', methods=['GET'])
@login_required
def get_friends():
    friends = current_user.friends.all()
    return jsonify({
        "friends": [{"id": friend.id, "username": friend.username, "email": friend.email} for friend in friends]
    })
 