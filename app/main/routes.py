import json
import re
from tkinter import Image
from flask import Response, render_template, request, jsonify, flash, redirect, send_file, url_for
from flask_login import login_required
import google.generativeai as genai
import os
from ics import Calendar
from ics import Event as IcsEvent
from app import db
from flask_login import current_user
from app.main.models import Event, Task, User, event_participants
import sqlalchemy as sqla
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
from app.main.forms import ProfileForm
from flask import current_app
from datetime import datetime, timedelta
from ultralytics import YOLO
from PIL import Image  # type: ignore
from io import BytesIO
from transformers import BlipProcessor, BlipForConditionalGeneration, CLIPModel, CLIPProcessor
from flask import current_app
from deep_translator import GoogleTranslator
from google.cloud import texttospeech
import tempfile
# Access the models
from app.main import main_blueprint as bp_main


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
        event.progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return render_template('index.html', events=all_events)


@bp_main.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    return render_template('chatbot.html', title="Event Chatbot")

@bp_main.route('/voicebot', methods=['GET', 'POST'])
def voicebot():
    return render_template('voicebot.html', title="Event VoiceBot")


@bp_main.route('/create_event', methods=['POST'])
@login_required
def create_event():
    data = request.json
    event_name = data.get('eventName')
    event_date = data.get('eventDate')  # Optional field
    event_description = data.get('eventDescription')  # Optional field
    user_id = current_user.id

    if not event_name:
        return jsonify({"error": "Event name is required."}), 400

    new_event = Event(
        name=event_name,
        user_id=user_id,
        strict_mode=False  # Default to False
    )
    if event_date:
        new_event.date = datetime.strptime(event_date, '%Y-%m-%d')
    if event_description:
        new_event.description = event_description
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
        Format the list into just a normal list, not a markdown list.
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
            {{"task": "Book hotel", "priority": 1, "item": "none"}},
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
    friends = current_user.friends.all()  # Fetch the user's friends
    
    assigned_friend_ids = [int(friend.id) for friend in event.participants]
    # Render the checklist.html template with the event and tasks
    return render_template('checklist.html', event=event, tasks=tasks, users=users, current_date=current_date, strict_mode=event.strict_mode,friends=friends,assigned_friend_ids=assigned_friend_ids)


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
        if task.image_link:
            image_path = os.path.join(current_app.static_folder, task.image_link)
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    print(f"Deleted image: {image_path}")  # Debugging log
                except Exception as e:
                    print(f"Error deleting image: {e}")  # Debugging log
        db.session.delete(task)

    # Delete the event
    db.session.delete(event)
    db.session.commit()

    return redirect(url_for('main.index'))


@bp_main.route('/delete_task/<int:task_id>', methods=['POST', 'DELETE'])
@login_required
def delete_task(task_id):
    # Find the task
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    # Delete the associated image file if it exists
    if task.image_link:
        image_path = os.path.join(current_app.static_folder, task.image_link)
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                print(f"Deleted image: {image_path}")  # Debugging log
            except Exception as e:
                print(f"Error deleting image: {e}")  # Debugging log

    # Delete the task
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
    task.note = data.get('note', task.note) 
    task.priority = data.get('priority', task.priority)
    print(data.get('due_date'))
    if data.get('due_date'):
        task.due_date = data.get(
            'due_date', task.due_date)  # Update the due date
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
    note = data.get('note') 
    item = data.get('item') 
    priority = data.get('priority')
    due_date = data.get('due_date')  
    event_id = data.get('event_id')

    if not description or not event_id:
        return jsonify({"success": False, "error": "Description and event ID are required"}), 400

    # Create a new task
    new_task = Task(
        description=description,
        note=note, 
        priority=priority,
        event_id=event_id,
        completed=False
    )
    if (due_date):
        new_task.due_date = datetime.strptime(due_date, '%Y-%m-%d')
    if item:
        new_task.item = item
    db.session.add(new_task)
    db.session.commit()

    return jsonify({"success": True, "message": "Task added successfully"})


