import io
import mimetypes
import sys
from flask import Response, abort, render_template, flash, redirect, send_file, url_for, request,jsonify
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload
import sqlalchemy as sqla

from app import db
from app.main.models import Post,Tag, postTags, ImageStore,Building
from app.main.forms import PostForm, FilterForm

from app.main import main_blueprint as bp_main

@bp_main.route('/', methods=['GET'])
@bp_main.route('/index', methods=['GET','POST'])
@login_required
def index(): 
    form = FilterForm()
    color_filter = request.args.get('color_filter')
    building_filter = request.args.get('building_filter')
    form.color_filter.data = color_filter  
    form.building_filter.data = building_filter
    print(f"Color Filter: {color_filter}")
    print(f"Building Filter: {building_filter}")
    # Start building the query for all posts ordered by timestamp
    query = db.session.scalars(sqla.select(Post).order_by(Post.timestamp.desc()))

    # If there is a color filter, add the condition to filter based on the color tag's name
    if color_filter and color_filter != '':
        if  building_filter and building_filter != '':
            query = db.session.scalars(sqla.select(Post).where(sqla.and_(Post.color_tag_id == color_filter , Post.building_tag_id == building_filter)))
        else:
            query = db.session.scalars(sqla.select(Post).where(Post.color_tag_id == color_filter ))
    else:
       if(building_filter) and building_filter != '':
            query = db.session.scalars(sqla.select(Post).where(Post.building_tag_id == building_filter))


    refresh = request.args.get('submit2')
    if refresh:
        query = db.session.scalars(sqla.select(Post).order_by(Post.timestamp.desc()))

     # Execute the query to get the filtered posts
    all_posts = query.all()
    if not all_posts:
        flash('No posts found with the selected filters')
        all_posts = db.session.scalars(sqla.select(Post).order_by(Post.timestamp.desc())).all()   
    
    # Render the page with the filtered posts
    return render_template('index.html', title="Lost And Found Portal", posts=all_posts, form=form)


@bp_main.route('/post', methods=['GET', 'POST'])
@login_required
def postsmile():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(writer = current_user,
                    title=form.title.data,
                    color_tag=form.color_tag.data,
                    building_tag=form.building_tag.data,
                    description=form.body.data)
        db.session.add(post)
        db.session.commit()
        if form.image.data:
            image_file = form.image.data
            image_data = image_file.read()  # Read the file data as binary
            image_type = mimetypes.guess_type(image_file.filename)[0]  # Guess the MIME type based on file extension
            image = ImageStore(post_id=post.id, image_data=image_data, image_type=image_type)
            db.session.add(image)
            db.session.commit()
        flash('Your new smile post is created')
        return redirect(url_for('main.index'))
    return render_template('create.html', title='Post', form=form)

@bp_main.route('/image/<int:post_id>')
def get_image(post_id):
    image_record = db.session.query(ImageStore).filter_by(post_id=post_id).first()
    if image_record is None or image_record.image_data is None:
        abort(404)
    return Response(image_record.image_data, mimetype=image_record.image_type or 'image/jpeg')



@bp_main.route('/post/<post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = db.session.scalars(sqla.select(Post).where(Post.id == post_id)).first()
    if post:
        tags = db.session.scalars(sqla.select(Tag).join(Post.tags).where(Post.id == post_id))
        for tag in tags:
            post.tags.remove(tag)
    db.session.commit()
    db.session.delete(post)
    db.session.commit()
    flash('The post and its tags have been successfully deleted.')
    return redirect(url_for('main.index'))



@bp_main.route('/map', methods=['GET'])
@login_required
def map():
    return render_template('map.html', title='Map')

@bp_main.route('/building/<building_id>', methods=['GET'])
@login_required
def map_building(building_id):
    building = db.session.get(Building, building_id)
    name = building.get_name()
    place = building.get_place()
    body = building.get_body()
    count = building.get_count()
    theme = building.get_theme()
    image = building.get_image()
    places_info = zip(place, body, image)
    return render_template('building.html', title='Map', building_id=building_id, name=name, place=place, body=body, count=count, theme=theme, image=image,places_info=places_info)


