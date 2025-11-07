# ---------------- CONFIGURATION ---------------- #
FIREBASE_CONFIG_PATH = os.environ.get('FIREBASE_CONFIG_PATH', 'firebase_key.json')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    raise ValueError('GROQ_API_KEY environment variable is required')

# ---------------- FIREBASE INIT ---------------- #
try:
    if not firebase_admin._apps:
        if os.path.exists(FIREBASE_CONFIG_PATH):
            cred = credentials.Certificate(FIREBASE_CONFIG_PATH)
            firebase_admin.initialize_app(cred)
        else:
            print('⚠ Firebase config file not found. Using mock database for local development.')
            # Fall back to mock database
            raise FileNotFoundError('Firebase config file not found')
    db = firestore.client()
    print('✅ Firebase initialized successfully')
except Exception as e:
    print(f'❌ Firebase initialization failed: {e}')
    print('🔄 Using mock database for local development...')
    
    # Mock database implementation
    class MockDB:
        def __init__(self):
            self.users = {}
            self.ingredients = {}
        
        def collection(self, name):
            return MockCollection(self, name)

    class MockCollection:
        def __init__(self, db, name):
            self.db = db
            self.name = name
        
        def document(self, doc_id):
            return MockDocument(self.db, self.name, doc_id)
        
        def stream(self):
            # Return empty generator for stream
            return iter([])

    class MockDocument:
        def __init__(self, db, collection, doc_id):
            self.db = db
            self.collection = collection
            self.doc_id = doc_id
        
        def get(self):
            return MockSnapshot(self.db, self.collection, self.doc_id)
        
        def set(self, data):
            if self.collection == 'users':
                self.db.users[self.doc_id] = data
                print(f'📝 MockDB: Created user {self.doc_id}')
            elif self.collection == 'ingredients':
                if self.doc_id not in self.db.ingredients:
                    self.db.ingredients[self.doc_id] = {}
                self.db.ingredients[self.doc_id].update(data)
                print(f'📝 MockDB: Updated ingredient {self.doc_id}')
            return None
        
        def delete(self):
            if self.collection == 'ingredients' and self.doc_id in self.db.ingredients:
                del self.db.ingredients[self.doc_id]
                print(f'🗑️ MockDB: Deleted ingredient {self.doc_id}')
            return None

    class MockSnapshot:
        def __init__(self, db, collection, doc_id):
            self.db = db
            self.collection = collection
            self.doc_id = doc_id
        
        def exists(self):
            if self.collection == 'users':
                return self.doc_id in self.db.users
            elif self.collection == 'ingredients':
                return self.doc_id in self.db.ingredients
            return False
        
        def to_dict(self):
            if self.collection == 'users' and self.doc_id in self.db.users:
                return self.db.users[self.doc_id]
            elif self.collection == 'ingredients' and self.doc_id in self.db.ingredients:
                return self.db.ingredients[self.doc_id]
            return {}
    
    db = MockDB()
