from flask import Blueprint, abort, render_template, session, redirect, url_for

from app.routes.auth import current_user

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

@bp.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')

@bp.route('/register')
def register():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('register.html')

@bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    return render_template('dashboard.html')

@bp.route('/wallet')
def wallet():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    return render_template('wallet.html')

@bp.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    user = current_user()
    if not user or not user.is_active:
        session.clear()
        return redirect(url_for('main.login'))
    if user.role != 'admin':
        abort(403)
    return render_template('admin.html')
