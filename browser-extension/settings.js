// Vatican Monitor - Settings Page Script

// Load settings on page load
document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  setupEventListeners();
});

// Load saved settings
async function loadSettings() {
  const settings = await chrome.storage.local.get([
    'profile',
    'participants',
    'card',
    'autoPayEnabled'
  ]);
  
  // Load profile
  if (settings.profile) {
    document.getElementById('firstName').value = settings.profile.firstName || '';
    document.getElementById('lastName').value = settings.profile.lastName || '';
    document.getElementById('email').value = settings.profile.email || '';
    document.getElementById('phone').value = settings.profile.phone || '';
    document.getElementById('city').value = settings.profile.city || '';
    document.getElementById('country').value = settings.profile.country || 'Italia';
    document.getElementById('gender').value = settings.profile.gender || 'M';
    document.getElementById('birthDate').value = settings.profile.birthDate || '';
  }
  
  // Load participants
  if (settings.participants && settings.participants.length > 0) {
    settings.participants.forEach(p => addParticipantRow(p));
  } else {
    // Add one empty participant by default
    addParticipantRow();
  }
  
  // Load card
  if (settings.card) {
    document.getElementById('cardHolder').value = settings.card.holder || '';
    document.getElementById('cardNumber').value = settings.card.number || '';
    document.getElementById('cardExpiry').value = settings.card.expiry || '';
    document.getElementById('cardCVV').value = settings.card.cvv || '';
    updateCardPreview();
  }
  
  // Load auto-pay setting
  document.getElementById('autoPayEnabled').checked = settings.autoPayEnabled || false;
}

// Setup event listeners
function setupEventListeners() {
  // Add participant button
  document.getElementById('addParticipant').addEventListener('click', () => {
    addParticipantRow();
  });
  
  // Save button
  document.getElementById('saveSettings').addEventListener('click', saveSettings);
  
  // Card preview updates
  document.getElementById('cardNumber').addEventListener('input', (e) => {
    formatCardNumber(e.target);
    updateCardPreview();
  });
  document.getElementById('cardExpiry').addEventListener('input', (e) => {
    formatExpiry(e.target);
    updateCardPreview();
  });
  document.getElementById('cardHolder').addEventListener('input', updateCardPreview);
  document.getElementById('cardCVV').addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/\D/g, '');
  });
}

// Add participant row
function addParticipantRow(participant = {}) {
  const container = document.getElementById('participantsList');
  const index = container.children.length;
  
  const div = document.createElement('div');
  div.className = 'participant-item';
  div.innerHTML = `
    <div class="participant-header">
      <h4>Participant ${index + 1}</h4>
      <button class="btn-remove" onclick="removeParticipant(this)">Remove</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>First Name</label>
        <input type="text" class="participant-first-name" placeholder="Mario" value="${participant.firstName || ''}">
      </div>
      <div class="form-group">
        <label>Last Name</label>
        <input type="text" class="participant-last-name" placeholder="Rossi" value="${participant.lastName || ''}">
      </div>
    </div>
  `;
  
  container.appendChild(div);
}

// Remove participant
window.removeParticipant = function(button) {
  const item = button.closest('.participant-item');
  item.remove();
  
  // Renumber remaining participants
  const items = document.querySelectorAll('.participant-item');
  items.forEach((item, index) => {
    item.querySelector('h4').textContent = `Participant ${index + 1}`;
  });
};

// Format card number (add spaces)
function formatCardNumber(input) {
  let value = input.value.replace(/\s/g, '').replace(/\D/g, '');
  let formatted = value.match(/.{1,4}/g)?.join(' ') || value;
  input.value = formatted;
}

// Format expiry (add slash)
function formatExpiry(input) {
  let value = input.value.replace(/\D/g, '');
  if (value.length >= 2) {
    value = value.slice(0, 2) + '/' + value.slice(2, 4);
  }
  input.value = value;
}

