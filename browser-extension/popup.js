// Vatican Ticket Monitor - Popup Script
// Handles UI interactions and displays monitoring status

document.addEventListener('DOMContentLoaded', async () => {
  // Initialize UI
  await loadState();
  setupEventListeners();
  updateUI();
  
  // Set minimum date to today
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('dateInput').min = today;
  document.getElementById('dateInput').value = today;
});

// Setup event listeners
function setupEventListeners() {
  document.getElementById('startBtn').addEventListener('click', startMonitoring);
  document.getElementById('stopBtn').addEventListener('click', stopMonitoring);
  document.getElementById('clearBtn').addEventListener('click', clearHistory);
  document.getElementById('settingsBtn').addEventListener('click', openSettings);
  document.getElementById('createTestSlotBtn').addEventListener('click', createTestSlot);
  document.getElementById('deleteTestSlotBtn').addEventListener('click', deleteTestSlot);
  
  // Show/hide language selector based on ticket type
  document.getElementById('ticketType').addEventListener('change', (e) => {
    const languageGroup = document.getElementById('languageGroup');
    languageGroup.style.display = e.target.value === 'guided' ? 'block' : 'none';
  });
  
  // Show/hide profile section based on auto-booking checkbox
  document.getElementById('autoBooking').addEventListener('change', (e) => {
    const profileSection = document.getElementById('profileSection');
    profileSection.style.display = e.target.checked ? 'block' : 'none';
  });
  
  // Show/hide backend config based on monitor mode
  document.getElementById('monitorMode').addEventListener('change', (e) => {
    const backendConfigSection = document.getElementById('backendConfigSection');
    backendConfigSection.style.display = e.target.value === 'backend' ? 'block' : 'none';
  });
  
  // Load saved profile
  loadProfile();
  
  // Load saved backend config
  loadBackendConfig();
}

// Start monitoring
async function startMonitoring() {
  const date = document.getElementById('dateInput').value;
  const visitors = parseInt(document.getElementById('visitorsInput').value);
  const ticketType = document.getElementById('ticketType').value;
  const language = document.getElementById('language').value;
  const checkInterval = parseInt(document.getElementById('checkInterval').value);
  const monitorMode = document.getElementById('monitorMode').value;
  const autoBooking = document.getElementById('autoBooking').checked;
  
  if (!date) {
    showNotification('Please select a date', 'error');
    return;
  }
  
  // If auto-booking enabled, validate profile
  if (autoBooking) {
    const profile = getProfile();
    if (!profile.firstName || !profile.lastName || !profile.email || !profile.phone) {
      showNotification('Please fill in all profile fields for auto-booking', 'error');
      return;
    }
    
    // Save profile
    await saveProfile(profile);
  }
  
  // Format date to DD/MM/YYYY
  const [year, month, day] = date.split('-');
  const formattedDate = `${day}/${month}/${year}`;
  
  const config = {
    date: formattedDate,
    visitors,
    ticketType: ticketType === 'standard' ? 0 : 1,
    language: ticketType === 'guided' ? language : null,
    checkInterval,
    monitorMode,
    autoBooking,
    profile: autoBooking ? getProfile() : null,
    isActive: true,
    startTime: Date.now()
  };
  
  // If backend listener mode, add backend config
  if (monitorMode === 'backend') {
    config.backendUrl = document.getElementById('backendUrl').value;
    config.apiKey = document.getElementById('apiKey').value;
    config.maxConcurrentBookings = parseInt(document.getElementById('maxConcurrentBookings').value);
    
    // Save backend config
    await saveBackendConfig({
      backendUrl: config.backendUrl,
      apiKey: config.apiKey,
      maxConcurrentBookings: config.maxConcurrentBookings
    });
    
    // Start backend listener
    chrome.runtime.sendMessage({ action: 'startBackendListener', config });
    
    showNotification('Backend listener started! Will open incognito windows when slots found.', 'success');
  } else {
    // Save config
    await chrome.storage.local.set({ monitorConfig: config });
    
    // Start background monitoring
    chrome.runtime.sendMessage({ action: 'startMonitoring', config });
    
    const mode = monitorMode === 'tab' ? 'with tab reload' : 'API-only';
    const booking = autoBooking ? ' + auto-booking' : '';
    showNotification(`Monitoring started ${mode}${booking}!`, 'success');
  }
  
  // Update UI
  document.getElementById('startBtn').disabled = true;
  document.getElementById('stopBtn').disabled = false;
  updateStatusBadge(true);
  updateMonitoringInfo(config);
}

