// Vatican Ticket Monitor - Content Script
// Runs on Vatican website pages to enable auto-booking

console.log('Vatican Ticket Monitor - Content Script Loaded');

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'startAutoBooking') {
    console.log('Starting auto-booking flow...', message.config);
    startAutoBookingFlow(message.config);
    sendResponse({ success: true });
  } else if (message.action === 'startHoldMode') {
    console.log('Starting hold mode...', message.config);
    startHoldMode(message.config);
    sendResponse({ success: true });
  } else if (message.action === 'checkPageState') {
    const state = detectPageState();
    sendResponse({ state });
  } else if (message.action === 'checkAvailabilityOnPage') {
    console.log('Checking availability on current page...');
    checkAvailabilityOnPage();
    sendResponse({ success: true });
  }
  return true; // Keep message channel open for async response
});

// Check availability directly on the page (for tab reload mode)
async function checkAvailabilityOnPage() {
  try {
    // Wait for page to fully load
    await sleep(3000);
    
    // Check if we're on the ticket selection page
    const state = detectPageState();
    
    if (state !== 'ticket_selection') {
      console.log('Not on ticket selection page, state:', state);
      notifyProgress('Waiting for ticket page to load...', 'info');
      return;
    }
    
    // ✅ CHECK FOR RATE LIMITING: Look for error messages or captcha
    const errorMessages = document.body.textContent.toLowerCase();
    if (errorMessages.includes('too many requests') || 
        errorMessages.includes('rate limit') ||
        errorMessages.includes('troppo') ||
        document.querySelector('iframe[src*="captcha"]') ||
        document.querySelector('iframe[src*="turnstile"]')) {
      console.error('⚠️ RATE LIMITED or CAPTCHA detected!');
      notifyProgress('⚠️ Rate limited! Increase check interval to 30-60 seconds', 'error');
      
      chrome.runtime.sendMessage({
        action: 'rateLimited'
      });
      return;
    }
    
    // Wait for tickets to appear (with longer timeout)
    try {
      await waitForElement("[data-cy^='bookTicket_']", 15000);
    } catch (error) {
      console.error('❌ Timeout waiting for ticket buttons:', error.message);
      notifyProgress('⚠️ Page load timeout - possible rate limiting', 'error');
      
      // Check if page is blank or has error
      const hasContent = document.querySelectorAll('button, a, input').length > 5;
      if (!hasContent) {
        console.error('⚠️ Page appears blank - likely rate limited!');
        notifyProgress('⚠️ Rate limited! Stopping monitoring...', 'error');
        
        chrome.runtime.sendMessage({
          action: 'rateLimited'
        });
      }
      
      chrome.runtime.sendMessage({
        action: 'noTicketsOnPage'
      });
      return;
    }
    
    // Get all ticket buttons
    const ticketButtons = document.querySelectorAll("[data-cy^='bookTicket_']");
    console.log(`Found ${ticketButtons.length} ticket buttons on page`);
    
    // ✅ FILTER: Only check Vatican Museums standard tickets
    const EXCLUDED = ['pellegrinaggi', 'lunch', 'pranzo', 'gruppi', 'specola', 'palazzo', 'didattiche', 'scuole'];
    
    const vaticanTickets = [];
    
    ticketButtons.forEach(btn => {
      const isDisabled = btn.disabled || btn.classList.contains('disabled') || btn.hasAttribute('disabled');
      const text = btn.textContent.trim();
      const isPrenota = text === 'PRENOTA' || text === 'BOOK';
      
      // Get ticket name from parent card
      const card = btn.closest('[class*="card"], [class*="ticket"], [data-cy*="visit"]');
      let ticketName = 'Unknown';
      if (card) {
        const nameEl = card.querySelector('h3, h4, [class*="title"], [class*="name"]');
        if (nameEl) ticketName = nameEl.textContent.trim();
      }
      
      // ✅ FILTER: Only Vatican Museums standard tickets
      const ticketNameLower = ticketName.toLowerCase();
      const isVaticanMuseum = ticketNameLower.includes('musei vaticani') || ticketNameLower.includes('vatican museum');
      const isStandardTicket = ticketNameLower.includes('biglietti') || ticketNameLower.includes('ingresso') || ticketNameLower.includes('entrance');
      const isExcluded = EXCLUDED.some(ex => ticketNameLower.includes(ex));
      
      if (!isDisabled && isPrenota && isVaticanMuseum && isStandardTicket && !isExcluded) {
        vaticanTickets.push({
          button: btn,
          name: ticketName,
          element: card || btn.parentElement
        });
      }
    });
    
    console.log(`✅ Found ${vaticanTickets.length} Vatican Museums standard tickets with PRENOTA enabled`);
    
    if (vaticanTickets.length === 0) {
      notifyProgress('No Vatican Museums tickets available yet...', 'info');
      chrome.runtime.sendMessage({ action: 'noTicketsOnPage' });
      return;
    }
    
    // ✅ DEEP CHECK: Click first ticket and check actual time slots
    notifyProgress(`Checking time slots for ${vaticanTickets[0].name}...`, 'info');
    
    const firstTicket = vaticanTickets[0];
    
    // Scroll to ticket
    firstTicket.element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await sleep(500);
    
    // Click PRENOTA button
    firstTicket.button.click();
    console.log('Clicked PRENOTA button for:', firstTicket.name);
    
    // Wait for time slot selection page to load
    await sleep(3000);
    
    // Check for time slots
    const timeSlots = await checkTimeSlots();
    
    if (timeSlots.length > 0) {
      // ✅ TICKETS AVAILABLE!
      console.log(`✅ Found ${timeSlots.length} available time slots!`);
      
      // Highlight available slots
      timeSlots.forEach(slot => {
        if (slot.element) {
          slot.element.style.border = '3px solid #4caf50';
          slot.element.style.boxShadow = '0 0 20px rgba(76, 175, 80, 0.5)';
          slot.element.style.animation = 'pulse 2s infinite';
        }
      });
      
      // Show success message
      notifyProgress(`✅ ${timeSlots.length} time slot(s) available!`, 'success');
      
      // Notify background script
      chrome.runtime.sendMessage({
        action: 'ticketsFoundOnPage',
        count: timeSlots.length,
        slots: timeSlots.map(s => ({ time: s.time }))
      });
      
      // Get monitoring config to check if auto-booking is enabled
      chrome.storage.local.get('monitorConfig', async (data) => {
        if (data.monitorConfig?.autoBooking) {
          notifyProgress('Auto-booking enabled - selecting first slot...', 'info');
          await sleep(1000);
          
          // Click first available slot
          timeSlots[0].element.click();
          
          // Continue with booking flow
          const config = {
            date: data.monitorConfig.date,
            visitors: data.monitorConfig.visitors,
            ticketType: data.monitorConfig.ticketType,
            language: data.monitorConfig.language,
            preferredTime: timeSlots[0].time,
            profile: data.monitorConfig.profile,
            autoConfirm: data.monitorConfig.profile?.autoConfirm || false
          };
          
          await sleep(2000);
          await continueBookingFlow(config);
        } else {
          notifyProgress('⚠️ Time slots available! Select one to continue or enable auto-booking.', 'warning');
        }
      });
    } else {
      // No time slots available
      console.log('❌ No available time slots found');
      notifyProgress('No time slots available - going back...', 'info');
      
      // Go back to ticket selection
      window.history.back();
      await sleep(2000);
      
      // Notify background script
      chrome.runtime.sendMessage({ action: 'noTicketsOnPage' });
    }
    
  } catch (error) {
    console.error('Error checking availability on page:', error);
    notifyProgress(`Error: ${error.message}`, 'error');
    
    // Notify background script of error
    chrome.runtime.sendMessage({ action: 'noTicketsOnPage' });
    
    // Try to go back if we're stuck
    try {
      window.history.back();
    } catch (e) {
      console.log('Could not go back');
    }
  }
}

