/**
 * Profile management logic.
 * Handles fetching, auto-saving dietary info, and token auth.
 */

// Always force the demo token so stale tokens never block access
localStorage.setItem('crave_token', 'crave-demo-token-hackathon');
const token = 'crave-demo-token-hackathon';

function getApiBase() {
    return localStorage.getItem('CRAVE_API_BASE') || 'http://127.0.0.1:8000';
}

let currentAllergies = [];

async function fetchProfile() {
    try {
        const response = await fetch(`${getApiBase()}/api/profile`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.status === 401) {
            // Re-set demo token and retry
            localStorage.setItem('crave_token', 'crave-demo-token-hackathon');
            window.location.reload();
            return;
        }

        const data = await response.json();
        
        // Hydrate User Info
        document.getElementById('user-name').textContent = data.name;
        document.getElementById('user-avatar').src = data.avatar_url;
        document.getElementById('header-avatar').src = data.avatar_url;

        // Hydrate Toggles
        document.getElementById('toggle-vegan').checked = data.dietary_preferences.vegan;
        document.getElementById('toggle-gluten').checked = data.dietary_preferences.gluten_free;
        document.getElementById('toggle-nut').checked = data.dietary_preferences.nut_free;
        document.getElementById('toggle-dairy').checked = data.dietary_preferences.dairy_free;

        // Hydrate Allergies
        currentAllergies = data.other_allergies || [];
        renderAllergies();

    } catch (err) {
        console.error("Failed to fetch profile", err);
    }
}

async function saveProfile() {
    const dietary_preferences = {
        vegan: document.getElementById('toggle-vegan').checked,
        gluten_free: document.getElementById('toggle-gluten').checked,
        nut_free: document.getElementById('toggle-nut').checked,
        dairy_free: document.getElementById('toggle-dairy').checked
    };

    const payload = {
        dietary_preferences,
        other_allergies: currentAllergies
    };

    try {
        await fetch(`${getApiBase()}/api/profile`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
    } catch (err) {
        console.error("Failed to save profile", err);
    }
}

function renderAllergies() {
    const container = document.getElementById('allergies-container');
    container.innerHTML = '';

    currentAllergies.forEach((allergy, index) => {
        const tag = document.createElement('div');
        tag.className = 'flex items-center gap-2 bg-primary-fixed text-primary px-3 py-1 rounded-full text-sm font-semibold';
        tag.innerHTML = `
            ${allergy}
            <button class="material-symbols-outlined text-sm hover:text-error transition-colors" data-index="${index}">close</button>
        `;
        container.appendChild(tag);
    });

    // Attach remove listeners
    container.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const index = parseInt(e.target.dataset.index, 10);
            currentAllergies.splice(index, 1);
            renderAllergies();
            saveProfile(); // Auto-save on remove
        });
    });
}

function addAllergy() {
    const input = document.getElementById('allergy-input');
    const val = input.value.trim();
    if (val && !currentAllergies.includes(val)) {
        currentAllergies.push(val);
        input.value = '';
        renderAllergies();
        saveProfile(); // Auto-save on add
    }
}

document.addEventListener('DOMContentLoaded', () => {
    fetchProfile();

    // Attach auto-save to toggles
    const toggles = ['toggle-vegan', 'toggle-gluten', 'toggle-nut', 'toggle-dairy'];
    toggles.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', saveProfile);
    });

    // Attach allergy add
    const addBtn = document.getElementById('add-allergy-btn');
    if (addBtn) {
        addBtn.addEventListener('click', addAllergy);
    }

    const allergyInput = document.getElementById('allergy-input');
    if (allergyInput) {
        allergyInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addAllergy();
            }
        });
    }

    // Hide logout in demo mode
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.style.display = 'none';
    }
});