// Get profile from form
function getProfile() {
  return {
    firstName: document.getElementById('firstName').value,
    lastName: document.getElementById('lastName').value,
    email: document.getElementById('email').value,
    phone: document.getElementById('phone').value,
    city: document.getElementById('city').value || 'Roma',
    autoConfirm: document.getElementById('autoConfirm').checked,
    birthDate: {
      year: '1990',
      month: 'GEN',
      day: '15'
    }
  };
}

// Save profile
async function saveProfile(profile) {
  await chrome.storage.local.set({ bookingProfile: profile });
}

// Load profile
async function loadProfile() {
  const data = await chrome.storage.local.get('bookingProfile');
  if (data.bookingProfile) {
    const p = data.bookingProfile;
    document.getElementById('firstName').value = p.firstName || '';
    document.getElementById('lastName').value = p.lastName || '';
    document.getElementById('email').value = p.email || '';
    document.getElementById('phone').value = p.phone || '';
    document.getElementById('city').value = p.city || 'Roma';
    document.getElementById('autoConfirm').checked = p.autoConfirm || false;
  }
}

// Stop monitoring
async function stopMonitoring() {
  await chrome.storage.local.set({ 
    monitorConfig: { isActive: false } 
  });
  
  chrome.runtime.sendMessage({ action: 'stopMonitoring' });
  
  document.getElementById('startBtn').disabled = false;
  document.getElementById('stopBtn').disabled = true;
  updateStatusBadge(false);
  
  showNotification('Monitoring stopped', 'info');
}

// Clear history
async function clearHistory() {
  if (confirm('Clear all monitoring history?')) {
    await chrome.storage.local.remove(['results', 'availableSlots']);
    document.getElementById('results').innerHTML = '<p class="no-data">No results yet</p>';
    document.getElementById('availableSlots').innerHTML = '<p class="no-data">No available slots found</p>';
    showNotification('History cleared', 'info');
  }
}

// Open settings
function openSettings() {
  chrome.tabs.create({ url: chrome.runtime.getURL('settings.html') });
}

// Load state from storage
async function loadState() {
  const data = await chrome.storage.local.get(['monitorConfig', 'results', 'availableSlots']);
  
  if (data.monitorConfig?.isActive) {
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    updateStatusBadge(true);
    updateMonitoringInfo(data.monitorConfig);
  }
  
  if (data.results?.length > 0) {
    displayResults(data.results);
  }
  
  if (data.availableSlots?.length > 0) {
    displayAvailableSlots(data.availableSlots);
  }
}

// Update UI
function updateUI() {
  // Listen for updates from background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.action === 'updateResults') {
      displayResults(message.results);
    } else if (message.action === 'updateSlots') {
      displayAvailableSlots(message.slots);
    } else if (message.action === 'monitoringStopped') {
      document.getElementById('startBtn').disabled = false;
      document.getElementById('stopBtn').disabled = true;
      updateStatusBadge(false);
    }
  });
}

// Update status badge
function updateStatusBadge(isActive) {
  const badge = document.getElementById('statusBadge');
  const statusText = badge.querySelector('.status-text');
  
  if (isActive) {
    badge.classList.add('active');
    statusText.textContent = 'Monitoring';
  } else {
    badge.classList.remove('active');
    statusText.textContent = 'Inactive';
  }
}

