// API Base URL
const API_BASE = '/api';

// Utility functions
function showLoading(button) {
    const originalText = button.innerHTML;
    button.innerHTML = '<div class="loading"></div> Loading...';
    button.disabled = true;
    return originalText;
}

function hideLoading(button, originalText) {
    button.innerHTML = originalText;
    button.disabled = false;
}

function showAlert(message, type = 'success') {
    // Remove existing alerts
    const existingAlerts = document.querySelectorAll('.alert');
    existingAlerts.forEach(alert => alert.remove());
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-${type === 'success' ? 'check' : type === 'error' ? 'exclamation-triangle' : 'info'}-circle"></i>
            <span>${message}</span>
        </div>
    `;
    
    document.querySelector('main').prepend(alert);
    
    setTimeout(() => {
        alert.remove();
    }, 5000);
}

// Auth functions
async function loginUser(username, password) {
    const button = document.querySelector('#login-form button[type="submit"]');
    const originalText = showLoading(button);
    
    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('Login successful! Redirecting...', 'success');
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 1000);
        } else {
            showAlert(data.message, 'error');
        }
    } catch (error) {
        showAlert('Login failed: ' + error.message, 'error');
    } finally {
        hideLoading(button, originalText);
    }
}

async function registerUser(userData) {
    const button = document.querySelector('#register-form button[type="submit"]');
    const originalText = showLoading(button);
    
    try {
        const response = await fetch('/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('Registration successful! Redirecting to login...', 'success');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
        } else {
            showAlert(data.message, 'error');
        }
    } catch (error) {
        showAlert('Registration failed: ' + error.message, 'error');
    } finally {
        hideLoading(button, originalText);
    }
}

// Pantry management
async function loadPantry() {
    try {
        const response = await fetch('/api/pantry/ingredients');
        if (!response.ok) {
            throw new Error('Failed to fetch pantry items');
        }
        const ingredients = await response.json();
        
        const container = document.getElementById('pantry-items');
        if (!container) return;
        
        if (ingredients.error) {
            container.innerHTML = `<p class="text-center">Error: ${ingredients.error}</p>`;
            return;
        }
        
        if (ingredients.length === 0) {
            container.innerHTML = '<p class="text-center" style="color: var(--gray-light); padding: 2rem;">No ingredients in your pantry yet. Add some to get started!</p>';
            return;
        }
        
        container.innerHTML = ingredients.map(ingredient => `
            <div class="pantry-item">
                <div>
                    <div class="pantry-item-name">${ingredient.name || ingredient.id.replace(/_/g, ' ').toUpperCase()}</div>
                    <div class="pantry-item-details">
                        ${ingredient.quantity} ${ingredient.unit} • ${ingredient.storage_method || 'pantry'}
                        ${ingredient.expiry_date ? `• Expires: ${ingredient.expiry_date}` : ''}
                    </div>
                </div>
                <div class="pantry-item-actions">
                    <button class="btn btn-outline btn-sm" onclick="deleteIngredient('${ingredient.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading pantry:', error);
        const container = document.getElementById('pantry-items');
        if (container) {
            container.innerHTML = `<p class="text-center">Error loading pantry: ${error.message}</p>`;
        }
    }
}

