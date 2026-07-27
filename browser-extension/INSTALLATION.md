# Installation Guide - Vatican Ticket Monitor Extension

## Prerequisites

- Google Chrome, Microsoft Edge, or Firefox browser
- Basic understanding of browser extensions

## Step-by-Step Installation

### 1. Create Icons

Before installing, you need to create the extension icons:

1. Open `create-icons.html` in your browser
2. Right-click each canvas image
3. Select "Save image as..."
4. Save as:
   - `icon16.png` (16x16 canvas)
   - `icon48.png` (48x48 canvas)
   - `icon128.png` (128x128 canvas)
5. Create an `icons` folder in the `browser-extension` directory
6. Move all three PNG files into the `icons` folder

**Folder structure should be:**
```
browser-extension/
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
├── manifest.json
├── popup.html
├── popup.css
├── popup.js
├── background.js
├── options.html
└── options.js
```

### 2. Install in Chrome/Edge

1. **Open Extensions Page**
   - Chrome: Navigate to `chrome://extensions/`
   - Edge: Navigate to `edge://extensions/`
   - Or click the puzzle icon → "Manage Extensions"

2. **Enable Developer Mode**
   - Toggle the "Developer mode" switch in the top right corner

3. **Load the Extension**
   - Click "Load unpacked" button
   - Navigate to and select the `browser-extension` folder
   - Click "Select Folder"

4. **Verify Installation**
   - The extension should appear in your extensions list
   - You should see the Vatican Ticket Monitor icon in your toolbar
   - If not visible, click the puzzle icon and pin it

### 3. Install in Firefox

#### Temporary Installation (for testing)

1. **Open Debugging Page**
   - Navigate to `about:debugging#/runtime/this-firefox`

2. **Load Temporary Add-on**
   - Click "Load Temporary Add-on..."
   - Navigate to the `browser-extension` folder
   - Select `manifest.json`
   - Click "Open"

3. **Note:** Temporary add-ons are removed when Firefox restarts

#### Permanent Installation (requires signing)

For permanent installation in Firefox, you need to:
1. Create an account at https://addons.mozilla.org/developers/
2. Submit your extension for review
3. Once approved, it can be installed permanently

## First-Time Setup

### 1. Grant Permissions

When you first install the extension, you may need to grant permissions:
- ✅ **Storage** - To save your monitoring preferences
- ✅ **Alarms** - To schedule periodic checks
- ✅ **Notifications** - To alert you when tickets are available
- ✅ **Access to tickets.museivaticani.va** - To check ticket availability

### 2. Test the Extension

1. Click the extension icon in your toolbar
2. You should see the Vatican Ticket Monitor popup
3. Select today's date or a future date
4. Set visitors to 1
5. Choose "Standard Entry"
6. Set check interval to "30 seconds"
7. Click "Start Monitoring"

### 3. Verify It's Working

1. The status badge should turn green and say "Monitoring"
2. Check the "Recent Results" section after 30 seconds
3. You should see check results appearing
4. If tickets are available, you'll see them in "Available Slots"

## Troubleshooting Installation

### Extension won't load

**Error: "Manifest file is missing or unreadable"**
- Make sure you selected the `browser-extension` folder, not a parent folder
- Verify `manifest.json` exists in the folder

**Error: "Icons not found"**
- Create the icons using `create-icons.html`
- Make sure they're in the `icons/` subfolder
- Verify filenames match exactly: `icon16.png`, `icon48.png`, `icon128.png`

### Extension loads but doesn't work

**No monitoring happening:**
1. Check browser console for errors (F12 → Console tab)
2. Verify you clicked "Start Monitoring"
3. Make sure the date is in the future
4. Check that browser is not blocking the extension

**No notifications:**
1. Check browser notification settings
2. Make sure notifications are enabled for your browser
3. Verify extension has notification permission

### Icons not showing

If icons don't display:
1. You can use any 16x16, 48x48, and 128x128 PNG images
2. Name them correctly and place in `icons/` folder
3. Reload the extension after adding icons

## Updating the Extension

When you make changes to the code:

1. Go to `chrome://extensions/` (or `edge://extensions/`)
2. Find Vatican Ticket Monitor
3. Click the refresh/reload icon
4. Test your changes

## Uninstalling

### Chrome/Edge
1. Go to `chrome://extensions/` (or `edge://extensions/`)
2. Find Vatican Ticket Monitor
3. Click "Remove"
4. Confirm removal

### Firefox
1. Go to `about:addons`
2. Find Vatican Ticket Monitor
3. Click "..." → "Remove"
4. Confirm removal

## Next Steps

After installation:
1. Read the [README.md](README.md) for usage instructions
2. Configure advanced settings if needed
3. Start monitoring for your desired dates

## Support

If you encounter issues:
1. Check the browser console (F12) for error messages
2. Verify all files are in the correct locations
3. Make sure icons are created and in the `icons/` folder
4. Try reloading the extension

---

**Need Help?** Check the main README.md for troubleshooting tips and usage guide.