@bp_main.route('/update_event_participants/<int:event_id>', methods=['POST'])
@login_required
def update_event_participants(event_id):
    data = request.get_json()
    add_ids = data.get('add', [])
    remove_ids = data.get('remove', [])

    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"success": False, "error": "Event not found."}), 404

    # Add users to the event
    for friend_id in add_ids:
        friend = db.session.get(User, friend_id)
        if friend and friend in current_user.friends and friend not in event.participants:
            event.participants.append(friend)

    # Remove users from the event
    for friend_id in remove_ids:
        friend = db.session.get(User, friend_id)
        if friend and friend in event.participants:
            event.participants.remove(friend)

    db.session.commit()
    return jsonify({"success": True, "message": "Event participants updated successfully."})


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


blip_processor = BlipProcessor.from_pretrained(
    "Salesforce/blip-image-captioning-base", use_fast=True)
blip_model = BlipForConditionalGeneration.from_pretrained(
    "Salesforce/blip-image-captioning-base")
@bp_main.route('/complete_task_with_image/<int:task_id>', methods=['POST'])
@login_required
def complete_task_with_image(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if not task.item:
        return jsonify({"error": "This task does not require an item to be verified."}), 400

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
         
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400


    try:
        # Validate the uploaded file as an image
        original_file_bytes = file.read()
        file_stream_for_blip = BytesIO(original_file_bytes)
        file_stream_for_save = BytesIO(original_file_bytes)
        try:
            img = Image.open(file_stream_for_blip)
            img.verify()  # Verify that the file is a valid image
        except Exception:
            return jsonify({"error": "The uploaded file is not a valid image."}), 400

        # Reload the image for BLIP processing
        file_stream_for_blip.seek(0)  # Reset the stream position to the beginning
        img = Image.open(file_stream_for_blip).convert('RGB')  # Ensure the image is in RGB format
        max_size = (512, 512)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Generate a caption using BLIP
        inputs = blip_processor(images=img, return_tensors="pt")
        outputs = blip_model.generate(**inputs, max_length=50, num_beams=5)
        caption = blip_processor.decode(outputs[0], skip_special_tokens=True)

        print(f"Generated caption: {caption}")

        # Use Google Generative AI to determine if the required item and caption are related
        required_item = task.item.lower()
        prompt = f"""
        Analyze if the following image caption likely describes an image is related to the  required item.
        Required item: "{required_item}"
        Caption: "{caption}"
        Try to be easy with this, and don't be too strict.
        Consider synonyms, context, and partial matches (e.g., 'mug' for 'cup', 'car' in 'parking lot with cars').
        Respond with 'true' if the item is likely present, 'false' if not,just "true" or "false".
        """
        try:
            response = model.generate_content(prompt)
            relation = response.text.strip().lower()
            print(f"Relation response: {relation}")

            if relation == "true":
                if allowed_file(file.filename):
                    if task.image_link:
                        # Delete the old image if it exists
                        old_image_path = os.path.join(
                            current_app.static_folder, task.image_link)
                        if os.path.exists(old_image_path):
                            try:
                                os.remove(old_image_path)
                                print(f"Deleted old image: {old_image_path}")  # Debugging log
                            except Exception as e:
                                print(f"Error deleting old image: {e}")
                    filename = secure_filename(file.filename)
                    image_folder = os.path.join(current_app.static_folder, 'task_images')
                    os.makedirs(image_folder, exist_ok=True)  # Create folder if not exists
                    image_path = os.path.join(image_folder, filename)

                    file_stream_for_save.seek(0)  # Reset before saving
                    with open(image_path, 'wb') as f:
                        f.write(file_stream_for_save.read())

            # Update task
                    task.image_link = f'task_images/{filename}'
                    task.completed = True
                    db.session.commit()
                # Save the image to the filesystem
                
                # Mark the task as completed and save the image path
                print("Item found in the image!")
                return jsonify({
                    "success": True,
                    "message": f"Task completed successfully! Great job!!",
                    "caption": caption,
                    "related": True
                })

            task.completed = False
            print("Item not found in the image!")
            db.session.commit()
            return jsonify({
                "success": False,
                "message": f"The required item was not found in the image. Please try again",
                "caption": caption,
                "related": False
            }), 400

        except Exception as e:
            return jsonify({"error": f"An error occurred while using Generative AI: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@bp_main.route('/bypass_item/<int:task_id>', methods=['POST'])
@login_required
def bypass_item(task_id):
    try:
        # Fetch the task
        task = db.session.get(Task, task_id)
        if not task:
            return jsonify({"success": False, "error": "Task not found."}), 404

        # Perform the bypass logic (e.g., mark the task as completed or remove the item requirement)
        task.item = None  # Example: Remove the item requirement
        task.completed = True  # Optionally mark the task as completed
        db.session.commit()

        return jsonify({"success": True, "message": "Task bypassed successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500


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
    
    
@bp_main.route('/add_friend', methods=['POST'])
@login_required
def add_friend():
    try:
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({"success": False, "error": "Email is required."}), 400

        friend_email = data.get('email')
        print(f"Received email: {friend_email}")  # Debugging log

        friend = db.session.scalar(sqla.select(User).where(User.email == friend_email))
        if not friend:
            return jsonify({"success": False, "error": "User not found."}), 404

        print(f"Found friend: {friend.username}")  # Debugging log

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
    
@bp_main.route('/edit_event/<int:event_id>', methods=['POST'])
@login_required
def edit_event(event_id):
    data = request.get_json()
    new_name = data.get('new_event_name')
    new_date = data.get('new_event_date')
    new_owner_id = data.get('new_owner_id')

    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"success": False, "error": "Event not found."}), 404

    if current_user.id != event.user_id:
        return jsonify({"success": False, "error": "Only the current owner can change ownership."}), 403

    new_owner = db.session.get(User, new_owner_id)
    if not new_owner or new_owner not in event.participants:
        return jsonify({"success": False, "error": "Selected user is not a participant of the event."}), 400

    # Update the event owner
    event.user_id = new_owner_id
    if new_name:
        event.name = new_name
    if new_date:
        event.date = new_date
    db.session.commit()

    return jsonify({"success": True, "message": "Event ownership changed successfully."})

@bp_main.route('/verify_task/<int:task_id>', methods=['POST'])
@login_required
def verify_task(task_id):
    data = request.get_json()
    is_verified = data.get('verified')
    note = data.get('note', '').strip()  # Get the note from the request

    # Fetch the task
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"success": False, "error": "Task not found."}), 404

    # Update the task's completion status and note
    task.completed = is_verified
    task.note = note
    db.session.commit()

    if is_verified:
        message = "Task verified successfully!"
    else:
        message = "Task marked as not completed. Note updated."

    return jsonify({"success": True, "message": message})

@bp_main.route('/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    text = data.get('text', '')
    target_lang = data.get('target_lang', 'en')

    try:
        translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
        return jsonify({'translated_text': translated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp_main.route('/speak', methods=['POST'])
def speak():
    try:
        data = request.json
        text = data.get('text', '')
        lang = data.get('lang', 'en-US')

        if not text:
            return jsonify({"error": "Text is required"}), 400

        # Log the number of characters used
        character_count = len(text)
        print(f"Characters used in this request: {character_count}")

        # Initialize the TTS client
        client = texttospeech.TextToSpeechClient()

        # Prepare the input text
        input_text = texttospeech.SynthesisInput(text=text)

        # Configure the voice
        voice = texttospeech.VoiceSelectionParams(
            language_code=lang,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
            name=f"{lang}-Standard-A"  # Customize this if needed
        )

        # Configure the audio output
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        # Call the TTS API
        response = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)

        # Save the audio to a temporary file
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_audio.write(response.audio_content)
        temp_audio.seek(0)

        # Send the audio file to the client
        return send_file(temp_audio.name, mimetype='audio/mpeg')

    except Exception as e:
        print(f"Error in /speak route: {e}")
        return jsonify({"error": "An error occurred while generating speech"}), 500

    finally:
        # Clean up temporary files
        if 'temp_audio' in locals():
            try:
                os.unlink(temp_audio.name)
            except Exception as cleanup_error:
                print(f"Error cleaning up temporary file: {cleanup_error}")
    