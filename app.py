import pymysql
pymysql.install_as_MySQLdb()

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mysqldb import MySQL
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import traceback

# --- FLASK APP SETUP ---
app = Flask(__name__)

# IMPORTANT: Set secret key BEFORE configuring CORS
app.secret_key = 'your_strong_secret_key_here_for_security_12345'

# Configure session cookie settings
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Enable CORS - MUST support credentials
CORS(app, 
     supports_credentials=True, 
     origins=["http://localhost:5000", "http://127.0.0.1:5000"],
     allow_headers=["Content-Type"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'password'  # CHANGE THIS!
app.config['MYSQL_DB'] = 'BloodDonationDB'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# --- DECORATORS & AUTH ---
def login_required(f):
    """Decorator to check if user is logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user_id exists in session
        if 'user_id' not in session:
            print(f"❌ Unauthorized access attempt to {request.path}")
            print(f"   Session data: {dict(session)}")
            if request.path.startswith('/api'):
                return jsonify({'success': False, 'message': 'Unauthorized - Please login'}), 401
            return redirect(url_for('login'))
        
        print(f"✅ Authorized user {session.get('username')} accessing {request.path}")
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    """Decorator to check if user has the required role."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role')
            if user_role == 'admin':
                return f(*args, **kwargs)
            if user_role != required_role:
                return jsonify({'success': False, 'message': 'Permission denied'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- BASE ROUTES ---
@app.route('/')
def index():
    """Root route, redirects based on login status."""
    if 'user_id' in session:
        return redirect(url_for('dashboard_react'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.json
            username = data.get('username')
            
            print(f"🔐 Login attempt for user: {username}")
            
            cur = mysql.connection.cursor()
            cur.execute("SELECT user_id, username, role FROM Users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()

            if user:
                # Set session data
                session.clear()  # Clear any existing session
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                session['role'] = user['role']
                session.permanent = True  # Make session permanent (24 hours)
                
                print(f"✅ Login successful for {username}")
                print(f"   Session ID: {session.get('user_id')}")
                print(f"   Role: {session.get('role')}")
                
                return jsonify({
                    'success': True, 
                    'role': user['role'], 
                    'redirect': url_for('dashboard_react'),
                    'user': {
                        'username': user['username'],
                        'role': user['role']
                    }
                })
            
            print(f"❌ Login failed: User not found")
            return jsonify({'success': False, 'message': 'Invalid username'}), 401
            
        except Exception as e:
            print(f"❌ Login Error: {str(e)}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs out the user and clears the session."""
    username = session.get('username', 'Unknown')
    session.clear()
    print(f"👋 User logged out: {username}")
    return redirect(url_for('login'))

@app.route('/dashboard-react')
@login_required
def dashboard_react():
    """Renders the main application dashboard."""
    print(f"📊 Dashboard accessed by {session.get('username')}")
    return render_template('dashboard-react.html', user_role=session['role'])

# --- API ENDPOINTS ---

@app.route('/api/test', methods=['GET'])
def test_api():
    """Tests database connection and API availability."""
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT DATABASE() as db_name")
        db = cur.fetchone()
        cur.close()
        
        # Check session
        session_info = {
            'logged_in': 'user_id' in session,
            'username': session.get('username'),
            'role': session.get('role')
        }
        
        return jsonify({
            'success': True, 
            'message': 'API is working!', 
            'database': db['db_name'],
            'session': session_info
        })
    except Exception as e:
        print(f"❌ Test API Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    """Check if user is authenticated."""
    if 'user_id' in session:
        return jsonify({
            'authenticated': True,
            'user': {
                'username': session.get('username'),
                'role': session.get('role')
            }
        })
    return jsonify({'authenticated': False}), 401

# --- Dashboard APIs ---

@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def dashboard_stats():
    """Fetches key statistics for the dashboard."""
    print("📊 Dashboard stats requested")
    cur = mysql.connection.cursor()
    try:
        # Total Donors
        cur.execute("SELECT COUNT(DISTINCT Donor_ID) as total_donors FROM Donors")
        total_donors = cur.fetchone()['total_donors'] or 0
        
        # Total Units
        cur.execute("SELECT SUM(units_available) as total_units FROM Blood_Stock WHERE component_type = 'Whole Blood'")
        total_units_result = cur.fetchone()
        total_units = int(total_units_result['total_units']) if total_units_result['total_units'] else 0
        
        # Pending Requests
        cur.execute("SELECT COUNT(*) as pending_requests FROM Hospital_Requests WHERE Status = 'Pending'")
        pending_requests = cur.fetchone()['pending_requests'] or 0
        
        # Donations This Month
        cur.execute("""
            SELECT COUNT(*) as donations_month 
            FROM Donations 
            WHERE MONTH(Donation_Date) = MONTH(CURDATE()) 
            AND YEAR(Donation_Date) = YEAR(CURDATE())
        """)
        donations_month = cur.fetchone()['donations_month'] or 0
        
        # Critical Stock
        cur.execute("SELECT COUNT(*) as critical_stock FROM Blood_Stock WHERE units_available < 20 AND component_type = 'Whole Blood'")
        critical_stock = cur.fetchone()['critical_stock'] or 0
        
        result = {
            'success': True,
            'stats': {
                'totalDonors': total_donors,
                'unitsInStock': total_units,
                'pendingRequests': pending_requests,
                'donationsThisMonth': donations_month,
                'criticalStock': critical_stock
            }
        }
        print(f"✅ Stats fetched: {result['stats']}")
        return jsonify(result)
    except Exception as e:
        print(f"❌ Error in dashboard_stats: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to fetch dashboard stats'}), 500
    finally:
        cur.close()

@app.route('/api/dashboard/critical-stock', methods=['GET'])
@login_required
def critical_stock():
    """Fetches list of blood groups with critical stock levels."""
    print("🚨 Critical stock requested")
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT 
                blood_group as blood,
                CAST(units_available AS SIGNED) as units,
                2 as expiring
            FROM Blood_Stock 
            WHERE units_available < 20 AND component_type = 'Whole Blood'
            ORDER BY units_available ASC
        """)
        items = cur.fetchall()
        print(f"✅ Found {len(items)} critical stock items")
        return jsonify(items)
    except Exception as e:
        print(f"❌ Error in critical_stock: {str(e)}")
        traceback.print_exc()
        return jsonify([])
    finally:
        cur.close()

@app.route('/api/dashboard/recent-donations', methods=['GET'])
@login_required
def recent_donations():
    """Fetches a list of the 5 most recent donations."""
    print("📝 Recent donations requested")
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT 
                d.Name as name,
                d.Blood_Group as blood,
                DATE_FORMAT(don.Donation_Date, '%%Y-%%m-%%d') as lastDonation
            FROM Donations don
            JOIN Donors d ON don.Donor_ID = d.Donor_ID
            ORDER BY don.Donation_Date DESC
            LIMIT 5
        """)
        donations = cur.fetchall()
        print(f"✅ Found {len(donations)} recent donations")
        return jsonify(donations)
    except Exception as e:
        print(f"❌ Error in recent_donations: {str(e)}")
        traceback.print_exc()
        return jsonify([])
    finally:
        cur.close()

@app.route('/api/dashboard/expiring-stock', methods=['GET'])
@login_required
def expiring_stock():
    """Fetches a list of stock that is near expiry."""
    print("⏰ Expiring stock requested")
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT 
                blood_group as blood,
                CAST(units_available / 10 AS SIGNED) as expiring
            FROM Blood_Stock 
            WHERE units_available > 0 AND component_type = 'Whole Blood'
            LIMIT 5
        """)
        items = cur.fetchall()
        print(f"✅ Found {len(items)} expiring stock items")
        return jsonify(items)
    except Exception as e:
        print(f"❌ Error in expiring_stock: {str(e)}")
        traceback.print_exc()
        return jsonify([])
    finally:
        cur.close()

# --- Donor Management APIs ---

@app.route('/api/donors/all', methods=['GET'])
@login_required
def get_all_donors():
    """Fetches a filtered and paginated list of donors."""
    search = request.args.get('search', '')
    blood_type = request.args.get('blood_type', 'all')
    print(f"👥 Donors requested - search: '{search}', blood_type: {blood_type}")
    
    cur = mysql.connection.cursor()
    try:
        query = """
            SELECT 
                Donor_ID as id,
                Name as name,
                Blood_Group as blood,
                Contact_Number as phone,
                COALESCE(Email, '') as email,
                COALESCE(City, '') as location,
                COALESCE(DATE_FORMAT(Last_Donation_Date, '%%Y-%%m-%%d'), 'Never') as lastDonation,
                COALESCE((SELECT total_donations FROM Donor_Rewards WHERE donor_id = Donors.Donor_ID), 0) as totalDonations,
                'active' as status
            FROM Donors
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND (Name LIKE %s OR Email LIKE %s OR Contact_Number LIKE %s)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])
        
        if blood_type != 'all' and blood_type:
            query += " AND Blood_Group = %s"
            params.append(blood_type)
        
        query += " ORDER BY Donor_ID DESC LIMIT 100"
        
        cur.execute(query, params)
        donors = cur.fetchall()
        print(f"✅ Found {len(donors)} donors")
        return jsonify(donors)
    except Exception as e:
        print(f"❌ Error in get_all_donors: {str(e)}")
        traceback.print_exc()
        return jsonify([])
    finally:
        cur.close()

@app.route('/api/donors/add', methods=['POST'])
@login_required
def add_donor():
    """Adds a new donor."""
    user_role = session.get('role')
    if user_role not in ['admin', 'staff']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    data = request.json
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            INSERT INTO Donors (Name, Blood_Group, Contact_Number, Email, City, Date_Of_Birth, Gender, Last_Donation_Date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
        """, (
            data['name'],
            data['blood'],
            data['phone'],
            data.get('email', ''),
            data.get('location', ''),
            data.get('dob', '1990-01-01'),
            data.get('gender', 'Other')
        ))
        mysql.connection.commit()
        donor_id = cur.lastrowid
        print(f"✅ Donor added with ID: {donor_id}")
        return jsonify({'success': True, 'message': 'Donor added successfully', 'donor_id': donor_id})
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error adding donor: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cur.close()

@app.route('/api/donors/update/<int:donor_id>', methods=['PUT'])
@login_required
def update_donor(donor_id):
    """Updates an existing donor's information."""
    user_role = session.get('role')
    if user_role not in ['admin', 'staff']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    data = request.json
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            UPDATE Donors 
            SET Name = %s, Blood_Group = %s, Contact_Number = %s, 
                Email = %s, City = %s
            WHERE Donor_ID = %s
        """, (
            data['name'],
            data['blood'],
            data['phone'],
            data.get('email', ''),
            data.get('location', ''),
            donor_id
        ))
        mysql.connection.commit()
        print(f"✅ Donor updated with ID: {donor_id}")
        return jsonify({'success': True, 'message': 'Donor updated successfully'})
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error updating donor: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cur.close()

@app.route('/api/donors/delete/<int:donor_id>', methods=['DELETE'])
@login_required
def delete_donor(donor_id):
    """Deletes a donor from the database."""
    user_role = session.get('role')
    if user_role not in ['admin', 'staff']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM Donors WHERE Donor_ID = %s", (donor_id,))
        mysql.connection.commit()
        print(f"✅ Donor deleted with ID: {donor_id}")
        return jsonify({'success': True, 'message': 'Donor deleted successfully'})
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error deleting donor: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cur.close()

# --- Request Management APIs ---

@app.route('/api/requests/all', methods=['GET'])
@login_required
def get_all_requests():
    """Fetches a list of all hospital requests."""
    search = request.args.get('search', '')
    print(f"📋 Requests requested - search: '{search}'")
    
    cur = mysql.connection.cursor()
    try:
        query = """
            SELECT 
                Request_ID as id,
                Hospital_Name as patient,
                Blood_Group as blood,
                CAST(Units_Requested AS SIGNED) as units,
                Hospital_Name as hospital,
                'urgent' as priority,
                DATE_FORMAT(Request_Date, '%%Y-%%m-%%d') as date,
                LOWER(Status) as status,
                City as contact
            FROM Hospital_Requests
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND (Hospital_Name LIKE %s OR City LIKE %s)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param])
        
        query += " ORDER BY Request_Date DESC LIMIT 100"
        
        cur.execute(query, params)
        requests_data = cur.fetchall()
        print(f"✅ Found {len(requests_data)} requests")
        return jsonify(requests_data)
    except Exception as e:
        print(f"❌ Error in get_all_requests: {str(e)}")
        traceback.print_exc()
        return jsonify([])
    finally:
        cur.close()

@app.route('/api/requests/add', methods=['POST'])
@login_required
def add_request():
    """Adds a new blood request from a hospital."""
    data = request.json
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            INSERT INTO Hospital_Requests 
            (Hospital_Name, City, Blood_Group, Component_Type, Units_Requested, Notes, Request_Date, Status)
            VALUES (%s, %s, %s, 'Whole Blood', %s, %s, CURDATE(), 'Pending')
        """, (
            data['patient'],
            data.get('hospital', 'N/A'),
            data['blood'],
            data['units'],
            data.get('notes', '')
        ))
        mysql.connection.commit()
        request_id = cur.lastrowid
        print(f"✅ Request added with ID: {request_id}")
        return jsonify({'success': True, 'message': 'Request added successfully', 'request_id': request_id})
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error adding request: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cur.close()

@app.route('/api/requests/approve/<int:request_id>', methods=['POST'])
@login_required
def approve_request(request_id):
    """Approves a request."""
    user_role = session.get('role')
    if user_role not in ['admin', 'staff']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT Units_Requested, Blood_Group, Status FROM Hospital_Requests WHERE Request_ID = %s", (request_id,))
        req = cur.fetchone()
        
        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404
        
        if req['Status'] != 'Pending':
            return jsonify({'success': False, 'message': f"Request is already {req['Status']}"}), 400
            
        units_requested = req['Units_Requested']
        blood_group = req['Blood_Group']
        
        cur.execute("SELECT units_available FROM Blood_Stock WHERE blood_group = %s AND component_type = 'Whole Blood'", (blood_group,))
        stock = cur.fetchone()
        
        if not stock or stock['units_available'] < units_requested:
            return jsonify({'success': False, 'message': f"Insufficient stock of {blood_group}. Available: {stock['units_available'] if stock else 0} units."}), 400

        cur.execute("""
            UPDATE Blood_Stock 
            SET units_available = units_available - %s, last_updated = NOW()
            WHERE blood_group = %s AND component_type = 'Whole Blood'
        """, (units_requested, blood_group))
        
        cur.execute("UPDATE Hospital_Requests SET Status = 'Fulfilled' WHERE Request_ID = %s", (request_id,))
        
        cur.execute("""
            INSERT INTO Requests_Fulfilled 
            (Request_ID, Units_Supplied, Fulfilled_Date, Fulfilled_By_User_ID)
            VALUES (%s, %s, CURDATE(), %s)
        """, (request_id, units_requested, session['user_id']))
        
        mysql.connection.commit()
        print(f"✅ Request {request_id} approved")
        return jsonify({'success': True, 'message': 'Request approved successfully'})
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error approving request: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cur.close()

@app.route('/api/requests/reject/<int:request_id>', methods=['POST'])
@login_required
def reject_request(request_id):
    """Rejects a pending hospital request."""
    user_role = session.get('role')
    if user_role not in ['admin', 'staff']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    cur = mysql.connection.cursor()
    try:
        cur.execute("UPDATE Hospital_Requests SET Status = 'Cancelled' WHERE Request_ID = %s AND Status = 'Pending'", (request_id,))
        rows_affected = cur.rowcount
        if rows_affected == 0:
            return jsonify({'success': False, 'message': 'Request not found or already processed'}), 404
            
        mysql.connection.commit()
        print(f"✅ Request {request_id} rejected")
        return jsonify({'success': True, 'message': 'Request rejected successfully'})
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error rejecting request: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cur.close()

# --- Inventory API ---

@app.route('/api/inventory/all', methods=['GET'])
@login_required
def get_inventory():
    """Fetches the current blood stock inventory."""
    print("📦 Inventory requested")
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT 
                blood_group as blood,
                CAST(units_available AS SIGNED) as units,
                CAST(units_available / 10 AS SIGNED) as expiring,
                DATE_FORMAT(last_updated, '%%Y-%%m-%%d %%H:%%i') as lastUpdated
            FROM Blood_Stock
            WHERE component_type = 'Whole Blood'
            ORDER BY blood_group
        """)
        inventory = cur.fetchall()
        print(f"✅ Found {len(inventory)} inventory items")
        return jsonify(inventory)
    except Exception as e:
        print(f"❌ Error in get_inventory: {str(e)}")
        traceback.print_exc()
        return jsonify([])
    finally:
        cur.close()

@app.route('/api/inventory/add-stock', methods=['POST'])
@login_required
def add_blood_stock():
    """Add blood stock."""
    user_role = session.get('role')
    if user_role not in ['admin', 'staff']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    data = request.json
    cur = mysql.connection.cursor()
    try:
        blood_type = data.get('blood_type')
        units = float(data.get('units', 0))
        
        if not blood_type or units <= 0:
            return jsonify({'success': False, 'message': 'Invalid blood type or units'}), 400
        
        print(f"📦 Adding {units} units of {blood_type}")
        
        cur.execute("""
            UPDATE Blood_Stock 
            SET units_available = units_available + %s,
                last_updated = NOW()
            WHERE blood_group = %s AND component_type = 'Whole Blood'
        """, (units, blood_type))
        
        mysql.connection.commit()
        
        cur.execute("""
            SELECT units_available 
            FROM Blood_Stock 
            WHERE blood_group = %s AND component_type = 'Whole Blood'
        """, (blood_type,))
        
        result = cur.fetchone()
        new_total = result['units_available'] if result else units
        
        print(f"✅ Stock updated. New total: {new_total}")
        
        return jsonify({
            'success': True, 
            'message': f'Successfully added {units} units of {blood_type}. New total: {new_total}'
        })
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error adding stock: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cur.close()


if __name__ == '__main__':
    print("🚀 Starting Flask application...")
    print("🚨 IMPORTANT: Ensure MySQL is running and BloodDonationDB is set up.")
    print("📍 Dashboard URL: http://localhost:5000/dashboard-react")
    print("🔧 Test API URL: http://localhost:5000/api/test")
    print("🔐 Login with username: 'admin' or 'staff' (any password)")
    app.run(debug=True, port=5000, host='0.0.0.0')