// Check for available time slots on the page
async function checkTimeSlots() {
  try {
    // Wait for time slots to appear
    await waitForElement("[data-cy='time']", 10000);
    
    const timeSlotElements = document.querySelectorAll("[data-cy='time']");
    console.log(`Found ${timeSlotElements.length} time slot elements`);
    
    const availableSlots = [];
    
    timeSlotElements.forEach(slotEl => {
      // Check if slot is clickable (not disabled)
      const isDisabled = slotEl.classList.contains('disabled') || 
                        slotEl.hasAttribute('disabled') ||
                        slotEl.style.pointerEvents === 'none' ||
                        slotEl.style.opacity === '0.5';
      
      // Get time text
      const timeText = slotEl.textContent.trim();
      
      // Check if it's a valid time format (HH:MM)
      const isValidTime = /\d{1,2}:\d{2}/.test(timeText);
      
      if (!isDisabled && isValidTime) {
        availableSlots.push({
          element: slotEl,
          time: timeText
        });
      }
    });
    
    console.log(`✅ Found ${availableSlots.length} available time slots`);
    return availableSlots;
    
  } catch (error) {
    console.error('Error checking time slots:', error);
    return [];
  }
}

// Detect current page state
function detectPageState() {
  const url = window.location.href;
  const path = window.location.pathname;
  
  if (path.includes('/home')) {
    // Check if we're on the ticket selection page
    const hasTickets = document.querySelectorAll("[data-cy^='bookTicket_']").length > 0;
    return hasTickets ? 'ticket_selection' : 'home';
  } else if (path.includes('/checkout')) {
    return 'checkout';
  } else if (path.includes('/payment')) {
    return 'payment';
  } else if (path.includes('/confirmation')) {
    return 'confirmation';
  }
  
  return 'unknown';
}

// Main auto-booking flow with realistic timing
async function startAutoBookingFlow(config) {
  try {
    console.log('🚀 Auto-booking started...');
    console.log('Auto-booking config:', config);
    
    // Notify user
    notifyProgress('🚀 Auto-booking started...', 'info');
    
    // ⏱️ Wait for page to fully load first
    notifyProgress('⏳ Loading Vatican website...', 'info');
    await sleep(randomDelay(4000, 6000));
    
    // Now detect page state after waiting
    const state = detectPageState();
    console.log('Current page state:', state);
    
    // Navigate to the correct entry point if needed
    if (state !== 'ticket_selection') {
      console.log('Not on ticket selection page, navigating...');
      await navigateToTicketPage(config);
      // Wait for navigation to complete
      await sleep(randomDelay(4000, 6000));
    }
    
    // Step 1: Select ticket
    notifyProgress('🎫 Step 1/10: Selecting ticket...', 'info');
    const ticketSelected = await selectTicket(config);
    if (!ticketSelected) {
      notifyProgress('❌ Failed to select ticket', 'error');
      return;
    }
    await sleep(randomDelay(1500, 2500)); // Human-like delay
    
    // Step 2: Select quantity
    notifyProgress('👥 Step 2/10: Setting quantity...', 'info');
    await selectQuantity(config.visitors || config.slot?.visitors || 1);
    await sleep(randomDelay(1000, 2000));
    
    // Step 3: Select time slot
    notifyProgress('⏰ Step 3/10: Selecting time slot...', 'info');
    const slotSelected = await selectTimeSlot(config.preferredTime || config.slot?.time);
    if (!slotSelected) {
      notifyProgress('❌ Exact time slot not available - booking cancelled', 'error');
      
      // Notify background script of failure
      chrome.runtime.sendMessage({
        action: 'bookingFailed',
        slotId: config.slot?.id,
        date: config.slot?.date,
        time: config.preferredTime || config.slot?.time,
        error: 'Exact time slot not available'
      });
      
      return;
    }
    
    // Verify time was selected by checking if PROCEDI button is enabled
    console.log('Verifying time slot selection...');
    await sleep(1000);
    
    const procediButton = document.querySelector("[data-cy='bookVisit']");
    if (procediButton && procediButton.disabled) {
      console.error('❌ PROCEDI button still disabled - time slot not selected properly');
      notifyProgress('❌ Time slot selection failed - retrying...', 'error');
      
      // Try one more time
      await sleep(1000);
      const retrySelected = await selectTimeSlot(config.preferredTime || config.slot?.time);
      if (!retrySelected) {
        notifyProgress('❌ Time slot selection failed after retry', 'error');
        return;
      }
    }
    
    await sleep(randomDelay(1500, 2500));
    
    // Step 4: Click PROCEDI
    notifyProgress('➡️ Step 4/10: Proceeding to checkout...', 'info');
    const procediClicked = await clickProcedi();
    
    if (!procediClicked) {
      console.error('❌ Failed to click PROCEDI button');
      notifyProgress('❌ Could not proceed to checkout', 'error');
      return;
    }
    
    console.log('Waiting for checkout page to load...');
    await sleep(randomDelay(4000, 6000)); // Wait for checkout page to load
    
    // Verify we're on checkout page
    const currentUrl = window.location.href;
    console.log('Current URL after PROCEDI:', currentUrl);
    
    // Check if we're on recap page (intermediate step before checkout)
    if (currentUrl.includes('recap')) {
      console.log('On recap page, clicking PROCEDI again to go to checkout...');
      await sleep(2000);
      await clickProcedi();
      await sleep(5000);
    } else if (!currentUrl.includes('checkout')) {
      console.error('❌ Not on checkout or recap page. Current URL:', currentUrl);
      notifyProgress('❌ Checkout page did not load', 'error');
      return; // Don't retry - something went wrong
    }
    
    // Step 5: Fill checkout form with participants
    notifyProgress('📝 Step 5/10: Filling form with participants...', 'info');
    const profile = config.profile || config.slot?.profile;
    const participants = config.participants || config.slot?.participants || [];
    const visitors = config.visitors || config.slot?.visitors || 1;
    
    if (!profile) {
      notifyProgress('❌ No profile data available', 'error');
      return;
    }
    
    await fillCheckoutFormWithParticipants(profile, participants, visitors);
    await sleep(randomDelay(2000, 3000));
    
    // Step 6: Handle Turnstile (if present)
    notifyProgress('🔐 Step 6/10: Solving Turnstile...', 'info');
    await waitForTurnstile();
    await sleep(randomDelay(1500, 2500));
    
    // ✅ AUTO-CONTINUE: Full automatic booking flow
    notifyProgress('✅ Form filled! Auto-continuing...', 'success');

    // Step 6: Click ACQUISTA button
    notifyProgress('💳 Step 6/10: Clicking ACQUISTA...', 'info');
    const buyClicked = await clickBuyButton();

    if (!buyClicked) {
      notifyProgress('⚠️ Could not click ACQUISTA - check page', 'warning');
      chrome.runtime.sendMessage({
        action: 'bookingPaused',
        message: 'ACQUISTA button not found - manual click needed',
        date: config.date, time: config.time
      }).catch(() => {});
      return;
    }

    await sleep(randomDelay(3000, 5000));

    // Step 7: Wait for recap/reservation response
    notifyProgress('⏳ Step 7/10: Waiting for reservation...', 'info');

    // Monitor network for recap/reservation response
    const reservationResult = await waitForReservationResponse(15000);

    if (!reservationResult) {
      notifyProgress('⚠️ No reservation response detected', 'warning');
      chrome.runtime.sendMessage({
        action: 'bookingPaused',
        message: 'Reservation pending - check page',
        date: config.date, time: config.time
      }).catch(() => {});
      return;
    }

    notifyProgress('✅ Reservation confirmed!', 'success');
    await sleep(randomDelay(2000, 3000));

    // Step 8: Wait for epay redirect or payment link
    notifyProgress('⏳ Step 8/10: Getting payment link...', 'info');
    const epayUrl = await waitForEpayRedirect(10000);

    if (epayUrl) {
      notifyProgress('✅ Payment page loaded!', 'success');

      // Extract payment link and notify
      chrome.runtime.sendMessage({
        action: 'bookingCompleted',
        date: config.date,
        time: config.time,
        epayUrl: epayUrl,
        slot: config.slot || config
      }).catch(() => {});

      notifyProgress('🎉 BOOKING COMPLETE! Payment link ready.', 'success');

    } else {
      // Check if we got a success page instead
      const currentUrl = window.location.href;
      if (currentUrl.includes('success') || currentUrl.includes('confirm') || currentUrl.includes('grazie')) {
        notifyProgress('🎉 Booking completed successfully!', 'success');
        chrome.runtime.sendMessage({
          action: 'bookingCompleted',
          date: config.date,
          time: config.time,
          epayUrl: currentUrl,
          slot: config.slot || config
        }).catch(() => {});
      } else {
        notifyProgress('⚠️ Payment page not loaded - check manually', 'warning');
      }
    }

  } catch (error) {
    console.error('Auto-booking error:', error);
    notifyProgress(`❌ Error: ${error.message}`, 'error');
    
    // Notify background script of failure
    chrome.runtime.sendMessage({
      action: 'bookingFailed',
      slotId: config.slot?.id,
      date: config.slot?.date,
      error: error.message
    });
  }
}

