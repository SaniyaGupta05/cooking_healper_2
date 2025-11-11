from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import hashlib
import re
from datetime import datetime, timedelta
import json
import os
import random
import requests

app = Flask(__name__)
app.secret_key = 'ai-meal-planner-secret-key-2024'  # Change this in production
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
CORS(app, supports_credentials=True)

# ---------------- CONFIGURATION ---------------- #
GROQ_API_KEY = "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"

# ---------------- TEMPORARY STORAGE ---------------- #
# In-memory storage for users and pantry (resets on server restart)
temp_users = {}
temp_pantry = {}
print("✅ Using temporary storage (no Firebase)")

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

def call_groq_api(prompt):
    """Call Groq API using requests to avoid proxies error"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messages": [{"role": "user", "content": prompt}],
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"❌ Groq API call failed: {e}")
        return None

# ---------------- DEBUG ROUTES ---------------- #
@app.route('/debug/create-simple-user')
def debug_create_simple_user():
    """Create a simple test user"""
    try:
        username = "saniya"
        password = "test123"
        
        # Create user in temporary storage
        temp_users[username] = {
            "password": hash_password(password),
            "diet_type": "Pure Veg",
            "dietary_restrictions": [],
            "preferred_cuisines": ["Indian"],
            "cooking_skill": "beginner",
            "created_at": datetime.now().isoformat(),
            "last_login": datetime.now().isoformat()
        }
        # Initialize empty pantry for this user
        temp_pantry[username] = []
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
        
        # Get users from temporary storage
        for username, user_data in temp_users.items():
            users_list.append({
                'username': username,
                'storage': 'temporary',
                'has_password': 'password' in user_data,
                'diet_type': user_data.get('diet_type', 'Not set'),
                'created_at': user_data.get('created_at', 'Unknown')
            })
        
        return jsonify({
            'total_users': len(users_list),
            'storage_type': 'temporary_memory',
            'users': users_list
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug/system-status')
def debug_system_status():
    """Check system status"""
    status = {
        'storage_type': 'temporary_memory',
        'total_users': len(temp_users),
        'total_pantry_items': sum(len(items) for items in temp_pantry.values()),
        'session_users': list(temp_users.keys()),
        'groq_api_available': GROQ_API_KEY is not None and GROQ_API_KEY != ""
    }
    return jsonify(status)

@app.route('/debug/clean-db')
def debug_clean_db():
    """Clean the database for testing"""
    try:
        # Clear temporary users and pantry
        temp_users.clear()
        temp_pantry.clear()
        
        return "Temporary storage cleaned successfully"
    except Exception as e:
        return f"Error cleaning storage: {e}"

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
            # Check if user exists in temporary storage
            if username in temp_users:
                user_data = temp_users[username]
                
                # Check password
                if user_data.get("password") == hash_password(password):
                    # Update last login
                    user_data["last_login"] = datetime.now().isoformat()
                    
                    # Create session with user data
                    session.permanent = True
                    session['user'] = {
                        'username': username,
                        'diet_type': user_data.get('diet_type'),
                        'dietary_restrictions': user_data.get('dietary_restrictions', []),
                        'preferred_cuisines': user_data.get('preferred_cuisines', []),
                        'cooking_skill': user_data.get('cooking_skill')
                    }
                    
                    print(f"✅ Login successful for user: {username} (Temporary Storage)")
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
            
            # Check if user exists in temporary storage
            if username in temp_users:
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
            
            # Save to temporary storage
            temp_users[username] = user_data
            temp_pantry[username] = []  # Initialize empty pantry
            
            print(f"✅ User '{username}' registered successfully in Temporary Storage")
            
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
        
        # Get pantry count from temporary storage
        if username in temp_pantry:
            pantry_count = len(temp_pantry[username])
        
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

@app.route('/api/pantry/ingredients', methods=['GET', 'POST', 'DELETE'])
def manage_ingredients():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    username = session['user']['username']
    
    if request.method == 'GET':
        try:
            # Get from temporary storage
            ingredients = temp_pantry.get(username, [])
            return jsonify(ingredients)
            
        except Exception as e:
            print(f"Error getting ingredients: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        data = request.get_json()
        name = data.get('name', '').strip()
        quantity = data.get('quantity', 1.0)
        unit = data.get('unit', 'units')
        
        try:
            if not name:
                return jsonify({'error': 'Ingredient name is required'}), 400
            
            ingredient_data = {
                "id": clean_name_for_id(name),
                "name": name,
                "quantity": float(quantity),
                "unit": unit,
                "added_on": datetime.now().strftime("%Y-%m-%d"),
                "last_updated": datetime.now().isoformat()
            }
            
            # Save to temporary storage
            if username not in temp_pantry:
                temp_pantry[username] = []
            
            # Check if ingredient exists and update quantity
            existing_index = None
            for i, item in enumerate(temp_pantry[username]):
                if item.get('name', '').lower() == name.lower():
                    existing_index = i
                    break
            
            if existing_index is not None:
                # Update existing ingredient
                temp_pantry[username][existing_index]['quantity'] += float(quantity)
                temp_pantry[username][existing_index]['last_updated'] = datetime.now().isoformat()
            else:
                # Add new ingredient
                temp_pantry[username].append(ingredient_data)
            
            return jsonify({'success': True, 'message': 'Ingredient added successfully'})
            
        except Exception as e:
            print(f"Error adding ingredient: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'DELETE':
        ingredient_id = request.args.get('id')
        
        try:
            if not ingredient_id:
                return jsonify({'error': 'Ingredient ID is required'}), 400
            
            # Remove from temporary storage
            if username in temp_pantry:
                temp_pantry[username] = [item for item in temp_pantry[username] if item.get('id') != ingredient_id]
            
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
        
        # Get user's pantry from temporary storage
        pantry_items = []
        if username in temp_pantry:
            for item in temp_pantry[username]:
                pantry_items.append(f"{item['name']} ({item['quantity']} {item['unit']})")
        
        # Prepare AI prompt based on request type
        if recipe_query:
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
            prompt = f"""
            USER REQUEST: Provide cooking instructions for {recipe_query}
            
            Please provide:
            - Complete ingredient list
            - Detailed step-by-step instructions
            - Cooking time and difficulty
            - Serving information
            """
        else:
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
        
        # Call Groq API
        suggestions = call_groq_api(prompt)
        
        if suggestions:
            return jsonify({'suggestions': suggestions})
        else:
            # Provide fallback suggestions
            fallback_suggestions = """
            Here are some delicious recipe suggestions:

            🍛 **Vegetable Biryani**
            - Basmati rice, mixed vegetables, spices
            - Cook time: 40 minutes
            - Difficulty: Intermediate

            🥗 **Fresh Garden Salad**
            - Lettuce, tomatoes, cucumbers, olive oil
            - Cook time: 10 minutes  
            - Difficulty: Easy

            🍲 **Tomato Pasta**
            - Pasta, tomatoes, garlic, herbs
            - Cook time: 20 minutes
            - Difficulty: Beginner

            🥘 **Vegetable Stir Fry**
            - Mixed vegetables, soy sauce, rice
            - Cook time: 15 minutes
            - Difficulty: Easy

            🍵 **Lentil Soup**
            - Lentils, vegetables, spices
            - Cook time: 30 minutes
            - Difficulty: Beginner

            Note: These are sample recipes. AI service is temporarily unavailable.
            """
            return jsonify({'suggestions': fallback_suggestions})
        
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
        
        # Get user's pantry from temporary storage
        pantry_items = []
        if username in temp_pantry:
            for item in temp_pantry[username]:
                pantry_items.append(item['name'])
        
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
        
        # Call Groq API
        meal_plan = call_groq_api(prompt)
        
        if meal_plan:
            return jsonify({'meal_plan': meal_plan})
        else:
            # Provide fallback meal plan
            fallback_meal_plan = """
            📅 **7-Day Sample Meal Plan**

            **Monday:**
            - Breakfast: Oatmeal with fruits and nuts
            - Lunch: Vegetable salad with quinoa and dressing
            - Dinner: Pasta with tomato sauce and herbs

            **Tuesday:**
            - Breakfast: Toast with avocado and spices
            - Lunch: Rice and vegetable curry
            - Dinner: Vegetable stir-fry with rice

            **Wednesday:**
            - Breakfast: Smoothie bowl with fruits and granola
            - Lunch: Lentil soup with bread
            - Dinner: Vegetable biryani with raita

            **Thursday:**
            - Breakfast: Yogurt with granola and honey
            - Lunch: Vegetable wrap with hummus
            - Dinner: Tomato pasta with garlic bread

            **Friday:**
            - Breakfast: Pancakes with maple syrup
            - Lunch: Rice and dal with vegetables
            - Dinner: Pizza (vegetarian) with salad

            **Saturday:**
            - Breakfast: Scrambled eggs (or tofu scramble)
            - Lunch: Vegetable noodles with sauce
            - Dinner: Burger with fries and salad

            **Sunday:**
            - Breakfast: French toast with fruits
            - Lunch: Leftovers or simple salad
            - Dinner: Special dinner - your choice!

            🛒 **Shopping List:**
            - Fresh vegetables (tomatoes, onions, carrots, bell peppers)
            - Fresh fruits (bananas, apples, berries)
            - Dairy alternatives (if needed)
            - Basic pantry staples (oil, spices, flour)

            Note: This is a sample meal plan. AI service is temporarily unavailable.
            """
            return jsonify({'meal_plan': fallback_meal_plan})
        
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
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
