// Vatican Ticket Monitor - Options/Settings Script

document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
  document.getElementById('saveBtn').addEventListener('click', saveSettings);
  document.getElementById('createTestSlotBtn').addEventListener('click', createTestSlot);
  document.getElementById('deleteTestSlotBtn').addEventListener('click', deleteTestSlot);
}

// Load settings from storage
async function loadSettings() {
  const settings = await chrome.storage.local.get('settings');
  
  if (settings.settings) {
    const s = settings.settings;
    
    document.getElementById('soundEnabled').checked = s.soundEnabled !== false;
    document.getElementById('desktopNotifications').checked = s.desktopNotifications !== false;
    document.getElementById('notificationFrequency').value = s.notificationFrequency || 'always';
    document.getElementById('maxRetries').value = s.maxRetries || 3;
    document.getElementById('timeout').value = s.timeout || 10;
    document.getElementById('autoStop').checked = s.autoStop || false;
    document.getElementById('historyLimit').value = s.historyLimit || 50;
    document.getElementById('autoCleanup').checked = s.autoCleanup !== false;
  }
}

// Save settings to storage
async function saveSettings() {
  const settings = {
    soundEnabled: document.getElementById('soundEnabled').checked,
    desktopNotifications: document.getElementById('desktopNotifications').checked,
    notificationFrequency: document.getElementById('notificationFrequency').value,
    maxRetries: parseInt(document.getElementById('maxRetries').value),
    timeout: parseInt(document.getElementById('timeout').value),
    autoStop: document.getElementById('autoStop').checked,
    historyLimit: parseInt(document.getElementById('historyLimit').value),
    autoCleanup: document.getElementById('autoCleanup').checked
  };
  
  await chrome.storage.local.set({ settings });
  
  // Show success message
  const successMessage = document.getElementById('successMessage');
  successMessage.style.display = 'block';
  
  setTimeout(() => {
    successMessage.style.display = 'none';
  }, 3000);
}

// Create test slot via backend API
async function createTestSlot() {
  const btn = document.getElementById('createTestSlotBtn');
  const testMessage = document.getElementById('testMessage');
  
  btn.disabled = true;
  btn.textContent = '⏳ Creating test slot...';
  
  try {
    // Get backend config
    const { backendListenerConfig } = await chrome.storage.local.get('backendListenerConfig');
    
    if (!backendListenerConfig || !backendListenerConfig.backendUrl) {
      showTestMessage('❌ Backend URL not configured. Please enable Backend Listener Mode first.', 'error');
      btn.disabled = false;
      btn.textContent = '🧪 Create Test Slot';
      return;
    }
    
    const backendUrl = backendListenerConfig.backendUrl || 'http://localhost:8000';
    const apiKey = backendListenerConfig.apiKey || '';
    
    // Call backend API to create test slot
    const response = await fetch(`${backendUrl}/api/v1/test/create-slot/`, {
      method: 'POST',
      headers: {
        'Authorization': apiKey ? `Bearer ${apiKey}` : '',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        date: '15/06/2026',
        time: '09:00',
        visitors: 2
      })
    });
    
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }
    
    const data = await response.json();
    
    showTestMessage(
      `✅ Test slot created successfully!<br>
      <strong>Slot ID:</strong> ${data.slot_id}<br>
      <strong>Date:</strong> ${data.date}<br>
      <strong>Time:</strong> ${data.time}<br>
      <br>
      <strong>Watch your browser console (F12)</strong><br>
      Within 10 seconds, an incognito window should open automatically!`,
      'success'
    );
    
  } catch (error) {
    console.error('Error creating test slot:', error);
    showTestMessage(
      `❌ Failed to create test slot: ${error.message}<br>
      <br>
      <strong>Alternative method:</strong><br>
      Run this command in terminal:<br>
      <code style="background: #f5f5f5; padding: 5px; display: block; margin-top: 5px;">
      docker-compose exec backend python /app/create_test_slot.py
      </code>`,
      'error'
    );
  } finally {
    btn.disabled = false;
    btn.textContent = '🧪 Create Test Slot';
  }
}

// Delete test slot via backend API
async function deleteTestSlot() {
  const btn = document.getElementById('deleteTestSlotBtn');
  const testMessage = document.getElementById('testMessage');
  
  btn.disabled = true;
  btn.textContent = '⏳ Deleting...';
  
  try {
    // Get backend config
    const { backendListenerConfig } = await chrome.storage.local.get('backendListenerConfig');
    
    if (!backendListenerConfig || !backendListenerConfig.backendUrl) {
      showTestMessage('❌ Backend URL not configured. Please enable Backend Listener Mode first.', 'error');
      btn.disabled = false;
      btn.textContent = '🗑️ Delete Test Slot';
      return;
    }
    
    const backendUrl = backendListenerConfig.backendUrl || 'http://localhost:8000';
    const apiKey = backendListenerConfig.apiKey || '';
    
    // Call backend API to delete test slots
    const response = await fetch(`${backendUrl}/api/v1/test/delete-slots/`, {
      method: 'DELETE',
      headers: {
        'Authorization': apiKey ? `Bearer ${apiKey}` : '',
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }
    
    const data = await response.json();
    
    showTestMessage(
      `✅ Deleted ${data.deleted_count} test slot(s) successfully!`,
      'success'
    );
    
  } catch (error) {
    console.error('Error deleting test slots:', error);
    showTestMessage(
      `❌ Failed to delete test slots: ${error.message}<br>
      <br>
      <strong>Alternative method:</strong><br>
      Run this command in terminal:<br>
      <code style="background: #f5f5f5; padding: 5px; display: block; margin-top: 5px;">
      docker-compose exec backend python /app/delete_test_slot.py
      </code>`,
      'error'
    );
  } finally {
    btn.disabled = false;
    btn.textContent = '🗑️ Delete Test Slot';
  }
}

// Show test message
function showTestMessage(message, type) {
  const testMessage = document.getElementById('testMessage');
  testMessage.innerHTML = message;
  testMessage.style.display = 'block';
  
  if (type === 'success') {
    testMessage.style.background = '#d4edda';
    testMessage.style.color = '#155724';
    testMessage.style.borderLeft = '4px solid #28a745';
  } else {
    testMessage.style.background = '#f8d7da';
    testMessage.style.color = '#721c24';
    testMessage.style.borderLeft = '4px solid #dc3545';
  }
}
