import json
import re
from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
import google.generativeai as genai
import os
from app import db
from flask_login import current_user
from app.main.models import Event, Task, User, event_participants
from app.main import main_blueprint as bp_main
import sqlalchemy as sqla
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
from app.main.forms import ProfileForm
from flask import current_app
from datetime import datetime

UPLOAD_FOLDER = 'static/profile_pics'  # Define where images should be stored
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="gemini-1.5-flash")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp_main.route('/', methods=['GET'])
def root():
    return redirect(url_for('main.chatbot'))


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
        event.progress = (completed_tasks / total_tasks *
                          100) if total_tasks > 0 else 0

    return render_template('index.html', events=all_events)


@bp_main.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    return render_template('chatbot.html', title="Event Chatbot")


@bp_main.route('/create_event', methods=['POST'])
@login_required
def create_event():
    data = request.json
    event_name = data.get('eventName')
    user_id = current_user.id

    if not event_name:
        return jsonify({"error": "Event name is required."}), 400

    new_event = Event(name=event_name, user_id=user_id)
    db.session.add(new_event)
    db.session.commit()
    # Add the current user as a participant
    new_event.participants.append(current_user)
    db.session.commit()
    return jsonify({"eventId": new_event.id})


@bp_main.route('/create_event_and_tasks', methods=['POST'])
@login_required
def create_event_and_tasks():
    data = request.json
    user_input = data.get('userInput')
    event_id = data.get('event_id')
    conversation_history = data.get('conversation_history', [])
    question_index = data.get('question_index', 0)

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404

    try:
        if not conversation_history:
            # Initial prompt, ask the first clarifying question
            prompt = f"""
            Based on the following event description: "{user_input}", ask ONE clarifying question to help me generate a more specific checklist.
            Return ONLY the question.
            """
        else:
            if question_index < 2:
                # Ask a follow-up question
                prompt = f"""
                Based on the following conversation:
                {conversation_history}
                Ask ONE more clarifying question. Return ONLY the question.
                """
            else:
                # Generate the checklist after all questions are answered
                prompt = f"""
                Based on the following conversation:
                {conversation_history}
                Generate a JSON checklist. Include keys for 'task', 'priority' (1:important/2:necessary/3:normal).

                Example JSON output:
                [
                    {{"task": "Book flights", "priority": 1}},
                    {{"task": "Pack sunscreen", "priority": 2}}
                ]

                Return ONLY the JSON. Do not include any other text or explanations, and do not wrap the JSON in markdown code blocks.
                """

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        if not conversation_history or question_index < 2:
            # Return a question
            return jsonify({"question": response_text, "conversation_history": conversation_history + [f"User: {user_input}", f"Bot: {response_text}"], "question_index": question_index + 1})
        else:
            # Return tasks
            json_match = re.search(
                r"```json\s*([\s\S]*?)\s*```", response_text)
            if json_match:
                response_text = json_match.group(1).strip()

            tasks_data = json.loads(response_text)

            for task_data in tasks_data:
                task = Task(
                    description=task_data.get(
                        'task', 'No description provided'),
                    priority=task_data.get('priority', 3),
                    event_id=event_id
                )
                db.session.add(task)

            db.session.commit()
            return jsonify({"eventId": event_id, "message": "Tasks created successfully!"})

    except json.JSONDecodeError as e:
        db.session.rollback()
        return jsonify({"error": f"Invalid JSON response from Gemini API: {e}. The response was: {response_text}"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error creating tasks: {e}"}), 500


@bp_main.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message')
    event_id = data.get('event_id')
    if not user_input:
        return jsonify({"error": "Message is required."}), 400
    # Check if the user is logged in
    if current_user.is_authenticated:
        # User is logged in, proceed as normal
        if not event_id:
            return jsonify({"error": "Event ID is required for logged-in users."}), 400

        event = Event.query.get(event_id)
        if not event:
            return jsonify({"error": "Event not found."}), 404

        prompt = f"""
        Generate a JSON checklist at least 8 tasks for the following event: {user_input}.
        Include keys for 'task', 'priority' (1:important/2:necessary/3:normal).

        Example JSON output:
        [
            {{"task": "Book flights", "priority": 1}},
            {{"task": "Pack sunscreen", "priority": 2}}
        ]

        Return ONLY the JSON. Do not include any other text or explanations, and do not wrap the JSON in markdown code blocks.
        """
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()

            json_match = re.search(
                r"```json\s*([\s\S]*?)\s*```", response_text)
            if json_match:
                response_text = json_match.group(1).strip()

            tasks_data = json.loads(response_text)

            for task_data in tasks_data:
                task = Task(
                    description=task_data.get(
                        'task', 'No description provided'),
                    priority=task_data.get('priority', 3),
                    event_id=event_id
                )
                db.session.add(task)

            db.session.commit()
            return jsonify({"response": "Tasks saved to the database successfully!"})

        except json.JSONDecodeError as e:
            db.session.rollback()
            return jsonify({"error": f"Invalid JSON response from Gemini API: {e}. The response was: {response_text}"}), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Error saving tasks to the database: {e}"}), 500

    else:
        # User is not logged in, generate a checklist and return it as plain text
        prompt = f"""
        Generate a checklist for the following event: {user_input}.
        Include tasks with priorities .
        Example output:
        Book flights (Priority: very important)
        Pack sunscreen (Priority: necessary)
        Buy snacks (Priority: normal)
        Return the checklist as plain text, with each task on a new line.
        """
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Return the checklist directly as plain text
            return jsonify({"response": response_text})

        except Exception as e:
            return jsonify({"error": f"Error generating checklist: {e}"}), 500


@bp_main.route('/update_tasks/<int:event_id>', methods=['POST'])
@login_required
def update_tasks(event_id):
    # Get the list of task IDs that were checked
    checked_task_ids = request.form.getlist('task_ids')

    # Get all tasks for the event
    tasks = db.session.scalars(sqla.select(
        Task).where(Task.event_id == event_id)).all()

    # Update the completion status of each task
    for task in tasks:
        task.completed = str(task.id) in checked_task_ids

    # Commit the changes to the database
    db.session.commit()

    flash("Tasks updated successfully!", "success")
    return redirect(url_for('main.index'))


@bp_main.route('/checklist_detail/<int:event_id>', methods=['GET', 'POST'])
@login_required
def checklist_detail(event_id):
    # Fetch the event and its tasks
    event = db.session.scalars(sqla.select(
        Event).where(Event.id == event_id)).first()
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for('main.index'))

    tasks = db.session.scalars(
        sqla.select(Task)
        .where(Task.event_id == event_id)
        .order_by(Task.priority.asc(), Task.due_date.asc())
    ).all()
    users = db.session.scalars(
        sqla.select(User).join(event_participants).where(
            event_participants.c.event_id == event_id)
    ).all()
    current_date = datetime.today()
    print("Retrieved Users:", users)
    # Render the checklist.html template with the event and tasks
    return render_template('checklist.html', event=event, tasks=tasks, users=users, current_date=current_date)


@bp_main.route('/get_event/<int:event_id>')
@login_required
def get_event(event_id):
    # Get the event
    event = db.session.get(Event, event_id)
    if not event:
        return "Event not found", 404

    # Fetch tasks sorted by priority
    tasks = db.session.scalars(
        sqla.select(Task).where(Task.event_id ==
                                event_id).order_by(Task.priority.asc())
    ).all()

    return render_template('checklist.html', event=event, tasks=tasks)


@bp_main.route('/update_task/<int:task_id>', methods=['POST'])
@login_required
def update_task(task_id):
    data = request.json
    completed = data.get('completed')

    # Find the task and update its completion status
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    task.completed = completed
    db.session.commit()

    return jsonify({"success": True})


@bp_main.route('/get_event_progress/<int:event_id>')
@login_required
def get_event_progress(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    total_tasks = len(event.tasks)
    completed_tasks = len([task for task in event.tasks if task.completed])
    progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return jsonify({"progress": progress})


@bp_main.route('/update_event_name/<int:event_id>', methods=['POST'])
@login_required
def update_event_name(event_id):
    data = request.json
    new_name = data.get('name')

    # Find the event and update its name
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    event.name = new_name
    db.session.commit()

    return jsonify({"success": True})


@bp_main.route('/update_event_date/<int:event_id>', methods=['POST'])
@login_required
def update_event_date(event_id):
    data = request.json
    new_date = data.get('date')

    # Find the event and update its date
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    event.date = new_date
    db.session.commit()

    return jsonify({"success": True})


@bp_main.route('/delete_event/<int:event_id>', methods=['POST', 'DELETE'])
@login_required
def delete_event(event_id):
    # Find the event
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    # Remove all relationships with users (participants)
    event.participants.clear()

    # Delete all tasks associated with the event
    tasks = db.session.scalars(sqla.select(
        Task).where(Task.event_id == event_id)).all()
    for task in tasks:
        db.session.delete(task)

    # Delete the event
    db.session.delete(event)
    db.session.commit()

    return redirect(url_for('main.index'))


@bp_main.route('/delete_task/<int:task_id>', methods=['POST', 'DELETE'])
@login_required
def delete_task(task_id):
    # Find the task and delete it
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    db.session.delete(task)
    db.session.commit()
    flash('The task has been successfully deleted.')
    return redirect(url_for('main.checklist_detail', event_id=task.event_id))


@bp_main.route('/edit_task/<int:task_id>', methods=['POST'])
@login_required
def edit_task(task_id):
    data = request.get_json()
    task = db.session.get(Task, task_id)

    if not task:
        return jsonify({"success": False, "error": "Task not found"}), 404

    task.description = data.get('description', task.description)
    task.priority = data.get('priority', task.priority)
    task.due_date = data.get('due_date', task.due_date)  # Update the due date

    db.session.commit()
    return jsonify({"success": True, "message": "Task updated successfully"})


@bp_main.route('/add_task', methods=['POST'])
@login_required
def add_task():
    data = request.get_json()
    description = data.get('description')
    priority = data.get('priority')
    due_date = data.get('due_date')  # Get the due date
    event_id = data.get('event_id')

    if not description or not event_id:
        return jsonify({"success": False, "error": "Description and event ID are required"}), 400

    # Create a new task
    new_task = Task(
        description=description,
        priority=priority,
        due_date=due_date,  # Set the due date
        event_id=event_id,
        completed=False
    )
    db.session.add(new_task)
    db.session.commit()

    return jsonify({"success": True, "message": "Task added successfully"})


@bp_main.route('/assign_user_to_event/<int:event_id>', methods=['POST'])
@login_required
def assign_user_to_event(event_id):
    data = request.get_json()
    user_email = data.get('user_email')

    if not user_email:
        return jsonify({"success": False, "error": "User email is required."}), 400

    # Find the user by email
    user = db.session.scalar(sqla.select(User).where(User.email == user_email))
    if not user:
        return jsonify({"success": False, "error": "User not found."}), 404

    # Find the event
    event = db.session.scalar(sqla.select(Event).where(Event.id == event_id))
    if not event:
        return jsonify({"success": False, "error": "Event not found."}), 404

    # Check if the user is already assigned to the event
    if user in event.participants:
        return jsonify({"success": False, "error": "User is already assigned to this event."}), 400

    # Assign the user to the event
    event.participants.append(user)
    db.session.commit()

    return jsonify({"success": True, "message": f"User {user.email} assigned to event {event.name}."})


@bp_main.route('/assign_users_to_task/<int:task_id>', methods=['POST'])
@login_required
def assign_users_to_task(task_id):
    try:
        # Parse the incoming JSON data
        data = request.json
        user_ids = data.get('user_ids', [])

        # Fetch the task
        task = db.session.get(Task, task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404

        # Fetch the users by their IDs
        users = db.session.scalars(
            sqla.select(User).where(User.id.in_(user_ids))
        ).all()

        for user in users:
            task.assigned_users.append(user)

        db.session.commit()

        return jsonify({"success": True, "message": "Users assigned to task successfully!"})
    except Exception as e:
        # Log the error for debugging
        print(f"Error assigning users to task: {e}")
        return jsonify({"error": "An error occurred while assigning users to the task."}), 500


@bp_main.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        # Save the filename to the user's profile picture field
        current_user.profile_picture = file_path
        db.session.commit()

        return f"Profile picture updated to {filename}", 200


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
        db.session.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for('main.display_profile'))

    # Render the edit profile form for GET requests
    return render_template('edit_profile.html', form=form, user=current_user)
