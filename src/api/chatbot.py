import json
import re
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
import google.generativeai as genai
import os
from src import db
from flask_login import current_user
from src.database.models import Event, Task


chatbot_router = Blueprint('chatbot_router', __name__,
                           url_prefix='/chatbot_router')

# Initialize Gemini API
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is not set")
genai.configure(api_key=api_key)
model = genai.GenerativeModel(model_name="gemini-1.5-flash")


@chatbot_router.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    return render_template('chatbot.html', title="Event Chatbot")


@chatbot_router.route('/voicebot', methods=['GET', 'POST'])
def voicebot():
    return render_template('voicebot.html', title="Event VoiceBot")


@chatbot_router.route('/create_event_and_tasks', methods=['POST'])
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
            # Return tasks - Use transaction for database operations
            json_match = re.search(
                r"```json\s*([\s\S]*?)\s*```", response_text)
            if json_match:
                response_text = json_match.group(1).strip()

            tasks_data = json.loads(response_text)

            try:
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
            except Exception as e:
                db.session.rollback()
                raise e

    except json.JSONDecodeError as e:
        db.session.rollback()
        return jsonify({"error": f"Invalid JSON response from Gemini API: {e}. The response was: {response_text}"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error creating tasks: {e}"}), 500


@chatbot_router.route('/chat', methods=['POST'])
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

            try:
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
            except Exception as e:
                db.session.rollback()
                raise e

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