// Update monitoring info
function updateMonitoringInfo(config) {
  const infoBox = document.getElementById('monitoringInfo');
  const ticketTypeText = config.ticketType === 0 ? 'Standard Entry' : 'Guided Tour';
  const languageText = config.language ? ` (${config.language})` : '';
  
  infoBox.innerHTML = `
    <p><strong>Date:</strong> ${config.date}</p>
    <p><strong>Visitors:</strong> ${config.visitors}</p>
    <p><strong>Ticket:</strong> ${ticketTypeText}${languageText}</p>
    <p><strong>Check Interval:</strong> ${config.checkInterval} seconds</p>
    <p><strong>Started:</strong> ${new Date(config.startTime).toLocaleTimeString()}</p>
  `;
}

// Display results
function displayResults(results) {
  const container = document.getElementById('results');
  
  if (!results || results.length === 0) {
    container.innerHTML = '<p class="no-data">No results yet</p>';
    return;
  }
  
  // Show last 10 results
  const recentResults = results.slice(-10).reverse();
  
  container.innerHTML = recentResults.map(result => {
    const statusClass = result.available ? 'available' : 'sold-out';
    const statusText = result.available ? '✅ Available' : '❌ Sold Out';
    
    // Show slot count if available
    const slotInfo = result.slotsCount ? ` (${result.slotsCount} slots)` : '';
    
    // Show message if present
    const message = result.message ? `<div style="font-size: 11px; color: #666;">${result.message}</div>` : '';
    
    // Show source badge
    const sourceBadge = result.source === 'tab_reload' 
      ? '<span style="font-size: 10px; background: #2196f3; color: white; padding: 2px 6px; border-radius: 3px; margin-left: 5px;">Visual</span>'
      : '<span style="font-size: 10px; background: #9c27b0; color: white; padding: 2px 6px; border-radius: 3px; margin-left: 5px;">API</span>';
    
    return `
      <div class="result-item ${statusClass}">
        <div><strong>${statusText}${slotInfo}</strong>${sourceBadge}</div>
        <div>${result.date} - ${result.visitors} visitor(s)</div>
        ${message}
        <div class="result-time">${new Date(result.timestamp).toLocaleString()}</div>
      </div>
    `;
  }).join('');
}

// Display available slots
function displayAvailableSlots(slots) {
  const container = document.getElementById('availableSlots');
  
  if (!slots || slots.length === 0) {
    container.innerHTML = '<p class="no-data">No available slots found</p>';
    return;
  }
  
  container.innerHTML = slots.map(slot => `
    <div class="slot-item">
      <div>
        <div class="slot-time">🕐 ${slot.time}</div>
        <div style="font-size: 11px; color: #666;">${slot.date}</div>
      </div>
      <button class="slot-action" onclick="openBookingPage('${slot.date}', '${slot.time}', ${slot.visitors})">
        Book Now
      </button>
    </div>
  `).join('');
}

// Open booking page
window.openBookingPage = function(date, time, visitors) {
  const url = `https://tickets.museivaticani.va/home`;
  chrome.tabs.create({ url });
};

// Show notification
function showNotification(message, type = 'info') {
  // You can enhance this with a toast notification library
  console.log(`[${type.toUpperCase()}] ${message}`);
}

