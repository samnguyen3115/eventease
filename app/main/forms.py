from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, TextAreaField,BooleanField,IntegerField
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms.validators import  DataRequired,Length
from flask_wtf.file import FileField, FileAllowed
from wtforms.widgets import ListWidget, CheckboxInput
from .models import User

class ProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Length(min=6, max=35)])
    profile_picture = FileField('Please add an image of the item', validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])    
    submit = SubmitField('Post')
    