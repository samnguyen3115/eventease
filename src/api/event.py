
from flask import Blueprint, request, jsonify, redirect, url_for
from flask_login import login_required
import os
from src import db
from flask_login import current_user
from src.database.models import Event, Task, User
import sqlalchemy as sqla
from flask import current_app
from datetime import datetime
from flask import current_app



event_router = Blueprint('event_router', __name__, url_prefix='/event_router')


@event_router.route('/create_event', methods=['POST'])
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


@event_router.route('/update_event_name/<int:event_id>', methods=['POST'])
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


@event_router.route('/update_event_date/<int:event_id>', methods=['POST'])
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


@event_router.route('/delete_event/<int:event_id>', methods=['POST', 'DELETE'])
@login_required
def delete_event(event_id):
    try:
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
                image_path = os.path.join(
                    current_app.static_folder, task.image_link)
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except Exception:
                        pass  # Continue even if deletion fails
            db.session.delete(task)

        # Delete the event
        db.session.delete(event)
        db.session.commit()

        return redirect(url_for('main.index'))

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@event_router.route('/update_event_participants/<int:event_id>', methods=['POST'])
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


@event_router.route('/edit_event/<int:event_id>', methods=['POST'])
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
