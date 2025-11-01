// Global API Helper Functions
const API = {
    // Base fetch wrapper
    async call(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || 'Request failed');
            }
            
            return data;
        } catch (error) {
            console.error('API Error:', error);
            showNotification(error.message, 'error');
            throw error;
        }
    },

    // Dashboard stats
    async getDashboardStats() {
        return await this.call('/api/dashboard/stats');
    },

    // Donors
    async getDonors() {
        return await this.call('/api/donors/summary');
    },

    async addDonor(donorData) {
        return await this.call('/api/donors', {
            method: 'POST',
            body: JSON.stringify(donorData)
        });
    },

    async recordDonation(donationData) {
        return await this.call('/api/donations', {
            method: 'POST',
            body: JSON.stringify(donationData)
        });
    },

    // Inventory
    async getInventory() {
        return await this.call('/api/inventory/stock');
    },

    // Requests
    async getPendingRequests() {
        return await this.call('/api/requests/pending');
    },

    async fulfillRequest(requestId, unitsSupplied) {
        return await this.call('/api/requests/fulfill', {
            method: 'POST',
            body: JSON.stringify({
                request_id: requestId,
                units_supplied: unitsSupplied
            })
        });
    },

    // Analytics
    async getDonorDistribution() {
        return await this.call('/api/analytics/donor_distribution');
    }
};

// Notification System
function showNotification(message, type = 'info') {
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500'
    };

    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 fade-in`;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Format Date
function formatDate(dateString) {
    if (!dateString || dateString === 'None') return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Debounce function for search
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Stock Status Color Helper
function getStockStatusColor(units) {
    if (units < 5) return 'bg-red-100 text-red-700';
    if (units < 10) return 'bg-yellow-100 text-yellow-700';
    return 'bg-green-100 text-green-700';
}

// Eligibility Status Helper
function getEligibilityStatus(lastDonationDate) {
    if (!lastDonationDate || lastDonationDate === 'None') {
        return { text: 'Eligible', color: 'text-green-600' };
    }
    
    const lastDonation = new Date(lastDonationDate);
    const today = new Date();
    const daysSince = Math.floor((today - lastDonation) / (1000 * 60 * 60 * 24));
    
    if (daysSince >= 90) {
        return { text: 'Eligible', color: 'text-green-600' };
    } else {
        return { 
            text: `Wait ${90 - daysSince} days`, 
            color: 'text-red-600' 
        };
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Blood Bank Management System - UI Loaded ✅');
});