// Random delay helper for human-like timing
function randomDelay(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// Navigate to ticket selection page
async function navigateToTicketPage(config) {
  const [day, month, year] = config.date.split('/');
  const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), 0, 0, 0);
  
  // Calculate timestamp in Rome timezone (UTC+1 or UTC+2)
  const timestamp = date.getTime();
  
  const url = `https://tickets.museivaticani.va/home/fromtag/${config.visitors}/${timestamp}/MV-Biglietti/1`;
  console.log('Navigating to:', url);
  
  window.location.href = url;
  
  // Wait for navigation
  await sleep(3000);
}

// Select ticket by type
async function selectTicket(config) {
  // Wait for tickets to load
  await waitForElement("[data-cy^='bookTicket_']", 15000);
  
  // Use ticket_id from slot if available (passed from backend)
  let ticketId = config.slot?.ticket_id || config.ticketId;
  
  // If no ticket ID provided, get fresh ticket ID from Search API
  if (!ticketId) {
    ticketId = await resolveTicketId(config);
  }
  
  if (!ticketId) {
    console.error('Could not resolve ticket ID');
    return false;
  }
  
  console.log('Using ticket ID:', ticketId);
  console.log('Looking for ticket:', config.slot?.ticket_name || 'Unknown');
  
  // Try to click the ticket button
  const button = document.querySelector(`[data-cy='bookTicket_${ticketId}']`);
  
  if (button) {
    scrollIntoView(button);
    await sleep(500);
    button.click();
    console.log('✅ Clicked ticket button for:', config.slot?.ticket_name || ticketId);
    return true;
  }
  
  console.warn(`Ticket button not found for ID: ${ticketId}`);
  
  // Fallback: click first available PRENOTA button
  const allButtons = Array.from(document.querySelectorAll("[data-cy^='bookTicket_']"));
  const prenotaBtn = allButtons.find(btn => btn.textContent.trim() === 'PRENOTA');
  
  if (prenotaBtn) {
    scrollIntoView(prenotaBtn);
    await sleep(500);
    prenotaBtn.click();
    console.log('⚠️ Clicked fallback PRENOTA button (first available)');
    return true;
  }
  
  return false;
}

// Resolve ticket ID via Search API
async function resolveTicketId(config) {
  try {
    const url = new URL('https://tickets.museivaticani.va/api/search/resultPerTag');
    url.searchParams.set('lang', 'it');
    url.searchParams.set('visitorNum', config.visitors);
    url.searchParams.set('visitDate', config.date);
    url.searchParams.set('area', '1');
    url.searchParams.set('who', '');
    url.searchParams.set('page', '0');
    url.searchParams.set('tag', 'MV-Biglietti');
    
    const response = await fetch(url.toString());
    const data = await response.json();
    
    const EXCLUDED = ['pellegrinaggi', 'lunch', 'pranzo', 'gruppi', 'specola', 'palazzo', 'didattiche'];
    
    const ticket = data.visits.find(v =>
      v.name.toLowerCase().includes('musei vaticani') &&
      v.name.toLowerCase().includes('ingresso') &&
      !EXCLUDED.some(ex => v.name.toLowerCase().includes(ex)) &&
      v.availability === 'AVAILABLE'
    );
    
    return ticket ? ticket.id.toString() : null;
  } catch (error) {
    console.error('Error resolving ticket ID:', error);
    return null;
  }
}

// Select quantity
async function selectQuantity(visitors) {
  // Wait for quantity selector
  await sleep(1000);
  
  // Strategy 1: <select> dropdown
  const selects = document.querySelectorAll('select');
  for (const sel of selects) {
    const parent = sel.closest('[class*="quantity"], [id*="quantity"]') || sel.parentElement;
    if (parent || selects.length === 1) {
      sel.value = visitors.toString();
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      console.log('Set quantity via select:', visitors);
      return true;
    }
  }
  
  // Strategy 2: Custom dropdown
  const qtyDropdown = document.querySelector("[data-cy='ticketQuantity']");
  if (qtyDropdown) {
    scrollIntoView(qtyDropdown);
    qtyDropdown.click();
    await sleep(800);
    
    const items = document.querySelectorAll("[data-cy='ticketQuantitySection']");
    for (const item of items) {
      const text = item.textContent.trim();
      if (text === visitors.toString() || text.startsWith(visitors.toString() + ' ')) {
        scrollIntoView(item);
        item.click();
        console.log('Set quantity via custom dropdown:', visitors);
        return true;
      }
    }
  }
  
  console.log('Quantity selector not found or already set to', visitors);
  return true;
}

