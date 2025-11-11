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
FIREBASE_CONFIG_PATH = r"app\mock_firebase.json"
GROQ_API_KEY = "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"

# ---------------- FIREBASE INIT ---------------- #
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CONFIG_PATH)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase initialized successfully")
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")

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
@app.route('/debug/check-user/<username>')
def debug_check_user(username):
    """Check if a specific user exists and verify password hash"""
    try:
        user_ref = db.collection("users").document(username)
        user = user_ref.get()
        
        if user.exists:
            user_data = user.to_dict()
            return jsonify({
                'exists': True,
                'username': username,
                'has_password': 'password' in user_data,
                'password_length': len(user_data.get('password', '')),
                'diet_type': user_data.get('diet_type'),
                'stored_password_hash': user_data.get('password')[:20] + '...' if user_data.get('password') else None
            })
        else:
            return jsonify({'exists': False, 'username': username})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug/test-hash/<password>')
def debug_test_hash(password):
    """Test password hashing"""
    hashed = hash_password(password)
    return jsonify({
        'original': password,
        'hashed': hashed,
        'hashed_first_20': hashed[:20] + '...'
    })

@app.route('/debug/create-test-user')
def create_test_user():
    """Temporary route to create a test user"""
    try:
        test_username = "testuser"
        test_password = "test123"
        
        user_ref = db.collection("users").document(test_username)
        if user_ref.get().exists:
            return jsonify({'success': False, 'message': 'Test user already exists'})
        
        user_data = {
            "password": hash_password(test_password),
            "diet_type": "Pure Veg",
            "dietary_restrictions": [],
            "preferred_cuisines": ["Indian"],
            "cooking_skill": "beginner",
            "created_at": datetime.now().isoformat(),
            "last_login": datetime.now().isoformat()
        }
        
        user_ref.set(user_data)
        return jsonify({
            'success': True, 
            'message': 'Test user created',
            'username': test_username,
            'password': test_password
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})
@app.route('/debug/users')
def debug_users():
    """Temporary route to check existing users"""
    try:
        users_ref = db.collection("users")
        users = []
        for doc in users_ref.stream():
            user_data = doc.to_dict()
            users.append({
                'username': doc.id,
                'diet_type': user_data.get('diet_type'),
                'has_password': 'password' in user_data,
                'created_at': user_data.get('created_at')
            })
        return jsonify({
            'total_users': len(users),
            'users': users
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug/session')
def debug_session():
    return jsonify({
        'session_exists': 'user' in session,
        'session_data': dict(session) if 'user' in session else 'No session data',
        'headers': {k: v for k, v in request.headers if k.lower() == 'cookie'}
    })

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
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        print(f"🔐 Login attempt for username: {username}")  # Debug
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'})
        
        try:
            user_ref = db.collection("users").document(username)
            user = user_ref.get()
            
            if user.exists:
                user_data = user.to_dict()
                if user_data.get("password") == hash_password(password):
                    # Update last login
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
                    
                    print(f"✅ Login successful for user: {username}")  # Debug
                    return jsonify({'success': True, 'message': 'Login successful'})
            
            print(f"❌ Login failed for user: {username}")  # Debug
            return jsonify({'success': False, 'message': 'Invalid username or password'})
            
        except Exception as e:
            print(f"Login error: {e}")
            return jsonify({'success': False, 'message': 'Login failed. Please try again.'})
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        diet_type = data.get('diet_type', 'Pure Veg')
        dietary_restrictions = data.get('dietary_restrictions', [])
        preferred_cuisines = data.get('preferred_cuisines', [])
        cooking_skill = data.get('cooking_skill', 'beginner')
        
        print(f"📝 Registration attempt for username: '{username}'")  # Debug
        print(f"📝 Password: '{password}' (length: {len(password)})")  # Debug
        print(f"📝 Diet type: {diet_type}")  # Debug
        print(f"📝 Full data received: {data}")  # Debug
        
        try:
            if not username or not password:
                print("❌ Missing username or password")  # Debug
                return jsonify({'success': False, 'message': 'Username and password are required'})
            
            if not validate_username(username):
                print(f"❌ Invalid username: {username}")  # Debug
                return jsonify({'success': False, 'message': 'Username must be at least 3 characters and contain only letters, numbers, dots, hyphens, or underscores'})
            
            if not validate_password(password):
                print(f"❌ Invalid password length: {len(password)}")  # Debug
                return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'})
            
            user_ref = db.collection("users").document(username)
            existing_user = user_ref.get()
            
            if existing_user.exists:
                print(f"❌ Username '{username}' already exists")  # Debug
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
            
            print(f"📝 Creating user with data: {user_data}")  # Debug
            print(f"📝 Password hash: {hashed_password[:20]}...")  # Debug
            
            # Save to Firebase
            user_ref.set(user_data)
            print(f"✅ User '{username}' registered successfully")  # Debug
            
            # Auto-login after registration
            session.permanent = True
            session['user'] = {
                'username': username,
                'diet_type': diet_type,
                'dietary_restrictions': dietary_restrictions,
                'preferred_cuisines': preferred_cuisines,
                'cooking_skill': cooking_skill
            }
            
            print(f"✅ Session created for user: {username}")  # Debug
            print(f"✅ Session data: {session['user']}")  # Debug
            
            return jsonify({'success': True, 'message': 'Registration successful'})
            
        except Exception as e:
            print(f"❌ Registration error: {e}")  # Debug
            import traceback
            print(f"❌ Full traceback: {traceback.format_exc()}")  # Debug
            return jsonify({'success': False, 'message': f'Registration failed: {str(e)}'})
    
    return render_template('register.html')
@app.route('/logout')
def logout():
    if 'user' in session:
        print(f"👋 User {session['user']['username']} logged out")  # Debug
    session.pop('user', None)
    return redirect(url_for('index'))

# ---------------- MAIN APPLICATION ROUTES ---------------- #
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        print("❌ No user in session, redirecting to login")  # Debug
        return redirect(url_for('login'))
    print(f"✅ User {session['user']['username']} accessing dashboard")  # Debug
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
        ingredients_ref = db.collection("users").document(username).collection("ingredients")
        ingredients = list(ingredients_ref.stream())
        
        # Calculate expiring items (simple implementation)
        today = datetime.now()
        expiring_count = 0
        for ing in ingredients:
            data = ing.to_dict()
            expiry_date = data.get('expiry_date')
            if expiry_date:
                try:
                    expiry = datetime.strptime(expiry_date, "%Y-%m-%d")
                    if (expiry - today).days <= 2:
                        expiring_count += 1
                except ValueError:
                    continue
        
        stats = {
            'pantry_count': len(ingredients),
            'expiring_count': expiring_count,
            'recipes_tried': random.randint(5, 20),
            'days_streak': random.randint(1, 30)
        }
        
        return jsonify(stats)
        
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pantry/ingredients', methods=['GET', 'POST', 'DELETE'])
def manage_ingredients():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    username = session['user']['username']
    
    if request.method == 'GET':
        try:
            ingredients_ref = db.collection("users").document(username).collection("ingredients")
            ingredients = []
            
            for doc in ingredients_ref.stream():
                ingredient_data = doc.to_dict()
                ingredient_data['id'] = doc.id
                # Ensure name field exists
                if 'name' not in ingredient_data:
                    ingredient_data['name'] = doc.id.replace('_', ' ').title()
                ingredients.append(ingredient_data)
            
            return jsonify(ingredients)
            
        except Exception as e:
            print(f"Error getting ingredients: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        data = request.get_json()
        name = data.get('name', '').strip()
        quantity = data.get('quantity', 1.0)
        unit = data.get('unit', 'units')
        storage_method = data.get('storage_method', 'pantry')
        
        try:
            if not name:
                return jsonify({'error': 'Ingredient name is required'}), 400
            
            if quantity <= 0:
                return jsonify({'error': 'Quantity must be positive'}), 400
            
            name_id = clean_name_for_id(name)
            if not name_id:
                return jsonify({'error': 'Invalid ingredient name'}), 400
            
            ingredient_ref = db.collection("users").document(username).collection("ingredients").document(name_id)
            
            # Simple expiry prediction (7 days default)
            expiry_days = 7
            expiry_date = (datetime.now() + timedelta(days=expiry_days)).strftime("%Y-%m-%d")
            
            ingredient_data = {
                "name": name,
                "quantity": float(quantity),
                "unit": unit,
                "storage_method": storage_method,
                "added_on": datetime.now().strftime("%Y-%m-%d"),
                "expiry_date": expiry_date,
                "last_updated": datetime.now().isoformat()
            }
            
            # Check if ingredient exists and update quantity
            existing_ing = ingredient_ref.get()
            if existing_ing.exists:
                existing_data = existing_ing.to_dict()
                ingredient_data['quantity'] = existing_data.get('quantity', 0) + float(quantity)
            
            ingredient_ref.set(ingredient_data)
            
            return jsonify({'success': True, 'message': 'Ingredient added successfully'})
            
        except Exception as e:
            print(f"Error adding ingredient: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'DELETE':
        ingredient_id = request.args.get('id')
        
        try:
            if not ingredient_id:
                return jsonify({'error': 'Ingredient ID is required'}), 400
            
            db.collection("users").document(username).collection("ingredients").document(ingredient_id).delete()
            return jsonify({'success': True, 'message': 'Ingredient deleted successfully'})
            
        except Exception as e:
            print(f"Error deleting ingredient: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/parse-ingredient', methods=['POST'])
def parse_ingredient():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    user_input = data.get('input', '')
    
    try:
        name, quantity, unit = parse_ingredient_input(user_input)
        
        if not name:
            return jsonify({'success': False, 'error': 'Could not parse ingredient name'})
        
        return jsonify({
            'name': name.title(),
            'quantity': quantity,
            'unit': unit,
            'success': True
        })
        
    except Exception as e:
        print(f"Error parsing ingredient: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/suggestions', methods=['POST'])
def get_suggestions():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    meal_type = data.get('meal_type')
    cuisine = data.get('cuisine')
    recipe_query = data.get('recipe_query')
    cooking_mode = data.get('cooking_mode', False)
    
    try:
        username = session['user']['username']
        user_data = session['user']
        
        # Get user's pantry
        ingredients_ref = db.collection("users").document(username).collection("ingredients")
        pantry_items = []
        for doc in ingredients_ref.stream():
            data = doc.to_dict()
            name = data.get('name', doc.id.replace('_', ' ').title())
            quantity = data.get('quantity', 1)
            unit = data.get('unit', 'units')
            pantry_items.append(f"{name} ({quantity} {unit})")
        
        # Prepare AI prompt based on request type
        if recipe_query:
            # Specific recipe request
            prompt = f"""
            USER REQUEST: Provide a detailed recipe for {recipe_query}
            
            USER PREFERENCES:
            - Diet: {user_data.get('diet_type', 'No restrictions')}
            - Dietary Restrictions: {', '.join(user_data.get('dietary_restrictions', []))}
            - Cooking Skill: {user_data.get('cooking_skill', 'beginner')}
            
            AVAILABLE INGREDIENTS: {', '.join(pantry_items) if pantry_items else 'No specific ingredients listed'}
            
            Please provide a complete recipe including:
            1. Ingredient list with quantities
            2. Step-by-step cooking instructions
            3. Cooking time
            4. Difficulty level
            5. Serving size
            6. Any helpful tips or variations
            
            Make it suitable for the user's cooking skill level and dietary preferences.
            """
        elif cooking_mode:
            # Cooking mode request
            prompt = f"""
            USER REQUEST: Provide cooking instructions for {recipe_query}
            
            Please provide:
            - Complete ingredient list
            - Detailed step-by-step instructions
            - Cooking time and difficulty
            - Serving information
            """
        else:
            # General meal suggestions
            prompt = f"""
            USER'S PANTRY INGREDIENTS: {', '.join(pantry_items) if pantry_items else 'Pantry is empty'}
            
            USER PREFERENCES:
            - Diet: {user_data.get('diet_type', 'No restrictions')}
            - Dietary Restrictions: {', '.join(user_data.get('dietary_restrictions', []))}
            - Preferred Cuisines: {', '.join(user_data.get('preferred_cuisines', []))}
            - Cooking Skill: {user_data.get('cooking_skill', 'beginner')}
            - Meal Type: {meal_type if meal_type else 'Any'}
            - Cuisine: {cuisine if cuisine else 'Any'}
            
            TASK: Suggest 3-5 creative, practical recipes that can be made with the user's available ingredients.
            
            For each recipe, provide:
            - Recipe name
            - Main ingredients used from pantry
            - Any additional ingredients needed
            - Brief cooking instructions
            - Estimated cooking time
            - Difficulty level
            
            Be creative and practical! If the pantry has limited ingredients, suggest simple yet delicious recipes.
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

@app.route('/api/mealplan', methods=['POST'])
def generate_meal_plan():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        username = session['user']['username']
        user_data = session['user']
        
        # Get user's pantry
        ingredients_ref = db.collection("users").document(username).collection("ingredients")
        pantry_items = []
        for doc in ingredients_ref.stream():
            data = doc.to_dict()
            name = data.get('name', doc.id.replace('_', ' ').title())
            pantry_items.append(name)
        
        prompt = f"""
        USER'S PANTRY INGREDIENTS: {', '.join(pantry_items) if pantry_items else 'Pantry is empty - suggest common pantry staples'}
        
        USER PREFERENCES:
        - Diet: {user_data.get('diet_type', 'No restrictions')}
        - Dietary Restrictions: {', '.join(user_data.get('dietary_restrictions', []))}
        - Preferred Cuisines: {', '.join(user_data.get('preferred_cuisines', []))}
        - Cooking Skill: {user_data.get('cooking_skill', 'beginner')}
        
        TASK: Create a COMPLETE 7-day weekly meal plan (breakfast, lunch, dinner for each day) using primarily the ingredients from the user's pantry.
        
        REQUIREMENTS:
        1. Use ingredients that are ALREADY in the pantry as main components
        2. Minimize additional ingredients needed
        3. Ensure variety across the week (different cuisines, cooking styles)
        4. Consider nutritional balance
        5. Account for dietary restrictions
        6. Suitable for the user's cooking skill level
        
        FORMAT:
        For each day (Monday through Sunday), provide:
        - Breakfast: [Recipe name] - [Brief description] - [Main pantry ingredients used]
        - Lunch: [Recipe name] - [Brief description] - [Main pantry ingredients used]
        - Dinner: [Recipe name] - [Brief description] - [Main pantry ingredients used]
        
        After the weekly plan, provide a shopping list of any additional ingredients needed for the entire week.
        
        Be creative and practical with the available ingredients!
        """
        
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=2500
        )
        
        meal_plan = response.choices[0].message.content
        
        return jsonify({'meal_plan': meal_plan})
        
    except Exception as e:
        print(f"Error generating meal plan: {e}")
        return jsonify({'error': f"Failed to generate meal plan: {str(e)}"}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')