# 🚀 Quick Start Guide

Get started with Vatican Ticket Monitor in 5 minutes!

## Installation (2 minutes)

### Step 1: Create Icons
1. Open `create-icons.html` in your browser
2. Right-click each canvas → "Save image as..."
3. Save as `icon16.png`, `icon48.png`, `icon128.png`
4. Create `icons/` folder and move PNG files there

### Step 2: Load Extension
**Chrome/Edge:**
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `browser-extension` folder

**Firefox:**
1. Go to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `manifest.json` from `browser-extension` folder

## First Use (3 minutes)

### 1. Open the Extension
Click the Vatican Ticket Monitor icon in your toolbar

### 2. Configure Monitoring
```
Date:           [Select your desired date]
Visitors:       [1-20]
Ticket Type:    Standard Entry (or Guided Tour)
Check Interval: 5 seconds (recommended)
```

### 3. Start Monitoring
Click **"Start Monitoring"** button

### 4. Wait for Results
- Status badge turns green ✅
- Results appear in "Recent Results"
- Available slots show in "Available Slots"
- Desktop notification when tickets found 🔔

## What Happens Next?

### When Tickets Are Available
1. **Desktop Notification** - "Vatican Tickets Available! 🎉"
2. **Popup Updates** - Available slots listed with times
3. **Book Now Button** - Click to open Vatican booking page

### While Monitoring
- Extension checks every X seconds (your interval)
- Results logged in "Recent Results"
- Browser must stay open
- Can minimize browser window

## Example Scenarios

### Scenario 1: Looking for Tomorrow's Tickets
```
Date: [Tomorrow's date]
Visitors: 2
Ticket Type: Standard Entry
Interval: 5 seconds
```
**Result:** Notified within 5-10 seconds when tickets available

### Scenario 2: Planning Ahead (Guided Tour)
```
Date: [Date 2 weeks from now]
Visitors: 4
Ticket Type: Guided Tour
Language: English
Interval: 30 seconds
```
**Result:** Checks every 30 seconds, notifies when English guided tour available

### Scenario 3: Last-Minute Tickets
```
Date: [Today or tomorrow]
Visitors: 1
Ticket Type: Standard Entry
Interval: 5 seconds
```
**Result:** Fast checking for cancellations/new releases

## Tips for Success

### ✅ DO:
- Keep browser open while monitoring
- Use 5-10 second intervals for urgent searches
- Check multiple dates by stopping/starting with new dates
- Enable desktop notifications
- Pin the extension icon for easy access

### ❌ DON'T:
- Close browser (monitoring stops)
- Use very short intervals (<5s) - may get rate-limited
- Monitor dates too far in future (Vatican hasn't released tickets yet)
- Expect auto-booking (you must book manually)

## Understanding Results

### Status Badge
- 🔴 **Red "Inactive"** - Not monitoring
- 🟢 **Green "Monitoring"** - Actively checking

### Result Types
- ✅ **Available** - Tickets found! Check "Available Slots"
- ❌ **Sold Out** - No tickets available
- ⚠️ **Error** - API issue, will retry

### Available Slots
```
🕐 09:00          [Book Now]
   01/06/2026
```
Click "Book Now" to open Vatican website

## Stopping Monitoring

Click **"Stop"** button when:
- You found tickets and booked
- You want to change dates
- You're done searching

## Advanced Features

### Settings (⚙️ button)
- Notification preferences
- Auto-stop after finding slots
- History retention
- Request timeout

### Clear History (🗑️ button)
- Removes all past results
- Clears available slots list
- Fresh start

## Troubleshooting

### Not checking?
- Verify status badge is green
- Check date is in future
- Ensure browser is open

### No notifications?
- Enable in browser settings
- Check extension permissions
- Verify "Desktop notifications" in settings

### API errors?
- Vatican website may be busy
- Try increasing interval
- Wait a few minutes and retry

## What's Next?

1. **Monitor Multiple Dates** - Stop and restart with different dates
2. **Adjust Settings** - Fine-tune notification preferences
3. **Share** - Help others find tickets too!

## Need More Help?

- 📖 Full documentation: [README.md](README.md)
- 🔧 Installation issues: [INSTALLATION.md](INSTALLATION.md)
- 🐛 Troubleshooting: Check browser console (F12)

---

**Happy Ticket Hunting! 🎫**

*Remember: This extension only monitors and notifies. You must book tickets manually on the Vatican website.*
