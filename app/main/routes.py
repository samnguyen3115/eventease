import json
import re
from tkinter import Image
from flask import Response, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
import google.generativeai as genai
import os
from ics import Calendar
from ics import Event as IcsEvent
from app import db
from flask_login import current_user
from app.main.models import Event, Task, User, event_participants
from app.main import main_blueprint as bp_main
import sqlalchemy as sqla
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
from app.main.forms import ProfileForm
from flask import current_app
from datetime import datetime,timedelta
from ultralytics import YOLO
from PIL import Image # type: ignore
import numpy as np
from io import BytesIO
from transformers import BlipProcessor, BlipForConditionalGeneration



UPLOAD_FOLDER = 'static/profile_pics'  # Define where images should be stored
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="gemini-1.5-flash")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp_main.route('/', methods=['GET'])
def root():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))  
    else:
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
        Based on the following event description: "{user_input}", ask ONE clarifying question that will help create a more specific checklist.
        Do not ask about things already mentioned in "{user_input}".
        Return ONLY the question.
        """
        else:
            if question_index < 2:
                # Ask a follow-up question
                prompt = f"""
        Based on the following conversation:
        {conversation_history}
        Ask the user what aspect of the event they want to prioritize most (e.g., fun, efficiency, preparation, safety, etc...).\
        Create the list of aspect based on their event, not the template. You can guess with "{event.name}".
        Format your response with just the question and a short list of example options. 
        Do not ask about things already mentioned in the chat: {conversation_history}
        """
            else:
                # Generate the checklist after all questions are answered
                prompt = f"""
        Based on the following conversation:
        {conversation_history}
        Generate a JSON checklist with at least 8 pre-event tasks related to the event "{event.name}".
        Use the priorities expressed in the second question to set 'priority' (1: important, 2: necessary, 3: normal).
        Each task should include:
        - 'task': the description of the task.
        - 'priority': based on how relevant it is to the user's stated priorities.
        - 'due_date': only if the user has already mentioned a date.
        - 'item': the physical item involved. For example:
            - If the task is "Bring guitar", item = "guitar"
            - If the task is "Book hotel", item = "none"
            - Remember the item just be 1 item, not a list of items.
        
        Return ONLY the JSON. No explanations. No markdown. Just pure JSON like:
        [
            {{"task": "Book hotel", "priority": 1, "due_date": "2023-10-01", "item": "none"}},
            {{"task": "Pack sunscreen", "priority": 2, "item": "sunscreen"}},
            {{"task": "Buy snacks", "priority": 3, "item": "snacks"}}
        ]
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
                    due_date=task_data.get('due_date', None),
                    item=task_data.get('item', None),
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
    return render_template('checklist.html', event=event, tasks=tasks, users=users, current_date=current_date,strict_mode=event.strict_mode)


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
    print (data.get('due_date'))
    if data.get('due_date'):
        task.due_date = data.get('due_date', task.due_date)  # Update the due date
    if data.get('item'):
        task.item = data.get('item', task.item)  # Update the item
    else:
        task.item = None
    db.session.commit()
    return jsonify({"success": True, "message": "Task updated successfully"})


@bp_main.route('/add_task', methods=['POST'])
@login_required
def add_task():
    data = request.get_json()
    description = data.get('description')
    item = data.get('item')  # Get the item
    priority = data.get('priority')
    due_date = data.get('due_date')  # Get the due date
    event_id = data.get('event_id')

    if not description or not event_id:
        return jsonify({"success": False, "error": "Description and event ID are required"}), 400

    # Create a new task
    new_task = Task(
        description=description,
        priority=priority,
        event_id=event_id,
        completed=False
    )
    if(due_date):
        new_task.due_date = datetime.strptime(due_date, '%Y-%m-%d')
    if item:
        new_task.item = item
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

@bp_main.route('/calender.ics', methods=['GET'])
def calender_feed():
    token = request.args.get('token')
    if token != "your_secure_token":
        return "Unauthorized", 401
    # Fetch tasks assigned to the current user
    tasks = db.session.scalars(
        sqla.select(Task).where(Task.assigned_users.any(User.id == current_user.id))
    ).all()

    calendar = Calendar()  # Create a new calendar

    for task in tasks:
        if task.due_date is not None:
            # Create an event for each task
            e = IcsEvent()
            e.name = task.description  # Set the name of the event
            e.begin = task.due_date  # Set the start time of the event
            e.end = task.due_date + timedelta(days=1)  # Set the end time (1 day duration)
            e.priority = task.priority  # Add priority (customize as needed)
            e.description = task.event.name if task.event else 'No Event Description'  # Add description

            calendar.events.add(e)  # Add the event to the calendar
                # Return the calendar feed as a response
    return Response(str(calendar), mimetype="text/calendar")

# Load the BLIP model and processor
blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

@bp_main.route('/complete_task_with_image/<int:task_id>', methods=['POST'])
@login_required
def complete_task_with_image(task_id):
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Fetch the task
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if not task.item:
        return jsonify({"error": "This task does not require an item to be verified."}), 400

    try:
        # Validate the uploaded file as an image
        file_stream = BytesIO(file.read())
        try:
            img = Image.open(file_stream)
            img.verify()  # Verify that the file is a valid image
        except Exception:
            return jsonify({"error": "The uploaded file is not a valid image."}), 400

        # Reload the image for BLIP processing
        file_stream.seek(0)  # Reset the stream position to the beginning
        img = Image.open(file_stream).convert('RGB')  # Ensure the image is in RGB format

        # Generate a caption using BLIP
        inputs = blip_processor(images=img, return_tensors="pt")
        outputs = blip_model.generate(**inputs)
        caption = blip_processor.decode(outputs[0], skip_special_tokens=True)

        print(f"Generated caption: {caption}")

        # Use Google Generative AI to determine if the required item and caption are related
        required_item = task.item.lower()
        prompt = f"""
        Determine if the following two phrases are related:
        1. Required item: "{required_item}"
        2. Caption: "{caption}"
        Respond with "true" if they are related and "false" if they are not.
        """
        try:
            # Use genai.generate_text instead of model.generate_text
            response = model.generate_content(prompt)
            relation = response.text.strip().lower()

            if relation == "true":
                # Mark the task as completed
                task.completed = True
                db.session.commit()
                return jsonify({
                    "success": True,
                    "message": f"Task '{task.description}' completed successfully!",
                    "caption": caption,
                    "related": True
                })
            task.completed = False
            db.session.commit()
            return jsonify({
                "success": False,
                "message": f"The required item '{task.item}' was not found in the image.",
                "caption": caption,
                "related": False
            }), 400

        except Exception as e:
            return jsonify({"error": f"An error occurred while using Generative AI: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    
@bp_main.route('/strict_mode/<int:event_id>', methods=['POST'])
@login_required
def strict_mode(event_id):
    try:
        # Parse the incoming JSON data
        data = request.get_json()
        if data is None or 'strict_mode' not in data:
            return jsonify({"error": "Missing 'strict_mode' field in the request."}), 400

        strict_mode = data.get('strict_mode')
        if not isinstance(strict_mode, bool):
            return jsonify({"error": "'strict_mode' must be a boolean value."}), 400

        # Find the event
        event = db.session.get(Event, event_id)
        if not event:
            return jsonify({"error": "Event not found."}), 404

        # Update the strict mode status
        event.strict_mode = strict_mode
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Strict mode {'enabled' if strict_mode else 'disabled'} successfully!",
            "strict_mode": event.strict_mode
        })

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500