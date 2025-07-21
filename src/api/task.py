
from flask import Blueprint, render_template, request, jsonify, flash, redirect, send_file, url_for
from flask_login import login_required
import google.generativeai as genai
import os
from src import db
from flask_login import current_user
from src.database.models import Event, Task, User, event_participants
import sqlalchemy as sqla
from werkzeug.utils import secure_filename
from flask import current_app
from datetime import datetime
from PIL import Image
from io import BytesIO
from transformers import BlipProcessor, BlipForConditionalGeneration
from flask import current_app
from deep_translator import GoogleTranslator  
from google.cloud import texttospeech  
import tempfile

task_router = Blueprint('task_router', __name__, url_prefix='/task_router')

# Global variables for lazy loading BLIP models
_blip_processor = None
_blip_model = None
model = genai.GenerativeModel(model_name="gemini-1.5-flash")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_blip_models():
    """Lazy load BLIP models only when needed"""
    global _blip_processor, _blip_model
    if _blip_processor is None or _blip_model is None:
        try:
            _blip_processor = BlipProcessor.from_pretrained(
                "Salesforce/blip-image-captioning-base",
                use_fast=True
            )
            _blip_model = BlipForConditionalGeneration.from_pretrained(
                "Salesforce/blip-image-captioning-base"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load BLIP models: {str(e)}")
    return _blip_processor, _blip_model


@task_router.route('/update_tasks/<int:event_id>', methods=['POST'])
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


@task_router.route('/checklist_detail/<int:event_id>', methods=['GET', 'POST'])
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
    return render_template('checklist.html', event=event, tasks=tasks, users=users, current_date=current_date, strict_mode=event.strict_mode, friends=friends, assigned_friend_ids=assigned_friend_ids)


@task_router.route('/update_task/<int:task_id>', methods=['POST'])
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


@task_router.route('/delete_task/<int:task_id>', methods=['POST', 'DELETE'])
@login_required
def delete_task(task_id):
    try:
        # Find the task
        task = db.session.get(Task, task_id)
        if not task:
            return jsonify({"success": False, "error": "Task not found"}), 404

        # Delete the associated image file if it exists
        if task.image_link:
            image_path = os.path.join(
                current_app.static_folder, task.image_link)
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except OSError:
                    pass  # Continue even if file deletion fails

        event_id = task.event_id
        # Delete the task
        db.session.delete(task)
        db.session.commit()

        if request.is_json:
            return jsonify({"success": True, "message": "Task deleted successfully"})
        else:
            flash('The task has been successfully deleted.')
            return redirect(url_for('main.checklist_detail', event_id=event_id))

    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500
        else:
            flash('An error occurred while deleting the task.')
            return redirect(url_for('main.index'))


@task_router.route('/edit_task/<int:task_id>', methods=['POST'])
@login_required
def edit_task(task_id):
    try:
        data = request.get_json()
        task = db.session.get(Task, task_id)

        if not task:
            return jsonify({"success": False, "error": "Task not found"}), 404

        task.description = data.get('description', task.description)
        task.note = data.get('note', task.note)
        task.priority = data.get('priority', task.priority)

        if data.get('due_date'):
            try:
                if isinstance(data.get('due_date'), str):
                    task.due_date = datetime.strptime(
                        data.get('due_date'), '%Y-%m-%d')
                else:
                    task.due_date = data.get('due_date', task.due_date)
            except ValueError:
                return jsonify({"success": False, "error": "Invalid due date format"}), 400

        if data.get('item'):
            task.item = data.get('item', task.item)
        else:
            task.item = None

        db.session.commit()
        return jsonify({"success": True, "message": "Task updated successfully"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500


@task_router.route('/add_task', methods=['POST'])
@login_required
def add_task():
    try:
        data = request.get_json()
        description = data.get('description')
        note = data.get('note')
        item = data.get('item')
        priority = data.get('priority')
        due_date = data.get('due_date')
        event_id = data.get('event_id')

        if not description or not event_id:
            return jsonify({"success": False, "error": "Description and event ID are required"}), 400

        # Validate event exists and user has access
        event = db.session.get(Event, event_id)
        if not event:
            return jsonify({"success": False, "error": "Event not found"}), 404

        # Create a new task
        new_task = Task(
            description=description,
            note=note,
            priority=priority or 3,  # Default to normal priority
            event_id=event_id,
            completed=False
        )

        if due_date:
            try:
                new_task.due_date = datetime.strptime(due_date, '%Y-%m-%d')
            except ValueError:
                return jsonify({"success": False, "error": "Invalid due date format"}), 400

        if item:
            new_task.item = item

        db.session.add(new_task)
        db.session.commit()

        return jsonify({"success": True, "message": "Task added successfully"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500


@task_router.route('/assign_users_to_task/<int:task_id>', methods=['POST'])
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
        db.session.rollback()
        return jsonify({"error": "An error occurred while assigning users to the task."}), 500


@task_router.route('/complete_task_with_image/<int:task_id>', methods=['POST'])
@login_required
def complete_task_with_image(task_id):
    try:
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

        # Validate the uploaded file as an image
        original_file_bytes = file.read()
        file_stream_for_blip = BytesIO(original_file_bytes)
        file_stream_for_save = BytesIO(original_file_bytes)

        try:
            img = Image.open(file_stream_for_blip)
            img.verify()  # Verify that the file is a valid image
        except Exception:
            return jsonify({"error": "The uploaded file is not a valid image."}), 400

        # Load BLIP models only when needed
        try:
            blip_processor, blip_model = get_blip_models()
        except RuntimeError as e:
            return jsonify({"error": f"AI model unavailable: {str(e)}"}), 503

        # Reload the image for BLIP processing
        # Reset the stream position to the beginning
        file_stream_for_blip.seek(0)
        img = Image.open(file_stream_for_blip).convert(
            'RGB')  # Ensure the image is in RGB format
        max_size = (512, 512)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Generate a caption using BLIP
        inputs = blip_processor(images=img, return_tensors="pt")
        outputs = blip_model.generate(**inputs, max_length=50, num_beams=5)
        caption = blip_processor.decode(outputs[0], skip_special_tokens=True)

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

            if relation == "true":
                if allowed_file(file.filename):
                    # Delete old image if exists
                    if task.image_link:
                        old_image_path = os.path.join(
                            current_app.static_folder, task.image_link)
                        if os.path.exists(old_image_path):
                            try:
                                os.remove(old_image_path)
                            except Exception:
                                pass  # Continue even if deletion fails

                    # Save new image
                    filename = secure_filename(file.filename)
                    image_folder = os.path.join(
                        current_app.static_folder, 'task_images')
                    os.makedirs(image_folder, exist_ok=True)
                    image_path = os.path.join(image_folder, filename)

                    file_stream_for_save.seek(0)
                    with open(image_path, 'wb') as f:
                        f.write(file_stream_for_save.read())

                    # Update task
                    task.image_link = f'task_images/{filename}'
                    task.completed = True
                    db.session.commit()

                return jsonify({
                    "success": True,
                    "message": f"Task completed successfully! Great job!!",
                    "caption": caption,
                    "related": True
                })

            # Item not found
            task.completed = False
            db.session.commit()
            return jsonify({
                "success": False,
                "message": f"The required item was not found in the image. Please try again",
                "caption": caption,
                "related": False
            }), 400

        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"An error occurred while using Generative AI: {str(e)}"}), 500

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@task_router.route('/bypass_item/<int:task_id>', methods=['POST'])
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


@task_router.route('/strict_mode/<int:event_id>', methods=['POST'])
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


@task_router.route('/verify_task/<int:task_id>', methods=['POST'])
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


@task_router.route('/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    text = data.get('text', '')
    target_lang = data.get('target_lang', 'en')

    try:
        translated = GoogleTranslator(
            source='auto', target=target_lang).translate(text)
        return jsonify({'translated_text': translated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@task_router.route('/speak', methods=['POST'])
def speak():
    try:
        data = request.json
        text = data.get('text', '')
        lang = data.get('lang', 'en-US')

        if not text:
            return jsonify({"error": "Text is required"}), 400

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
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3)

        # Call the TTS API
        response = client.synthesize_speech(
            input=input_text, voice=voice, audio_config=audio_config)

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