// Select time slot - STRICT MODE: Only select exact time specified
async function selectTimeSlot(preferredTime) {
  // Wait for time slots to load
  await waitForElement("[data-cy='time']", 15000);
  
  const slots = document.querySelectorAll("[data-cy='time']");
  console.log(`Found ${slots.length} time slots`);
  
  if (slots.length === 0) {
    console.error('❌ No time slots found on page');
    return false;
  }
  
  // ✅ STRICT MODE: Only select the EXACT time specified
  if (!preferredTime) {
    console.error('❌ No preferred time specified - cannot proceed');
    notifyProgress('❌ No time specified - booking cancelled', 'error');
    return false;
  }
  
  // Try to find EXACT preferred time
  for (const slot of slots) {
    const text = slot.textContent.trim();
    
    // Check if slot is disabled
    const isDisabled = slot.classList.contains('disabled') || 
                      slot.hasAttribute('disabled') ||
                      slot.style.pointerEvents === 'none' ||
                      slot.style.opacity === '0.5';
    
    if (isDisabled) {
      console.log(`⏭️ Skipping disabled slot: ${text}`);
      continue;
    }
    
    // Match exact time (e.g., "10:00" matches "10:00")
    if (text === preferredTime || text.includes(preferredTime)) {
      console.log(`🎯 Found matching time slot: ${text}`);
      
      // Scroll into view
      scrollIntoView(slot);
      await sleep(500);
      
      // Try multiple click methods to ensure it works
      console.log('Attempting to click time slot...');
      
      // Method 1: Focus first
      slot.focus();
      await sleep(200);
      
      // Method 2: Direct click
      slot.click();
      await sleep(300);
      
      // Method 3: Dispatch mouse event
      slot.dispatchEvent(new MouseEvent('click', { 
        bubbles: true, 
        cancelable: true, 
        view: window 
      }));
      await sleep(300);
      
      // Method 4: If it's a radio/checkbox, check it
      if (slot.type === 'radio' || slot.type === 'checkbox') {
        slot.checked = true;
        slot.dispatchEvent(new Event('change', { bubbles: true }));
      }
      
      console.log(`✅ Clicked time slot: ${preferredTime}`);
      notifyProgress(`✅ Selected time slot: ${preferredTime}`, 'success');
      
      // Wait a bit to ensure selection registers
      await sleep(1000);
      
      return true;
    }
  }
  
  // ❌ STRICT MODE: If exact time not found, FAIL (don't select alternative)
  console.error(`❌ Exact time "${preferredTime}" not found or not available`);
  notifyProgress(`❌ Time ${preferredTime} not available - booking cancelled`, 'error');
  
  // Log available times for debugging
  const availableTimes = Array.from(slots)
    .filter(s => !s.classList.contains('disabled'))
    .map(s => s.textContent.trim());
  console.log('Available times:', availableTimes);
  
  return false;
}

// Click PROCEDI button
let procediClickInProgress = false;

async function clickProcedi() {
  // Prevent double-clicking
  if (procediClickInProgress) {
    console.log('⚠️ PROCEDI click already in progress, skipping...');
    return false;
  }
  
  procediClickInProgress = true;
  
  try {
    await waitForElement("[data-cy='bookVisit']", 10000);
    
    const button = document.querySelector("[data-cy='bookVisit']") ||
      Array.from(document.querySelectorAll('button')).find(b => /PROCEDI/i.test(b.textContent));
    
    if (button) {
      scrollIntoView(button);
      await sleep(500);
      button.click();
      console.log('✅ Clicked PROCEDI');
      
      // Keep lock for 3 seconds to prevent immediate re-click
      await sleep(3000);
      return true;
    }
    
    return false;
  } finally {
    procediClickInProgress = false;
  }
}

// Fill checkout form
async function fillCheckoutForm(profile) {
  // Wait for form to load
  await waitForElement("[data-cy='managerSurname']", 30000);
  
  console.log('Filling form with profile:', profile);
  
  // Fill text fields
  await fillField("[data-cy='managerSurname']", profile.lastName);
  await fillField("[data-cy='managerName']", profile.firstName);
  await fillField("[data-cy='managerCity']", profile.city);
  await fillField("[data-cy='managerEmail']", profile.email);
  await fillField("[data-cy='managerConfirmEmail']", profile.email);
  
  // Fill phone (digit by digit for validation)
  await fillPhoneField("[data-cy='managerPhone']", profile.phone);
  await sleep(300);
  
  // Select gender
  const genderBtn = document.querySelector("[data-cy='managerSex']");
  if (genderBtn) {
    genderBtn.click();
    await sleep(300);
    const genderOption = document.querySelector("[data-cy='managerSexSection']");
    if (genderOption) genderOption.click();
    await sleep(300);
  }
  
  // Select country (Italia)
  const countryBtn = document.querySelector("[data-cy='managerCountry']");
  if (countryBtn) {
    countryBtn.click();
    await sleep(300);
    
    const searchInput = document.querySelector('#searchInput_country');
    if (searchInput) {
      searchInput.value = 'Ital';
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      await sleep(400);
    }
    
    const countryItems = document.querySelectorAll("[data-cy='managerCountrySection']");
    const italia = Array.from(countryItems).find(el => /^ital/i.test(el.textContent.trim()));
    if (italia) {
      italia.click();
    } else if (countryItems[0]) {
      countryItems[0].click();
    }
    await sleep(300);
  }
  
  // Birth date
  await fillBirthDate(profile.birthDate);
  
  console.log('Form filled successfully');
}

// Fill a text field
async function fillField(selector, value) {
  const el = document.querySelector(selector);
  if (!el) return;
  
  el.focus();
  el.value = '';
  el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new Event('blur', { bubbles: true }));
  
  await sleep(100);
}

// Fill phone field digit by digit
async function fillPhoneField(selector, phone) {
  const el = document.querySelector(selector);
  if (!el) return;
  
  // Remove + and any spaces from phone number
  const cleanPhone = phone.replace(/[\+\s]/g, '');
  
  el.focus();
  el.value = '';
  el.dispatchEvent(new Event('input', { bubbles: true }));
  
  for (const digit of cleanPhone) {
    el.value += digit;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(30);
  }
  
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new Event('blur', { bubbles: true }));
}

// Fill birth date
async function fillBirthDate(birthDate) {
  // birthDate format: { year: '1990', month: 'GEN', day: '15' }
  
  // Year
  const yearBtn = document.querySelector("[data-cy='managerBirthYear']");
  if (yearBtn) {
    yearBtn.click();
    await sleep(300);
    const yearOption = Array.from(document.querySelectorAll("[data-cy='managerBirthYearSection']"))
      .find(el => el.textContent.trim() === birthDate.year);
    if (yearOption) yearOption.click();
    await sleep(300);
  }
  
  // Month
  const monthBtn = document.querySelector("[data-cy='managerBirthMonth']");
  if (monthBtn) {
    monthBtn.click();
    await sleep(300);
    const monthOption = Array.from(document.querySelectorAll("[data-cy='managerBirthMonthSection']"))
      .find(el => el.textContent.trim() === birthDate.month);
    if (monthOption) monthOption.click();
    await sleep(300);
  }
  
  // Day
  const dayBtn = document.querySelector("[data-cy='managerBirthDay']");
  if (dayBtn) {
    dayBtn.click();
    await sleep(300);
    const dayOption = Array.from(document.querySelectorAll("[data-cy='managerBirthDaySection']"))
      .find(el => el.textContent.trim() === birthDate.day);
    if (dayOption) dayOption.click();
    await sleep(300);
  }
}

// Wait for Turnstile to complete
async function waitForTurnstile() {
  console.log('Waiting for Turnstile...');
  
  // Check if Turnstile iframe exists
  const turnstileIframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
  
  if (!turnstileIframe) {
    console.log('No Turnstile detected');
    return;
  }
  
  // Wait for Turnstile to complete (max 30 seconds)
  for (let i = 0; i < 60; i++) {
    // Check if BUY button is enabled (Turnstile solved)
    const buyButton = document.querySelector("[data-cy='buyButton']");
    if (buyButton && !buyButton.disabled) {
      console.log('Turnstile solved!');
      return;
    }
    
    await sleep(500);
  }
  
  console.log('Turnstile timeout - may need manual solving');
}