// Create test slot via backend API
async function createTestSlot() {
  const btn = document.getElementById('createTestSlotBtn');
  const testMessage = document.getElementById('testMessage');
  
  btn.disabled = true;
  btn.textContent = '🔍 Searching for real availability...';
  
  try {
    // Get backend config
    const { backendConfig } = await chrome.storage.local.get('backendConfig');
    
    if (!backendConfig || !backendConfig.backendUrl) {
      showTestMessage('❌ Backend URL not configured. Please enable Backend Listener Mode first.', 'error');
      btn.disabled = false;
      btn.textContent = '🧪 Create Test Slot';
      return;
    }
    
    const backendUrl = backendConfig.backendUrl || 'http://localhost:8000';
    const apiKey = backendConfig.apiKey || '';
    
    showTestMessage('🔍 Checking Vatican website for Vatican Museums tickets in the next 90 days...<br>This may take 20-30 seconds...', 'info');
    
    // Call backend API to create test slot (it will check real availability)
    const response = await fetch(`${backendUrl}/api/v1/test/create-slot/`, {
      method: 'POST',
      headers: {
        'Authorization': apiKey ? `Bearer ${apiKey}` : '',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        visitors: 1,
        ticket_type: 0,  // 0=standard entry, 1=guided tour
        language: null
      })
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      if (response.status === 404) {
        showTestMessage(
          `❌ ${data.error || 'No availability found'}<br>
          <br>
          ${data.message || 'Vatican Museums has no available slots in the next 90 days.'}<br>
          <br>
          <strong>What to do:</strong><br>
          • Try again in a few hours<br>
          • Check Vatican website manually<br>
          • Tickets usually open up 2-3 months in advance`,
          'error'
        );
      } else {
        throw new Error(`API returned ${response.status}`);
      }
      btn.disabled = false;
      btn.textContent = '🧪 Create Test Slot';
      return;
    }
    
    showTestMessage(
      `✅ Real available slot found and created!<br>
      <strong>Date:</strong> ${data.date}<br>
      <strong>Time:</strong> ${data.time}<br>
      <strong>Ticket:</strong> ${data.ticket_name}<br>
      <strong>Visitors:</strong> ${data.visitors}<br>
      <br>
      <strong>🎉 This is a REAL available slot from Vatican!</strong><br>
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
    const { backendConfig } = await chrome.storage.local.get('backendConfig');
    
    if (!backendConfig || !backendConfig.backendUrl) {
      showTestMessage('❌ Backend URL not configured. Please enable Backend Listener Mode first.', 'error');
      btn.disabled = false;
      btn.textContent = '🗑️ Delete Test';
      return;
    }
    
    const backendUrl = backendConfig.backendUrl || 'http://localhost:8000';
    const apiKey = backendConfig.apiKey || '';
    
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
    btn.textContent = '🗑️ Delete Test';
  }
}

// Show test message
function showTestMessage(message, type) {
  const testMessage = document.getElementById('testMessage');
  testMessage.innerHTML = message;
  testMessage.style.display = 'block';
  
  if (type === 'success') {
    testMessage.style.background = 'rgba(255,255,255,0.3)';
    testMessage.style.color = 'white';
    testMessage.style.borderLeft = '4px solid #28a745';
  } else if (type === 'error') {
    testMessage.style.background = 'rgba(255,255,255,0.2)';
    testMessage.style.color = 'white';
    testMessage.style.borderLeft = '4px solid #dc3545';
  } else if (type === 'info') {
    testMessage.style.background = 'rgba(255,255,255,0.2)';
    testMessage.style.color = 'white';
    testMessage.style.borderLeft = '4px solid #17a2b8';
  }
}


// Load backend config
async function loadBackendConfig() {
  const { backendConfig } = await chrome.storage.local.get('backendConfig');
  
  if (backendConfig) {
    document.getElementById('backendUrl').value = backendConfig.backendUrl || 'http://localhost:8000';
    document.getElementById('apiKey').value = backendConfig.apiKey || '';
    document.getElementById('maxConcurrentBookings').value = backendConfig.maxConcurrentBookings || 10;
  }
}

// Save backend config
async function saveBackendConfig(config) {
  await chrome.storage.local.set({ backendConfig: config });
}


// ============================================================================
// TIMING TRACKING - Show exact timing like Telegram
// ============================================================================

let timingUpdateInterval = null;

/**
 * Start timing display updates
 */
function startTimingDisplay() {
  // Clear any existing interval
  if (timingUpdateInterval) {
    clearInterval(timingUpdateInterval);
  }
  
  // Show timing info section
  document.getElementById('timingInfo').style.display = 'block';
  
  // Update immediately
  updateTimingDisplay();
  
  // Update every second
  timingUpdateInterval = setInterval(updateTimingDisplay, 1000);
}

/**
 * Stop timing display updates
 */
function stopTimingDisplay() {
  if (timingUpdateInterval) {
    clearInterval(timingUpdateInterval);
    timingUpdateInterval = null;
  }
  
  // Hide timing info section
  document.getElementById('timingInfo').style.display = 'none';
}

/**
 * Update timing display with current values
 */
async function updateTimingDisplay() {
  try {
    const { monitorConfig, monitoringStats } = await chrome.storage.local.get(['monitorConfig', 'monitoringStats']);
    
    if (!monitorConfig || !monitorConfig.isActive) {
      stopTimingDisplay();
      return;
    }
    
    const stats = monitoringStats || {
      startTime: monitorConfig.startTime || Date.now(),
      lastCheckTime: null,
      totalChecks: 0,
      checkInterval: monitorConfig.checkInterval || 10
    };
    
    // Format times
    const startTime = new Date(stats.startTime);
    const lastCheckTime = stats.lastCheckTime ? new Date(stats.lastCheckTime) : null;
    
    // Calculate next check time
    const nextCheckTime = lastCheckTime 
      ? new Date(lastCheckTime.getTime() + (stats.checkInterval * 1000))
      : new Date(Date.now() + (stats.checkInterval * 1000));
    
    // Calculate running duration
    const runningMs = Date.now() - stats.startTime;
    const runningDuration = formatDuration(runningMs);
    
    // Calculate time until next check
    const timeUntilNext = Math.max(0, Math.floor((nextCheckTime - Date.now()) / 1000));
    
    // Update display
    document.getElementById('startTime').textContent = formatTime(startTime);
    document.getElementById('lastCheckTime').textContent = lastCheckTime ? formatTime(lastCheckTime) : 'Not yet';
    document.getElementById('nextCheckTime').textContent = `${formatTime(nextCheckTime)} (in ${timeUntilNext}s)`;
    document.getElementById('totalChecks').textContent = stats.totalChecks;
    document.getElementById('checkIntervalDisplay').textContent = `${stats.checkInterval} seconds`;
    document.getElementById('runningDuration').textContent = runningDuration;
    
    // Update mode display
    const modeNames = {
      'backend': '🚀 Backend Listener',
      'tab': '🔍 Tab Reload',
      'api': '⚡ API Only'
    };
    document.getElementById('modeDisplay').textContent = modeNames[monitorConfig.monitorMode] || monitorConfig.monitorMode;
    
    // Update monitoring details
    document.getElementById('monitoringDate').textContent = monitorConfig.date;
    document.getElementById('monitoringVisitors').textContent = monitorConfig.visitors;
    
    const ticketTypeNames = {
      0: '🎫 Standard Entry',
      1: `🎫 Guided Tour (${monitorConfig.language || 'N/A'})`
    };
    document.getElementById('monitoringTicketType').textContent = ticketTypeNames[monitorConfig.ticketType] || 'Unknown';
    
  } catch (error) {
    console.error('Error updating timing display:', error);
  }
}

/**
 * Format time as HH:MM:SS
 */
function formatTime(date) {
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

/**
 * Format duration as "Xh Ym Zs" or "Ym Zs" or "Zs"
 */
function formatDuration(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  
  const s = seconds % 60;
  const m = minutes % 60;
  const h = hours;
  
  if (h > 0) {
    return `${h}h ${m}m ${s}s`;
  } else if (m > 0) {
    return `${m}m ${s}s`;
  } else {
    return `${s}s`;
  }
}

/**
 * Update monitoring stats (called from background script)
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'updateMonitoringStats') {
    chrome.storage.local.get('monitoringStats', (data) => {
      const stats = data.monitoringStats || {
        startTime: Date.now(),
        lastCheckTime: null,
        totalChecks: 0,
        checkInterval: 10
      };
      
      stats.lastCheckTime = Date.now();
      stats.totalChecks = (stats.totalChecks || 0) + 1;
      
      chrome.storage.local.set({ monitoringStats: stats });
      
      // Update display immediately
      updateTimingDisplay();
    });
  } else if (message.action === 'resetMonitoringStats') {
    chrome.storage.local.remove('monitoringStats');
    stopTimingDisplay();
  }
});

// Start timing display when popup opens if monitoring is active
chrome.storage.local.get('monitorConfig', (data) => {
  if (data.monitorConfig && data.monitorConfig.isActive) {
    startTimingDisplay();
  }
});
