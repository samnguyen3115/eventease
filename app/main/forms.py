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
    language = SelectField('Language', choices=[
        ('en-US', 'English'),
        ('fr-FR', 'French'),
        ('es-ES', 'Spanish'),
        ('de-DE', 'German'),
        ('it-IT', 'Italian'),
        ('pt-PT', 'Portuguese'),
        ('zh-CN', 'Chinese'),
        ('ja-JP', 'Japanese'),
        ('ru-RU', 'Russian'),
        ('ar-SA', 'Arabic'),
        ('ko-KR', 'Korean'),
        ('hi-IN', 'Hindi'),
        ('tr-TR', 'Turkish'),
        ('nl-NL', 'Dutch'),
        ('sv-SE', 'Swedish'),
        ('no-NO', 'Norwegian'),
        ('da-DK', 'Danish'),
        ('fi-FI', 'Finnish'),
        ('pl-PL', 'Polish'),
        ('cs-CZ', 'Czech'),
        ('hu-HU', 'Hungarian'),
        ('ro-RO', 'Romanian'),
        ('sk-SK', 'Slovak'),
        ('bg-BG', 'Bulgarian'),
        ('el-GR', 'Greek'),
        ('th-TH', 'Thai'),
        ('vi-VN', 'Vietnamese'),
        ('id-ID', 'Indonesian'),
        ('ms-MY', 'Malay'),
        ('tl-PH', 'Filipino'),
        ('sw-KE', 'Swahili')
        
    ], validators=[DataRequired()])
    profile_picture = FileField('Please add an image of the item', validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])    
    
    submit = SubmitField('Post')
    