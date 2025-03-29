import json
import re
from flask import render_template, request, jsonify, flash, redirect, url_for
import google.generativeai as genai
import os
from app import db
from flask_login import current_user
from app.main.models import Event, Task
from app.main import main_blueprint as bp_main
import sqlalchemy as sqla
from sqlalchemy.orm import joinedload

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="gemini-1.5-flash")

@bp_main.route('/')
@bp_main.route('/index')
def index():
    # Query all events and their associated tasks
    events = db.session.scalars(
        sqla.select(Event).options(joinedload(Event.tasks))
    ).unique().all()  # Ensure unique results

    # Pass the events (with tasks) to the template
    return render_template('index.html', title="Event Portal", events=events)

@bp_main.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    return render_template('chatbot.html', title="Event Chatbot")

@bp_main.route('/create_event', methods=['POST'])
def create_event():
    data = request.json
    event_name = data.get('eventName')
    user_id = current_user.id

    if not event_name:
        return jsonify({"error": "Event name is required."}), 400

    new_event = Event(name=event_name, user_id=user_id)
    db.session.add(new_event)
    db.session.commit()

    return jsonify({"eventId": new_event.id})

@bp_main.route('/create_event_and_tasks', methods=['POST'])
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
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
            if json_match:
                response_text = json_match.group(1).strip()

            tasks_data = json.loads(response_text)

            for task_data in tasks_data:
                task = Task(
                    description=task_data.get('task', 'No description provided'),
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

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404

    prompt = f"""
    Generate a JSON checklist for the following event: {user_input}.
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

        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            response_text = json_match.group(1).strip()

        tasks_data = json.loads(response_text)

        for task_data in tasks_data:
            task = Task(
                description=task_data.get('task', 'No description provided'),
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
    
@bp_main.route('/update_tasks/<int:event_id>', methods=['POST'])    
def update_tasks(event_id):
    # Get the list of task IDs that were checked
    checked_task_ids = request.form.getlist('task_ids')

    # Get all tasks for the event
    tasks = db.session.scalars(sqla.select(Task).where(Task.event_id == event_id)).all()

    # Update the completion status of each task
    for task in tasks:
        task.completed = str(task.id) in checked_task_ids

    # Commit the changes to the database
    db.session.commit()

    flash("Tasks updated successfully!", "success")
    return redirect(url_for('main.index'))

@bp_main.route('/checklist_detail/<int:event_id>', methods=['GET', 'POST'])
def checklist_detail(event_id):
    # Get the event and its tasks
    event = db.session.scalars(sqla.select(Event).where(Event.id == event_id)).first()
    if not event:
        return jsonify({"error": "Event not found."}), 404

    # Fetch tasks sorted by priority
    tasks = db.session.scalars(
        sqla.select(Task).where(Task.event_id == event_id).order_by(Task.priority.asc())
    ).all()

    return render_template('checklist.html', event=event, tasks=tasks)

@bp_main.route('/get_event/<int:event_id>')
def get_event(event_id):
    # Get the event
    event = db.session.get(Event, event_id)
    if not event:
        return "Event not found", 404

    # Fetch tasks sorted by priority
    tasks = db.session.scalars(
        sqla.select(Task).where(Task.event_id == event_id).order_by(Task.priority.asc())
    ).all()

    return render_template('checklist.html', event=event, tasks=tasks)

@bp_main.route('/update_task/<int:task_id>', methods=['POST'])
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