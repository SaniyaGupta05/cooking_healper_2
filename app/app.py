from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import hashlib
import re
from datetime import datetime, timedelta
from groq import Groq
import json
import os
import random

app = Flask(__name__)
app.secret_key = 'ai-meal-planner-secret-key-2024'  # Change this in production
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
CORS(app, supports_credentials=True)

# ---------------- CONFIGURATION ---------------- #
GROQ_API_KEY = "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"

# ---------------- FIREBASE INIT ---------------- #
db = None  # Initialize db variable globally

# Temporary in-memory user storage for testing
temp_users = {}

try:
    if not firebase_admin._apps:
        # Use absolute path to ensure file is found
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        FIREBASE_CONFIG_PATH = os.path.join(BASE_DIR, "mock_firebase.json")
        
        print(f"📁 Looking for Firebase config at: {FIREBASE_CONFIG_PATH}")
        print(f"📁 File exists: {os.path.exists(FIREBASE_CONFIG_PATH)}")
        
        if os.path.exists(FIREBASE_CONFIG_PATH):
            # Validate the JSON file first
            with open(FIREBASE_CONFIG_PATH, 'r') as f:
                config_content = f.read().strip()
                if not config_content or config_content == "{}":
                    print("❌ Firebase config file is empty")
                    raise ValueError("Empty Firebase config file")
                
                try:
                    config_data = json.loads(config_content)
                    # Check if it has required fields
                    if 'type' not in config_data or config_data.get('type') != 'service_account':
                        print("❌ Invalid Firebase config: not a service account")
                        raise ValueError("Invalid service account file")
                except json.JSONDecodeError:
                    print("❌ Invalid JSON in Firebase config file")
                    raise ValueError("Invalid JSON in config file")
            
            cred = credentials.Certificate(FIREBASE_CONFIG_PATH)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase initialized successfully")
            
            # Test the connection
            test_ref = db.collection("test_connection").document("test")
            test_ref.set({"timestamp": datetime.now().isoformat()})
            print("✅ Firebase connection test passed")
            
        else:
            print("❌ Firebase config file not found - using temporary storage")
            
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")
    print("⚠️ Running with temporary user storage")
    db = None

# ---------------- DIETARY PROFILES & CONFIG ---------------- #
DIETARY_RESTRICTIONS = {
    "gluten_free": {"name": "Gluten Free", "description": "Excludes wheat, barley, rye"},
    "dairy_free": {"name": "Dairy Free", "description": "Excludes milk, cheese, yogurt"},
    "vegetarian": {"name": "Vegetarian", "description": "No meat, fish, or poultry"},
    "vegan": {"name": "Vegan", "description": "No animal products"},
    "low_carb": {"name": "Low Carb", "description": "Limited carbohydrates"},
    "nut_free": {"name": "Nut Free", "description": "No nuts or peanuts"},
    "egg_free": {"name": "Egg Free", "description": "No eggs or egg products"},
    "seafood_free": {"name": "Seafood Free", "description": "No fish or seafood"}
}

CUISINE_TYPES = ["Indian", "Italian", "Chinese", "Mexican", "Thai", "Mediterranean", "American", "French", "Japanese"]

# ---------------- UTILITY FUNCTIONS ---------------- #
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def validate_password(password: str) -> bool:
    return len(password) >= 6

def validate_username(username: str) -> bool:
    return len(username) >= 3 and bool(re.match(r'^[a-zA-Z0-9_.-]+$', username))

