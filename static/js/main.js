// Main JavaScript functionality for MediSync

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.bg-green-100, .bg-red-100');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.transition = 'opacity 0.5s';
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 500);
        }, 5000);
    });

    // Search functionality
    const searchInputs = document.querySelectorAll('input[type="text"][placeholder*="Search"]');
    searchInputs.forEach(input => {
        input.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const table = this.closest('.bg-white').querySelector('tbody');
            if (table) {
                const rows = table.querySelectorAll('tr');
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(searchTerm) ? '' : 'none';
                });
            }
        });
    });
});

// Sales cart functionality
let salesCart = JSON.parse(localStorage.getItem('salesCart')) || [];

function addToCart(medicineId, medicineName, price, maxQuantity) {
    const existingItem = salesCart.find(item => item.medicine_id === medicineId);
    
    if (existingItem) {
        if (existingItem.quantity < maxQuantity) {
            existingItem.quantity += 1;
            existingItem.total_price = existingItem.quantity * existingItem.unit_price;
        } else {
            alert(`Only ${maxQuantity} units available in stock.`);
            return;
        }
    } else {
        salesCart.push({
            medicine_id: medicineId,
            name: medicineName,
            unit_price: price,
            quantity: 1,
            total_price: price
        });
    }
    
    updateCartDisplay();
    saveCartToStorage();
}

function removeFromCart(medicineId) {
    salesCart = salesCart.filter(item => item.medicine_id !== medicineId);
    updateCartDisplay();
    saveCartToStorage();
}

function updateCartQuantity(medicineId, newQuantity) {
    const item = salesCart.find(item => item.medicine_id === medicineId);
    if (item && newQuantity > 0) {
        item.quantity = newQuantity;
        item.total_price = item.quantity * item.unit_price;
        updateCartDisplay();
        saveCartToStorage();
    }
}

function updateCartDisplay() {
    const cartItems = document.getElementById('cartItems');
    const cartTotal = document.getElementById('cartTotal');
    const cartCount = document.getElementById('cartCount');
    
    if (cartItems) {
        cartItems.innerHTML = salesCart.map(item => `
            <div class="flex justify-between items-center p-3 border-b">
                <div>
                    <h4 class="font-medium">${item.name}</h4>
                    <p class="text-sm text-gray-600">$${item.unit_price} x ${item.quantity}</p>
                </div>
                <div class="flex items-center space-x-2">
                    <button onclick="updateCartQuantity(${item.medicine_id}, ${item.quantity - 1})" class="px-2 py-1 bg-gray-200 rounded">-</button>
                    <span>${item.quantity}</span>
                    <button onclick="updateCartQuantity(${item.medicine_id}, ${item.quantity + 1})" class="px-2 py-1 bg-gray-200 rounded">+</button>
                    <button onclick="removeFromCart(${item.medicine_id})" class="ml-2 text-red-600">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    if (cartTotal) {
        const total = salesCart.reduce((sum, item) => sum + item.total_price, 0);
        cartTotal.textContent = `$${total.toFixed(2)}`;
    }
    
    if (cartCount) {
        cartCount.textContent = salesCart.reduce((sum, item) => sum + item.quantity, 0);
    }
}

function saveCartToStorage() {
    localStorage.setItem('salesCart', JSON.stringify(salesCart));
}

function clearCart() {
    salesCart = [];
    updateCartDisplay();
    saveCartToStorage();
}

// Initialize cart on page load
document.addEventListener('DOMContentLoaded', function() {
    updateCartDisplay();
});