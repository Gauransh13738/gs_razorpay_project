// API Configuration for Render Deployment
// Update this file with your actual Render backend URL

const API_CONFIG = {
    // Development (local)
    development: {
        baseURL: 'http://localhost:8000'
    },
    
    // Production (Render)
    production: {
        baseURL: 'https://your-backend-service.onrender.com'
    }
};

// Use production URL by default, change to development for local testing
const currentEnv = 'production'; // Change to 'development' for local testing

const API_BASE_URL = API_CONFIG[currentEnv].baseURL;

// Export for use in dashboard.html
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { API_BASE_URL, currentEnv };
}