def clean_name_for_id(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\b(i have|i've|i|have|now|got|today|add|added|can you|please|some|a few)\b", " ", s)
    s = re.sub(r"\d+\.?\d*", " ", s)
    s = re.sub(r"\b(kg|kgs|g|grams?|gm|gms|l|ltr|litre|litres|ml|milliliters?|cup|cups|tbsp|tbs|tablespoons?|tsp|teaspoons?|pieces?|pcs|pc|unit|units|bunch|pinch)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "_")

def parse_ingredient_input(user_input: str):
    try:
        # Extract quantity
        quantity_match = re.search(r"(\d+\.?\d*)", user_input)
        quantity = float(quantity_match.group(1)) if quantity_match else 1.0
        
        # Extract unit
        unit_pattern = r"\b(kg|kgs|g|grams?|gm|gms|kg\.|l|ltr|litre|litres|liter|liters|ml|milliliters?|cup|cups|tbsp|tbs|tablespoons?|tsp|teaspoons?|pieces?|pcs|pc|unit|units|bunch|pinch)\b"
        unit_match = re.search(unit_pattern, user_input.lower())
        unit = unit_match.group(0) if unit_match else "units"
        
        # Clean unit
        unit = unit.lower().rstrip('s').rstrip('.')
        if unit in ['kg', 'kgs', 'kg.']:
            unit = 'kg'
        elif unit in ['g', 'gram', 'gm']:
            unit = 'g'
        elif unit in ['l', 'ltr', 'litre', 'liter']:
            unit = 'l'
        elif unit in ['ml', 'milliliter']:
            unit = 'ml'
        elif unit in ['tbsp', 'tbs', 'tablespoon']:
            unit = 'tbsp'
        elif unit in ['tsp', 'teaspoon']:
            unit = 'tsp'
        elif unit in ['piece', 'pieces', 'pcs', 'pc']:
            unit = 'pieces'
        
        # Extract name
        name = re.sub(r"\d+\.?\d*", "", user_input)
        name = re.sub(unit_pattern, "", name, flags=re.IGNORECASE)
        name = re.sub(r"\b(of)\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"[^a-zA-Z0-9 ]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        
        return name, quantity, unit
    except Exception as e:
        print(f"Error parsing ingredient: {e}")
        return user_input, 1.0, "units"

# ---------------- DEBUG ROUTES ---------------- #
@app.route('/debug/firebase-test')
def debug_firebase_test():
    """Test Firebase connection and database operations"""
    try:
        if db is None:
            return jsonify({'success': False, 'message': 'Firebase not initialized'})
        
        # Test if we can access Firestore
        test_ref = db.collection("test_connection").document("connection_test")
        test_ref.set({
            "timestamp": datetime.now().isoformat(),
            "message": "Firebase connection test successful"
        })
        
        # Read it back
        test_doc = test_ref.get()
        if test_doc.exists:
            return jsonify({
                'success': True,
                'message': 'Firebase read/write working',
                'data': test_doc.to_dict()
            })
        else:
            return jsonify({'success': False, 'message': 'Firebase write failed'})
            
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug/create-simple-user')
def debug_create_simple_user():
    """Create a simple test user"""
    try:
        username = "saniya"
        password = "test123"
        
        # Try Firebase first
        if db is not None:
            user_ref = db.collection("users").document(username)
            user_data = {
                "password": hash_password(password),
                "diet_type": "Pure Veg",
                "dietary_restrictions": [],
                "preferred_cuisines": ["Indian"],
                "cooking_skill": "beginner",
                "created_at": datetime.now().isoformat(),
                "last_login": datetime.now().isoformat()
            }
            user_ref.set(user_data)
            message = "User created in Firebase"
        else:
            # Fallback to temporary storage
            temp_users[username] = {
                "password": hash_password(password),
                "diet_type": "Pure Veg",
                "dietary_restrictions": [],
                "preferred_cuisines": ["Indian"],
                "cooking_skill": "beginner"
            }
            message = "User created in temporary storage"
        
        return f"""
        <h1>User Created Successfully! ✅</h1>
        <p>Username: <strong>{username}</strong></p>
        <p>Password: <strong>{password}</strong></p>
        <p>Storage: <strong>{message}</strong></p>
        <p><a href="/login">Go to Login</a></p>
        <p><a href="/debug/list-users">Check Users</a></p>
        """
            
    except Exception as e:
        return f"❌ Error creating user: {str(e)}"

@app.route('/debug/list-users')
def debug_list_users():
    """List all users in the database"""
    try:
        users_list = []
        
        # Get users from Firebase
        if db is not None:
            users_ref = db.collection("users")
            for doc in users_ref.stream():
                user_data = doc.to_dict()
                users_list.append({
                    'username': doc.id,
                    'storage': 'firebase',
                    'has_password': 'password' in user_data,
                    'diet_type': user_data.get('diet_type', 'Not set')
                })
        
        # Get users from temporary storage
        for username, user_data in temp_users.items():
            users_list.append({
                'username': username,
                'storage': 'temporary',
                'has_password': 'password' in user_data,
                'diet_type': user_data.get('diet_type', 'Not set')
            })
        
        return jsonify({
            'total_users': len(users_list),
            'firebase_available': db is not None,
            'users': users_list
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug/firebase-status')
def debug_firebase_status():
    """Check Firebase connection status"""
    firebase_status = {
        'db_initialized': db is not None,
        'firebase_config_path': os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_firebase.json"),
        'file_exists': os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_firebase.json")),
        'current_directory': os.getcwd(),
        'temporary_users_count': len(temp_users)
    }
    return jsonify(firebase_status)

@app.route('/debug/clean-db')
def debug_clean_db():
    """Clean the database for testing"""
    try:
        if db is not None:
            # Delete all test users
            users_ref = db.collection("users")
            for doc in users_ref.stream():
                doc.reference.delete()
        
        # Clear temporary users
        temp_users.clear()
        
        return "Database cleaned successfully"
    except Exception as e:
        return f"Error cleaning database: {e}"

# ---------------- AUTHENTICATION ROUTES ---------------- #
@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        
        print(f"🔐 Login attempt for username: {username}")
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'})
        
        try:
            # Try Firebase first
            user_found = False
            user_data = None
            
            if db is not None:
                user_ref = db.collection("users").document(username)
                user = user_ref.get()
                
                if user.exists:
                    user_data = user.to_dict()
                    user_found = True
                    storage_type = "Firebase"
            
            # If not found in Firebase, try temporary storage
            if not user_found and username in temp_users:
                user_data = temp_users[username]
                user_found = True
                storage_type = "Temporary"
            
            # Check password
            if user_found and user_data.get("password") == hash_password(password):
                # Update last login (only for Firebase)
                if db is not None and storage_type == "Firebase":
                    user_ref.update({"last_login": datetime.now().isoformat()})
                
                # Create session with user data
                session.permanent = True
                session['user'] = {
                    'username': username,
                    'diet_type': user_data.get('diet_type'),
                    'dietary_restrictions': user_data.get('dietary_restrictions', []),
                    'preferred_cuisines': user_data.get('preferred_cuisines', []),
                    'cooking_skill': user_data.get('cooking_skill')
                }
                
                print(f"✅ Login successful for user: {username} ({storage_type})")
                return jsonify({'success': True, 'message': 'Login successful'})
            
            print(f"❌ Login failed for user: {username}")
            return jsonify({'success': False, 'message': 'Invalid username or password'})
            
        except Exception as e:
            print(f"Login error: {e}")
            return jsonify({'success': False, 'message': f'Login failed: {str(e)}'})
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        diet_type = data.get('diet_type', 'Pure Veg')
        dietary_restrictions = data.get('dietary_restrictions', [])
        preferred_cuisines = data.get('preferred_cuisines', [])
        cooking_skill = data.get('cooking_skill', 'beginner')
        
        print(f"📝 Registration attempt for username: '{username}'")
        
        try:
            if not username or not password:
                return jsonify({'success': False, 'message': 'Username and password are required'})
            
            if not validate_username(username):
                return jsonify({'success': False, 'message': 'Username must be at least 3 characters and contain only letters, numbers, dots, hyphens, or underscores'})
            
            if not validate_password(password):
                return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'})
            
            # Check if user exists in Firebase
            user_exists = False
            if db is not None:
                user_ref = db.collection("users").document(username)
                if user_ref.get().exists:
                    user_exists = True
            
            # Check if user exists in temporary storage
            if not user_exists and username in temp_users:
                user_exists = True
            
            if user_exists:
                return jsonify({'success': False, 'message': 'Username already exists'})
            
            # Create user data
            hashed_password = hash_password(password)
            user_data = {
                "password": hashed_password,
                "diet_type": diet_type,
                "dietary_restrictions": dietary_restrictions,
                "preferred_cuisines": preferred_cuisines,
                "cooking_skill": cooking_skill,
                "created_at": datetime.now().isoformat(),
                "last_login": datetime.now().isoformat()
            }
            
            # Save to appropriate storage
            if db is not None:
                user_ref.set(user_data)
                storage_type = "Firebase"
            else:
                temp_users[username] = user_data
                storage_type = "Temporary"
            
            print(f"✅ User '{username}' registered successfully in {storage_type}")
            
            # Auto-login after registration
            session.permanent = True
            session['user'] = {
                'username': username,
                'diet_type': diet_type,
                'dietary_restrictions': dietary_restrictions,
                'preferred_cuisines': preferred_cuisines,
                'cooking_skill': cooking_skill
            }
            
            return jsonify({'success': True, 'message': 'Registration successful'})
            
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return jsonify({'success': False, 'message': f'Registration failed: {str(e)}'})
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    if 'user' in session:
        print(f"👋 User {session['user']['username']} logged out")
    session.pop('user', None)
    return redirect(url_for('index'))

# ---------------- MAIN APPLICATION ROUTES ---------------- #
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        print("❌ No user in session, redirecting to login")
        return redirect(url_for('login'))
    print(f"✅ User {session['user']['username']} accessing dashboard")
    return render_template('dashboard.html')

@app.route('/pantry')
def pantry():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('pantry.html')

@app.route('/suggestions')
def suggestions():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('suggestions.html')

@app.route('/mealplan')
def mealplan():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('mealplan.html')

@app.route('/cooking')
def cooking():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('cooking.html')

# ---------------- API ENDPOINTS ---------------- #
@app.route('/api/user')
def get_user():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_data = session['user'].copy()
    return jsonify(user_data)

@app.route('/api/dashboard/stats')
def get_dashboard_stats():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        username = session['user']['username']
        pantry_count = 0
        
        # Get pantry count from Firebase if available
        if db is not None:
            ingredients_ref = db.collection("users").document(username).collection("ingredients")
            pantry_count = len(list(ingredients_ref.stream()))
        
        stats = {
            'pantry_count': pantry_count,
            'expiring_count': 0,
            'recipes_tried': random.randint(5, 20),
            'days_streak': random.randint(1, 30)
        }
        
        return jsonify(stats)
        
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return jsonify({'error': str(e)}), 500

# Simplified pantry management that works without Firebase
@app.route('/api/pantry/ingredients', methods=['GET'])
def get_ingredients():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Return empty list for now - you can extend this later
    return jsonify([])

@app.route('/api/suggestions', methods=['POST'])
def get_suggestions():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    meal_type = data.get('meal_type')
    cuisine = data.get('cuisine')
    recipe_query = data.get('recipe_query')
    
    try:
        user_data = session['user']
        
        # Prepare AI prompt
        if recipe_query:
            prompt = f"""
            USER REQUEST: Provide a detailed recipe for {recipe_query}
            
            USER PREFERENCES:
            - Diet: {user_data.get('diet_type', 'No restrictions')}
            - Dietary Restrictions: {', '.join(user_data.get('dietary_restrictions', []))}
            - Cooking Skill: {user_data.get('cooking_skill', 'beginner')}
            
            Please provide a complete recipe including:
            1. Ingredient list with quantities
            2. Step-by-step cooking instructions
            3. Cooking time
            4. Difficulty level
            5. Serving size
            6. Any helpful tips or variations
            
            Make it suitable for the user's cooking skill level and dietary preferences.
            """
        else:
            prompt = f"""
            USER PREFERENCES:
            - Diet: {user_data.get('diet_type', 'No restrictions')}
            - Dietary Restrictions: {', '.join(user_data.get('dietary_restrictions', []))}
            - Preferred Cuisines: {', '.join(user_data.get('preferred_cuisines', []))}
            - Cooking Skill: {user_data.get('cooking_skill', 'beginner')}
            - Meal Type: {meal_type if meal_type else 'Any'}
            - Cuisine: {cuisine if cuisine else 'Any'}
            
            TASK: Suggest 3-5 creative, practical recipes.
            
            For each recipe, provide:
            - Recipe name
            - Ingredients needed
            - Brief cooking instructions
            - Estimated cooking time
            - Difficulty level
            
            Consider the user's dietary restrictions and cooking skill level.
            """
        
        # Call Groq AI
        client = Groq(api_key=GROQ_API_KEY)
        
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=2000
        )
        
        suggestions = response.choices[0].message.content
        
        return jsonify({'suggestions': suggestions})
        
    except Exception as e:
        print(f"Error getting suggestions: {e}")
        return jsonify({'error': f"Failed to generate suggestions: {str(e)}"}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')