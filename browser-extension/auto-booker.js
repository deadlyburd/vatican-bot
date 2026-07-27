// Auto-booker module - handles full Vatican booking flow
// This is loaded as a web_accessible_resource by content.js

console.log("[Vatican Auto-Booker] Module loaded");

// Expose booking functions to the page context
window.VaticanAutoBooker = {
    fillForm: function(profile, participants) {
        console.log("[Auto-Booker] Filling form with", profile);
        // Delegate to content script
        window.postMessage({
            type: VATICAN_AUTO_BOOK,
            action: fillForm,
            profile: profile,
            participants: participants
        }, *);
    },

    clickAcquista: function() {
        console.log("[Auto-Booker] Clicking ACQUISTA");
        window.postMessage({
            type: VATICAN_AUTO_BOOK,
            action: clickAcquista
        }, *);
    },

    solveTurnstile: function() {
        console.log("[Auto-Booker] Waiting for Turnstile auto-solve");
        window.postMessage({
            type: VATICAN_AUTO_BOOK,
            action: solveTurnstile
        }, *);
    },

    completeBooking: function() {
        console.log("[Auto-Booker] Completing booking");
        window.postMessage({
            type: VATICAN_AUTO_BOOK,
            action: completeBooking
        }, *);
    }
};

console.log("[Vatican Auto-Booker] Ready");