// Click BUY button
async function clickBuyButton() {
  console.log('🔍 Looking for BUY button...');
  
  const buyButton = document.querySelector("[data-cy='buyButton']") ||
    Array.from(document.querySelectorAll('button')).find(b => /ACQUISTA|BUY/i.test(b.textContent));
  
  console.log('🔍 BUY button found:', !!buyButton, 'Disabled:', buyButton?.disabled);
  
  if (buyButton && !buyButton.disabled) {
    scrollIntoView(buyButton);
    await sleep(500);
    buyButton.click();
    console.log('✅ Clicked BUY button (ACQUISTA)');
    return true;
  }
  
  console.log('❌ BUY button not found or disabled');
  return false;
}

// Utility functions
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForElement(selector, timeout = 10000) {
  const startTime = Date.now();
  
  while (Date.now() - startTime < timeout) {
    const element = document.querySelector(selector);
    if (element) {
      return element;
    }
    await sleep(100);
  }
  
  throw new Error(`Element ${selector} not found after ${timeout}ms`);
}

function scrollIntoView(element) {
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function notifyProgress(message, type) {
  console.log(`[${type.toUpperCase()}] ${message}`);
  
  // Send to background script for notification
  chrome.runtime.sendMessage({
    action: 'autoBookingProgress',
    message,
    type
  });
  
  // Show on page
  showToast(message, type);
}

function showToast(message, type) {
  // Remove existing toast
  const existing = document.getElementById('vatican-monitor-toast');
  if (existing) existing.remove();
  
  // Create toast
  const toast = document.createElement('div');
  toast.id = 'vatican-monitor-toast';
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: ${type === 'error' ? '#f44336' : type === 'success' ? '#4caf50' : type === 'warning' ? '#ff9800' : '#2196f3'};
    color: white;
    padding: 16px 24px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    z-index: 999999;
    font-family: Arial, sans-serif;
    font-size: 14px;
    max-width: 400px;
    animation: slideIn 0.3s ease-out;
  `;
  toast.textContent = message;
  
  document.body.appendChild(toast);
  
  // Auto-remove after 5 seconds
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease-out';
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from {
      transform: translateX(400px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
  
  @keyframes slideOut {
    from {
      transform: translateX(0);
      opacity: 1;
    }
    to {
      transform: translateX(400px);
      opacity: 0;
    }
  }
  
  @keyframes pulse {
    0%, 100% {
      box-shadow: 0 0 20px rgba(76, 175, 80, 0.5);
    }
    50% {
      box-shadow: 0 0 40px rgba(76, 175, 80, 0.8);
    }
  }
`;
document.head.appendChild(style);

// Continue booking flow after ticket selection
async function continueBookingFlow(config) {
  try {
    notifyProgress('Continuing booking flow...', 'info');
    
    // Wait for quantity selector
    await sleep(2000);
    
    // Select quantity
    await selectQuantity(config.visitors);
    await sleep(1500);
    
    // Select time slot
    const slotSelected = await selectTimeSlot(config.preferredTime);
    if (!slotSelected) {
      notifyProgress('❌ No available time slots', 'error');
      return;
    }
    
    await sleep(2000);
    
    // Click PROCEDI
    await clickProcedi();
    await sleep(5000);
    
    // Fill checkout form with participants
    await fillCheckoutFormWithParticipants(config.profile, config.participants, config.visitors);
    await sleep(2000);
    
    // Wait for Turnstile
    await waitForTurnstile();
    await sleep(2000);
    
    // Click BUY button if auto-confirm enabled
    if (config.autoConfirm) {
      await clickBuyButton();
      await sleep(3000);
      
      // Wait for epay redirect
      const epayUrl = await waitForEpayRedirect();
      
      if (epayUrl && config.card) {
        // Fill payment form
        await fillPaymentForm(config.card, config.profile);
        await sleep(2000);
        
        // Click PAY if auto-pay enabled
        if (config.autoPay) {
          await clickPayButton();
          notifyProgress('✅ Payment submitted!', 'success');
        } else {
          notifyProgress('⚠️ Card filled - review and click PAY manually', 'warning');
        }
      } else {
        notifyProgress('✅ Booking completed! Redirected to payment.', 'success');
      }
    } else {
      notifyProgress('⚠️ Ready to confirm - please review and click BUY manually', 'warning');
    }
    
  } catch (error) {
    console.error('Booking flow error:', error);
    notifyProgress(`❌ Error: ${error.message}`, 'error');
  }
}

// Fill checkout form with participants (full implementation)
async function fillCheckoutFormWithParticipants(profile, participants, visitors) {
  console.log('🔍 Waiting for checkout form to load...');
  console.log('📍 Current URL:', window.location.href);
  console.log('📋 Profile:', profile);
  console.log('👥 Participants:', participants);
  console.log('🎫 Visitors:', visitors);
  
  // Wait for form to load - try multiple selectors
  console.log('⏳ Attempting to detect form elements...');
  
  const formLoaded = await Promise.race([
    waitForElement("[data-cy='managerSurname']", 30000).then(() => 'managerSurname'),
    waitForElement("input[name='surname']", 30000).then(() => 'surname'),
    waitForElement("input[placeholder*='Cognome']", 30000).then(() => 'cognome'),
    waitForElement("form", 30000).then(() => 'form')
  ]).catch((err) => {
    console.error('❌ Form detection failed:', err.message);
    console.log('📄 Current page title:', document.title);
    console.log('🔗 Current URL:', window.location.href);
    console.log('📝 Page HTML preview:', document.body.innerHTML.substring(0, 1000));
    return null;
  });
  
  if (!formLoaded) {
    console.error('❌ Checkout form did not load');
    throw new Error('Checkout form not found');
  }
  
  console.log(`✅ Form loaded (detected via: ${formLoaded})`);
  console.log('📝 Starting form fill...');
  
  // Fill representative (manager) fields
  await fillField("[data-cy='managerSurname']", profile.last_name || profile.lastName);
  await fillField("[data-cy='managerName']", profile.first_name || profile.firstName);
  await fillField("[data-cy='managerCity']", profile.city);
  await fillField("[data-cy='managerEmail']", profile.email);
  await fillField("[data-cy='managerConfirmEmail']", profile.email);
  
  // Fill phone (digit by digit for validation)
  await fillPhoneField("[data-cy='managerPhone']", profile.phone);
  await sleep(300);
  
  // Select gender
  const genderBtn = document.querySelector("[data-cy='managerSex']");
  if (genderBtn) {
    genderBtn.click();
    await sleep(300);
    const genderOption = document.querySelector("[data-cy='managerSexSection']");
    if (genderOption) genderOption.click();
    await sleep(300);
  }
  
  // Select country
  const countryBtn = document.querySelector("[data-cy='managerCountry']");
  if (countryBtn) {
    countryBtn.click();
    await sleep(300);
    
    const searchInput = document.querySelector('#searchInput_country');
    if (searchInput) {
      searchInput.value = 'Ital';
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      await sleep(400);
    }
    
    const countryItems = document.querySelectorAll("[data-cy='managerCountrySection']");
    const italia = Array.from(countryItems).find(el => /^ital/i.test(el.textContent.trim()));
    if (italia) {
      italia.click();
    } else if (countryItems[0]) {
      countryItems[0].click();
    }
    await sleep(300);
  }
  
  // Birth date
  if (profile.birth_date || profile.birthDate) {
    await fillBirthDateFromISO(profile.birth_date || profile.birthDate);
  }
  
  // Language
  const langBtn = document.querySelector("[data-cy='managerLanguage']");
  if (langBtn) {
    langBtn.click();
    await sleep(300);
    const langOption = document.querySelector("[data-cy='managerLanguageSection']");
    if (langOption) langOption.click();
    await sleep(300);
  }
  
  // Fill participants
  for (let i = 0; i < visitors; i++) {
    const participant = participants[i] || participants[0] || profile;
    
    // Expand participant section if not first
    if (i > 0) {
      const expandBtn = document.querySelector(`#participantElement_${i} div.tw-flex-grow > div`);
      if (expandBtn) {
        expandBtn.click();
        await sleep(500);
      }
    }
    
    // Fill participant name
    const firstName = participant.first_name || participant.firstName || profile.first_name || profile.firstName;
    const lastName = participant.last_name || participant.lastName || profile.last_name || profile.lastName;
    
    await fillField(`#participantSurname_${i}`, lastName);
    await fillField(`#participantName_${i}`, firstName);
  }
  
  // Check GDPR checkboxes
  await sleep(500);
  
  console.log('📋 Clicking checkboxes...');
  
  // First checkbox (terms) - ID: mat-mdc-checkbox-1-input
  const cb0 = document.querySelector('#mat-mdc-checkbox-1-input');
  console.log('🔍 First checkbox found:', !!cb0, 'Checked:', cb0?.checked);
  
  if (cb0 && !cb0.checked) {
    console.log('✅ Clicking first checkbox (terms)...');
    cb0.click();
    await sleep(1500);
    
    // Close modal if it appears
    const closeBtn = document.querySelector("[data-cy='purchase-rules-close-btn']");
    if (closeBtn) {
      console.log('✅ Closing terms modal...');
      closeBtn.click();
      await sleep(1000);
    } else {
      console.log('ℹ️ No modal to close');
    }
  } else {
    console.log('ℹ️ First checkbox already checked or not found');
  }
  
  // Second checkbox (privacy) - ID: mat-mdc-checkbox-4-input
  const cb1 = document.querySelector('#mat-mdc-checkbox-4-input');
  console.log('🔍 Second checkbox found:', !!cb1, 'Checked:', cb1?.checked);
  
  if (cb1 && !cb1.checked) {
    console.log('✅ Clicking second checkbox (privacy)...');
    cb1.click();
    await sleep(500);
  } else {
    console.log('ℹ️ Second checkbox already checked or not found');
  }
  
  console.log('✅ Checkboxes processed');
  
  console.log('Form filled successfully with participants');
}

// Fill birth date from ISO format (YYYY-MM-DD or ISO datetime)
async function fillBirthDateFromISO(birthDateISO) {
  try {
    // Parse ISO date
    const date = new Date(birthDateISO);
    const year = date.getFullYear().toString();
    const monthNames = ['GEN', 'FEB', 'MAR', 'APR', 'MAG', 'GIU', 'LUG', 'AGO', 'SET', 'OTT', 'NOV', 'DIC'];
    const month = monthNames[date.getMonth()];
    const day = date.getDate().toString();
    
    console.log(`Setting birth date: ${day}/${month}/${year}`);
    
    // Try direct input first
    const dateInput = document.querySelector("[data-cy='dateCalendar']");
    if (dateInput) {
      const monthNum = (date.getMonth() + 1).toString().padStart(2, '0');
      const dayNum = day.padStart(2, '0');
      const displayDate = `${dayNum}/${monthNum}/${year}`;
      
      dateInput.removeAttribute('readonly');
      dateInput.focus();
      dateInput.value = displayDate;
      dateInput.dispatchEvent(new Event('input', { bubbles: true }));
      dateInput.dispatchEvent(new Event('change', { bubbles: true }));
      dateInput.setAttribute('readonly', 'true');
      
      await sleep(500);
      
      // Check if it worked
      if (dateInput.value === displayDate) {
        console.log('Birth date set via direct input');
        return;
      }
    }
    
    // Fallback: use calendar picker
    console.log('Using calendar picker for birth date');
    
    // Open calendar
    const calendarBtn = document.querySelector("mat-datepicker-toggle button[aria-label='Open calendar']");
    if (calendarBtn) calendarBtn.click();
    await sleep(1000);
    
    // Navigate to multi-year view
    for (let i = 0; i < 2; i++) {
      const periodBtn = document.querySelector('button.mat-calendar-period-button');
      if (periodBtn) {
        periodBtn.click();
        await sleep(500);
      }
    }
    
    // Find and click year
    for (let i = 0; i < 30; i++) {
      const cells = Array.from(document.querySelectorAll('.mat-calendar-body-cell'));
      const yearCell = cells.find(c => c.textContent.trim() === year);
      if (yearCell) {
        yearCell.click();
        await sleep(500);
        break;
      }
      const prevBtn = document.querySelector('.mat-calendar-previous-button');
      if (prevBtn) prevBtn.click();
      await sleep(300);
    }
    
    // Select month
    const monthCells = Array.from(document.querySelectorAll('.mat-calendar-body-cell'));
    const monthCell = monthCells.find(c => c.textContent.trim().toUpperCase() === month);
    if (monthCell) {
      monthCell.click();
      await sleep(500);
    }
    
    // Select day
    const dayCells = Array.from(document.querySelectorAll('span.mat-calendar-body-cell-content'));
    const dayCell = dayCells.find(c => c.textContent.trim() === day);
    if (dayCell) {
      dayCell.click();
      await sleep(400);
    }
    
    console.log('Birth date set via calendar picker');
    
  } catch (error) {
    console.error('Error setting birth date:', error);
  }
}

// Wait for epay redirect
async function waitForEpayRedirect(timeout = 60000) {
  console.log('⏳ Waiting for epay redirect...');
  const startTime = Date.now();
  
  while (Date.now() - startTime < timeout) {
    const currentUrl = window.location.href;
    
    if (currentUrl.includes('epay')) {
      console.log('✅ Redirected to epay:', currentUrl);
      
      // Send payment link to background script
      chrome.runtime.sendMessage({
        action: 'paymentLinkReady',
        url: currentUrl
      }).catch(err => console.log('Could not send payment link:', err.message));
      
      return currentUrl;
    }
    
    // Check for error page
    if (currentUrl.includes('error') || currentUrl.includes('errore')) {
      console.error('❌ Vatican error page detected:', currentUrl);
      return null;
    }
    
    await sleep(500);
  }
  
  console.log('❌ Timeout waiting for epay redirect');
  console.log('📍 Final URL:', window.location.href);
  return null;
}

// Wait for reservation response after clicking ACQUISTA
async function waitForReservationResponse(timeout = 15000) {
  console.log('⏳ Waiting for reservation response...');
  const startTime = Date.now();

  return new Promise((resolve) => {
    // Method 1: Intercept XHR/fetch responses
    const originalFetch = window.fetch;
    let resolved = false;

    window.fetch = async function(...args) {
      const response = await originalFetch.apply(this, args);
      const url = args[0]?.url || '';

      if (!resolved && (url.includes('/api/visit/reservation') || url.includes('/api/visit/recap'))) {
        try {
          const clone = response.clone();
          const data = await clone.json();
          console.log('📡 Reservation API response:', data);

          if (response.status === 200) {
            resolved = true;
            window.fetch = originalFetch; // Restore
            resolve(data);
          }
        } catch (e) {
          console.log('Could not parse reservation response');
        }
      }
      return response;
    };

    // Method 2: Check URL changes
    const urlCheckInterval = setInterval(() => {
      if (resolved) {
        clearInterval(urlCheckInterval);
        return;
      }

      const currentUrl = window.location.href;
      if (currentUrl.includes('/payment') || currentUrl.includes('/epay') ||
          currentUrl.includes('/thankyou') || currentUrl.includes('/confirmation') ||
          currentUrl.includes('success')) {
        resolved = true;
        clearInterval(urlCheckInterval);
        window.fetch = originalFetch;
        resolve({ redirectUrl: currentUrl, success: true });
      }
    }, 500);

    // Method 3: Look for success messages on page
    const domObserver = new MutationObserver(() => {
      if (resolved) {
        domObserver.disconnect();
        return;
      }

      const body = document.body?.textContent?.toLowerCase() || '';
      if (body.includes('grazie') || body.includes('thank you') ||
          body.includes('conferma') || body.includes('confirmed')) {
        resolved = true;
        domObserver.disconnect();
        window.fetch = originalFetch;
        resolve({ success: true, source: 'dom' });
      }
    });

    try {
      domObserver.observe(document.body, { childList: true, subtree: true });
    } catch(e) {}

    // Timeout
    setTimeout(() => {
      if (!resolved) {
        clearInterval(urlCheckInterval);
        domObserver.disconnect();
        window.fetch = originalFetch;
        console.log('⏰ Reservation response timeout');
        // Even on timeout, check URL
        const currentUrl = window.location.href;
        if (currentUrl.includes('/payment') || currentUrl.includes('/epay')) {
          resolve({ redirectUrl: currentUrl, success: true });
        } else {
          resolve(null);
        }
      }
    }, timeout);
  });
}

// Fill payment form on epay page
async function fillPaymentForm(card, profile) {
  console.log('Filling payment form...');
  
  // Wait for epay page to load
  await sleep(3000);
  
  // Fill name fields
  const cardNames = card.holder.split(' ');
  const firstName = cardNames[0] || '';
  const lastName = cardNames.slice(1).join(' ') || firstName;
  
  await fillField('#name', firstName);
  await fillField('#surname', lastName);
  await fillField('#email', profile.email);
  await fillField('#repeatEmail', profile.email);
  await sleep(300);
  
  console.log('Name and email filled');
  
  // Fill card number (Datatrans iframe)
  console.log('Filling card number...');
  try {
    const cardIframe = document.querySelector('iframe[name*="cardNumber"], iframe[id*="cardNumber"]');
    if (cardIframe) {
      cardIframe.click();
      await sleep(500);
      
      // Type card number digit by digit
      for (const digit of card.number) {
        const event = new KeyboardEvent('keydown', { key: digit, bubbles: true });
        cardIframe.dispatchEvent(event);
        await sleep(50);
      }
      
      await sleep(300);
      console.log('Card number filled');
    }
  } catch (error) {
    console.error('Error filling card number:', error);
  }
  
  // Fill CVV (Datatrans iframe)
  console.log('Filling CVV...');
  try {
    const cvvIframe = document.querySelector('iframe[name*="cvv"], iframe[id*="cvv"]');
    if (cvvIframe) {
      cvvIframe.click();
      await sleep(500);
      
      // Type CVV digit by digit
      for (const digit of card.cvv) {
        const event = new KeyboardEvent('keydown', { key: digit, bubbles: true });
        cvvIframe.dispatchEvent(event);
        await sleep(50);
      }
      
      // Tab out
      const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true });
      cvvIframe.dispatchEvent(tabEvent);
      await sleep(300);
      console.log('CVV filled');
    }
  } catch (error) {
    console.error('Error filling CVV:', error);
  }
  
  // Fill expiry date
  const [expMonth, expYear] = card.expiry.split('/');
  const fullYear = expYear.length === 2 ? '20' + expYear : expYear;
  
  console.log(`Setting expiry: ${expMonth}/${fullYear}`);
  
  // Month dropdown
  const dropdowns = document.querySelectorAll('app-dropdown');
  if (dropdowns[0]) {
    dropdowns[0].querySelector('.select__box--selectedValue').click();
    await sleep(400);
    
    const monthItems = Array.from(document.querySelectorAll('.select__list--item span'));
    const monthItem = monthItems.find(el => el.textContent.trim() === expMonth.padStart(2, '0'));
    if (monthItem) monthItem.click();
    await sleep(300);
  }
  
  // Year dropdown
  if (dropdowns[1]) {
    dropdowns[1].querySelector('.select__box--selectedValue').click();
    await sleep(400);
    
    const yearItems = Array.from(document.querySelectorAll('.select__list--item span'));
    const yearItem = yearItems.find(el => el.textContent.trim() === fullYear);
    if (yearItem) yearItem.click();
    await sleep(300);
  }
  
  console.log('Expiry date set');
  
  // Check agreement checkbox
  const agreementCheckbox = document.querySelector('#mat-checkbox-1-input');
  if (agreementCheckbox && !agreementCheckbox.checked) {
    agreementCheckbox.click();
    await sleep(300);
  }
  
  console.log('Payment form filled');
}