// Update card preview
function updateCardPreview() {
  const number = document.getElementById('cardNumber').value;
  const holder = document.getElementById('cardHolder').value;
  const expiry = document.getElementById('cardExpiry').value;
  
  const preview = document.getElementById('cardPreview');
  
  if (number || holder || expiry) {
    preview.style.display = 'block';
    
    // Mask card number
    const cleanNumber = number.replace(/\s/g, '');
    let maskedNumber = '•••• •••• •••• ••••';
    if (cleanNumber.length >= 4) {
      const lastFour = cleanNumber.slice(-4);
      maskedNumber = `•••• •••• •••• ${lastFour}`;
    }
    
    document.getElementById('cardPreviewNumber').textContent = maskedNumber;
    document.getElementById('cardPreviewHolder').textContent = holder || 'CARDHOLDER NAME';
    document.getElementById('cardPreviewExpiry').textContent = expiry || 'MM/YY';
  } else {
    preview.style.display = 'none';
  }
}

// Save settings
async function saveSettings() {
  try {
    // Validate required fields
    const firstName = document.getElementById('firstName').value.trim();
    const lastName = document.getElementById('lastName').value.trim();
    const email = document.getElementById('email').value.trim();
    const phone = document.getElementById('phone').value.trim();
    const city = document.getElementById('city').value.trim();
    const birthDate = document.getElementById('birthDate').value;
    
    if (!firstName || !lastName || !email || !phone || !city || !birthDate) {
      alert('Please fill in all required profile fields (marked with *)');
      return;
    }
    
    // Validate age (must be 18+)
    const birth = new Date(birthDate);
    const today = new Date();
    const age = today.getFullYear() - birth.getFullYear();
    if (age < 18) {
      alert('You must be at least 18 years old');
      return;
    }
    
    // Validate email
    if (!email.includes('@')) {
      alert('Please enter a valid email address');
      return;
    }
    
    // Collect profile data
    const profile = {
      firstName,
      lastName,
      email,
      phone,
      city,
      country: document.getElementById('country').value,
      gender: document.getElementById('gender').value,
      birthDate,
      language: 'en'
    };
    
    // Collect participants
    const participants = [];
    const participantItems = document.querySelectorAll('.participant-item');
    participantItems.forEach(item => {
      const firstName = item.querySelector('.participant-first-name').value.trim();
      const lastName = item.querySelector('.participant-last-name').value.trim();
      
      if (firstName && lastName) {
        participants.push({ firstName, lastName });
      }
    });
    
    if (participants.length === 0) {
      alert('Please add at least one participant');
      return;
    }
    
    // Collect card data (optional)
    const cardNumber = document.getElementById('cardNumber').value.replace(/\s/g, '');
    const cardExpiry = document.getElementById('cardExpiry').value;
    const cardCVV = document.getElementById('cardCVV').value;
    const cardHolder = document.getElementById('cardHolder').value.trim();
    
    let card = null;
    if (cardNumber || cardExpiry || cardCVV || cardHolder) {
      // Validate card if any field is filled
      if (!cardNumber || cardNumber.length < 13) {
        alert('Please enter a valid card number (13-19 digits)');
        return;
      }
      
      if (!cardExpiry || !cardExpiry.match(/^\d{2}\/\d{2}$/)) {
        alert('Please enter expiry date in MM/YY format');
        return;
      }
      
      if (!cardCVV || cardCVV.length < 3) {
        alert('Please enter a valid CVV (3-4 digits)');
        return;
      }
      
      if (!cardHolder) {
        alert('Please enter cardholder name');
        return;
      }
      
      card = {
        number: cardNumber,
        expiry: cardExpiry,
        cvv: cardCVV,
        holder: cardHolder.toUpperCase()
      };
    }
    
    // Get auto-pay setting
    const autoPayEnabled = document.getElementById('autoPayEnabled').checked;
    
    // Save to storage
    await chrome.storage.local.set({
      profile,
      participants,
      card,
      autoPayEnabled
    });
    
    // Show success message
    const successMsg = document.getElementById('successMessage');
    successMsg.style.display = 'block';
    setTimeout(() => {
      successMsg.style.display = 'none';
    }, 3000);
    
    console.log('Settings saved:', {
      profile,
      participants: participants.length,
      hasCard: !!card,
      autoPayEnabled
    });
    
  } catch (error) {
    console.error('Error saving settings:', error);
    alert('Error saving settings: ' + error.message);
  }
}
