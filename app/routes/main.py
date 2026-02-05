from flask import Blueprint, render_template, session, redirect, url_for

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
    # RBAC check is also done in API, but good to check here or let API 403 handle it
    # We'll just render and let the JS fetch fail if not admin
    return render_template('admin.html')