// Click PAY button on epay page
async function clickPayButton() {
  console.log('Clicking PAY button...');
  
  // Blur any focused element
  document.body.click();
  if (document.activeElement) {
    document.activeElement.blur();
  }
  await sleep(500);
  
  // Find and click PAY button
  const payButton = document.querySelector("button#form-submit[type='submit'].btn-submit") ||
    Array.from(document.querySelectorAll("button[type='submit']"))
      .find(b => b.textContent.includes('Paga') && !b.disabled);
  
  if (payButton && !payButton.disabled) {
    scrollIntoView(payButton);
    payButton.focus();
    payButton.click();
    console.log('PAY button clicked');
    return true;
  }
  
  console.log('PAY button not found or disabled');
  return false;
}


// ============================================================================
// HOLD MODE - Keep slot alive by refreshing checkout page every 4 minutes
// ============================================================================

let holdModeInterval = null;
let holdModeActive = false;

/**
 * Start hold mode - keeps the slot alive by refreshing the checkout page
 * Vatican holds slots for ~55 minutes, but we refresh every 4 minutes to be safe
 */
async function startHoldMode(config) {
  try {
    console.log('🔒 Starting HOLD MODE...', config);
    notifyProgress('🔒 HOLD MODE: Keeping slot alive...', 'info');
    
    holdModeActive = true;
    
    // Store config in chrome.storage for persistence
    await chrome.storage.local.set({ 
      holdModeConfig: config,
      holdModeActive: true,
      holdModeStartTime: Date.now()
    });
    
    // Navigate to checkout page if not already there
    const state = detectPageState();
    if (state !== 'checkout') {
      await navigateToCheckoutPage(config);
    }
    
    // Fill form once at the start
    await fillCheckoutFormForHold(config);
    
    // Set up refresh interval (4 minutes = 240000ms)
    const REFRESH_INTERVAL = 4 * 60 * 1000; // 4 minutes
    
    holdModeInterval = setInterval(async () => {
      if (!holdModeActive) {
        clearInterval(holdModeInterval);
        return;
      }
      
      try {
        console.log('🔄 HOLD MODE: Refreshing checkout page...');
        notifyProgress('🔄 Refreshing to keep slot alive...', 'info');
        
        // Reload the page
        window.location.reload();
        
        // Wait for page to load
        await sleep(5000);
        
        // Re-fill the form
        await fillCheckoutFormForHold(config);
        
        // Calculate time held
        const { holdModeStartTime } = await chrome.storage.local.get('holdModeStartTime');
        const minutesHeld = Math.floor((Date.now() - holdModeStartTime) / 60000);
        
        notifyProgress(`✅ Slot held for ${minutesHeld} minutes`, 'success');
        
      } catch (error) {
        console.error('Hold mode refresh error:', error);
        notifyProgress(`⚠️ Hold refresh error: ${error.message}`, 'warning');
      }
    }, REFRESH_INTERVAL);
    
    // Show hold mode status
    showHoldModeStatus(config);
    
    console.log(`✅ HOLD MODE active - refreshing every 4 minutes`);
    
  } catch (error) {
    console.error('Hold mode error:', error);
    notifyProgress(`❌ Hold mode error: ${error.message}`, 'error');
  }
}