async function addIngredient(ingredientData) {
    const button = document.querySelector('#add-ingredient-form button[type="submit"]');
    const originalText = showLoading(button);
    
    try {
        const response = await fetch('/api/pantry/ingredients', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(ingredientData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('Ingredient added successfully!', 'success');
            loadPantry();
            document.getElementById('add-ingredient-form').reset();
        } else {
            showAlert(data.error || 'Failed to add ingredient', 'error');
        }
    } catch (error) {
        showAlert('Failed to add ingredient: ' + error.message, 'error');
    } finally {
        hideLoading(button, originalText);
    }
}

async function deleteIngredient(ingredientId) {
    if (!confirm('Are you sure you want to delete this ingredient?')) return;
    
    try {
        const response = await fetch(`/api/pantry/ingredients?id=${encodeURIComponent(ingredientId)}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('Ingredient deleted successfully!', 'success');
            loadPantry();
        } else {
            showAlert(data.error || 'Failed to delete ingredient', 'error');
        }
    } catch (error) {
        showAlert('Failed to delete ingredient: ' + error.message, 'error');
    }
}

// Quick add ingredient parsing
async function quickAddIngredient() {
    const input = document.getElementById('quick-add-input');
    const userInput = input.value.trim();
    
    if (!userInput) {
        showAlert('Please enter ingredient details', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/parse-ingredient', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ input: userInput })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const storageMethod = document.getElementById('storage_method').value;
            await addIngredient({
                name: data.name,
                quantity: data.quantity,
                unit: data.unit,
                storage_method: storageMethod
            });
            input.value = '';
        } else {
            showAlert('Could not parse ingredient. Please use format: "2 kg tomatoes"', 'error');
        }
    } catch (error) {
        showAlert('Failed to parse ingredient: ' + error.message, 'error');
    }
}

// Meal suggestions
async function getSuggestions(filters = {}) {
    const button = document.querySelector('#get-suggestions-btn');
    const originalText = showLoading(button);
    
    try {
        const response = await fetch('/api/suggestions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(filters)
        });
        
        const data = await response.json();
        
        if (data.suggestions) {
            document.getElementById('suggestions-content').innerHTML = 
                `<div class="suggestions-content">${formatSuggestions(data.suggestions)}</div>`;
        } else if (data.error) {
            showAlert(data.error, 'error');
        } else {
            showAlert('No suggestions available', 'warning');
        }
    } catch (error) {
        showAlert('Failed to get suggestions: ' + error.message, 'error');
    } finally {
        hideLoading(button, originalText);
    }
}

function formatSuggestions(text) {
    // Convert markdown-like formatting to HTML
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>')
        .replace(/(\d+\.)\s/g, '<br><strong>$1</strong> ')
        .replace(/^- (.*?)(?=\n|$)/gm, '<br>• $1');
}

async function generateMealPlan() {
    const button = document.querySelector('#generate-plan-btn');
    const originalText = showLoading(button);
    
    try {
        const response = await fetch('/api/mealplan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.meal_plan) {
            document.getElementById('meal-plan-content').innerHTML = 
                `<div class="suggestions-content">${formatSuggestions(data.meal_plan)}</div>`;
            showAlert('Weekly meal plan generated successfully!', 'success');
        } else if (data.error) {
            showAlert(data.error, 'error');
        } else {
            showAlert('Failed to generate meal plan', 'error');
        }
    } catch (error) {
        showAlert('Failed to generate meal plan: ' + error.message, 'error');
    } finally {
        hideLoading(button, originalText);
    }
}

async function searchRecipe() {
    const query = document.getElementById('quick-recipe-search').value.trim();
    if (!query) {
        showAlert('Please enter a recipe name', 'error');
        return;
    }
    
    const button = document.querySelector('#get-suggestions-btn');
    const originalText = showLoading(button);
    
    try {
        const response = await fetch('/api/suggestions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ recipe_query: query })
        });
        
        const data = await response.json();
        
        if (data.suggestions) {
            document.getElementById('quick-recipe-result').innerHTML = `
                <div class="suggestions-content">
                    <h3 style="color: var(--primary); margin-bottom: 1rem;">${query}</h3>
                    ${formatSuggestions(data.suggestions)}
                </div>
            `;
        } else {
            showAlert('No recipe found', 'warning');
        }
    } catch (error) {
        showAlert('Search failed: ' + error.message, 'error');
    } finally {
        hideLoading(button, originalText);
    }
}

// Dashboard functions
async function initDashboard() {
    try {
        const response = await fetch('/api/user');
        if (!response.ok) {
            throw new Error('Failed to fetch user data');
        }
        const user = await response.json();
        
        if (user.error) {
            console.error('User error:', user.error);
            return;
        }
        
        // Update user info
        const welcomeElement = document.getElementById('user-welcome');
        const dietElement = document.getElementById('user-diet');
        const skillElement = document.getElementById('user-skill');
        
        if (welcomeElement) welcomeElement.textContent = `Welcome, ${user.username}`;
        if (dietElement) dietElement.textContent = user.diet_type || 'Not set';
        if (skillElement) skillElement.textContent = user.cooking_skill || 'beginner';
        
        // Load dashboard stats
        await loadDashboardStats();
        
        // Load pantry for quick overview
        await loadPantryOverview();
        
    } catch (error) {
        console.error('Failed to initialize dashboard:', error);
    }
}

async function loadDashboardStats() {
    try {
        const response = await fetch('/api/dashboard/stats');
        if (!response.ok) {
            throw new Error('Failed to fetch dashboard stats');
        }
        const stats = await response.json();
        
        if (stats.error) {
            console.error('Stats error:', stats.error);
            return;
        }
        
        document.getElementById('pantry-count').textContent = stats.pantry_count || 0;
        document.getElementById('expiring-count').textContent = stats.expiring_count || 0;
        document.getElementById('recipes-tried').textContent = stats.recipes_tried || 0;
        document.getElementById('days-streak').textContent = stats.days_streak || 0;
        
    } catch (error) {
        console.error('Error loading dashboard stats:', error);
    }
}

async function loadPantryOverview() {
    try {
        const response = await fetch('/api/pantry/ingredients');
        const ingredients = await response.json();
        
        if (ingredients.error) {
            return;
        }
        
        const overviewContainer = document.getElementById('pantry-overview');
        if (overviewContainer && ingredients.length > 0) {
            const topItems = ingredients.slice(0, 8).map(ing => 
                `<span class="pantry-item">${ing.name || ing.id.replace(/_/g, ' ')}</span>`
            ).join('');
            
            overviewContainer.innerHTML = topItems;
            
            if (ingredients.length > 8) {
                overviewContainer.innerHTML += `<span class="pantry-item">+${ingredients.length - 8} more</span>`;
            }
        }
        
    } catch (error) {
        console.error('Error loading pantry overview:', error);
    }
}

// Cooking mode
async function startCooking() {
    const recipeName = document.getElementById('recipe-input').value.trim();
    if (!recipeName) {
        showAlert('Please enter a recipe name', 'error');
        return;
    }
    
    const button = document.querySelector('#cooking-interface button');
    const originalText = showLoading(button);
    
    try {
        const response = await fetch('/api/suggestions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                recipe_query: recipeName,
                cooking_mode: true 
            })
        });
        
        const data = await response.json();
        
        if (data.suggestions) {
            document.getElementById('cooking-interface').style.display = 'block';
            document.getElementById('cooking-ingredients').innerHTML = `
                <div class="suggestions-content">
                    <h4>Ingredients for ${recipeName}:</h4>
                    ${formatSuggestions(data.suggestions)}
                </div>
            `;
            
            // Extract basic info
            const totalTime = data.suggestions.match(/time.*?(\d+)/i) ? '30 mins' : 'Not specified';
            const difficulty = data.suggestions.match(/difficulty.*?(beginner|intermediate|advanced)/i) ? 
                data.suggestions.match(/difficulty.*?(beginner|intermediate|advanced)/i)[1] : 'Not specified';
            const servings = data.suggestions.match(/servings.*?(\d+)/i) ? 
                data.suggestions.match(/servings.*?(\d+)/i)[1] : 'Not specified';
            
            document.getElementById('total-time').textContent = totalTime;
            document.getElementById('difficulty').textContent = difficulty;
            document.getElementById('servings').textContent = servings;
            
            // Scroll to cooking interface
            document.getElementById('cooking-interface').scrollIntoView({ behavior: 'smooth' });
            
            showAlert(`Ready to cook ${recipeName}! Follow the instructions below.`, 'success');
        } else {
            showAlert('Could not generate cooking instructions', 'error');
        }
    } catch (error) {
        showAlert('Failed to start cooking: ' + error.message, 'error');
    } finally {
        hideLoading(button, originalText);
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    // Auth forms
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(loginForm);
            await loginUser(formData.get('username'), formData.get('password'));
        });
    }
    
    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(registerForm);
            
            const userData = {
                username: formData.get('username'),
                password: formData.get('password'),
                diet_type: formData.get('diet_type'),
                dietary_restrictions: Array.from(formData.getAll('dietary_restrictions')),
                preferred_cuisines: Array.from(formData.getAll('preferred_cuisines')),
                cooking_skill: formData.get('cooking_skill')
            };
            
            await registerUser(userData);
        });
    }
    
    // Pantry management
    const addIngredientForm = document.getElementById('add-ingredient-form');
    if (addIngredientForm) {
        addIngredientForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(addIngredientForm);
            
            await addIngredient({
                name: formData.get('name'),
                quantity: parseFloat(formData.get('quantity')),
                unit: formData.get('unit'),
                storage_method: formData.get('storage_method')
            });
        });
    }
    
    // Quick add button
    const quickAddBtn = document.getElementById('quick-add-btn');
    if (quickAddBtn) {
        quickAddBtn.addEventListener('click', quickAddIngredient);
    }
    
    // Quick add input enter key
    const quickAddInput = document.getElementById('quick-add-input');
    if (quickAddInput) {
        quickAddInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                quickAddIngredient();
            }
        });
    }
    
    // Suggestions
    const suggestionsForm = document.getElementById('suggestions-form');
    if (suggestionsForm) {
        suggestionsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(suggestionsForm);
            
            await getSuggestions({
                meal_type: formData.get('meal_type'),
                cuisine: formData.get('cuisine')
            });
        });
    }
    
    // Meal plan
    const mealPlanBtn = document.getElementById('generate-plan-btn');
    if (mealPlanBtn) {
        mealPlanBtn.addEventListener('click', generateMealPlan);
    }
    
    // Quick recipe search
    const quickSearchInput = document.getElementById('quick-recipe-search');
    if (quickSearchInput) {
        quickSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                searchRecipe();
            }
        });
    }
    
    // Cooking mode
    const cookingStartBtn = document.querySelector('#cooking-interface button');
    if (cookingStartBtn) {
        cookingStartBtn.addEventListener('click', startCooking);
    }
    
    const recipeInput = document.getElementById('recipe-input');
    if (recipeInput) {
        recipeInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                startCooking();
            }
        });
    }
    
    // Initialize dashboard if on dashboard page
    if (window.location.pathname === '/dashboard' || window.location.pathname === '/') {
        initDashboard();
    }
    
    // Load pantry if on pantry page
    if (window.location.pathname === '/pantry') {
        loadPantry();
    }
    
    // Auto-load suggestions if on suggestions page
    if (window.location.pathname === '/suggestions') {
        // Optional: auto-load some suggestions
        // getSuggestions();
    }
});

// Global function for HTML onclick
window.quickAddIngredient = quickAddIngredient;
window.searchRecipe = searchRecipe;
window.startCooking = startCooking;
window.deleteIngredient = deleteIngredient;