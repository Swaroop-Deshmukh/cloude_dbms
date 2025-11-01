import pymysql
# Important: Install as MySQLdb for flask_mysqldb compatibility
pymysql.install_as_MySQLdb()

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mysqldb import MySQL
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash # Not used for login here, but kept for completeness
from datetime import datetime, timedelta
from functools import wraps
import traceback

# --- FLASK APP SETUP ---
app = Flask(__name__)
# Enable CORS for frontend communication
CORS(app, supports_credentials=True, origins=["http://localhost:3000", "http://127.0.0.1:3000"]) # Assuming frontend runs on 3000

# Security configuration
app.secret_key = 'your_strong_secret_key_here_for_security'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'password'  # CHANGE THIS!
app.config['MYSQL_DB'] = 'BloodDonationDB'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor' # Returns rows as dictionaries

mysql = MySQL(app)

# --- DECORATORS & AUTH ---
def login_required(f):
    """Decorator to check if user is logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # For API requests, return JSON error
            if request.path.startswith('/api'):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            # For page requests, redirect to login
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    """Decorator to check if user has the required role."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role')
            # Admins bypass role check
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
    """Root route, redirects to login."""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        # We ignore data.get('password') here to allow any password
        
        try:
            cur = mysql.connection.cursor()
            # FIX 1: Removed 'password_hash' column to prevent database error (1054)
            # FIX 2: Only check for the existence of the username
            cur.execute("SELECT user_id, username, role FROM Users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()

            if user:
                # Bypass: Any provided password will result in a successful login 
                # if the username exists.
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                session['role'] = user['role']
                print(f"✅ User logged in (Bypass Mode): {username} with role {user['role']}")
                return jsonify({'success': True, 'role': user['role'], 'redirect': url_for('dashboard_react')})
            
            # If user not found
            return jsonify({'success': False, 'message': 'Invalid username'}), 401
        except Exception as e:
            print(f"❌ Login Error: {str(e)}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': 'Database error or internal server error'}), 500
    
    return render_template('login.html')
@app.route('/logout')
def logout():
    """Logs out the user and clears the session."""
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard-react')
@login_required
def dashboard_react():
    """Renders the main application dashboard."""
    return render_template('dashboard-react.html', user_role=session['role'])

# --- API ENDPOINTS ---

# Test endpoint
@app.route('/api/test', methods=['GET'])
def test_api():
    """Tests database connection and API availability."""
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT DATABASE()")
        db = cur.fetchone()
        cur.close()
        return jsonify({'success': True, 'message': 'API is working!', 'database': db})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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
        total_donors = cur.fetchone()['total_donors']
        
        # Total Units
        # Aggregates units for 'Whole Blood' or all components, depending on schema
        cur.execute("SELECT SUM(units_available) as total_units FROM Blood_Stock WHERE component_type = 'Whole Blood'")
        total_units_result = cur.fetchone()
        total_units = int(total_units_result['total_units']) if total_units_result['total_units'] else 0
        
        # Pending Requests
        cur.execute("SELECT COUNT(*) as pending_requests FROM Hospital_Requests WHERE Status = 'Pending'")
        pending_requests = cur.fetchone()['pending_requests']
        
        # Donations This Month
        # Uses SQL's CURDATE() for current month/year
        cur.execute("""
            SELECT COUNT(*) as donations_month 
            FROM Donations 
            WHERE MONTH(Donation_Date) = MONTH(CURDATE()) 
            AND YEAR(Donation_Date) = YEAR(CURDATE())
        """)
        donations_month = cur.fetchone()['donations_month']
        
        # Critical Stock (Units < 20)
        cur.execute("SELECT COUNT(*) as critical_stock FROM Blood_Stock WHERE units_available < 20 AND component_type = 'Whole Blood'")
        critical_stock = cur.fetchone()['critical_stock']
        
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
                2 as expiring # Mock data for 'expiring' as per original code
            FROM Blood_Stock 
            WHERE units_available < 20 AND component_type = 'Whole Blood'
            ORDER BY units_available ASC
        """)
        items = cur.fetchall()
        return jsonify(items)
    except Exception as e:
        print(f"❌ Error in critical_stock: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to fetch critical stock'}), 500
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
    """Fetches a list of stock that is near expiry (mock data)."""
    print("⏰ Expiring stock requested")
    cur = mysql.connection.cursor()
    try:
        # NOTE: This endpoint uses mock data for 'expiring' units (units/10)
        # Real expiring stock requires a 'Storage_Date' or 'Expiry_Date' column in Blood_Stock or a related table.
        cur.execute("""
            SELECT 
                blood_group as blood,
                CAST(units_available / 10 AS SIGNED) as expiring # Mock value
            FROM Blood_Stock 
            WHERE units_available > 0 AND component_type = 'Whole Blood'
            LIMIT 5
        """)
        items = cur.fetchall()
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
    print(f"👥 Donors requested - search: {search}, blood_type: {blood_type}")
    
    cur = mysql.connection.cursor()
    try:
        # Corrected: Used double percent signs (%%) for DATE_FORMAT inside the query string
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
        
        if blood_type != 'all' and blood_type: # Added check for truthiness
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
        return jsonify({'success': False, 'message': 'Failed to fetch donors'}), 500
    finally:
        cur.close()

@app.route('/api/donors/add', methods=['POST'])
@login_required
@role_required('staff')
def add_donor():
    """Adds a new donor to the database."""
    data = request.json
    cur = mysql.connection.cursor()
    try:
        # Added a check to ensure Last_Donation_Date is NULL on insert
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
@role_required('staff')
def update_donor(donor_id):
    """Updates an existing donor's information."""
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
@role_required('staff')
def delete_donor(donor_id):
    """Deletes a donor from the database."""
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
    """Fetches a list of all hospital requests with filtering."""
    search = request.args.get('search', '')
    print(f"📋 Requests requested - search: {search}")
    
    cur = mysql.connection.cursor()
    try:
        # Corrected: Used double percent signs (%%) for DATE_FORMAT
        query = """
            SELECT 
                Request_ID as id,
                Hospital_Name as patient, # Hospital Name is used as 'patient' name in frontend
                Blood_Group as blood,
                CAST(Units_Requested AS SIGNED) as units,
                Hospital_Name as hospital,
                'urgent' as priority, # Priority is hardcoded to 'urgent'
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
        return jsonify(requests_data)
    except Exception as e:
        print(f"❌ Error in get_all_requests: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to fetch requests'}), 500
    finally:
        cur.close()

@app.route('/api/requests/add', methods=['POST'])
@login_required
# NOTE: Removed @role_required('staff') to allow all logged-in users to potentially add a request (e.g., a hospital user)
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
@role_required('staff')
def approve_request(request_id):
    """Approves a request, updates stock, and logs fulfillment."""
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
        
        # Check available stock
        cur.execute("SELECT units_available FROM Blood_Stock WHERE blood_group = %s AND component_type = 'Whole Blood'", (blood_group,))
        stock = cur.fetchone()
        
        if not stock or stock['units_available'] < units_requested:
            return jsonify({'success': False, 'message': f"Insufficient stock of {blood_group}. Available: {stock['units_available'] if stock else 0} units."}), 400

        # 1. Update Blood Stock
        cur.execute("""
            UPDATE Blood_Stock 
            SET units_available = units_available - %s, last_updated = NOW()
            WHERE blood_group = %s AND component_type = 'Whole Blood'
        """, (units_requested, blood_group))
        
        # 2. Update Request Status
        cur.execute("UPDATE Hospital_Requests SET Status = 'Fulfilled' WHERE Request_ID = %s", (request_id,))
        
        # 3. Insert Fulfillment Record
        cur.execute("""
            INSERT INTO Requests_Fulfilled 
            (Request_ID, Units_Supplied, Fulfilled_Date, Fulfilled_By_User_ID)
            VALUES (%s, %s, CURDATE(), %s)
        """, (request_id, units_requested, session['user_id']))
        
        mysql.connection.commit()
        print(f"✅ Request {request_id} approved and fulfilled.")
        return jsonify({'success': True, 'message': 'Request approved and stock updated successfully'})
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Error approving request: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cur.close()

@app.route('/api/requests/reject/<int:request_id>', methods=['POST'])
@login_required
@role_required('staff')
def reject_request(request_id):
    """Rejects a pending hospital request."""
    cur = mysql.connection.cursor()
    try:
        cur.execute("UPDATE Hospital_Requests SET Status = 'Cancelled' WHERE Request_ID = %s AND Status = 'Pending'", (request_id,))
        rows_affected = cur.rowcount
        if rows_affected == 0:
            return jsonify({'success': False, 'message': 'Request not found or already processed'}), 404
            
        mysql.connection.commit()
        print(f"✅ Request {request_id} rejected.")
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
        # Corrected: Used double percent signs (%%) for DATE_FORMAT
        cur.execute("""
            SELECT 
                blood_group as blood,
                CAST(units_available AS SIGNED) as units,
                CAST(units_available / 10 AS SIGNED) as expiring, # Mock value
                DATE_FORMAT(last_updated, '%%Y-%%m-%%d %%H:%%i') as lastUpdated
            FROM Blood_Stock
            WHERE component_type = 'Whole Blood'
            ORDER BY blood_group
        """)
        inventory = cur.fetchall()
        return jsonify(inventory)
    except Exception as e:
        print(f"❌ Error in get_inventory: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to fetch inventory'}), 500
    finally:
        cur.close()


if __name__ == '__main__':
    print("🚀 Starting Flask application...")
    print("🚨 IMPORTANT: Ensure your MySQL is running and the 'BloodDonationDB' schema is set up.")
    print("   The 'Users' table must contain a user (e.g., 'admin', 'staff') for login.")
    print("📍 Dashboard URL: http://localhost:5000/dashboard-react")
    print("🔧 Test API URL: http://localhost:5000/api/test")
    app.run(debug=True, port=5000)