/**
 * Stop hold mode
 */
async function stopHoldMode() {
  console.log('🛑 Stopping HOLD MODE...');
  
  holdModeActive = false;
  
  if (holdModeInterval) {
    clearInterval(holdModeInterval);
    holdModeInterval = null;
  }
  
  await chrome.storage.local.remove(['holdModeConfig', 'holdModeActive', 'holdModeStartTime']);
  
  // Remove status display
  const statusEl = document.getElementById('hold-mode-status');
  if (statusEl) statusEl.remove();
  
  notifyProgress('🛑 Hold mode stopped', 'info');
}

/**
 * Navigate to checkout page for hold mode
 */
async function navigateToCheckoutPage(config) {
  const slot = config.slot || config;
  const [day, month, year] = slot.date.split('/');
  const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), 0, 0, 0);
  const timestamp = date.getTime();
  
  const url = `https://tickets.museivaticani.va/home/fromtag/${slot.visitors}/${timestamp}/MV-Biglietti/1`;
  console.log('Navigating to checkout:', url);
  
  window.location.href = url;
  await sleep(5000);
  
  // Select ticket and proceed to checkout
  await selectTicket(config);
  await sleep(2000);
  await selectQuantity(slot.visitors);
  await sleep(1500);
  await selectTimeSlot(slot.time);
  await sleep(2000);
  await clickProcedi();
  await sleep(5000);
}

