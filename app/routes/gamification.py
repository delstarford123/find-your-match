import os
from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.database import db

gamification_v4_bp = Blueprint('gamification_v4', __name__, url_prefix='/api/v4/gamification')

@gamification_v4_bp.route('/pop-the-balloon')
def pop_the_balloon():
    user_id = session.get('user_id')
    if not user_id:
        flash("You must be logged in to enter the virtual dating room.")
        return redirect(url_for('auth.login'))
        
    user_ref = db.reference(f'profiles/{user_id}')
    user_data = user_ref.get()
    
    if not user_data:
        return redirect(url_for('auth.login'))
        
    return render_template('pop_the_balloon.html', 
                           current_user=user_data,
                           user_id=user_id)
