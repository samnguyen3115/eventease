from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, TextAreaField,BooleanField
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms.validators import  DataRequired,Length
from flask_wtf.file import FileField, FileAllowed
from wtforms.widgets import ListWidget, CheckboxInput
from .models import Tag

from app import db
import sqlalchemy as sqla

class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(),Length(min=1, max=150)])
    body = TextAreaField('Description', validators=[DataRequired(),Length(min=1, max=1500)])
    color_tag = QuerySelectField(
        'Color Tag',
        query_factory=lambda: db.session.scalars(sqla.select(Tag).where(Tag.category == "color").order_by(Tag.name)),  
        get_label=lambda tag: tag.name,  
        allow_blank=True
    )

    # Dropdown for Building Tag
    building_tag = QuerySelectField(
        'Building Tag',
        query_factory=lambda: db.session.scalars(sqla.select(Tag).where(Tag.category == "building").order_by(Tag.name)),  
        get_label=lambda tag: tag.name,  
        allow_blank=True,  
        blank_text=''  
    )

    image = FileField('Please add an image of the item', validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])    
    submit = SubmitField('Post')
    
class FilterForm(FlaskForm):
    color_filter = SelectField('Filter By Color', choices=[
        ('',''),
        ('1', 'Red'),
        ('2', 'Orange'),
        ('3', 'Yellow'),
        ('4', 'Green'),
        ('5', 'Blue'),
        ('6', 'Purple'),
        ('7', 'Pink'),
        ('8', 'Brown'),
        ('9', 'Black'),
        ('10', 'White'),
        ('11', 'Gray')
    ])
    building_filter = SelectField(
        'Filter By Building',
        choices=[
            ('',''),
            ('12', 'Unity Hall'),
            ('13', 'Gordon Library'),
            ('14', 'Alden Memorial'),
            ('15', 'Atwater Kent Lab'),
            ('16', 'Fuller Lab'),
            ('17', 'Goddard Hall'),
            ('18', 'Higgins Lab'),
            ('19', 'Kaven Hall'),
            ('20', 'Olin Hall'),
            ('21', 'Campus Center'),
            ('22', 'Salisbury Lab'),
            ('23', 'Stratton Lab'),
            ('24', 'Innovation Studio'),
            ('25', 'Morgan Dining Hall'),
            ('26', 'Sports & Recreation Center'),
            ('27', 'Harrington Auditorium'),
            ('28', 'Bartlett Center'),
        ]
    )
    submit = SubmitField('Filter')
    submit2 = SubmitField('Refresh')

    