/**
 * Fill checkout form for hold mode (without submitting)
 */
async function fillCheckoutFormForHold(config) {
  try {
    const profile = config.profile || config.slot?.profile;
    const participants = config.participants || config.slot?.participants || [];
    const visitors = config.visitors || config.slot?.visitors || 1;
    
    if (!profile) {
      console.warn('No profile data for hold mode');
      return;
    }
    
    // Wait for form to load
    await waitForElement("[data-cy='managerSurname']", 30000);
    
    // Fill the form
    await fillCheckoutFormWithParticipants(profile, participants, visitors);
    
    console.log('✅ Checkout form filled for hold mode');
    
  } catch (error) {
    console.error('Error filling form for hold mode:', error);
  }
}

/**
 * Show hold mode status overlay
 */
function showHoldModeStatus(config) {
  // Remove existing status if any
  const existing = document.getElementById('hold-mode-status');
  if (existing) existing.remove();
  
  const slot = config.slot || config;
  
  // Create status overlay
  const statusDiv = document.createElement('div');
  statusDiv.id = 'hold-mode-status';
  statusDiv.style.cssText = `
    position: fixed;
    top: 80px;
    right: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    z-index: 999998;
    font-family: Arial, sans-serif;
    font-size: 14px;
    min-width: 300px;
    max-width: 400px;
  `;
  
  statusDiv.innerHTML = `
    <div style="display: flex; align-items: center; margin-bottom: 12px;">
      <div style="font-size: 24px; margin-right: 10px;">🔒</div>
      <div style="font-size: 18px; font-weight: bold;">HOLD MODE ACTIVE</div>
    </div>
    <div style="margin-bottom: 8px; padding: 10px; background: rgba(255,255,255,0.2); border-radius: 6px;">
      <div style="margin-bottom: 4px;">📅 <strong>Date:</strong> ${slot.date}</div>
      <div style="margin-bottom: 4px;">⏰ <strong>Time:</strong> ${slot.time}</div>
      <div style="margin-bottom: 4px;">👥 <strong>Visitors:</strong> ${slot.visitors}</div>
      <div style="margin-bottom: 4px;">🎫 <strong>Ticket:</strong> ${slot.ticket_name || 'Vatican Museums'}</div>
    </div>
    <div style="margin-bottom: 12px; font-size: 12px; opacity: 0.9;">
      🔄 Auto-refreshing every 4 minutes to keep slot alive
    </div>
    <div style="display: flex; gap: 8px;">
      <button id="hold-mode-complete" style="
        flex: 1;
        background: #4caf50;
        color: white;
        border: none;
        padding: 10px;
        border-radius: 6px;
        cursor: pointer;
        font-weight: bold;
        font-size: 13px;
      ">✅ Complete Booking</button>
      <button id="hold-mode-stop" style="
        flex: 1;
        background: #f44336;
        color: white;
        border: none;
        padding: 10px;
        border-radius: 6px;
        cursor: pointer;
        font-weight: bold;
        font-size: 13px;
      ">🛑 Stop Hold</button>
    </div>
    <div id="hold-timer" style="margin-top: 12px; text-align: center; font-size: 12px; opacity: 0.8;">
      Held for: <span id="hold-duration">0</span> minutes
    </div>
  `;
  
  document.body.appendChild(statusDiv);
  
  // Add button handlers
  document.getElementById('hold-mode-complete').addEventListener('click', async () => {
    notifyProgress('▶️ Completing booking...', 'info');
    await stopHoldMode();
    
    // Continue with booking flow
    await waitForTurnstile();
    await sleep(2000);
    await clickBuyButton();
    
    // Continue to payment
    const epayUrl = await waitForEpayRedirect();
    if (epayUrl && config.card) {
      await fillPaymentForm(config.card, config.profile);
      if (config.autoPay) {
        await clickPayButton();
      }
    }
  });
  
  document.getElementById('hold-mode-stop').addEventListener('click', async () => {
    await stopHoldMode();
  });
  
  // Update timer every minute
  setInterval(async () => {
    const { holdModeStartTime } = await chrome.storage.local.get('holdModeStartTime');
    if (holdModeStartTime) {
      const minutes = Math.floor((Date.now() - holdModeStartTime) / 60000);
      const durationEl = document.getElementById('hold-duration');
      if (durationEl) {
        durationEl.textContent = minutes;
        
        // Warn if approaching 50 minutes (Vatican hold expires at ~55 min)
        if (minutes >= 50) {
          durationEl.style.color = '#ff5252';
          durationEl.style.fontWeight = 'bold';
        }
      }
    }
  }, 60000); // Update every minute
}

// Check if hold mode was active before page reload
chrome.storage.local.get(['holdModeActive', 'holdModeConfig'], async (data) => {
  if (data.holdModeActive && data.holdModeConfig) {
    console.log('🔄 Resuming hold mode after page reload...');
    
    // Wait for page to load
    await sleep(3000);
    
    // Re-fill form
    await fillCheckoutFormForHold(data.holdModeConfig);
    
    // Show status
    showHoldModeStatus(data.holdModeConfig);
    
    // Restart interval
    holdModeActive = true;
    const REFRESH_INTERVAL = 4 * 60 * 1000;
    
    holdModeInterval = setInterval(async () => {
      if (!holdModeActive) {
        clearInterval(holdModeInterval);
        return;
      }
      
      console.log('🔄 HOLD MODE: Refreshing checkout page...');
      window.location.reload();
    }, REFRESH_INTERVAL);
  }
});
